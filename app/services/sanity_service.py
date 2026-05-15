import httpx
from app.core.config import get_settings

settings = get_settings()

class SanityService:
    def __init__(self):
        self.base_url = f"https://{settings.SANITY_PROJECT_ID}.api.sanity.io/v{settings.SANITY_API_VERSION}/data/query/{settings.SANITY_DATASET}"
        self.headers = {}
        if settings.SANITY_TOKEN:
            self.headers["Authorization"] = f"Bearer {settings.SANITY_TOKEN}"
            print(f"DEBUG: Sanity token loaded (starts with {settings.SANITY_TOKEN[:5]}...)")
        else:
            print("WARNING: No Sanity token found in environment!")


    async def query_sanity(self, groq_query: str, params: dict = None):
        """
        Executes a GROQ query against the Sanity API.
        """
        import json
        params_with_quotes = {k: json.dumps(v) for k, v in (params or {}).items()}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.base_url,
                params={"query": groq_query, **params_with_quotes},
                headers=self.headers
            )

            if response.status_code != 200:
                print(f"ERROR: Sanity API returned {response.status_code}")
                print(f"Response body: {response.text}")
                response.raise_for_status()
            
            data = response.json()
            return data.get("result", [])


    async def search_content(self, query_text: str):
        """
        Searches across products, services, and team members for a given text.
        This is a basic keyword search using GROQ's match operator.
        """
        # Search query for multiple document types
        groq_query = """
        *[
          (_type == "product" && (name match $search || description match $search)) ||
          (_type == "service" && (title match $search || description match $search)) ||
          (_type == "team" && (name match $search || bio match $search))
        ] {
          _type,
          "title": coalesce(name, title),
          "description": coalesce(description, bio),
          "slug": slug.current,
          "link": coalesce(link, "/products/" + slug.current, "/team")
        }
        """
        params = {"$search": f"*{query_text}*"}
        return await self.query_sanity(groq_query, params)


sanity_service = SanityService()
