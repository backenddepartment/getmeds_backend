# pyrefly: ignore [missing-import]
import httpx
from app.core.config import get_settings

settings = get_settings()

class SanityService:
    def __init__(self, project_id: str = None, dataset: str = None):
        pid = project_id or settings.SANITY_PROJECT_ID
        ds = dataset or settings.SANITY_DATASET
        self.project_id = pid
        self.dataset = ds
        self.base_url = f"https://{pid}.api.sanity.io/v{settings.SANITY_API_VERSION}/data/query/{ds}"
        self.headers = {}
        if settings.SANITY_TOKEN:
            self.headers["Authorization"] = f"Bearer {settings.SANITY_TOKEN}"

    _client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0))
        return self._client

    async def query_sanity(self, groq_query: str, params: dict = None):
        """
        Executes a GROQ query against the Sanity API.
        """
        import json
        params_with_quotes = {k: json.dumps(v) for k, v in (params or {}).items()}
        client = self._get_client()
        response = await client.get(
            self.base_url,
            params={"query": groq_query, **params_with_quotes},
            headers=self.headers
        )

        if response.status_code != 200:
            print(f"ERROR: Sanity API returned {response.status_code}")
            print(f"Response body: {response.text}")
            response.raise_for_status()
        
        data = response.json()
        return data.get("result", [])

    async def mutate_sanity(self, mutations: list):
        """
        Executes mutations (create, update, delete) against the Sanity API.
        Automatically preprocesses mutations to strip nulls and convert patch set nulls into unsets.
        """
        def clean_null_values(val):
            if isinstance(val, dict):
                cleaned = {}
                for k, v in val.items():
                    if v is None:
                        continue
                    cleaned_v = clean_null_values(v)
                    if cleaned_v is not None:
                        cleaned[k] = cleaned_v
                if not cleaned:
                    return None
                if cleaned.get("_type") == "image" and "asset" not in cleaned:
                    return None
                if cleaned.get("_type") == "reference" and "_ref" not in cleaned:
                    return None
                return cleaned
            elif isinstance(val, list):
                cleaned_list = []
                for x in val:
                    if x is not None:
                        cleaned_x = clean_null_values(x)
                        if cleaned_x is not None:
                            cleaned_list.append(cleaned_x)
                return cleaned_list
            return val

        def preprocess_mutations(muts: list) -> list:
            cleaned = []
            for mut in muts:
                cleaned_mut = {}
                for op, body in mut.items():
                    if op in ("create", "createOrReplace", "createIfNotExists"):
                        cleaned_mut[op] = clean_null_values(body)
                    elif op == "patch":
                        patch_id = body.get("id")
                        set_data = body.get("set", {})
                        unset_fields = list(body.get("unset", []))
                        new_set = {}
                        
                        def extract_unsets(d, current_path=""):
                            for k, v in d.items():
                                field_path = f"{current_path}.{k}" if current_path else k
                                if v is None:
                                    if field_path not in unset_fields:
                                        unset_fields.append(field_path)
                                elif isinstance(v, dict):
                                    is_image_or_ref = v.get("_type") in ("image", "reference")
                                    has_null_child = any(val is None for val in v.values())
                                    if is_image_or_ref and has_null_child:
                                        if field_path not in unset_fields:
                                            unset_fields.append(field_path)
                                    else:
                                        cleaned_d = clean_null_values(v)
                                        if cleaned_d is None or not cleaned_d:
                                            if field_path not in unset_fields:
                                                unset_fields.append(field_path)
                                        else:
                                            new_set[k] = cleaned_d
                                else:
                                    new_set[k] = v
                        
                        extract_unsets(set_data)
                        cleaned_patch = {"id": patch_id}
                        if new_set:
                            cleaned_patch["set"] = new_set
                        if unset_fields:
                            cleaned_patch["unset"] = unset_fields
                        for other_op in body:
                            if other_op not in ("id", "set", "unset"):
                                cleaned_patch[other_op] = body[other_op]
                        cleaned_mut["patch"] = cleaned_patch
                    else:
                        cleaned_mut[op] = body
                cleaned.append(cleaned_mut)
            return cleaned

        processed_mutations = preprocess_mutations(mutations)
        url = f"https://{self.project_id}.api.sanity.io/v{settings.SANITY_API_VERSION}/data/mutate/{self.dataset}"
        client = self._get_client()
        response = await client.post(
            url,
            json={"mutations": processed_mutations},
            headers=self.headers
        )
        if response.status_code != 200:
            print(f"ERROR: Mutation failed: {response.text}")
            response.raise_for_status()
        return response.json()

    async def save_chat_turn(self, session_id: str, user_text: str, ai_text: str, last_subject: str = None):
        """
        Saves a User+AI interaction pair as a single 'turn' object in Sanity.
        Also checks if we need to compress history to stay under the limit.
        """
        import uuid
        from datetime import datetime
        from app.core.config import get_settings
        settings = get_settings()
        
        turn_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        turn_obj = {
            "_key": turn_id,
            "user": user_text,
            "ai": ai_text,
            "timestamp": timestamp
        }
        
        # 1. Fetch current message count
        query = f'*[_id == "{session_id}"][0]{{ "count": count(messages), "summary": sessionSummary, "messages": messages }}'
        session = await self.query_sanity(query)
        msg_count = session.get("count", 0) if session else 0
        
        # 2. Prepare mutations
        mutations = [
            {
                "createIfNotExists": {
                    "_id": session_id,
                    "_type": "chatSession",
                    "sessionId": session_id,
                    "lastActivity": timestamp,
                    "messages": []
                }
            }
        ]

        patch_data = {
            "setIfMissing": {"messages": []},
            "insert": {
                "after": "messages[-1]",
                "items": [turn_obj]
            },
            "set": {"lastActivity": timestamp}
        }
        if last_subject:
            patch_data["set"]["lastSubject"] = last_subject

        # 3. Handle Compression if limit reached
        if msg_count >= settings.CHAT_HISTORY_LIMIT:
            old_messages = session.get("messages", [])
            old_summary = session.get("summary") or ""
            
            # Simple algorithmic summary (concatenation)
            new_bits = [f"User: {m.get('user')} | AI: {m.get('ai')}" for m in old_messages[-10:]]
            new_summary = f"{old_summary}\n--- Archived Segment ---\n" + "\n".join(new_bits)
            
            patch_data["set"]["sessionSummary"] = new_summary
            patch_data["set"]["messages"] = [turn_obj]
            del patch_data["insert"]

        mutations.append({
            "patch": {
                "id": session_id,
                **patch_data
            }
        })
        
        return await self.mutate_sanity(mutations)

    async def search_content(self, query_text: str):
        """
        Searches across products, FAQs, and team members for a given text.
        Optimized by targeting existing schema types/fields and slicing results.
        """
        # Step 1: Try combined match (AND) with wildcard
        groq_query = """
        *[
          (_type == "product" && (
            name match $search || 
            brandName match $search || 
            genericName match $search || 
            subCategory match $search || 
            description match $search ||
            indications match $search
          )) ||
          (_type == "faq" && (
            question match $search || 
            answer match $search || 
            keywords match $search
          )) ||
          (_type == "teams" && (
            name match $search || 
            designation match $search
          ))
        ] {
          "_type": select(_type == "teams" => "team", _type),
          "title": coalesce(
            select(_type == "product" => brandName + " (" + genericName + ")"),
            brandName,
            genericName,
            name,
            question
          ),
          "description": coalesce(description, answer),
          "answer": answer,
          "role": designation,
          "slug": slug.current,
          "link": coalesce(
            select(_type == "product" => "/products/" + slug.current),
            select(_type == "teams" => "/team"),
            "/faq"
          ),
          availability,
          brandName,
          genericName,
          form,
          strength,
          packaging,
          storageCondition,
          dosageAdministration,
          directionForReconstitution,
          mechanismOfAction,
          indications,
          accreditations,
          distributor,
          importer,
          supplier,
          "score": select(
            _type == "teams" && name match $search => 100,
            _type == "product" && (brandName match $search || name match $search) => 80,
            _type == "faq" && question match $search => 60,
            10
          )
        } | order(score desc) [0...10]
        """
        
        params = {"$search": f"{query_text}*"}
        results = await self.query_sanity(groq_query, params)
        
        # Step 2: If no results, try matching words individually (Fuzzy OR)
        if not results:
            # Clean up the search: remove punctuation and split into words
            import re
            search_terms = re.findall(r'\w+', query_text)
            
            if len(search_terms) > 1:
                # Try matching if ANY of the words exist
                or_terms = " || ".join([f"(coalesce(question, name, brandName, genericName, designation, answer, description) match '{t}*')" for t in search_terms])
                groq_query_or = f"""
                *[_type in ["faq", "product", "teams"] && ({or_terms})] {{
                  "_type": select(_type == "teams" => "team", _type),
                  "title": coalesce(name, question),
                  "description": coalesce(description, answer),
                  "role": designation,
                  "slug": slug.current,
                  "link": coalesce(
                    select(_type == "product" => "/products/" + slug.current),
                    select(_type == "teams" => "/team"),
                    "/faq"
                  ),
                  availability
                }} | order(_type desc) [0...10]
                """
                results = await self.query_sanity(groq_query_or)
        
        return results

sanity_service = SanityService()
