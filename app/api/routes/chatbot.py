# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException, Body

from app.schemas.chatbot import ChatRequest, ChatResponse
from app.services.chatbot_service import chatbot_service

router = APIRouter()

@router.post("/ask", response_model=ChatResponse)
async def ask_chatbot(request_data: dict | str = Body(...)):
    """
    Endpoint for the chatbot to receive questions and return Sanity-sourced answers.
    """
    try:
        # Handle cases where the body is sent as a string (double-encoded JSON)
        if isinstance(request_data, str):
            import json
            request_data = json.loads(request_data)
        
        request = ChatRequest(**request_data)
        
        session_id = request.session_id or "anonymous-user"
        response = await chatbot_service.get_response(
            request.message,
            session_id=session_id,
            page_context=request.page_context
        )
        return response

    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR in /ask: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e) or "Internal Server Error")


@router.get("/status")
async def get_status():
    """
    Health check endpoint.
    """
    return {"status": "online", "service": "GetMEDS Chatbot API"}
