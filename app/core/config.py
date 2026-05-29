# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List

class Settings(BaseSettings):
    # Sanity Configuration
    SANITY_PROJECT_ID: str = "s7ocz8zp"
    SANITY_DATASET: str = "production"
    SANITY_API_VERSION: str = "2023-05-03"
    SANITY_TOKEN: str = "skCgFfGBsFDPop8HAzyvtZQ62TnHAwQdFGzZoQAFH8b9Upzcvu8jIBXQ9euuMZpIgG7G5Lhpn5T7q4MNSpCZokjnFod76UFIsQbnyy3PzorlTW9bVth6DmKn0xTVKHVFhgLOoSZ3mTwlZeLXR3yOYc4MrZQlrSs3SkLPe7ULcf1QcKUhq0OS"

    # Google Sheets Configuration
    GOOGLE_CLIENT_EMAIL: str = ""
    GOOGLE_PRIVATE_KEY: str = ""

    # Anthropic Configuration
    ANTHROPIC_API_KEY: str = ""

    # Chatbot Routing Configuration
    PRIMARY: str = "trained_assistant"
    SECONDARY: str = "anthropic_ai"

    # App Configuration
    APP_NAME: str = "GetMEDS Chatbot API"
    DEBUG: bool = False
    PORT: int = 8000
    CHAT_HISTORY_LIMIT: int = 30
    
    # CORS Configuration
    allowed_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "https://getmeds.app",
        "*"
    ]

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra fields from .env

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()