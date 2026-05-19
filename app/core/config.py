# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Sanity Configuration
    SANITY_PROJECT_ID: str = "s7ocz8zp"
    SANITY_DATASET: str = "production"
    SANITY_API_VERSION: str = "2023-05-03"
    SANITY_TOKEN: str = "skCgFfGBsFDPop8HAzyvtZQ62TnHAwQdFGzZoQAFH8b9Upzcvu8jIBXQ9euuMZpIgG7G5Lhpn5T7q4MNSpCZokjnFod76UFIsQbnyy3PzorlTW9bVth6DmKn0xTVKHVFhgLOoSZ3mTwlZeLXR3yOYc4MrZQlrSs3SkLPe7ULcf1QcKUhq0OS"

    # App Configuration
    APP_NAME: str = "GetMEDS Chatbot API"
    DEBUG: bool = False
    PORT: int = 8000
    CHAT_HISTORY_LIMIT: int = 30
    ADMIN_TOKEN: str = "getmeds-admin-secret-key"

    # Security Database Configuration
    SANITY_SECURITY_PROJECT_ID: str = "s7ocz8zp"
    SANITY_SECURITY_DATASET: str = "security"

    # Centralized Postgres Database Connection (Supabase)
    DATABASE_URL: str = "postgresql://postgres.odnqyiilnxvlwfiexfgw:gAwmOpE92ve2qrTu@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
