import asyncio
from app.services import sanity_service

async def main():
    try:
        settings_query = '*[_type == "siteSettings"][0].contactInfo.emails[]{ value, scope }'
        emails_config = await sanity_service.query_sanity(settings_query)
        print("EMAILS CONFIG:")
        import pprint
        pprint.pprint(emails_config)
            
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
