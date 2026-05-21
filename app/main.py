# pyrefly: ignore [missing-import]
from fastapi import FastAPI, HTTPException, Request
# pyrefly: ignore [missing-import]
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from fastapi.responses import HTMLResponse, RedirectResponse
# pyrefly: ignore [missing-import]
from fastapi.templating import Jinja2Templates
import os
from pathlib import Path
from app.api.routes import chatbot, admin, pages
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    description="A chatbot backend that queries Sanity CMS for reliable information.",
    version="1.0.0"
)

# Resolve absolute path to the templates directory relative to this file
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@app.on_event("startup")
async def startup_event():
    from app.services.sanity_service import sanity_service
    try:
        print("Running session cleanup...")
        deleted_count = await sanity_service.cleanup_old_sessions()
        print(f"Cleanup complete. Deleted {deleted_count} old sessions.")
    except Exception as e:
        print(f"WARNING: Startup cleanup skipped (non-fatal): {e}")


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
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(pages.router, prefix="/api/pages", tags=["Pages"])

from app.api.routes.admin import decode_access_token, decode_refresh_token

def check_authenticated(request: Request) -> bool:
    access_token = request.cookies.get("gmp_access_token")
    if access_token:
        try:
            if decode_access_token(access_token):
                return True
        except Exception:
            pass
            
    refresh_token = request.cookies.get("gmp_refresh_token")
    if refresh_token:
        try:
            if decode_refresh_token(refresh_token):
                return True
        except Exception:
            pass
            
    return False

@app.get("/admin/login", response_class=HTMLResponse)
async def serve_login(request: Request):
    if check_authenticated(request):
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )

@app.get("/admin", response_class=HTMLResponse)
async def serve_admin(request: Request):
    if not check_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={}
    )

@app.get("/admin/document/{doc_id}", response_class=HTMLResponse)
async def serve_document_detail(request: Request, doc_id: str):
    if not check_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="document_detail.html",
        context={
            "doc_id": doc_id,
            "sanity_project_id": settings.SANITY_PROJECT_ID,
            "sanity_dataset": settings.SANITY_DATASET,
        }
    )

@app.get("/admin/create/{collection}", response_class=HTMLResponse)
async def serve_create_document(request: Request, collection: str):
    if not check_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="create_document.html",
        context={
            "collection": collection,
            "sanity_project_id": settings.SANITY_PROJECT_ID,
            "sanity_dataset": settings.SANITY_DATASET,
        }
    )

@app.get("/")
async def root():
    return RedirectResponse(url="/admin", status_code=302)

if __name__ == "__main__":
    # pyrefly: ignore [missing-import]
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)