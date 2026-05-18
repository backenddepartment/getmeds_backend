from app.services.sanity_service import sanity_service
from app.schemas.chatbot import ResourceLink, ChatResponse
import re

class ChatbotService:
    async def get_response(self, user_message: str, session_id: str = "default") -> ChatResponse:
        """
        Hyper-Contextual Sales Assistant: Eliminates hallucinations by strictly locking context on 'order' intents.
        """
        # Load session context
        session_query = f'*[_type == "chatSession" && sessionId == $sid][0]'
        session_data = await sanity_service.query_sanity(session_query, {"$sid": session_id})
        
        current_user_name = session_data.get("userName") if session_data else None
        last_subject = session_data.get("lastSubject") if session_data else None
        session_summary = session_data.get("sessionSummary", "") if session_data else ""
        
        last_ai_msg = ""
        if session_data and session_data.get("messages"):
            last_ai_msg = session_data["messages"][-1].get("ai", "").lower()
        elif session_summary:
            summary_parts = session_summary.split("| AI:")
            if summary_parts: last_ai_msg = summary_parts[-1].strip().lower()

        # 1. Pre-process Query
        query = user_message.lower().strip()
        
        # SMART INTENT DETECTION (Including 'order it' style confirmations)
        is_confirmation = any(w in query for w in ["yes", "yup", "sure", "ok", "proceed", "deal", "like the", "want the", "order it", "buy it", "get it", "want to order"])
        is_memory_check = any(w in query for w in ["rememb", "recap", "summar", "inqui", "i say", "talking about", "mention"])
        is_identity_check = any(w in query for w in ["who am i", "my name", "know me", "what is my name"])
        is_asking_alternative = any(w in query for w in ["anoth", "other", "else", "differen", "variation"])
        is_recommendation = any(w in query for w in ["sugges", "recommen", "show me", "list", "options"])

        # QUANTITY EXTRACTION
        quantity = 1
        qty_match = re.search(r"(?:i want|need|qty|quantity|x|buy)\s*(\d+)|(\d+)\s*(?:pcs|pieces|qty|items)", query)
        if qty_match: quantity = int(qty_match.group(1) or qty_match.group(2))
        
        query_clean = re.sub(r'[^a-zA-Z0-9\s]', '', query)
        query_clean = re.sub(r'(\d+)([a-zA-Z]+)', r'\1 \2', query_clean)

        # IDENTITY RECOGNITION
        new_user_name = None
        name_match = re.search(r"(?:my name is|im|i am|call me|name is) ([\w\s]+)", query)
        if name_match:
            new_user_name = name_match.group(1).strip().title()
            from datetime import datetime
            timestamp = datetime.utcnow().isoformat() + "Z"
            await sanity_service.mutate_sanity([
                {
                    "createIfNotExists": {
                        "_id": session_id,
                        "_type": "chatSession",
                        "sessionId": session_id,
                        "lastActivity": timestamp,
                        "messages": []
                    }
                },
                {
                    "patch": {
                        "id": session_id,
                        "set": {"userName": new_user_name}
                    }
                }
            ])
        
        effective_name = new_user_name or current_user_name
        
        # 2. Context & Keywords
        stop_words = {
            "do", "you", "have", "what", "is", "are", "tell", "me", "about", 
            "search", "find", "the", "a", "an", "for", "how", "much", "can", 
            "please", "i", "want", "to", "order", "with", "any", "some", "of",
            "could", "would", "should", "get", "give", "show", "from", "it", "this", "that", "who", "of",
            "getmeds", "company", "cost", "total", "price", "worth", "buy", "need", "products", "medicine", "meds",
            "suggest", "recommend", "another", "other", "else", "like", "want the", "i like the", str(quantity), "remember", "inquiry"
        }
        keywords = [word for word in query_clean.split() if word not in stop_words]
        
        # IMPROVED PRONOUN LOCK (If 'it', 'this', 'that' is used, we MUST use context)
        query_words = set(query_clean.split())
        has_pronoun = any(w in query_words for w in ["it", "this", "that"])
        context_words = {"it", "this", "that", "how", "much", "is", "cost", "price", "total", "yes", "no", "ok", "another", "other", "remember", "inquiry", "name"}
        is_generic_followup = query_words.issubset(context_words) or (len(query_words) <= 5 and has_pronoun)

        # TOPIC RESOLUTION
        effective_subject = last_subject
        if not effective_subject and session_summary:
            brand_match = re.search(r"AI: I found \*\*([\w\s]+)\*\*", session_summary)
            if brand_match: effective_subject = brand_match.group(1)

        if (is_generic_followup or is_asking_alternative or is_confirmation) and effective_subject:
            brand = effective_subject.split()[0]
            clean_search = f"{brand} {' '.join(keywords)}".strip()
            using_context = True
        else:
            clean_search = " ".join(keywords) if keywords else query_clean
            using_context = False

        # 3. Medical Safety
        is_medical_query = any(k in query_clean for k in ["suggest", "recommend", "cure", "treat", "treatment", "medicine", "cancer"])

        resp = None
        detected_subject = None

        # 4. Intent Routing
        
        # PROCEED TO ORDER (Confirmation)
        if is_confirmation and ("proceed with the order" in last_ai_msg or "like to order" in last_ai_msg):
            resp = ChatResponse(
                answer=f"Great! I've noted that you want to order **{effective_subject}**. Please proceed to the **'Order Medicines'** page to upload your prescription. We'll handle the rest!",
                resources=[ResourceLink(title="Upload Prescription", url="/order-medicines", type="page")]
            )
        
        # IDENTITY & MEMORY
        elif is_identity_check:
            resp = ChatResponse(answer=f"You are **{effective_name or 'a valued customer'}**! How can I assist you today?", resources=[])
        elif is_memory_check:
            if effective_subject:
                resp = ChatResponse(answer=f"Yes, I remember! We were discussing **{effective_subject}**. Should we continue?", resources=[])
            else:
                resp = ChatResponse(answer="I remember our talk, but we haven't picked a specific medicine yet.", resources=[])
        
        elif any(greet in query_clean for greet in ["hello", "hi", "hey"]):
            greeting = f"Hello {effective_name if effective_name else ''}! "
            resp = ChatResponse(answer=f"{greeting}How can I help you today?", resources=[])

        else:
            # 5. Database Search
            results = await sanity_service.search_content(clean_search)
            if results and keywords:
                results = [r for r in results if any(k in r.get("title", "").lower() for k in keywords)]

            if results:
                team_results = [r for r in results if r.get("_type") == "team"]
                product_results = [r for r in results if r.get("_type") == "product"]
                top_result = team_results[0] if team_results else (product_results[0] if product_results else results[0])
                top_title = top_result.get("title") or ""
                top_type = top_result.get("_type")
                if top_type == "product": detected_subject = top_title
                
                answer_text = ""
                if is_medical_query: answer_text = "⚠️ **Note:** I am an AI assistant and **not a doctor**.\n\n"

                if top_type == "product":
                    if len(product_results) > 1 and is_recommendation:
                        answer_text += f"I found these variations for **{clean_search.title()}**:\n"
                        for prod in product_results[:3]:
                            answer_text += f"\n• **{prod.get('title')}**: ₱{(prod.get('price') or 0):,.2f}"
                        answer_text += "\n\nWhich one would you like to order?"
                    else:
                        price = top_result.get('price') or 0
                        answer_text += f"I found **{top_title}** for **₱{price:,.2f}**. Would you like to proceed with the order?"
                elif top_type == "team":
                    role = top_result.get("role", "Team Member")
                    answer_text += f"**{top_title}** is the **{role}** of GetMEDS."
                else:
                    answer_text += top_result.get("answer") or top_result.get("description") or f"I found information about **{top_title}**."

                resource_list = []
                sorted_results = team_results + product_results + [r for r in results if r.get("_type") not in ["team", "product"]]
                for res in sorted_results[:3]:
                    resource_list.append(ResourceLink(title=res.get("title", "View Detail"), url=res.get("link", "#"), type=res.get("_type", "page")))
                resp = ChatResponse(answer=answer_text, resources=resource_list)
            else:
                resp = ChatResponse(answer="I'm sorry, I couldn't find exactly that. Can I help you with another search?", resources=[ResourceLink(title="Contact Us", url="/contact", type="page")])

        if resp:
            final_subject = detected_subject or last_subject
            await sanity_service.save_chat_turn(session_id, user_message, resp.answer, last_subject=final_subject)
        
        return resp

chatbot_service = ChatbotService()
