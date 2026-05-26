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
            
            # Resolve product from search or last subject context
            active_product = None
            product_results = [r for r in results if r.get("_type") == "product"] if results else []
            team_results = [r for r in results if r.get("_type") == "team"] if results else []
            
            if product_results:
                active_product = product_results[0]
            elif effective_subject:
                clean_subj = effective_subject.split(" (")[0]
                subject_results = await sanity_service.search_content(clean_subj)
                subject_products = [r for r in subject_results if r.get("_type") == "product"]
                if subject_products:
                    active_product = subject_products[0]

            query_lower = query.lower().strip()
            # Detect intents
            is_price = any(w in query_lower for w in ["price", "cost", "how much", "pricing", "value", "rate", "fee", "how much is", "worth"])
            is_usage = any(w in query_lower for w in ["how to use", "dosage", "administration", "how to take", "directions", "reconstitute", "prepare", "administer", "use it"])
            is_purpose = any(w in query_lower for w in ["what is it for", "purpose", "indications", "what does it do", "indications of", "mechanism", "action", "treat", "cure"])
            is_supplier = any(w in query_lower for w in ["supplier", "importer", "distributor", "origin", "where from", "who makes", "manufacturer", "accreditation", "certificate"])
            is_availability = any(w in query_lower for w in ["do you have", "in stock", "available", "is it available", "stock", "availability"])

            if active_product and (is_price or is_usage or is_purpose or is_supplier or is_availability):
                brand = active_product.get("brandName") or active_product.get("title") or "the medicine"
                generic = active_product.get("genericName") or ""
                prod_title = f"{brand} ({generic})" if generic else brand
                detected_subject = prod_title
                
                answer_text = ""
                if is_medical_query:
                    answer_text += "⚠️ **Note:** I am an AI assistant and **not a doctor**.\n\n"
                
                if is_price:
                    answer_text += (
                        f"Specialty and imported medicines like **{prod_title}** are subject to direct inquiry to provide you with the most accurate pricing and logistics. "
                        f"Would you like to submit an inquiry? You can submit it directly on the **Product Range** page or check out using the **Order Medicines** page."
                    )
                elif is_usage:
                    dosage = active_product.get("dosageAdministration") or "Please consult your physician for exact dosage details."
                    storage = active_product.get("storageCondition") or "Store as directed on the packaging."
                    reconstitution = active_product.get("directionForReconstitution")
                    
                    answer_text += f"**Dosage & Administration for {prod_title}:**\n\n{dosage}\n\n**Storage Conditions:** {storage}"
                    if reconstitution:
                        answer_text += f"\n\n**Directions for Reconstitution:** {reconstitution}"
                elif is_purpose:
                    indications = active_product.get("indications") or active_product.get("description") or "Used for targeted specialty medical therapy."
                    moa = active_product.get("mechanismOfAction")
                    
                    answer_text += f"**Indications for {prod_title}:**\n\n{indications}"
                    if moa:
                        answer_text += f"\n\n**Mechanism of Action:** {moa}"
                elif is_supplier:
                    supplier = active_product.get("supplier") or "Specialty Importers"
                    importer = active_product.get("importer")
                    distributor = active_product.get("distributor")
                    accreditations = active_product.get("accreditations")
                    
                    answer_text += f"**Logistics & Origin for {prod_title}:**\n\n• **Supplier:** {supplier}"
                    if importer: answer_text += f"\n• **Importer:** {importer}"
                    if distributor: answer_text += f"\n• **Distributor:** {distributor}"
                    if accreditations: answer_text += f"\n• **Accreditations:** {accreditations}"
                elif is_availability:
                    avail = active_product.get("availability")
                    in_stock = "in stock and available for order" if avail != False else "currently out of stock (available for import inquiry)"
                    answer_text += f"**{prod_title}** is {in_stock}. Would you like to proceed with the order?"

                resource_list = [
                    ResourceLink(title=f"Inquire {brand}", url=f"product-range.html?search={brand}", type="product"),
                    ResourceLink(title="Order Medicines", url="order-medicines.html", type="page")
                ]
                resp = ChatResponse(answer=answer_text, resources=resource_list)

            elif results:
                top_result = team_results[0] if team_results else (product_results[0] if product_results else results[0])
                top_title = top_result.get("title") or ""
                top_type = top_result.get("_type")
                if top_type == "product":
                    detected_subject = top_title
                
                answer_text = ""
                if is_medical_query:
                    answer_text = "⚠️ **Note:** I am an AI assistant and **not a doctor**.\n\n"

                if top_type == "product":
                    prod = product_results[0]
                    brand = prod.get("brandName") or prod.get("title") or "the medicine"
                    generic = prod.get("genericName") or ""
                    prod_title = f"{brand} ({generic})" if generic else brand
                    detected_subject = prod_title
                    
                    form = prod.get("form") or ""
                    strength = prod.get("strength") or ""
                    desc = prod.get("description") or prod.get("indications") or "Specialty medicine."
                    avail = "In Stock" if prod.get("availability") != False else "Out of Stock (Import Inquiry Available)"
                    
                    answer_text += (
                        f"I found **{prod_title}**:\n\n"
                        f"• **Strength/Form:** {strength} {form}\n"
                        f"• **Availability:** {avail}\n"
                        f"• **Indications:** {desc[:180]}...\n\n"
                        f"Would you like to proceed with the order?"
                    )
                elif top_type == "team":
                    role = top_result.get("role", "Team Member")
                    answer_text += f"**{top_title}** is the **{role}** of GetMEDS."
                else:
                    answer_text += top_result.get("answer") or top_result.get("description") or f"I found information about **{top_title}**."

                resource_list = []
                # Map resources based on search results
                sorted_results = team_results + product_results + [r for r in results if r.get("_type") not in ["team", "product"]]
                for res in sorted_results[:3]:
                    type_ = res.get("_type")
                    if type_ == "product":
                        brand = res.get("brandName") or res.get("title")
                        resource_list.append(ResourceLink(title=f"Inquire {brand}", url=f"product-range.html?search={brand}", type="product"))
                        resource_list.append(ResourceLink(title="Order Medicines", url="order-medicines.html", type="page"))
                    else:
                        resource_list.append(ResourceLink(title=res.get("title", "View Detail"), url=res.get("link", "#"), type=type_ or "page"))
                        
                resp = ChatResponse(answer=answer_text, resources=resource_list)
            else:
                resp = ChatResponse(
                    answer="I'm sorry, I couldn't find exactly that. Can I help you with another search or connect you with our team?",
                    resources=[ResourceLink(title="Contact Us", url="contact-us.html", type="page")]
                )

        if resp:
            final_subject = detected_subject or last_subject
            await sanity_service.save_chat_turn(
                session_id, 
                user_message, 
                resp.answer, 
                resources=resp.resources, 
                last_subject=final_subject
            )
        
        return resp

chatbot_service = ChatbotService()
