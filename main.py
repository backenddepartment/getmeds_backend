# pyrefly: ignore [missing-import]
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.chatbot import router as chatbot_router
from app.core.config import settings

# ── Skill File Loading ──────────────────────────────────────────────────────
# These files are loaded once at startup and used when Anthropic Claude
# is called as the primary responder. The trained assistant does not use them.

def _load_skill(filename: str) -> str:
    """Load a skill .md file from app/skills/. Returns empty string if missing."""
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "app", "skills", filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            print(f"INFO: Loaded skill file: {filename} ({len(content)} chars)")
            return content
    except FileNotFoundError:
        print(f"WARNING: Skill file not found at {path} — Anthropic primary will have no system prompt")
        return ""

ANTHROPIC_SKILL = _load_skill("ANTHROPIC_SKILL_CHATBOT.md")
CUSTOMER_SERVICE_SKILL = _load_skill("CUSTOMER_SERVICE_SKILL_CHATBOT.md")

# Combined system prompt — injected into Claude when it acts as primary
COMBINED_SYSTEM_PROMPT = (
    f"{ANTHROPIC_SKILL}\n\n---\n\n{CUSTOMER_SERVICE_SKILL}"
    if ANTHROPIC_SKILL and CUSTOMER_SERVICE_SKILL
    else ""
)

# ── FastAPI App ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="GetMEDS Chatbot API",
    description="GetMEDS AI Assist — Anthropic Claude primary, trained assistant fallback",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chatbot_router, prefix="/api/chatbot", tags=["chatbot"])

@app.get("/")
async def root():
    return {
        "message": "Welcome to GetMEDS Chatbot API",
        "version": "2.0.0",
        "primary": "anthropic-claude" if settings.ANTHROPIC_API_KEY else "trained-assistant",
        "fallback": "trained-assistant" if settings.ANTHROPIC_API_KEY else "static-response",
        "skills_loaded": bool(COMBINED_SYSTEM_PROMPT)
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "GetMEDS Chatbot",
        "mode": "anthropic-primary / trained-fallback" if settings.ANTHROPIC_API_KEY else "trained-primary / static-fallback"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
