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
            print(f"DEBUG: Sanity token loaded (starts with {settings.SANITY_TOKEN[:5]}...) for dataset '{ds}'")
        else:
            print("WARNING: No Sanity token found in environment!")


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
        """
        url = f"https://{self.project_id}.api.sanity.io/v{settings.SANITY_API_VERSION}/data/mutate/{self.dataset}"
        client = self._get_client()
        response = await client.post(
            url,
            json={"mutations": mutations},
            headers=self.headers
        )
        if response.status_code != 200:
            print(f"ERROR: Mutation failed: {response.text}")
            response.raise_for_status()
        return response.json()


    async def upload_asset(self, asset_type: str, file_bytes: bytes, filename: str, content_type: str = None):
        """
        Uploads an image or file asset to the Sanity API.
        asset_type: "images" or "files"
        """
        url = f"https://{self.project_id}.api.sanity.io/v{settings.SANITY_API_VERSION}/assets/{asset_type}/{self.dataset}"
        headers = {**self.headers}
        if content_type:
            headers["Content-Type"] = content_type
        
        params = {"filename": filename}
        
        client = self._get_client()
        response = await client.post(
            url,
            content=file_bytes,
            headers=headers,
            params=params
        )
        if response.status_code not in (200, 201):
            print(f"ERROR: Asset upload failed: {response.text}")
            response.raise_for_status()
        return response.json()


    async def save_chat_message(self, session_id: str, role: str, content: str):
        """
        Saves a chat message to Sanity. If session doesn't exist, it creates one.
        """
        from datetime import datetime
        import uuid
        now = datetime.utcnow().isoformat() + "Z"
        msg_id = str(uuid.uuid4())
        
        # Check if session exists
        query = f'*[_type == "chatSession" && sessionId == $sid][0]'
        existing = await self.query_sanity(query, {"$sid": session_id})
        
        message_obj = {
            "_key": msg_id, 
            "role": role, 
            "content": content, 
            "timestamp": now
        }

        
        if existing:
            # Update existing
            doc_id = existing["_id"]
            mutations = [{
                "patch": {
                    "id": doc_id,
                    "set": {"lastActivity": now},
                    "insert": {"after": "messages[-1]", "items": [message_obj]}
                }
            }]
        else:
            # Create new
            mutations = [{
                "create": {
                    "_type": "chatSession",
                    "sessionId": session_id,
                    "lastActivity": now,
                    "messages": [message_obj]
                }
            }]
            
        return await self.mutate_sanity(mutations)
            
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
            print(f"DEBUG: Session {session_id} reached limit ({msg_count}). Compressing...")
            old_messages = session.get("messages", [])
            old_summary = session.get("summary") or ""
            
            # Simple algorithmic summary (concatenation)
            # In a real-world scenario, you might send this to an LLM to "summarize"
            new_bits = [f"User: {m.get('user')} | AI: {m.get('ai')}" for m in old_messages[-10:]] # Keep last 10 for context
            new_summary = f"{old_summary}\n--- Archived Segment ---\n" + "\n".join(new_bits)
            
            patch_data["set"]["sessionSummary"] = new_summary
            patch_data["set"]["messages"] = [turn_obj] # Reset messages with the current one
            del patch_data["insert"] # No need to insert if we are resetting the whole array

        mutations.append({
            "patch": {
                "id": session_id,
                **patch_data
            }
        })
        
        return await self.mutate_sanity(mutations)


    async def cleanup_old_sessions(self):
        """
        Deletes sessions older than 30 days.
        """
        from datetime import datetime, timedelta
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
        
        query = f'*[_type == "chatSession" && lastActivity < $date]._id'
        old_ids = await self.query_sanity(query, {"$date": thirty_days_ago})
        
        if not old_ids:
            return 0
            
        mutations = [{"delete": {"id": oid}} for oid in old_ids]
        await self.mutate_sanity(mutations)
        return len(old_ids)


    async def search_content(self, query_text: str):
        """
        Searches across products, services, and team members for a given text.
        Includes a fallback 'OR' search if the specific query fails.
        """
        # Step 1: Try combined match (AND) with wildcard
        groq_query = """
        *[
          _type in ["faq", "product", "service", "team"] && (
            (question match $search || name match $search || title match $search) ||
            (answer match $search || description match $search || bio match $search || role match $search || subtitle match $search || badge match $search) ||
            (tags match $search)
          )
        ] {
          _type,
          "title": coalesce(question, name, title),
          "description": coalesce(answer, description, bio),
          "answer": answer,
          "role": role,
          "subtitle": subtitle,
          "badge": badge,
          "slug": slug.current,
          "link": coalesce(
            link, 
            select(_type == "product" => "/products/" + slug.current),
            select(_type == "service" => "/services"),
            select(_type == "team" => "/team"),
            "/faq"
          ),
          relatedLinks,
          price,
          availability,
          "score": select(
            _type == "team" && (role match $search || name match $search) => 100,
            _type == "product" && (name match $search || title match $search) => 80,
            _type == "service" && (title match $search || description match $search) => 60,
            (coalesce(question, name, title) match $search) => 20,
            10
          )
        } | order(score desc)
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
                # We use lower() and [0...10] for performance
                or_terms = " || ".join([f"(coalesce(question, name, title, role, subtitle, badge) match '{t}*')" for t in search_terms])
                groq_query_or = f"""
                *[_type in ["faq", "product", "service", "team"] && ({or_terms})] {{
                  _type,
                  "title": coalesce(question, name, title),
                  "description": coalesce(answer, description, bio),
                  "role": role,
                  "subtitle": subtitle,
                  "badge": badge,
                  "slug": slug.current,
                  "link": coalesce(
                    link, 
                    select(_type == "product" => "/products/" + slug.current),
                    select(_type == "service" => "/services"),
                    select(_type == "team" => "/team"),
                    "/faq"
                  ),
                  price,
                  availability
                }} | order(_type desc) [0...10]
                """
                results = await self.query_sanity(groq_query_or)
        
        return results


sanity_service = SanityService()
sanity_security_service = SanityService(
    project_id=settings.SANITY_SECURITY_PROJECT_ID,
    dataset=settings.SANITY_SECURITY_DATASET
)
