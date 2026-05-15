# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Sanity Configuration
    SANITY_PROJECT_ID: str
    SANITY_DATASET: str = "production"
    SANITY_API_VERSION: str = "2023-05-03"
    SANITY_TOKEN: str = ""

    # App Configuration
    APP_NAME: str = "GetMEDS Chatbot API"
    DEBUG: bool = False
    PORT: int = 8000
    CHAT_HISTORY_LIMIT: int = 30

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
