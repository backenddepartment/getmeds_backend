import asyncio
import httpx

async def main():
    payload = {
        "inquiryType": "Contact Us",
        "fullName": "Test User",
        "email": "testuser@example.com",
        "phone": "+1234567890",
        "subject": "General Inquiry Test",
        "message": "This is a test submission to check dynamic default email routing.",
        "additionalData": {},
        "files": []
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post("http://127.0.0.1:8001/api/inquiry/submit", json=payload, timeout=30.0)
            print("STATUS CODE:", response.status_code)
            print("RESPONSE:")
            import pprint
            pprint.pprint(response.json())
        except Exception as e:
            print("Error contacting local server:", e)

if __name__ == "__main__":
    asyncio.run(main())
