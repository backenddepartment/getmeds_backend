# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import chatbot
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    description="A chatbot backend that queries Sanity CMS for reliable information.",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    from app.services.sanity_service import sanity_service
    print("Running session cleanup...")
    deleted_count = await sanity_service.cleanup_old_sessions()
    print(f"Cleanup complete. Deleted {deleted_count} old sessions.")


# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chatbot.router, prefix="/api/chatbot", tags=["Chatbot"])

@app.get("/")
async def root():
    return {
        "message": "Welcome to the GetMEDS Chatbot API",
        "docs": "/docs"
    }

if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)
