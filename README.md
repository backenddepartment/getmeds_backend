# GetMEDS Chatbot API

A hyper-contextual AI sales assistant API built with FastAPI that eliminates hallucinations by strictly locking context on user intents. This is a stripped-down version containing only the chatbot API endpoints.

## Features

- 🤖 **Hyper-Contextual Responses**: Smart intent detection with session-based context management
- 🔍 **Smart Search**: Searches across products, services, FAQs, and team members
- 💾 **Session Management**: Tracks conversation history and user information
- 🎯 **Intent Routing**: Handles confirmations, memory checks, identity verification, and recommendations
- 📝 **Medical Safety Warnings**: Includes appropriate disclaimers for medical queries
- 🔌 **Sanity CMS Integration**: Powered by Sanity.io as the content backend

## Installation

### Prerequisites
- Python 3.9+
- pip or uv package manager

### Setup

1. Clone the repository and navigate to the project directory:
```bash
cd chatbot-api
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
```

Edit `.env` and add your Sanity credentials:
```env
SANITY_PROJECT_ID=your_project_id
SANITY_DATASET=production
SANITY_TOKEN=your_sanity_token
```

## Running the API

### Development
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Production
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

The API will be available at `http://localhost:8000`

## API Endpoints

### POST `/api/chatbot/ask`
Send a message to the chatbot and receive a contextual response.

**Request:**
```json
{
  "message": "Do you have pain relief medicine?",
  "session_id": "user-123"  // Optional
}
```

**Response:**
```json
{
  "answer": "I found **Aspirin**. Would you like to proceed with the order?",
  "resources": [
    {
      "title": "Aspirin",
      "url": "/products/aspirin",
      "type": "product"
    }
  ],
  "confidence": 1.0
}
```

### GET `/api/chatbot/status`
Health check endpoint for the chatbot service.

**Response:**
```json
{
  "status": "online",
  "service": "GetMEDS Chatbot API"
}
```

### GET `/health`
General health check for the API.

**Response:**
```json
{
  "status": "healthy",
  "service": "GetMEDS Chatbot"
}
```

## Architecture

```
chatbot-api/
├── app/
│   ├── api/
│   │   └── routes/
│   │       └── chatbot.py          # Chatbot API endpoints
│   ├── core/
│   │   └── config.py               # Configuration and settings
│   ├── schemas/
│   │   └── chatbot.py              # Pydantic models
│   └── services/
│       ├── chatbot_service.py       # Chatbot logic and intent routing
│       └── sanity_service.py        # Sanity CMS integration
├── main.py                          # FastAPI application entry point
├── requirements.txt                 # Python dependencies
├── .env.example                     # Environment variables template
└── README.md                        # This file
```

## Intent Detection

The chatbot automatically detects various user intents:

- **Confirmation**: "yes", "sure", "proceed", "like the", "order it"
- **Memory Check**: "remember", "recap", "summarize"
- **Identity Check**: "who am i", "my name", "what is my name"
- **Alternative Request**: "another", "other", "different variation"
- **Recommendation**: "suggest", "recommend", "show me", "list"

## Session Management

Each conversation is tracked with a unique `session_id`. The service maintains:
- User name (if provided)
- Last discussed subject (for context)
- Message history (with automatic compression after 30 messages)
- Session summary for long conversations

## Database Integration

The chatbot uses Sanity CMS as the content backend with support for:
- **Products**: Medicine and healthcare products
- **Services**: GetMEDS services and offerings
- **Team Members**: Staff directory with roles
- **FAQs**: Frequently asked questions

## Configuration

Edit `app/core/config.py` to customize:
- Sanity API settings
- CORS allowed origins
- Chat history limits
- Application name and debug mode

## API Documentation

Once the server is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Error Handling

The API returns appropriate HTTP status codes:
- `200 OK`: Successful request
- `400 Bad Request`: Invalid input
- `500 Internal Server Error`: Server-side error with detailed message

## CORS Configuration

By default, CORS is enabled for:
- `http://localhost:3000`
- `http://localhost:8000`
- `https://getmeds.app`
- All origins (`*`)

Modify `allowed_origins` in `app/core/config.py` to restrict as needed.

## Performance Considerations

- Async/await for non-blocking I/O
- Connection pooling for Sanity API
- Session message compression after 30 messages
- Automatic cleanup of sessions older than 30 days

## Security Notes

⚠️ **Important**: 
- Never commit your `.env` file with real Sanity tokens
- Use environment variables for sensitive configuration in production
- Implement proper authentication for production deployments
- Validate all user input before processing

## Support

For issues or questions, please refer to the main GetMEDS documentation or contact the development team.

## License

This project is part of the GetMEDS platform.
