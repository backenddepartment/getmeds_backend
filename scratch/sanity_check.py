import asyncio
from app.services import sanity_service

async def main():
    try:
        docs = await sanity_service.query_sanity('*[_type == "googleSpreadsheet"]{ title, _id, id, spreadsheetId, link }')
        print("GOOGLE SPREADSHEETS FOUND IN SANITY:")
        for doc in docs:
            print(f"Title: {doc.get('title')}")
            print(f"  ID: {doc.get('_id')}")
            print(f"  Slug ID: {doc.get('id')}")
            print(f"  SpreadsheetID: {doc.get('spreadsheetId')}")
            print(f"  Link: {doc.get('link')}")
            print("-" * 40)
            
        routing = await sanity_service.query_sanity('*[_type == "inquiryRouting"]{ inquiryType, recipients, "spreadsheet": spreadsheet->title }')
        print("\nINQUIRY ROUTING RULES:")
        for r in routing:
            print(f"Type: {r.get('inquiryType')}")
            print(f"  Recipients: {r.get('recipients')}")
            print(f"  Spreadsheet Title: {r.get('spreadsheet')}")
            print("-" * 40)
            
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
