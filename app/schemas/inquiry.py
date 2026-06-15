from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class FilePayload(BaseModel):
    name: str
    type: str
    base64: str

class InquirySubmitRequest(BaseModel):
    inquiryType: str  # Career Inquiry, Contact Us, Product Inquiry, Order Medicine, Partnership
    fullName: str
    email: str
    phone: Optional[str] = ""
    subject: Optional[str] = ""
    message: Optional[str] = ""
    additionalData: Optional[Dict[str, Any]] = {}
    files: Optional[List[FilePayload]] = []
