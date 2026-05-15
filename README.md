# GetMEDS Chatbot Backend

A clean, scalable FastAPI backend for a website customer support chatbot that uses **Sanity CMS** as the primary content database.

## Features
- **Sanity-Powered**: Answers are retrieved directly from your Sanity Studio data.
- **Hallucination-Free**: Only returns information found in your database.
- **Scalable Structure**: Follows DRY principles with separated routes, services, and schemas.
- **FastAPI**: High performance, auto-generated documentation (`/docs`), and validation.

## Project Structure
```text
getmeds_backend/
├── app/
│   ├── api/
│   │   └── routes/
│   │       └── chatbot.py    # API Endpoints
│   ├── core/
│   │   └── config.py         # App Settings (Pydantic)
│   ├── schemas/
│   │   └── chatbot.py        # Request/Response validation
│   ├── services/
│   │   ├── sanity_service.py # Sanity GROQ communication
│   │   └── chatbot_service.py # Business Logic
│   └── main.py               # App Entry point
├── .env                      # Environment Variables
├── requirements.txt          # Dependencies
└── README.md
```

## Setup Instructions

### 1. Prerequisites
- Python 3.9+
- A Sanity Project ID and Token (optional for public datasets)

### 2. Local Development Setup
1. **Navigate to the directory**:
   ```bash
   cd getmeds_backend
   ```
2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   venv\Scripts\activate  # On Windows
   source venv/bin/activate  # On Unix/macOS
   ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Configure Environment**:
   Update the `.env` file with your Sanity Project ID:
   ```env
   SANITY_PROJECT_ID=s7ocz8zp
   SANITY_DATASET=production
   ```

### 3. Run the Server
```bash
python -m app.main
```
The API will be available at `http://localhost:8000`.
Check the docs at `http://localhost:8000/docs`.

## Example Usage

### Request
**POST** `http://localhost:8000/api/chatbot/ask`
```json
{
  "message": "What services do you offer?"
}
```

### Response
```json
{
  "answer": "I found 2 relevant items for you:\n- Medicine Delivery (service)\n- Online Consultation (service)\n\nYou can click the links below for more details.",
  "resources": [
    {
      "title": "Medicine Delivery",
      "url": "/services/medicine-delivery",
      "type": "service"
    },
    {
      "title": "Online Consultation",
      "url": "/services/online-consultation",
      "type": "service"
    }
  ],
  "confidence": 1.0
}
```

## Future Enhancements
- **Semantic Search**: Integrate Vector databases or OpenAI embeddings for better intent matching.
- **FAQ Schema**: Add a specific `faq` or `article` schema to Sanity for specialized support content.
- **Rate Limiting**: Add middleware to protect the API.
