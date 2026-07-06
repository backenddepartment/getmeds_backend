# pyrefly: ignore [missing-import]
from app.services.sanity_service import sanity_service
from app.schemas.chatbot import ResourceLink, ChatResponse
from app.core.config import get_settings
import re
import json

settings = get_settings()

# Sentinel value — returned by trained engine when it cannot handle the query
_FALLBACK_SENTINEL = "__FALLBACK__"

# Unified keyword filter list to ensure search query extraction is clean
_STOP_WORDS = {
    # English common pronouns, auxiliary verbs, and function words
    "do",
    "does",
    "did",
    "doing",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
    "have",
    "has",
    "had",
    "having",
    "what",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "am",
    "tell",
    "me",
    "about",
    "search",
    "find",
    "the",
    "a",
    "an",
    "for",
    "how",
    "much",
    "can",
    "please",
    "i",
    "we",
    "us",
    "our",
    "ours",
    "want",
    "to",
    "order",
    "with",
    "any",
    "some",
    "of",
    "could",
    "would",
    "should",
    "get",
    "give",
    "show",
    "from",
    "it",
    "this",
    "that",
    "who",
    "they",
    "them",
    "their",
    "theirs",
    "getmeds",
    "company",
    "cost",
    "total",
    "price",
    "worth",
    "buy",
    "need",
    "products",
    "medicine",
    "meds",
    "suggest",
    "recommend",
    "another",
    "other",
    "else",
    "like",
    "remember",
    "inquiry",
    "philippines",
    "phil",
    "ph",
    "here",
    "there",
    "he",
    "she",
    "him",
    "her",
    "his",
    "hers",

    # Tagalog/Taglish particles and common words
    "ang",
    "ng",
    "mga",
    "sa",
    "na",
    "para",
    "po",
    "at",
    "o",
    "si",
    "ni",
    "kay",
    "ako",
    "ikaw",
    "siya",
    "kami",
    "tayo",
    "kayo",
    "sila",
    "ito",
    "iyan",
    "iyon",
    "dito",
    "diyan",
    "doon",
    "ano",
    "sino",
    "saan",
    "kailan",
    "bakit",
    "paano",
    "magkano",
    "may",
    "mayroon",
    "wala",
    "hindi",
    "huwag",
    "opo",
    "oho",
    "meron",
    "pabili",
    "salamat",
    "tuloy",
    "ba",
    "kayong",
    "inyo",
    "ninyo",
    "gamot",
    "sana",
    "lang",
    "din",
    "rin",
    "naman",
    "nga",
    "mismo",
    "gusto",
    "kailangan",
    "namin",
    "ko",
    "mo",
    "aking",
    "iyong",
    "stock",
    "available",
    "availability"
}


def product_belongs_to_subcategory(product, subcategory_name):
    prod_sub = product.get("subCategory") or ""
    subparts = [s.strip().lower() for s in prod_sub.split("/")]
    return subcategory_name.lower() in subparts or subcategory_name.lower(
    ) in prod_sub.lower()


# ── Cancer/oncology routing (frontend split: /cancer-medicines vs /product-range) ──
# A category counts as cancer-related if its Sanity `category` name is Oncology or
# Neuro-Oncology, or if a subcategory/category slug is one of the known cancer slugs
# below, or if the specific product's brandName is zoloGet (zoledronic acid — filed
# under "Orthopedic" in Sanity but clinically used for cancer bone-metastasis).
_CANCER_CATEGORY_NAMES = {"oncology", "neuro-oncology"}
_CANCER_CATEGORY_SLUGS = {
    "oncology", "breast-cancer", "ovarian-cancer",
    "non-small-cell-lung-cancer", "lung-cancer", "prostate-cancer",
    "gastric-cancer-gastric-adenocarcinoma", "pancreatic-cancer",
    "colorectal-cancer", "hodgkin-non-hodgkins-lymphoma",
    "hodgkin-non-hodgkin-s-lymphoma", "lymphoma",
    "acute-lymphoblastic-leukemia", "malignant-pleural-mesothelioma",
    "head-and-neck-cancer", "chronic-myeloid-leukemia", "cml",
    "sickle-cell-anemia", "sickle-cell", "malignant-pleural-effusion",
    "gastrointestinal-stromal-tumors", "acute-myeloid-leukemia", "aml",
    "acute-lymphocytic-leukemia", "chronic-myelocytic-leukemia",
    "meningeal-leukemia", "acute-promyelocytic-leukemia",
    "chronic-lymphocytic-leukemia", "mantle-cell-lymphoma",
    "multiple-myeloma", "neuro-oncology", "glioblastoma-multiforme"
}
_CANCER_BRAND_NAMES = {"zoloGet".lower()}


def _category_url_prefix(category_name=None, slug=None, brand_name=None):
    """
    Returns "cancer-medicines" or "product-range" — the frontend now splits the
    single /product-range listing page into two URL prefixes depending on whether
    the category/product is cancer-related. Both prefixes render the identical
    listing page; this only picks which string to build the link with.
    Pass whatever of category_name / slug / brand_name is available in scope.
    """
    if category_name and category_name.strip().lower() in _CANCER_CATEGORY_NAMES:
        return "cancer-medicines"
    if slug and slug.strip().lower() in _CANCER_CATEGORY_SLUGS:
        return "cancer-medicines"
    if brand_name and brand_name.strip().lower() in _CANCER_BRAND_NAMES:
        return "cancer-medicines"
    return "product-range"


# ── AI Responder: Anthropic Claude ──────────────────────────────────
async def _call_anthropic(system_prompt: str,
                          user_message: str,
                          session_context: dict,
                          search_results: list,
                          lang: str = "en",
                          page_context: str = None) -> ChatResponse | None:
    """
    Calls Anthropic Claude as the primary responder.
    Returns ChatResponse, or None if the call fails.
    """
    if not settings.ANTHROPIC_API_KEY:
        print("INFO: ANTHROPIC_API_KEY not set — skipping Claude primary")
        return None

    if not system_prompt:
        print(
            "WARNING: No system prompt loaded — Claude primary will run without skill context"
        )

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Define target language style instruction
        lang_instruction = ""
        if lang == "tl":
            lang_instruction = """
Target Response Language: Tagalog (Filipino)
- Please reply in clear, polite, and helpful Tagalog.
- Use polite particles such as 'po' and 'opo' where appropriate to keep a professional and respectful customer service tone.
- Keep branding names (like Getmeds, PacliGet, Irose) in their original English forms.
"""
        elif lang == "tg":
            lang_instruction = """
Target Response Language: Taglish (Tagalog-English code-switching)
- Please reply in natural, polite, and helpful Taglish (a mix of Tagalog and English).
- Use Tagalog grammatical sentence structures and connectors, but feel free to use English words/phrases for key technical terms, action names (e.g. order, prescription, stock, upload, inquiry), or page paths.
- Use polite particles such as 'po' and 'opo' to maintain a professional, friendly, and respectful customer service tone.
- Make it sound natural and conversational, just like a customer service agent chatting with a Filipino user.
"""
        else:
            lang_instruction = """
Target Response Language: English
- Reply in standard professional English.
"""

        # Build the live context block — this tells Claude everything it needs
        page_context_block = f"\nRaw text from the page the user is currently viewing:\n{page_context}\n" if page_context else ""

        context_block = f"""
--- LIVE CONTEXT ---
Session ID: {session_context.get('sessionId', 'unknown')}
User Name: {session_context.get('userName') or 'Unknown'}
Last Subject: {session_context.get('lastSubject') or 'None'}
Session Summary: {session_context.get('sessionSummary') or 'No previous history'}

Search Results from Getmeds Catalog (top 5):
{json.dumps(search_results[:5], indent=2, default=str) if search_results else '[]'}

{page_context_block}

Note: You are Getmeds AI Assist, the primary responder. Stay within Getmeds context only.
Use only the data provided above — do not invent product information.

{lang_instruction}
Current User Message: {user_message}
---

Respond ONLY with a valid JSON object. No preamble, no markdown code fences.
Required format:
{{
  "answer": "your reply in markdown",
  "resources": [
    {{"title": "...", "url": "...", "type": "product|category|page|article"}}
  ]
}}
Maximum 3 resource links. Only use URLs that exist in Getmeds (/product-range, /order-medicines, /contact-us, /pap, /about-us, /services, /global-presence, /careers, /articles, /csr, /ungc, /meditations).
"""
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            temperature=0.0,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": context_block
            }])

        raw = response.content[0].text.strip()

        # Strip markdown code fences if Claude wrapped JSON anyway
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        raw = raw.strip()

        parsed = json.loads(raw)

        resources = [
            ResourceLink(title=r.get("title", ""),
                         url=r.get("url", "#"),
                         type=r.get("type", "page"))
            for r in parsed.get("resources", [])
            if r.get("title") and r.get("url")
        ]

        answer = parsed.get("answer", "").strip()
        if not answer:
            print(
                "WARNING: Claude returned empty answer — treating as primary failure"
            )
            return None

        print(
            f"INFO: Claude primary succeeded for message: {user_message[:60]}..."
        )
        return ChatResponse(answer=answer, resources=resources, confidence=1.0)

    except json.JSONDecodeError as e:
        print(f"WARNING: Claude returned invalid JSON: {e} — raw: {raw[:200]}")
        return None
    except Exception as e:
        status_code_str = ""
        if hasattr(e, "status_code"):
            status_code_str = f" (Status Code: {getattr(e, 'status_code')})"
        print(
            f"WARNING: Anthropic API call failed{status_code_str}: {type(e).__name__}: {e}"
        )
        return None


