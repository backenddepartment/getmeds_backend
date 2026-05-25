# Quick Start Guide - GetMEDS Chatbot API

## 5-Minute Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env and add your Sanity credentials
```

### 3. Run the Server
```bash
uvicorn main:app --reload
```

**Success!** Your API is running at `http://localhost:8000`

## Test the API

### Using cURL
```bash
curl -X POST "http://localhost:8000/api/chatbot/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Do you have aspirin?",
    "session_id": "test-user-1"
  }'
```

### Using Python
```python
import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/chatbot/ask",
            json={
                "message": "Do you have aspirin?",
                "session_id": "test-user-1"
            }
        )
        print(response.json())

asyncio.run(test())
```

### Using JavaScript/Fetch
```javascript
fetch('http://localhost:8000/api/chatbot/ask', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    message: 'Do you have aspirin?',
    session_id: 'test-user-1'
  })
})
.then(res => res.json())
.then(data => console.log(data))
```

## Interactive Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Deployment Options

### Vercel (Recommended for Serverless)
```bash
vercel deploy
```

### Docker
```bash
docker build -t chatbot-api .
docker run -p 8000:8000 --env-file .env chatbot-api
```

### Traditional Server
```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
```

### Railway.app
```bash
railway link
railway up
```

## Environment Variables

Required:
- `SANITY_PROJECT_ID` - Your Sanity project ID
- `SANITY_TOKEN` - Your Sanity API token

Optional:
- `DEBUG=True` - Enable debug mode
- `PORT=8000` - Server port
- `CHAT_HISTORY_LIMIT=30` - Message limit per session

## Common Issues

### "No Sanity token found"
Make sure `.env` file exists and has `SANITY_TOKEN` set:
```bash
echo "SANITY_TOKEN=your_token_here" >> .env
```

### Port 8000 already in use
Use a different port:
```bash
uvicorn main:app --port 8001
```

### Connection timeout to Sanity
Check your network and Sanity token validity

## Next Steps

1. ✅ Read `README.md` for detailed documentation
2. ✅ Check `STRUCTURE.md` to understand what's included
3. ✅ Review API endpoints in Swagger UI at `/docs`
4. ✅ Integrate into your frontend application

## Support

Refer to the main README for comprehensive documentation.
