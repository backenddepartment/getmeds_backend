# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
from typing import List, Optional

class ChatRequest(BaseModel):
    message: str = Field(..., description="The user's message to the chatbot")
    session_id: Optional[str] = Field(None, description="Optional session ID for tracking conversations")
    page_context: Optional[str] = Field(None, description="Optional page context / raw text from the frontend page")

class ResourceLink(BaseModel):
    title: str
    url: str
    type: str  # e.g., 'product', 'service', 'article'

class ChatResponse(BaseModel):
    answer: str
    resources: List[ResourceLink] = []
    confidence: float = 1.0