async def _call_groq(system_prompt: str,
                     user_message: str,
                     session_context: dict,
                     search_results: list,
                     lang: str = "en",
                     page_context: str = None) -> ChatResponse | None:
    """
    Calls Groq Cloud API as a responder.
    Rotates through multiple GROQ_API_KEY values if one fails.
    Tries llama-3.1-8b-instant first, and falls back to other models if needed.
    """
    import httpx
    if not settings.GROQ_API_KEY:
        print("INFO: GROQ_API_KEY not set — skipping Groq responder")
        return None

    # Parse key list
    keys = [k.strip() for k in settings.GROQ_API_KEY.split(",") if k.strip()]
    if not keys:
        print(
            "INFO: GROQ_API_KEY format is invalid or empty — skipping Groq responder"
        )
        return None

    # Define target language style instruction
    lang_instruction = ""
    if lang == "tl":
        lang_instruction = """
Target Response Language: Tagalog (Filipino)
- Please reply in clear, polite, and helpful Tagalog.
- Use polite particles such as 'po' and 'opo' where appropriate to keep a professional and respectful customer service tone.
- Keep branding names (like Getmeds, PacliGet, Irose) in their original English forms.
"""
    elif lang == "tg":
        lang_instruction = """
Target Response Language: Taglish (Tagalog-English code-switching)
- Please reply in natural, polite, and helpful Taglish (a mix of Tagalog and English).
- Use Tagalog grammatical sentence structures and connectors, but feel free to use English words/phrases for key technical terms, action names (e.g. order, prescription, stock, upload, inquiry), or page paths.
- Use polite particles such as 'po' and 'opo' to maintain a professional, friendly, and respectful customer service tone.
- Make it sound natural and conversational, just like a customer service agent chatting with a Filipino user.
"""
    else:
        lang_instruction = """
Target Response Language: English
- Reply in standard professional English.
"""

    page_context_block = f"\nRaw text from the page the user is currently viewing:\n{page_context}\n" if page_context else ""

    context_block = f"""
--- LIVE CONTEXT ---
Session ID: {session_context.get('sessionId', 'unknown')}
User Name: {session_context.get('userName') or 'Unknown'}
Last Subject: {session_context.get('lastSubject') or 'None'}
Session Summary: {session_context.get('sessionSummary') or 'No previous history'}

Search Results from Getmeds Catalog (top 5):
{json.dumps(search_results[:5], indent=2, default=str) if search_results else '[]'}

{page_context_block}

Note: You are Getmeds AI Assist. Stay within Getmeds context only.
Use only the data provided above — do not invent product information.

{lang_instruction}
Current User Message: {user_message}
---

Respond ONLY with a valid JSON object. No preamble, no markdown code fences.
Required format:
{{
  "answer": "your reply in markdown",
  "resources": [
    {{"title": "...", "url": "...", "type": "product|category|page|article"}}
  ]
}}
Maximum 3 resource links. Only use URLs that exist in Getmeds (/product-range, /order-medicines, /contact-us, /pap, /about-us, /services, /global-presence, /careers, /articles, /csr, /ungc, /meditations).
"""
    # Models ordered by capability — larger context models first to handle full system prompt.
    # llama3-8b-8192 has been decommissioned by Groq and is removed.
    models = [
        "llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"
    ]

    # Condensed system prompt for small models that can't handle the full prompt (TPM < 8K)
    condensed_system_prompt = """You are Getmeds AI Assist, a helpful customer service assistant for Getmeds, a specialty pharmaceutical importer and distributor in the Philippines.
Rules:
- Only answer about Getmeds products, services, ordering, and company information.
- Never invent product data. Use only what is provided in the search results.
- Never give specific prices — redirect to inquiry form.
- Always include a medical disclaimer if clinical questions arise.
- Be warm, empathetic, professional, and concise.
- Respond in the user's language (English, Tagalog, or Taglish).
- Maximum 3 resource links per response. Valid pages: /product-range, /order-medicines, /contact-us, /pap, /about-us, /services, /global-presence, /careers, /articles, /csr, /ungc, /meditations."""

    url = "https://api.groq.com/openai/v1/chat/completions"

    for api_key in keys:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        for model in models:
            try:
                # Use condensed prompt for smaller models to stay under TPM limits
                effective_prompt = system_prompt if "70b" in model or "mixtral" in model else condensed_system_prompt

                payload = {
                    "model":
                    model,
                    "messages": [{
                        "role": "system",
                        "content": effective_prompt
                    }, {
                        "role": "user",
                        "content": context_block
                    }],
                    "temperature":
                    0.0,
                    "max_tokens":
                    1024,
                    "response_format": {
                        "type": "json_object"
                    }
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(url,
                                                 headers=headers,
                                                 json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        raw = data["choices"][0]["message"]["content"].strip()
                        if raw.startswith("```"):
                            raw = re.sub(r"^```[a-z]*\n?", "", raw)
                            raw = re.sub(r"\n?```$", "", raw)
                        raw = raw.strip()

                        parsed = json.loads(raw)

                        resources = [
                            ResourceLink(title=r.get("title", ""),
                                         url=r.get("url", "#"),
                                         type=r.get("type", "page"))
                            for r in parsed.get("resources", [])
                            if r.get("title") and r.get("url")
                        ]
                        answer = parsed.get("answer", "").strip()
                        if answer:
                            print(
                                f"INFO: Groq responder succeeded with model '{model}' for message: {user_message[:60]}..."
                            )
                            return ChatResponse(answer=answer,
                                                resources=resources,
                                                confidence=1.0)
                    elif response.status_code == 413:
                        # Request too large for this model — skip to next (larger) model, same key
                        print(
                            f"WARNING: Groq model {model} can't handle prompt size (413). Reason: {response.text}. Trying next model..."
                        )
                        continue
                    elif response.status_code == 400:
                        # Model decommissioned or invalid — skip to next model
                        print(
                            f"WARNING: Groq model {model} returned 400 (possibly decommissioned). Reason: {response.text}. Trying next model..."
                        )
                        continue
                    elif response.status_code in [401, 403, 429]:
                        print(
                            f"WARNING: Groq key {api_key[:12]}... failed with status {response.status_code}. Reason: {response.text}. Trying next key..."
                        )
                        break  # Break models loop to try next key
                    else:
                        print(
                            f"WARNING: Groq call failed with status {response.status_code} for model {model}. Reason: {response.text}"
                        )
            except Exception as e:
                print(
                    f"WARNING: Groq call with model {model} failed using key {api_key[:12]}...: {type(e).__name__}: {e}"
                )

    return None


# ── Main Chatbot Service ────────────────────────────────────────────────────


class ChatbotService:
    _categories_cache = None

    def _detect_language(self, text: str) -> str:
        # Common Tagalog words/particles
        tagalog_words = {
            "ang", "ng", "mga", "sa", "na", "para", "po", "at", "o", "si",
            "ni", "kay", "ako", "ikaw", "siya", "kami", "tayo", "kayo", "sila",
            "ito", "iyan", "iyon", "dito", "diyan", "doon", "ano", "sino",
            "saan", "kailan", "bakit", "paano", "magkano", "may", "mayroon",
            "wala", "hindi", "huwag", "opo", "oho", "meron", "pabili",
            "salamat", "tuloy", "ba", "kayong", "inyo", "ninyo", "gamot",
            "pampainit"
        }
        words = set(re.findall(r'[a-z]+', text.lower()))
        tagalog_count = sum(1 for w in words if w in tagalog_words)

        if tagalog_count == 0:
            return "en"

        # Check for English keywords commonly used in Taglish
        taglish_indicators = {
            "order", "prescription", "upload", "stock", "price", "available",
            "availability", "proceed", "inquire", "inquiry", "status",
            "cancel", "submit", "deliver", "delivery", "payment", "ship",
            "shipping", "about", "contact", "support"
        }
        has_taglish_indicator = any(w in taglish_indicators for w in words)

        has_english_question = any(
            w in words for w in
            ["how", "what", "where", "who", "why", "when", "can", "do", "you"])

        if has_taglish_indicator or (has_english_question and "po" in words):
            return "tg"

        return "tl"

    async def _get_categories(self):
        if self._categories_cache is None:
            query = '*[_type == "category"] { _id, category, "slug": slug.current, subcategory }'
            self._categories_cache = await sanity_service.query_sanity(query)
        return self._categories_cache

    async def get_response(self,
                           user_message: str,
                           session_id: str = "default",
                           page_context: str = None) -> ChatResponse:
        """
        5-step orchestrator:
          1. Pre-process (session load, name detection, keyword extraction)
          2. Sanity database search
          3. Generate Plan & Tasks (Stage 1) - stored in Sanity
          4. Generate Walkthrough (Stage 2) - using primary/fallback responders
          5. Combine Plan, Tasks, and Walkthrough + Cleanup temporary state in Sanity
        """
        lang = self._detect_language(user_message)

        # ── Step 1: Pre-processing ───────────────────────────────────────────
        session_query = '*[_type == "chatSession" && sessionId == $sid][0]'
        session_data = await sanity_service.query_sanity(
            session_query, {"$sid": session_id})

        current_user_name = session_data.get(
            "userName") if session_data else None
        last_subject = session_data.get(
            "lastSubject") if session_data else None
        session_summary = session_data.get("sessionSummary",
                                           "") if session_data else ""

        # Fetch temporary plan and tasks if already present (e.g. from prior cutoff)
        temp_plan = session_data.get("tempPlan") if session_data else None
        temp_tasks = session_data.get("tempTasks") if session_data else None

        last_ai_msg = ""
        if session_data and session_data.get("messages"):
            last_ai_msg = session_data["messages"][-1].get("ai", "").lower()
        elif session_summary:
            summary_parts = session_summary.split("| AI:")
            if summary_parts:
                last_ai_msg = summary_parts[-1].strip().lower()

        query = user_message.lower().strip()
        query_clean = re.sub(r'[^a-zA-Z0-9\s]', '', query)
        query_clean = re.sub(r'(\d+)([a-zA-Z]+)', r'\1 \2', query_clean)

        # Name detection — always run, persists to Sanity immediately
        new_user_name = None
        name_match = re.search(
            r"(?:my name is|im|i am|call me|name is) ([\w\s]+)", query)
        if name_match:
            new_user_name = name_match.group(1).strip().title()
            from datetime import datetime
            timestamp = datetime.utcnow().isoformat() + "Z"
            await sanity_service.mutate_sanity([{
                "createIfNotExists": {
                    "_id": session_id,
                    "_type": "chatSession",
                    "sessionId": session_id,
                    "lastActivity": timestamp,
                    "messages": []
                }
            }, {
                "patch": {
                    "id": session_id,
                    "set": {
                        "userName": new_user_name
                    }
                }
            }])

        effective_name = new_user_name or current_user_name

        # Keyword extraction
        keywords = [w for w in query_clean.split() if w not in _STOP_WORDS]

        # Pronoun context lock
        query_words = set(query_clean.split())
        has_pronoun = any(w in query_words for w in ["it", "this", "that"])
        context_words = {
            "it", "this", "that", "how", "much", "is", "cost", "price",
            "total", "yes", "no", "ok", "another", "other", "remember",
            "inquiry", "name"
        }
        is_generic_followup = query_words.issubset(context_words) or (
            len(query_words) <= 5 and has_pronoun)

        is_confirmation = any(w in query for w in [
            "yes", "yup", "sure", "ok", "proceed", "deal", "like the",
            "want the", "order it", "buy it", "get it", "want to order"
        ])
        is_asking_alternative = any(
            w in query
            for w in ["anoth", "other", "else", "differen", "variation"])

        effective_subject = last_subject
        if not effective_subject and session_summary:
            brand_match = re.search(r"AI: I found \*\*([\w\s]+)\*\*",
                                    session_summary)
            if brand_match:
                effective_subject = brand_match.group(1)

        if (is_generic_followup or is_asking_alternative
                or is_confirmation) and effective_subject:
            brand = effective_subject.split()[0]
            clean_search = f"{brand} {' '.join(keywords)}".strip()
        else:
            clean_search = " ".join(keywords) if keywords else query_clean

        # ── Step 2: Sanity Database Search ──────────────────────────────────
        search_results = []
        matched_category = None
        matched_subcategory = None

        # Check for category/subcategory in query first
        query_lower = query.lower().strip()
        try:
            categories = await self._get_categories()
            for cat in categories:
                cat_name = cat.get("category", "")
                cat_slug = cat.get("slug", "")
                subcats = cat.get("subcategory", []) or []

                # Check if query mentions category name or slug
                if cat_name.lower() in query_lower or (
                        cat_slug and cat_slug.lower() in query_lower):
                    matched_category = cat
                    # Keep scanning to see if a specific subcategory is mentioned too
                    for sub in subcats:
                        if sub.lower() in query_lower:
                            matched_subcategory = sub
                            break
                    break

                # Check if query mentions any subcategory directly
                for sub in subcats:
                    if sub.lower() in query_lower:
                        matched_subcategory = sub
                        matched_category = cat
                        break

                if matched_subcategory:
                    break
        except Exception as ex:
            print(f"WARNING: Failed to check categories cache: {ex}")

        if matched_category:
            try:
                cat_id = matched_category["_id"]
                # Fetch products
                if matched_subcategory:
                    # Fetch all products matching the subcategory
                    products_query = '*[_type == "product" && subCategory match $subcat] { _id, brandName, genericName, subCategory, strength, form, availability, description, indications, slug, category }'
                    products = await sanity_service.query_sanity(
                        products_query,
                        {"$subcat": f"*{matched_subcategory}*"})

                    # Resolve correct matched_category based on the products returned
                    if products:
                        first_prod_cat_ref = products[0].get("category",
                                                             {}).get("_ref")
                        if first_prod_cat_ref:
                            resolved_cat = next(
                                (c for c in categories
                                 if c.get("_id") == first_prod_cat_ref), None)
                            if resolved_cat:
                                matched_category = resolved_cat
                                cat_id = resolved_cat["_id"]
                else:
                    # Fetch all products in this category
                    products_query = '*[_type == "product" && category._ref == $cat_id] { _id, brandName, genericName, subCategory, strength, form, availability, description, indications, slug, category }'
                    products = await sanity_service.query_sanity(
                        products_query, {"$cat_id": cat_id})

                # Format category
                formatted_category = {
                    "_type":
                    "category",
                    "title":
                    matched_category.get("category"),
                    "description":
                    matched_category.get("description"),
                    "slug":
                    matched_category.get("slug"),
                    "subcategory":
                    matched_category.get("subcategory"),
                    "link":
                    f"/{_category_url_prefix(matched_category.get('category'), matched_category.get('slug'))}?category={matched_category.get('slug')}"
                    if matched_category.get("slug") else "/product-range"
                }

                # Format subcategory if matched
                formatted_subcategory = None
                if matched_subcategory:
                    sub_slug = re.sub(
                        r'[^a-z0-9-]', '',
                        re.sub(r'\s+', '-', matched_subcategory.lower()))
                    formatted_subcategory = {
                        "_type": "category",
                        "title": matched_subcategory,
                        "description":
                        f"Browse the {matched_subcategory} subcategory under {matched_category.get('category')}.",
                        "slug": sub_slug,
                        "link": f"/{_category_url_prefix(matched_category.get('category'), sub_slug)}?category={sub_slug}"
                    }

                # Format products
                formatted_products = []
                for p in products:
                    brand = p.get("brandName") or p.get(
                        "title") or "the medicine"
                    generic = p.get("genericName") or ""
                    prod_title = f"{brand} ({generic})" if generic else brand

                    if matched_subcategory and not product_belongs_to_subcategory(
                            p, matched_subcategory):
                        continue

                    formatted_products.append({
                        "_type":
                        "product",
                        "title":
                        prod_title,
                        "brandName":
                        p.get("brandName"),
                        "genericName":
                        p.get("genericName"),
                        "subCategory":
                        p.get("subCategory"),
                        "strength":
                        p.get("strength"),
                        "form":
                        p.get("form"),
                        "availability":
                        p.get("availability"),
                        "description":
                        p.get("description"),
                        "indications":
                        p.get("indications"),
                        "link":
                        f"/products/{p.get('slug', {}).get('current', '')}"
                        if p.get("slug") else
                        f"/products/{brand.lower().replace(' ', '-')}"
                    })

                if formatted_subcategory:
                    search_results = [
                        formatted_subcategory, formatted_category
                    ] + formatted_products
                else:
                    search_results = [formatted_category] + formatted_products
            except Exception as ex:
                print(
                    f"WARNING: Failed to query products for matched category: {ex}"
                )
                if clean_search.strip():
                    search_results = await sanity_service.search_content(
                        clean_search)
        elif clean_search.strip():
            search_results = await sanity_service.search_content(clean_search)

        # ── Data policy: Sanity-only mode ───────────────────────────────────
        # "Sanity-only" means: use only Sanity search results as the truth source.
        # LLM responders can still be used, but page_context is not passed through,
        # and responders are instructed to refuse answering when Sanity has no match.
        sanity_only = bool(getattr(settings, "CHATBOT_SANITY_ONLY", False))
        if sanity_only:
            page_context = None

            # Hard stop: if Sanity has no matches, do NOT call any LLM responder.
            # This prevents false positives like "I found X" when X isn't in the catalog.
            if not search_results:
                resp = await self._rule_based_response(
                    query=query,
                    query_clean=query_clean,
                    user_message=user_message,
                    effective_name=effective_name,
                    effective_subject=effective_subject,
                    last_ai_msg=last_ai_msg,
                    is_confirmation=is_confirmation,
                    search_results=search_results,
                    matched_category=matched_category,
                    matched_subcategory=matched_subcategory,
                    lang=lang)

                detected_subject = None
                for r in resp.resources:
                    if r.type == "product" and "Inquire" in r.title:
                        detected_subject = r.title.replace("Inquire ", "")
                        break
                final_subject = detected_subject or effective_subject
                await sanity_service.save_chat_turn(session_id,
                                                    user_message,
                                                    resp.answer,
                                                    resources=resp.resources,
                                                    last_subject=final_subject)
                return resp

        primary_responder = settings.PRIMARY.lower().strip(
        ) if settings.PRIMARY else "anthropic_ai"
        secondary_responder = settings.SECONDARY.lower().strip(
        ) if settings.SECONDARY else "trained_assistant"
        tertiary_responder = settings.TERTIARY.lower().strip(
        ) if settings.TERTIARY else "groq_ai"

        responders_tried = []

        def _apply_sanity_only_guard(system_prompt: str) -> str:
            if not sanity_only:
                return system_prompt or ""
            guard = """
SANITY-ONLY MODE (STRICT):
- You must ONLY use the provided "Search Results from Getmeds Catalog" to answer.
- Do NOT use general knowledge, web knowledge, or assumptions.
- Do NOT use page context (none will be provided).
- Do NOT mention "Sanity" or any internal database/vendor name to the user. Refer to it only as "Getmeds catalog" or "our catalog".
- If the Search Results list is empty, you MUST reply that the item/info is not found in the Getmeds catalog and suggest:
  1) Search Products: /product-range?search=<query>
  2) Contact Us: /contact-us
- Never mention competitors or non-Getmeds products. If the user asks outside Getmeds, redirect to /contact-us.
"""
            base = (system_prompt or "").strip()
            return (base + "\n\n" + guard.strip()).strip()

        async def try_responder(name):
            if name == "anthropic_ai":
                if not settings.ANTHROPIC_API_KEY:
                    print(
                        "INFO: ANTHROPIC_API_KEY not set — skipping Claude responder"
                    )
                    return None
                try:
                    import main as app_main
                    system_prompt = getattr(app_main, "COMBINED_SYSTEM_PROMPT",
                                            "")
                except Exception:
                    system_prompt = ""
                system_prompt = _apply_sanity_only_guard(system_prompt)
                session_context = {
                    "sessionId": session_id,
                    "userName": effective_name,
                    "lastSubject": effective_subject,
                    "sessionSummary": session_summary
                }
                print(f"INFO: Trying Claude responder: {user_message[:60]}...")
                return await _call_anthropic(system_prompt=system_prompt,
                                             user_message=user_message,
                                             session_context=session_context,
                                             search_results=search_results,
                                             lang=lang,
                                             page_context=page_context)
            elif name == "groq_ai":
                try:
                    import main as app_main
                    system_prompt = getattr(app_main, "COMBINED_SYSTEM_PROMPT",
                                            "")
                except Exception:
                    system_prompt = ""
                system_prompt = _apply_sanity_only_guard(system_prompt)
                session_context = {
                    "sessionId": session_id,
                    "userName": effective_name,
                    "lastSubject": effective_subject,
                    "sessionSummary": session_summary
                }
                print(
                    f"INFO: Trying Groq AI responder: {user_message[:60]}...")
                return await _call_groq(system_prompt=system_prompt,
                                        user_message=user_message,
                                        session_context=session_context,
                                        search_results=search_results,
                                        lang=lang,
                                        page_context=page_context)
            elif name == "trained_assistant":
                print(
                    f"INFO: Trying trained assistant responder: {user_message[:60]}..."
                )
                return await self._rule_based_response(
                    query=query,
                    query_clean=query_clean,
                    user_message=user_message,
                    effective_name=effective_name,
                    effective_subject=effective_subject,
                    last_ai_msg=last_ai_msg,
                    is_confirmation=is_confirmation,
                    search_results=search_results,
                    matched_category=matched_category,
                    matched_subcategory=matched_subcategory,
                    lang=lang)
            else:
                print(f"WARNING: Unknown responder name: '{name}'")
                return None

        # ── Step 3: Generate Response ──────────────────────────────────────────
        resp = None

        if primary_responder:
            resp = await try_responder(primary_responder)
            responders_tried.append(primary_responder)

        if resp is None or resp.answer == _FALLBACK_SENTINEL:
            if secondary_responder and secondary_responder not in responders_tried:
                print(
                    f"WARNING: Primary responder '{primary_responder}' failed. Trying secondary '{secondary_responder}'..."
                )
                resp = await try_responder(secondary_responder)
                responders_tried.append(secondary_responder)

        if resp is None or resp.answer == _FALLBACK_SENTINEL:
            if tertiary_responder and tertiary_responder not in responders_tried:
                print(
                    f"WARNING: Secondary responder '{secondary_responder}' failed. Trying tertiary '{tertiary_responder}'..."
                )
                resp = await try_responder(tertiary_responder)
                responders_tried.append(tertiary_responder)

        # ── Step 4: Static Last-Resort Fallback ──────────────────────────────
        if resp is None or resp.answer == _FALLBACK_SENTINEL:
            print("INFO: All responders failed — serving static last-resort")

            in_scope_keywords = {
                "medicine", "medicines", "product", "products", "drug",
                "drugs", "brand", "generic", "strength", "form",
                "availability", "stock", "inquire", "inquiry", "order", "buy",
                "purchase", "prescribe", "prescription", "pap", "assistance",
                "support", "help", "contact", "address", "phone", "email",
                "office", "team", "ceo", "manager", "staff", "news", "article",
                "services", "regulatory", "distribution", "cancer", "tumor",
                "leukemia", "lymphoma", "anemia", "cardiology", "oncology",
                "hematology", "immunology", "nephrology", "gynecology",
                "obstetrician", "infective", "treatment", "therapy", "doctor",
                "physician", "pharmacist", "getmeds", "assist", "faq",
                "shipping", "delivery", "payment"
            }
            query_words = set(re.findall(r'[a-z]+', user_message.lower()))
            is_possibly_in_scope = any(w in in_scope_keywords
                                       for w in query_words)

            if is_possibly_in_scope:
                fallbacks = {
                    "en":
                    "I'm sorry, I wasn't able to find exactly what you're looking for. Our team would be happy to help you directly.",
                    "tl":
                    "Pasensya na po, hindi ko nahanap ang eksaktong inyong hinahanap. Ikaliligaya ng aming koponan na tulungan kayo nang direkta.",
                    "tg":
                    "Pasensya na po, hindi ko nahanap ang eksaktong hinahanap ninyo. Our team would be happy to help you directly po."
                }
                answer_text = fallbacks.get(lang, fallbacks["en"])
            else:
                out_of_scopes = {
                    "en":
                    "That's a bit outside what I can help with directly, but I'd be happy to connect you with our team who can assist you further.",
                    "tl":
                    "Medyo labas po iyan sa maaari kong tulungan nang direkta, ngunit ikaliligaya kong ikonekta kayo sa aming koponan na makakatulong sa inyo nang higit pa.",
                    "tg":
                    "Medyo labas po iyan sa maaari kong tulungan directly, pero I'd be happy to connect you with our team who can assist you further po."
                }
                answer_text = out_of_scopes.get(lang, out_of_scopes["en"])

            contact_titles = {
                "en": "Contact Us",
                "tl": "Kontakin Kami",
                "tg": "Contact Us po"
            }
            resp = ChatResponse(answer=answer_text,
                                resources=[
                                    ResourceLink(title=contact_titles.get(
                                        lang, contact_titles["en"]),
                                                 url="/contact-us",
                                                 type="page")
                                ],
                                confidence=0.5)

        # ── Step 5: Save turn permanently to chat logs ──────────────────────
        detected_subject = None
        for r in resp.resources:
            if r.type == "product" and "Inquire" in r.title:
                detected_subject = r.title.replace("Inquire ", "")
                break

        final_subject = detected_subject or effective_subject
        await sanity_service.save_chat_turn(session_id,
                                            user_message,
                                            resp.answer,
                                            resources=resp.resources,
                                            last_subject=final_subject)

        return resp

    async def _rule_based_response(self,
                                   query: str,
                                   query_clean: str,
                                   user_message: str,
                                   effective_name: str | None,
                                   effective_subject: str | None,
                                   last_ai_msg: str,
                                   is_confirmation: bool,
                                   search_results: list,
                                   matched_category: dict = None,
                                   matched_subcategory: str = None,
                                   lang: str = "en") -> ChatResponse:
        """
        The original trained assistant engine — your custom-built responder.

        Returns a normal ChatResponse when it can handle the query.
        Returns ChatResponse(answer='__FALLBACK__', confidence=0.0) when it cannot,
        which signals the orchestrator to try static fallback instead.
        """
        # If Sanity returns nothing, we must not "guess" from general knowledge.
        # Provide a safe, Sanity-backed response instead of letting an LLM hallucinate.
        if not search_results:
            # Heuristic: treat short keyword queries as product searches (e.g., "biogesic")
            keywords = [w for w in query_clean.split() if w and w not in _STOP_WORDS]
            candidate = " ".join(keywords).strip() or user_message.strip()

            from urllib.parse import quote_plus
            search_q = quote_plus(candidate) if candidate else ""
            search_url = f"/product-range?search={search_q}" if search_q else "/product-range"

            not_found_msgs = {
                "en":
                f"I couldn't find **{candidate}** in our Getmeds catalog. You can try searching our Product Range, or contact our team so we can confirm availability for you.",
                "tl":
                f"Pasensya na po, wala akong nahanap na **{candidate}** sa catalog ng Getmeds. Maaari ninyong subukan i-search sa Product Range, o kontakin ang aming team para ma-check namin ang availability.",
                "tg":
                f"Pasensya na po, wala akong nahanap na **{candidate}** sa catalog ng Getmeds. Pwede ninyong i-search sa Product Range, or contact our team para ma-check namin ang availability po."
            }
            answer = not_found_msgs.get(lang, not_found_msgs["en"])

            titles = {
                "en": ("Search Products", "Contact Us"),
                "tl": ("Maghanap ng Produkto", "Kontakin Kami"),
                "tg": ("Search Products po", "Contact Us po")
            }
            t1, t2 = titles.get(lang, titles["en"])

            return ChatResponse(answer=answer,
                                resources=[
                                    ResourceLink(title=t1,
                                                 url=search_url,
                                                 type="product"),
                                    ResourceLink(title=t2,
                                                 url="/contact-us",
                                                 type="page"),
                                ],
                                confidence=0.9)

        # Relevance check to prevent weak matches (e.g. single generic word matches like "philippines")
        query_words = set(query_clean.split())
        query_keywords = {w for w in query_words if w not in _STOP_WORDS}

        def is_result_relevant(res):
            res_type = res.get("_type")
            title = (res.get("title") or res.get("name") or "").lower()
            desc = (res.get("description") or res.get("answer") or "").lower()

            title_words = set(re.findall(r'[a-z]+', title))
            if any(k in title_words for k in query_keywords):
                return True

            if res_type == "product":
                brand = (res.get("brandName") or "").lower()
                generic = (res.get("genericName") or "").lower()
                brand_words = set(re.findall(r'[a-z]+', brand))
                generic_words = set(re.findall(r'[a-z]+', generic))
                if any(k in brand_words or k in generic_words
                       for k in query_keywords):
                    return True

            if res_type == "faq":
                faq_keywords = [
                    kw.lower() for kw in res.get("keywords", []) or []
                ]
                if any(k in faq_keywords for k in query_keywords):
                    return True

            desc_words = set(re.findall(r'[a-z]+', desc))
            matches_in_desc = [k for k in query_keywords if k in desc_words]

            if len(query_keywords) <= 1 and len(matches_in_desc) >= 1:
                return True
            if len(query_keywords) > 1 and len(matches_in_desc) >= 2:
                return True

            return False

        if search_results:
            search_results = [
                r for r in search_results
                if r.get("_type") == "category" or is_result_relevant(r)
            ]

        is_memory_check = any(w in query for w in [
            "rememb", "recap", "summar", "inqui", "i say", "talking about",
            "mention"
        ])
        is_identity_check = any(
            w in query
            for w in ["who am i", "my name", "know me", "what is my name"])
        is_medical_query = any(k in query_clean for k in [
            "suggest", "recommend", "cure", "treat", "treatment", "medicine",
            "cancer"
        ])

        # ── Category / Subcategory Inquiry Handler ─────────────────────────────
        if matched_category:
            cat_name = matched_category.get("category")
            cat_slug = matched_category.get("slug")

            disclaimers = {
                "en":
                "⚠️ **Note:** I am an AI assistant and **not a doctor**.\n\n",
                "tl":
                "⚠️ **Paunawa:** Ako ay isang AI assistant at **hindi isang doktor**.\n\n",
                "tg":
                "⚠️ **Note po:** I am an AI assistant at **hindi po ako doktor**.\n\n"
            }
            answer_text = disclaimers.get(lang, disclaimers["en"])

            if matched_subcategory:
                subcat_headers = {
                    "en":
                    f"I found the following products in the **{matched_subcategory}** subcategory:\n\n",
                    "tl":
                    f"Nahanap ko ang mga sumusunod na produkto sa subcategory ng **{matched_subcategory}**:\n\n",
                    "tg":
                    f"Nahanap ko po ang mga sumusunod na products sa **{matched_subcategory}** subcategory:\n\n"
                }
                answer_text += subcat_headers.get(lang, subcat_headers["en"])

                sub_products = [
                    p for p in search_results if p.get("_type") == "product"
                    and product_belongs_to_subcategory(p, matched_subcategory)
                ]

                if sub_products:
                    for p in sub_products[:10]:
                        brand = p.get("brandName") or p.get("title")
                        generic = p.get("genericName")
                        strength = p.get("strength") or ""
                        form = p.get("form") or ""

                        stock_labels = {
                            "en": {
                                "in_stock":
                                "In Stock",
                                "out_of_stock":
                                "Out of Stock (Import Inquiry Available)"
                            },
                            "tl": {
                                "in_stock":
                                "May Stock",
                                "out_of_stock":
                                "Wala sa Stock (Maaaring mag-inquire para sa Import)"
                            },
                            "tg": {
                                "in_stock":
                                "In Stock po",
                                "out_of_stock":
                                "Out of Stock (Import Inquiry is Available po)"
                            }
                        }
                        labels = stock_labels.get(lang, stock_labels["en"])
                        avail = labels["in_stock"] if p.get(
                            "availability"
                        ) is not False else labels["out_of_stock"]

                        prod_desc = f" ({generic})" if generic else ""
                        answer_text += f"• **{brand}{prod_desc}**: {strength} {form} ({avail})\n"

                    if len(sub_products) > 10:
                        more_labels = {
                            "en": "\n...and more products are available.",
                            "tl":
                            "\n...at mayroon pang ibang mga produkto na magagamit.",
                            "tg": "\n...and more products are available po."
                        }
                        answer_text += more_labels.get(lang, more_labels["en"])
                else:
                    no_prod_labels = {
                        "en":
                        "No products are currently listed in this subcategory.",
                        "tl":
                        "Walang mga produkto na kasalukuyang nakalista sa subcategory na ito.",
                        "tg":
                        "Walang products na kasalukuyang listed sa subcategory na ito po."
                    }
                    answer_text += no_prod_labels.get(lang,
                                                      no_prod_labels["en"])

                sub_slug = re.sub(
                    r'[^a-z0-9-]', '',
                    re.sub(r'\s+', '-', matched_subcategory.lower()))

                browse_sub_titles = {
                    "en": f"Browse {matched_subcategory}",
                    "tl": f"Tingnan ang {matched_subcategory}",
                    "tg": f"Browse {matched_subcategory} po"
                }
                browse_cat_titles = {
                    "en": f"Browse {cat_name}",
                    "tl": f"Tingnan ang {cat_name}",
                    "tg": f"Browse {cat_name} po"
                }
                order_med_titles = {
                    "en": "Order Medicines",
                    "tl": "Mag-order ng Gamot",
                    "tg": "Order Medicines po"
                }

                resource_list = [
                    ResourceLink(title=browse_sub_titles.get(
                        lang, browse_sub_titles["en"]),
                                 url=f"/{_category_url_prefix(cat_name, sub_slug)}?category={sub_slug}",
                                 type="category"),
                    ResourceLink(title=browse_cat_titles.get(
                        lang, browse_cat_titles["en"]),
                                 url=f"/{_category_url_prefix(cat_name, cat_slug)}?category={cat_slug}"
                                 if cat_slug else "/product-range",
                                 type="category"),
                    ResourceLink(title=order_med_titles.get(
                        lang, order_med_titles["en"]),
                                 url="/order-medicines",
                                 type="page")
                ]
            else:
                cat_headers = {
                    "en":
                    f"I found the **{cat_name}** category. Here are our products grouped by subcategory:\n\n",
                    "tl":
                    f"Nahanap ko ang kategoryang **{cat_name}**. Narito ang aming mga produkto na nakapangkat ayon sa subcategory:\n\n",
                    "tg":
                    f"Nahanap ko po ang **{cat_name}** category. Narito ang aming mga products grouped by subcategory:\n\n"
                }
                answer_text += cat_headers.get(lang, cat_headers["en"])

                subcategories = matched_category.get("subcategory") or []
                cat_products = [
                    p for p in search_results if p.get("_type") == "product"
                ]

                for sub in subcategories:
                    sub_products = [
                        p for p in cat_products
                        if product_belongs_to_subcategory(p, sub)
                    ]
                    if sub_products:
                        answer_text += f"**{sub}**\n"
                        for p in sub_products[:3]:
                            brand = p.get("brandName") or p.get("title")
                            generic = p.get("genericName")
                            strength = p.get("strength") or ""
                            form = p.get("form") or ""

                            stock_labels = {
                                "en": {
                                    "in_stock": "In Stock",
                                    "out_of_stock": "Out of Stock"
                                },
                                "tl": {
                                    "in_stock": "May Stock",
                                    "out_of_stock": "Wala sa Stock"
                                },
                                "tg": {
                                    "in_stock": "In Stock po",
                                    "out_of_stock": "Out of Stock"
                                }
                            }
                            labels = stock_labels.get(lang, stock_labels["en"])
                            avail = labels["in_stock"] if p.get(
                                "availability"
                            ) is not False else labels["out_of_stock"]

                            prod_desc = f" ({generic})" if generic else ""
                            answer_text += f"• **{brand}{prod_desc}**: {strength} {form} ({avail})\n"

                        if len(sub_products) > 3:
                            more_prod_labels = {
                                "en":
                                f"• *and {len(sub_products) - 3} more product(s)...*\n",
                                "tl":
                                f"• *at {len(sub_products) - 3} pang produkto...*\n",
                                "tg":
                                f"• *and {len(sub_products) - 3} more products po...*\n"
                            }
                            answer_text += more_prod_labels.get(
                                lang, more_prod_labels["en"])
                        answer_text += "\n"

                browse_cat_titles = {
                    "en": f"Browse {cat_name}",
                    "tl": f"Tingnan ang {cat_name}",
                    "tg": f"Browse {cat_name} po"
                }
                order_med_titles = {
                    "en": "Order Medicines",
                    "tl": "Mag-order ng Gamot",
                    "tg": "Order Medicines po"
                }
                resource_list = [
                    ResourceLink(title=browse_cat_titles.get(
                        lang, browse_cat_titles["en"]),
                                 url=f"/{_category_url_prefix(cat_name, cat_slug)}?category={cat_slug}"
                                 if cat_slug else "/product-range",
                                 type="category"),
                    ResourceLink(title=order_med_titles.get(
                        lang, order_med_titles["en"]),
                                 url="/order-medicines",
                                 type="page")
                ]

            return ChatResponse(answer=answer_text,
                                resources=resource_list[:3],
                                confidence=1.0)

        # ── Deterministic intents — always handled by trained engine ─────────

        # Order / Prescription / Upload Help
        is_order_help = any(phrase in query for phrase in [
            "how to order", "how do i order", "how to upload",
            "how do i upload", "where to upload", "paano mag-order",
            "paano i-upload", "saan mag-upload", "mag-upload", "mag upload",
            "i-upload", "i upload", "magorder", "paano umorder",
            "paano magorder"
        ])
        if is_order_help:
            order_guides = {
                "en":
                "To place an order, please go to the **'Order Medicines'** page where you can upload your prescription, select your medicines, and submit your contact details. Our team will then review and process your request.",
                "tl":
                "Upang mag-order, mangyaring pumunta sa **'Order Medicines'** page kung saan maaari ninyong i-upload ang inyong reseta, piliin ang inyong mga gamot, at i-submit ang inyong contact details. Susuriin at ipoproseso po ito ng aming koponan.",
                "tg":
                "Para mag-order, please go to the **'Order Medicines'** page kung saan pwede ninyong i-upload ang inyong prescription, piliin ang inyong meds, at i-submit ang inyong contact details. Our team will review and process your request po."
            }
            res_titles = {
                "en": "Order Medicines / Upload Prescription",
                "tl": "Mag-order ng Gamot / I-upload ang Reseta",
                "tg": "Order Medicines / Upload Prescription po"
            }
            return ChatResponse(
                answer=order_guides.get(lang, order_guides["en"]),
                resources=[
                    ResourceLink(title=res_titles.get(lang, res_titles["en"]),
                                 url="/order-medicines",
                                 type="page")
                ],
                confidence=1.0)

        # Order confirmation
        if is_confirmation and ("proceed with the order" in last_ai_msg
                                or "like to order" in last_ai_msg
                                or "magpatuloy sa pag-order" in last_ai_msg
                                or "proceed sa order" in last_ai_msg):
            confirmations = {
                "en":
                f"Great! I've noted that you want to order **{effective_subject}**. Please proceed to the **'Order Medicines'** page to upload your prescription. We'll handle the rest!",
                "tl":
                f"Mabuti! Aking naitala na nais ninyong i-order ang **{effective_subject}**. Mangyaring magtungo sa **'Order Medicines'** page upang i-upload ang inyong reseta. Kami na ang bahala sa iba!",
                "tg":
                f"Great! Naisulat ko po na gusto ninyong mag-order ng **{effective_subject}**. Please proceed sa **'Order Medicines'** page para i-upload ang inyong prescription. Kami na po ang bahala sa rest!"
            }
            res_titles = {
                "en": "Upload Prescription",
                "tl": "I-upload ang Reseta",
                "tg": "Upload Prescription po"
            }
            return ChatResponse(
                answer=confirmations.get(lang, confirmations["en"]),
                resources=[
                    ResourceLink(title=res_titles.get(lang, res_titles["en"]),
                                 url="/order-medicines",
                                 type="page")
                ],
                confidence=1.0)

        # Identity check
        if is_identity_check:
            name_val = effective_name or ("a valued customer"
                                          if lang == "en" else
                                          "isang mahalagang customer" if lang
                                          == "tl" else "isang valued customer")
            identities = {
                "en": f"You are **{name_val}**! How can I assist you today?",
                "tl":
                f"Kayo po si **{name_val}**! Paano ko kayo matutulungan ngayon?",
                "tg":
                f"Kayo po si **{name_val}**! How can I assist you today po?"
            }
            return ChatResponse(answer=identities.get(lang, identities["en"]),
                                resources=[],
                                confidence=1.0)

        # Memory / recap check
        if is_memory_check:
            if effective_subject:
                memories_sub = {
                    "en":
                    f"Yes, I remember! We were discussing **{effective_subject}**. Should we continue?",
                    "tl":
                    f"Opo, natatandaan ko! Pinag-uusapan natin ang tungkol sa **{effective_subject}**. Nais niyo bang magpatuloy?",
                    "tg":
                    f"Opo, I remember! Pinag-uusapan natin ang tungkol sa **{effective_subject}**. Should we continue po?"
                }
                return ChatResponse(answer=memories_sub.get(
                    lang, memories_sub["en"]),
                                    resources=[],
                                    confidence=1.0)
            memories_empty = {
                "en":
                "I remember our talk, but we haven't picked a specific medicine yet. What would you like to explore?",
                "tl":
                "Natatandaan ko po ang ating pag-uusap, ngunit hindi pa tayo pumipili ng partikular na gamot. Ano po ang nais ninyong alamin?",
                "tg":
                "I remember our conversation po, pero hindi pa tayo nakakapili ng specific medicine. Ano po ang gusto ninyong i-explore?"
            }
            return ChatResponse(answer=memories_empty.get(
                lang, memories_empty["en"]),
                                resources=[],
                                confidence=1.0)

        # Greeting
        query_words = set(query_clean.split())
        if any(
                g in query_words for g in
            ["hello", "hi", "hey", "heya", "greetings", "kumusta", "kamusta"]):
            if effective_name:
                greetings_name = {
                    "en":
                    f"Hello {effective_name}! How can I help you today?",
                    "tl":
                    f"Magandang araw {effective_name}! Paano ko kayo matutulungan ngayon?",
                    "tg":
                    f"Hello po {effective_name}! How can I help you today po?"
                }
                answer_text = greetings_name.get(lang, greetings_name["en"])
            else:
                greetings_general = {
                    "en": "Hello! How can I help you today?",
                    "tl": "Magandang araw! Paano ko kayo matutulungan ngayon?",
                    "tg": "Hello po! Paano ko po kayo matutulungan today?"
                }
                answer_text = greetings_general.get(lang,
                                                    greetings_general["en"])
            return ChatResponse(answer=answer_text,
                                resources=[],
                                confidence=1.0)

        # ── Database-dependent intents — return sentinel if no results ────────

        if not search_results:
            return ChatResponse(answer=_FALLBACK_SENTINEL,
                                resources=[],
                                confidence=0.0)

        product_results = [
            r for r in search_results if r.get("_type") == "product"
        ]
        category_results = [
            r for r in search_results if r.get("_type") == "category"
        ]
        team_results = [r for r in search_results if r.get("_type") == "team"]

        active_product = product_results[0] if product_results else None

        is_price = any(w in query for w in [
            "price", "cost", "how much", "pricing", "rate", "fee", "worth",
            "presyo", "magkano"
        ])
        is_usage = any(w in query for w in [
            "how to use", "dosage", "administration", "how to take",
            "directions", "reconstitute", "administer", "use it",
            "paano inumin", "paano gamitin", "inumin", "gamitin"
        ])
        is_purpose = any(w in query for w in [
            "what is it for", "purpose", "indications", "what does it do",
            "mechanism", "treat", "cure", "para saan", "gamot sa", "indikas"
        ])
        is_supplier = any(w in query for w in [
            "supplier", "importer", "distributor", "origin", "where from",
            "who makes", "manufacturer", "accreditation", "galing sa",
            "saan galing"
        ])
        is_availability = any(w in query for w in [
            "do you have", "do we have", "we have", "in stock", "available",
            "availability", "meron ba", "mayroon ba", "may stock"
        ])

        # ── Specific product intent ───────────────────────────────────────────
        if active_product and (is_price or is_usage or is_purpose
                               or is_supplier or is_availability):
            brand = active_product.get("brandName") or active_product.get(
                "title") or "the medicine"
            generic = active_product.get("genericName") or ""
            prod_title = f"{brand} ({generic})" if generic else brand

            disclaimers = {
                "en":
                "⚠️ **Note:** I am an AI assistant and **not a doctor**.\n\n",
                "tl":
                "⚠️ **Paunawa:** Ako ay isang AI assistant at **hindi isang doktor**.\n\n",
                "tg":
                "⚠️ **Note po:** I am an AI assistant at **hindi po ako doktor**.\n\n"
            }
            answer_text = disclaimers.get(
                lang, disclaimers["en"]) if is_medical_query else ""

            if is_price:
                prices = {
                    "en":
                    (f"Specialty and imported medicines like **{prod_title}** are priced through direct inquiry "
                     "to give you the most accurate quote based on your requirements. "
                     "Would you like to submit an inquiry on the **Product Range** page, or start an order on the **Order Medicines** page?"
                     ),
                    "tl":
                    (f"Ang mga specialty at imported na gamot tulad ng **{prod_title}** ay may presyong nakabatay sa direktang inquiry "
                     "upang mabigyan kayo ng pinakatumpak na quote base sa inyong mga pangangailangan. "
                     "Nais niyo bang mag-submit ng inquiry sa **Product Range** page, o magsimula ng order sa **Order Medicines** page?"
                     ),
                    "tg":
                    (f"Ang mga specialty at imported na gamot tulad ng **{prod_title}** ay priced sa pamamagitan ng direct inquiry "
                     "para mabigyan kayo ng most accurate quote base sa inyong requirements. "
                     "Would you like to submit an inquiry sa **Product Range** page, o mag-start ng order sa **Order Medicines** page po?"
                     )
                }
                answer_text += prices.get(lang, prices["en"])
            elif is_usage:
                dosage_val = active_product.get("dosageAdministration")
                storage_val = active_product.get("storageCondition")

                if not dosage_val:
                    dosage_val = "Please consult your physician for exact dosage details." if lang == "en" else "Mangyaring kumunsulta sa inyong doktor para sa eksaktong detalye ng dosage." if lang == "tl" else "Please consult your physician para sa exact dosage details po."
                if not storage_val:
                    storage_val = "Store as directed on the packaging." if lang == "en" else "I-imbak tulad ng nakasaad sa pakete." if lang == "tl" else "Store as directed sa packaging po."

                usage_headers = {
                    "en":
                    f"**Dosage & Administration for {prod_title}:**\n\n{dosage_val}\n\n**Storage:** {storage_val}",
                    "tl":
                    f"**Dosage at Pag-inom para sa {prod_title}:**\n\n{dosage_val}\n\n**Pag-imbak:** {storage_val}",
                    "tg":
                    f"**Dosage & Administration para sa {prod_title}:**\n\n{dosage_val}\n\n**Storage po:** {storage_val}"
                }
                answer_text += usage_headers.get(lang, usage_headers["en"])

                recon = active_product.get("directionForReconstitution")
                if recon:
                    recon_headers = {
                        "en":
                        f"\n\n**Directions for Reconstitution:** {recon}",
                        "tl":
                        f"\n\n**Mga Direksyon para sa Reconstitution:** {recon}",
                        "tg":
                        f"\n\n**Directions for Reconstitution po:** {recon}"
                    }
                    answer_text += recon_headers.get(lang, recon_headers["en"])
            elif is_purpose:
                indications = active_product.get(
                    "indications") or active_product.get("description")
                if not indications:
                    indications = "Used for targeted specialty medical therapy." if lang == "en" else "Ginagamit para sa target na specialty na medikal na terapiya." if lang == "tl" else "Used para sa targeted specialty medical therapy po."

                purpose_headers = {
                    "en":
                    f"**Indications for {prod_title}:**\n\n{indications}",
                    "tl":
                    f"**Mga Indikasyon para sa {prod_title}:**\n\n{indications}",
                    "tg":
                    f"**Indications para sa {prod_title}:**\n\n{indications}"
                }
                answer_text += purpose_headers.get(lang, purpose_headers["en"])

                moa = active_product.get("mechanismOfAction")
                if moa:
                    moa_headers = {
                        "en":
                        f"\n\n**Mechanism of Action:** {moa}",
                        "tl":
                        f"\n\n**Mechanism of Action (Paano ito gumagana):** {moa}",
                        "tg":
                        f"\n\n**Mechanism of Action (Paano ito gumagana po):** {moa}"
                    }
                    answer_text += moa_headers.get(lang, moa_headers["en"])
            elif is_supplier:
                supplier = active_product.get("supplier") or (
                    "Specialty Importers"
                    if lang == "en" else "Mga Specialty Importer"
                    if lang == "tl" else "Specialty Importers po")

                logistics_headers = {
                    "en":
                    f"**Logistics & Origin for {prod_title}:**\n\n• **Supplier:** {supplier}",
                    "tl":
                    f"**Logistics at Pinagmulan para sa {prod_title}:**\n\n• **Supplier:** {supplier}",
                    "tg":
                    f"**Logistics & Origin para sa {prod_title}:**\n\n• **Supplier:** {supplier}"
                }
                answer_text += logistics_headers.get(lang,
                                                     logistics_headers["en"])

                if active_product.get("importer"):
                    importer_headers = {
                        "en":
                        f"\n• **Importer:** {active_product['importer']}",
                        "tl":
                        f"\n• **Importer:** {active_product['importer']}",
                        "tg":
                        f"\n• **Importer po:** {active_product['importer']}"
                    }
                    answer_text += importer_headers.get(
                        lang, importer_headers["en"])
                if active_product.get("distributor"):
                    distributor_headers = {
                        "en":
                        f"\n• **Distributor:** {active_product['distributor']}",
                        "tl":
                        f"\n• **Distributor:** {active_product['distributor']}",
                        "tg":
                        f"\n• **Distributor po:** {active_product['distributor']}"
                    }
                    answer_text += distributor_headers.get(
                        lang, distributor_headers["en"])
                if active_product.get("accreditations"):
                    accreditation_headers = {
                        "en":
                        f"\n• **Accreditations:** {active_product['accreditations']}",
                        "tl":
                        f"\n• **Accreditations:** {active_product['accreditations']}",
                        "tg":
                        f"\n• **Accreditations po:** {active_product['accreditations']}"
                    }
                    answer_text += accreditation_headers.get(
                        lang, accreditation_headers["en"])
            elif is_availability:
                avail = active_product.get("availability")

                in_stock_labels = {
                    "en":
                    "in stock and available for order" if avail is not False
                    else "currently available for import inquiry",
                    "tl":
                    "may stock at maaaring i-order" if avail is not False else
                    "kasalukuyang magagamit sa pamamagitan ng import inquiry",
                    "tg":
                    "in stock at available for order po" if avail is not False
                    else "currently available for import inquiry po"
                }
                stock_desc = in_stock_labels.get(lang, in_stock_labels["en"])

                availability_headers = {
                    "en":
                    f"**{prod_title}** is {stock_desc}. Would you like to proceed with the order?",
                    "tl":
                    f"Ang **{prod_title}** ay {stock_desc}. Nais niyo bang magpatuloy sa pag-order?",
                    "tg":
                    f"Ang **{prod_title}** ay {stock_desc}. Nais niyo po bang mag-proceed sa order?"
                }
                answer_text += availability_headers.get(
                    lang, availability_headers["en"])

            inquire_titles = {
                "en": f"Inquire {brand}",
                "tl": f"Magtanong ukol sa {brand}",
                "tg": f"Inquire {brand} po"
            }
            order_med_titles = {
                "en": "Order Medicines",
                "tl": "Mag-order ng Gamot",
                "tg": "Order Medicines po"
            }
            return ChatResponse(answer=answer_text,
                                resources=[
                                    ResourceLink(
                                        title=inquire_titles.get(
                                            lang, inquire_titles["en"]),
                                        url=f"/{_category_url_prefix(brand_name=brand)}?search={brand}",
                                        type="product"),
                                    ResourceLink(title=order_med_titles.get(
                                        lang, order_med_titles["en"]),
                                                 url="/order-medicines",
                                                 type="page")
                                ],
                                confidence=1.0)

        # ── General result display ────────────────────────────────────────────
        top = (category_results or product_results or team_results
               or search_results)[0]
        top_type = top.get("_type")

        disclaimers = {
            "en":
            "⚠️ **Note:** I am an AI assistant and **not a doctor**.\n\n",
            "tl":
            "⚠️ **Paunawa:** Ako ay isang AI assistant at **hindi isang doktor**.\n\n",
            "tg":
            "⚠️ **Note po:** I am an AI assistant at **hindi po ako doktor**.\n\n"
        }
        answer_text = disclaimers.get(
            lang, disclaimers["en"]) if is_medical_query else ""

        if top_type == "product":
            p = top
            brand = p.get("brandName") or p.get("title") or "the medicine"
            generic = p.get("genericName") or ""
            prod_title = f"{brand} ({generic})" if generic else brand
            form = p.get("form") or ""
            strength = p.get("strength") or ""
            desc = (p.get("description") or p.get("indications")
                    or ("Specialty medicine."
                        if lang == "en" else "Espesyal na gamot."
                        if lang == "tl" else "Specialty medicine po."))[:180]

            stock_labels = {
                "en": {
                    "in_stock": "In Stock",
                    "out_of_stock": "Out of Stock (Import Inquiry Available)"
                },
                "tl": {
                    "in_stock":
                    "May Stock",
                    "out_of_stock":
                    "Wala sa Stock (Maaaring mag-inquire para sa Import)"
                },
                "tg": {
                    "in_stock": "In Stock po",
                    "out_of_stock":
                    "Out of Stock (Import Inquiry is Available po)"
                }
            }
            labels = stock_labels.get(lang, stock_labels["en"])
            avail = labels["in_stock"] if p.get(
                "availability") is not False else labels["out_of_stock"]

            general_prods = {
                "en": (f"I found **{prod_title}**:\n\n"
                       f"• **Strength/Form:** {strength} {form}\n"
                       f"• **Availability:** {avail}\n"
                       f"• **Indications:** {desc}...\n\n"
                       "Would you like to proceed with the order?"),
                "tl": (f"Nahanap ko ang **{prod_title}**:\n\n"
                       f"• **Strength/Form:** {strength} {form}\n"
                       f"• **Availability:** {avail}\n"
                       f"• **Mga Indikasyon:** {desc}...\n\n"
                       "Nais niyo bang magpatuloy sa pag-order?"),
                "tg": (f"Nahanap ko po ang **{prod_title}**:\n\n"
                       f"• **Strength/Form:** {strength} {form}\n"
                       f"• **Availability:** {avail}\n"
                       f"• **Indications:** {desc}...\n\n"
                       "Would you like to proceed sa order po?")
            }
            answer_text += general_prods.get(lang, general_prods["en"])
        elif top_type == "category":
            desc = top.get("description") or top.get("subtitle") or (
                "Specialty therapeutic range."
                if lang == "en" else "Espesyal na saklaw ng terapiya."
                if lang == "tl" else "Specialty therapeutic range po.")

            general_cats = {
                "en":
                (f"I found the **{top.get('title', 'Unknown')}** category:\n\n"
                 f"{desc}\n\n"
                 f"Would you like to view our full range of **{top.get('title')}** products?"
                 ),
                "tl":
                (f"Nahanap ko ang kategoryang **{top.get('title', 'Hindi Alamin')}**:\n\n"
                 f"{desc}\n\n"
                 f"Nais niyo bang tingnan ang aming buong saklaw ng mga produktong **{top.get('title')}**?"
                 ),
                "tg":
                (f"Nahanap ko po ang **{top.get('title', 'Unknown')}** category:\n\n"
                 f"{desc}\n\n"
                 f"Would you like to view our full range of **{top.get('title')}** products po?"
                 )
            }
            answer_text += general_cats.get(lang, general_cats["en"])
        elif top_type == "team":
            team_texts = {
                "en":
                f"**{top.get('title')}** is the **{top.get('role', 'Team Member')}** of Getmeds.",
                "tl":
                f"Si **{top.get('title')}** ay ang **{top.get('role', 'Kasapi ng Koponan')}** ng Getmeds.",
                "tg":
                f"Si **{top.get('title')}** po ay ang **{top.get('role', 'Team Member')}** ng Getmeds."
            }
            answer_text += team_texts.get(lang, team_texts["en"])
        else:
            answer_text += top.get("answer") or top.get("description") or (
                f"I found information about **{top.get('title')}**."
                if lang == "en" else
                f"Nahanap ko ang impormasyon tungkol sa **{top.get('title')}**."
                if lang == "tl" else
                f"Nahanap ko po ang information tungkol sa **{top.get('title')}**."
            )

        resource_list = []
        for res in (category_results + product_results + team_results)[:3]:
            t = res.get("_type")
            if t == "product":
                b = res.get("brandName") or res.get("title")

                inquire_titles = {
                    "en": f"Inquire {b}",
                    "tl": f"Magtanong ukol sa {b}",
                    "tg": f"Inquire {b} po"
                }
                order_med_titles = {
                    "en": "Order Medicines",
                    "tl": "Mag-order ng Gamot",
                    "tg": "Order Medicines po"
                }

                resource_list.append(
                    ResourceLink(title=inquire_titles.get(
                        lang, inquire_titles["en"]),
                                 url=f"/{_category_url_prefix(brand_name=b)}?search={b}",
                                 type="product"))
                if not any(r.url == "/order-medicines" for r in resource_list):
                    resource_list.append(
                        ResourceLink(title=order_med_titles.get(
                            lang, order_med_titles["en"]),
                                     url="/order-medicines",
                                     type="page"))
            elif t == "category":
                link = res.get("link") or (
                    f"/{_category_url_prefix(res.get('title'), res.get('slug'))}"
                    f"?category={res.get('slug')}")

                browse_cat_titles = {
                    "en": f"Browse {res.get('title')}",
                    "tl": f"Tingnan ang {res.get('title')}",
                    "tg": f"Browse {res.get('title')} po"
                }
                resource_list.append(
                    ResourceLink(title=browse_cat_titles.get(
                        lang, browse_cat_titles["en"]),
                                 url=link,
                                 type="category"))
            else:
                link = res.get("link", "#")
                if not link.startswith("/") and not link.startswith("http"):
                    link = "/" + link

                view_detail_titles = {
                    "en": res.get("title", "View Detail"),
                    "tl": res.get("title", "Tingnan ang Detalye"),
                    "tg": res.get("title", "View Detail po")
                }
                resource_list.append(
                    ResourceLink(title=view_detail_titles.get(
                        lang, view_detail_titles["en"]),
                                 url=link,
                                 type=t or "page"))

        return ChatResponse(answer=answer_text,
                            resources=resource_list[:3],
                            confidence=1.0)


chatbot_service = ChatbotService()
