# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    # Sanity Configuration — non-secret defaults are fine to keep here (project ID
    # and dataset are already public via CDN image URLs); the token must only ever
    # come from .env (see .env.example) since it grants write access to the dataset.
    SANITY_PROJECT_ID: str = "s7ocz8zp"
    SANITY_DATASET: str = "production"
    SANITY_API_VERSION: str = "2023-05-03"
    SANITY_TOKEN: str = ""

    # Google Sheets Configuration — service account identity/key must come from .env only.
    GOOGLE_CLIENT_EMAIL: str = ""
    GOOGLE_PRIVATE_KEY: str = ""

    # Anthropic Configuration
    ANTHROPIC_API_KEY: str = ""

    # Groq Configuration — fallback/trained-assistant AI responder
    GROQ_API_KEY: str = ""

    # Chatbot Routing Configuration
    PRIMARY: str = "anthropic_ai"
    SECONDARY: str = "trained_assistant"
    TERTIARY: str = "groq_ai"

    # WordPress Configuration — Application Password used only for preview requests
    # (draft/private posts require authenticated `edit_posts` access to WP's REST API).
    # Generate under WP Admin -> Users -> Profile -> Application Passwords.
    WP_PREVIEW_USER: str = ""
    WP_PREVIEW_APP_PASSWORD: str = ""

    # SMTP Configuration
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "info@getmeds.ph"

    # App Configuration
    APP_NAME: str = "Getmeds Chatbot API"
    DEBUG: bool = False
    PORT: int = 8000
    CHAT_HISTORY_LIMIT: int = 30

    # Chatbot Data Policy
    # When enabled, the chatbot will ONLY use Sanity data to produce answers.
    # It will not rely on page_context or LLM "general knowledge" to fill gaps.
    CHATBOT_SANITY_ONLY: bool = True

    # CORS Configuration
    allowed_origins: List[str] = [
        "http://localhost:3000", "http://localhost:5173",
        "http://127.0.0.1:5173", "http://localhost:8000",
        "https://getmeds.app", "*"
    ]

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra fields from .env


@lru_cache()
def get_settings():
    return Settings()


settings = get_settings()
