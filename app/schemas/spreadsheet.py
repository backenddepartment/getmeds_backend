from pydantic import BaseModel
from typing import List, Optional

class FilePayload(BaseModel):
    name: str
    type: str
    base64: str

class AppendSpreadsheetRequest(BaseModel):
    spreadsheetId: str
    row: List[str]
    files: Optional[List[FilePayload]] = []

class CreateSpreadsheetRequest(BaseModel):
    title: str
    headers: List[str]
