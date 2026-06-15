# Force IPv4 socket resolution globally to prevent Windows IPv6 httplib2 connection timeouts
import socket

orig_getaddrinfo = socket.getaddrinfo


def forced_getaddrinfo(*args, **kwargs):
    args = list(args)
    if len(args) > 2:
        args[2] = socket.AF_INET
    else:
        while len(args) < 2:
            args.append(None)
        args.append(socket.AF_INET)
    return orig_getaddrinfo(*args, **kwargs)


socket.getaddrinfo = forced_getaddrinfo

# pyrefly: ignore [missing-import]
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.chatbot import router as chatbot_router
from app.api.routes.spreadsheet import router as spreadsheet_router
from app.api.routes.inquiry import router as inquiry_router
from app.core.config import settings

# ── Skill File Loading ──────────────────────────────────────────────────────
# These files are loaded once at startup and shared by all AI responders
# (Anthropic Claude, Groq, trained assistant) as system prompt context.


def _load_skill(filename: str) -> str:
    """Load a skill .md file from app/skills/. Returns empty string if missing."""
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "app", "skills", filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            print(
                f"INFO: Loaded skill file: {filename} ({len(content)} chars)")
            return content
    except FileNotFoundError:
        print(
            f"WARNING: Skill file not found at {path} — AI responders will have no system prompt"
        )
        return ""


AI_SKILL = _load_skill("AI_SKILL_CHATBOT.md")
CUSTOMER_SERVICE_SKILL = _load_skill("CUSTOMER_SERVICE_SKILL_CHATBOT.md")

# Combined system prompt — injected into Claude/Groq when acting as responder
COMBINED_SYSTEM_PROMPT = (f"{AI_SKILL}\n\n---\n\n{CUSTOMER_SERVICE_SKILL}"
                          if AI_SKILL and CUSTOMER_SERVICE_SKILL else "")

# ── FastAPI App ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="Getmeds Chatbot API",
    description=
    "Getmeds AI Assist — Anthropic Claude primary, trained assistant fallback",
    version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chatbot_router, prefix="/api/chatbot", tags=["chatbot"])
app.include_router(spreadsheet_router, prefix="/api", tags=["spreadsheet"])
app.include_router(inquiry_router, prefix="/api", tags=["inquiry"])


@app.get("/")
async def root():
    return {
        "message": "Welcome to Getmeds Chatbot API",
        "version": "2.0.0",
        "primary": settings.PRIMARY,
        "secondary": settings.SECONDARY,
        "tertiary": settings.TERTIARY,
        "skills_loaded": bool(COMBINED_SYSTEM_PROMPT)
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Getmeds Chatbot",
        "mode":
        f"{settings.PRIMARY} / {settings.SECONDARY} / {settings.TERTIARY}"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
