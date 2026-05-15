from fastapi import APIRouter, HTTPException
from app.schemas.chatbot import ChatRequest, ChatResponse
from app.services.chatbot_service import chatbot_service

router = APIRouter()

@router.post("/ask", response_model=ChatResponse)
async def ask_chatbot(request: ChatRequest):
    """
    Endpoint for the chatbot to receive questions and return Sanity-sourced answers.
    """
    try:
        response = await chatbot_service.get_response(request.message)
        return response
    except Exception as e:
        # Log error in production
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_status():
    """
    Health check endpoint.
    """
    return {"status": "online", "service": "GetMEDS Chatbot API"}
