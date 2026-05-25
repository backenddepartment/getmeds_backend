# GetMEDS Chatbot API - Structure & Changes

## What Was Removed ❌

The following components from the original backend have been removed to create a dedicated chatbot API:

### Admin Routes & Services
- `app/api/routes/admin.py` - Admin dashboard endpoints
- `app/schemas/admin.py` - Admin-related data models
- `app/services/security_service.py` - Security & authentication utilities

### Page Management
- `app/api/routes/pages.py` - CMS page management routes

### Web Templates
- `app/templates/` - All HTML templates for the admin dashboard
  - `login.html`
  - `admin.html`
  - `document_detail.html`
  - `create_document.html`
  - `access_security.html`
  - `components/` - All component templates

### Configuration Files
- `AI_PLANNING_AND_EXECUTION.md` - Project planning document

## What Was Kept ✅

### Core Chatbot Functionality
- `app/api/routes/chatbot.py` - Chatbot API endpoints
- `app/schemas/chatbot.py` - Chat request/response models
- `app/services/chatbot_service.py` - Chatbot logic engine
- `app/services/sanity_service.py` - Sanity CMS integration

### Configuration & Setup
- `app/core/config.py` - Application settings
- `main.py` - FastAPI application entry point
- `requirements.txt` - Python dependencies (minimal)
- `.env.example` - Environment variables template
- `vercel.json` - Vercel deployment configuration

### Documentation
- `README.md` - Comprehensive API documentation
- `STRUCTURE.md` - This file

## API Endpoints

The chatbot API provides the following endpoints:

### Chatbot Routes (`/api/chatbot`)
- `POST /api/chatbot/ask` - Send a message and get a response
- `GET /api/chatbot/status` - Check chatbot service status

### Health Checks
- `GET /` - Welcome message
- `GET /health` - API health status

## Technology Stack

- **Framework**: FastAPI (async web framework)
- **Server**: Uvicorn (ASGI server)
- **Validation**: Pydantic (data validation)
- **HTTP Client**: httpx (async HTTP requests)
- **Content Backend**: Sanity CMS (via API)

## File Structure

```
chatbot-api/
├── app/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── chatbot.py          [KEPT] Chatbot endpoints
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py               [KEPT] Configuration
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── chatbot.py              [KEPT] Data models
│   └── services/
│       ├── __init__.py
│       ├── chatbot_service.py       [KEPT] Chat logic
│       └── sanity_service.py        [KEPT] CMS integration
├── main.py                          [KEPT] App entry point
├── requirements.txt                 [KEPT] Dependencies
├── .env.example                     [KEPT] Config template
├── .gitignore                       [NEW] Git ignore rules
├── vercel.json                      [KEPT] Vercel config
├── README.md                        [NEW] Documentation
└── STRUCTURE.md                     [NEW] This file
```

## Key Features Retained

1. **Hyper-Contextual Intelligence**
   - Smart intent detection
   - Session-based context management
   - Conversation history with auto-compression

2. **Content Search**
   - Cross-database search (products, services, team, FAQs)
   - Intelligent ranking and filtering
   - Fallback search strategies

3. **User Management**
   - Session tracking
   - User name recognition
   - Conversation state persistence

4. **Safety Features**
   - Medical query disclaimers
   - Pronoun resolution (it, this, that)
   - Confirmation-based order handling

## Setup Instructions

See `README.md` for complete setup and deployment instructions.

## Migration Notes

If you were using the full backend:

1. **Admin functionality** is no longer available - use Sanity Studio for content management
2. **Page management** is removed - manage pages in Sanity CMS
3. **Security features** are simplified - implement your own authentication in production
4. **Web interface** is removed - build your frontend separately or use the API directly

This focused API is ideal for:
- Integrating chatbot functionality into existing applications
- Deploying as a microservice
- Scaling independently from other backend services
- Building custom frontends

## Dependencies Reduction

**Original**: 20+ dependencies
**Now**: 6 core dependencies
- fastapi
- uvicorn
- pydantic
- pydantic-settings
- httpx
- python-dotenv

This significant reduction in dependencies means:
- Faster installation
- Smaller deployment size
- Fewer security vulnerabilities to manage
- Easier maintenance
