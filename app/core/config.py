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
    GOOGLE_CLIENT_EMAIL: str = "getmeds-inquiry-services@getmedsadmin.iam.gserviceaccount.com"
    GOOGLE_PRIVATE_KEY: str = "-----BEGIN PRIVATE KEY-----\\nMIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQDPaE3Wl/Mr7Bd/\\ntY+vsau6jiPi+YxF84KReOR2LBaTlLNAHKjVcPZ3poOlC03Opawu+3UXfbzdDrXt\\nmDvad/gYAD/N09wAOqHiDPJHTT+R2AsbgSm73d5TVm2mGuFotAI58EHX0f6uGxhB\\ndQkxCaTSTieq9ZA3Ix0CwlnTBhaUFpBwQC3nKylmJ/wD8NFAdWGoPrsQLgtOe0R/\\n5qZ9yCWvHAZIxm0FW49/QpdqYs+8QOlXcfNPxYBVMTM9ugcqBAz0+BtM+WjCZ61f\\nEoGJA+GI4c7Wys4R1nxraBMUbKZNjhUpNIVYjj0Fx80P6rexJyYi9b1eRDk2vwAl\\nELQXs3JFAgMBAAECggEAHFKkioDugpl3bgenqvjquAuQB/9G8gh6VI47OI31uUqN\\nndwsDBWkepthD8k241jJZhMNntsbTt6i5mKrDb7jQLfL/roHKXrYP2vALA929l4X\\nyjY9sjtukFfVmmDCVk96nFncS/IPwsvNaKboTeuAt/1XOmfVPUpMvGM46/HBZJBf\\nLQffcAcewW2QtNkavWhTBboVyPAj4vd2bnjGsu9RXkosNZCkYQT9qRAtloa4lYru\\nNr2BZW5FIk96VeSygHBddp9rkEXShqImZJr0rmZbkCFe+fKY7Tq0dYzOSin4gVf2\\nnO+eXEiy9V5yFe6jo4IGmEExxU9C/3ZbcIBUFoY+UQKBgQD20py8NMWUWAw+xixD\\nh1JMM/9tttikJtdogF6M3qlrqY5kiokwxGZTBA20SxgQ39+nEpz6d+Gsv3No9fEd\\nI0zUjrmV2Ru+2vGYX8byeZ6KmCFGLosFUmc2sTaOH82WtmHRIOGWmC9PPZ1clrc/\\n4JQPnDpdsml31FfgvXk1oUJbyQKBgQDXHoREANgfZs2Z2Fq2eHlFxDHt0nL4n0yE\\nXmiHllZ7uzjcbwWkq+a6eGEbKvQ2YQycBr0VP/bcepA/NPKQ46oFnJUpDZeWWpr+\\n9tFvpEiUEc6XEKQMUVDuckI6rwSeMQaJfPuM4eTkp6xdRMpUGOXA3FpCWeLXgP/9\\nhrEma7vonQKBgCUIWp3eaRqlz0iH4VJMdmuajaN/gKe4cC9su0L1kYPmz8eEBat8\\nfEHOZOP9NGIrxNnDcCwgWorZus4vwHp3tmpZ87xo88HCBeevzyDIYKI4yx1FlHQ6\\n9eN92UqfuO/481o2TcKTmN2RyA+BSYNbBbwF27f9MdfZ00mUBCCozlUJAoGAMXjz\\nMjB/g7lAz4DSW+SY/1J/qRIdHtCD6G1N3ODWQt5r1UYzJgvipD/LFVRrlZX8MGXc\\nVma/fzUwt1iV8HxrPZ8lLqvRkOKFgt2AjQxbJLJzsIpDMBIDatMcKCLYDQl5V2VG\\n9L9+xJdLLKgFYBHZxODoYRoK8UTZmpS/aPad4IECgYAv1wS6ruefsLJlIV77vf2E\\nGLmno7xhSxJ1TEPA1F1lJIGIXIE6txYufdZKee4bxJ5nR52jBDGxyQaJTNW4uJer\\ny3cICwvd+68XC7JwD2nsQgX1/LBz4Iyojv05efZsz+imK8+fHnmZBirWTU2uUSfx\\nb+bv+Qso4XkoDfU+QluUpQ==\\n-----END PRIVATE KEY-----\\n"

    # Anthropic Configuration
    ANTHROPIC_API_KEY: str = ""

    # Groq Configuration — fallback/trained-assistant AI responder
    GROQ_API_KEY: str = ""

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