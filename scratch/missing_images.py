import asyncio
from app.services import sanity_service

async def main():
    try:
        query = '*[_type == "product" && !defined(image)]{ name, brandName, genericName }'
        products = await sanity_service.query_sanity(query)
        print(f"FOUND {len(products)} PRODUCTS WITH MISSING IMAGE:")
        print("=" * 80)
        for idx, p in enumerate(products, 1):
            name = p.get("name") or "N/A"
            brand = p.get("brandName") or "N/A"
            generic = p.get("genericName") or "N/A"
            print(f"{idx}. Name: {name}")
            print(f"   Brand Name: {brand}")
            print(f"   Generic Name: {generic}")
            print("-" * 50)
            
    except Exception as e:
        print("Error querying Sanity:", e)

if __name__ == "__main__":
    asyncio.run(main())
