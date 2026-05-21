# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
from typing import List, Optional

class FAQCreate(BaseModel):
    question: str = Field(..., description="The FAQ question")
    answer: str = Field(..., description="The answer to the question")
    keywords: Optional[List[str]] = Field([], description="Keywords that trigger this FAQ")
    relatedLinks: Optional[List[dict]] = Field([], description="List of related links containing title and url")

class ProductCreate(BaseModel):
    name: str = Field(..., description="Product name")
    price: float = Field(..., description="Product price in PHP")
    availability: Optional[bool] = Field(True, description="Is in stock?")
    description: Optional[str] = Field("", description="Detailed product description")
    strength: Optional[str] = Field("", description="e.g. 100 MG / 16.7 ML")
    packaging: Optional[str] = Field("", description="e.g. Injection, Box")
