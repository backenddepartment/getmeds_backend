from app.services.sanity_service import sanity_service
from app.schemas.chatbot import ResourceLink, ChatResponse
import re

class ChatbotService:
    async def get_response(self, user_message: str) -> ChatResponse:
        """
        Main logic for processing user messages and returning responses.
        Currently uses keyword matching to find relevant Sanity content.
        """
        # 1. Clean query (remove special characters that break GROQ match)
        query = user_message.lower().strip()
        query = re.sub(r'[^a-zA-Z0-9\s]', '', query)

        # 2. Basic intent detection (Static responses for common greetings)
        if any(greet in query for greet in ["hello", "hi", "hey"]):
            return ChatResponse(
                answer="Hello! I'm the GetMEDS assistant. How can I help you navigate our services or find medicines today?",
                resources=[]
            )

        # 3. Query Sanity for relevant content
        results = await sanity_service.search_content(query)

        # 4. Format response based on results
        if not results:
            return ChatResponse(
                answer="I'm sorry, I couldn't find any specific information about that on our website. Would you like to see our general services or contact support?",
                resources=[
                    ResourceLink(title="Our Services", url="/services", type="service"),
                    ResourceLink(title="Contact Us", url="/contact", type="page")
                ]
            )

        # 5. Build friendly answer
        resource_list = []
        answer_text = f"I found {len(results)} relevant items for you:\n"
        
        for item in results[:3]:  # Limit to top 3 for brevity
            title = item.get("title", "Untitled")
            item_type = item.get("_type", "resource")
            link = item.get("link", "#")
            
            resource_list.append(ResourceLink(
                title=title,
                url=link,
                type=item_type
            ))
            
            answer_text += f"- {title} ({item_type})\n"

        answer_text += "\nYou can click the links below for more details."

        return ChatResponse(
            answer=answer_text,
            resources=resource_list
        )

chatbot_service = ChatbotService()
