# pyrefly: ignore [missing-import]
import re
import base64
import httpx
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException, Query
# pyrefly: ignore [missing-import]
from google.oauth2 import service_account
# pyrefly: ignore [missing-import]
from googleapiclient.discovery import build

from app.schemas.spreadsheet import AppendSpreadsheetRequest, CreateSpreadsheetRequest
from app.core.config import settings

router = APIRouter()

def clean_spreadsheet_id(id_or_url: str) -> str:
    """Helper to extract spreadsheet ID if a full URL is passed."""
    if "docs.google.com" in id_or_url:
        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", id_or_url)
        return match.group(1) if match else id_or_url
    return id_or_url

def get_google_services():
    """Initializes Google Sheets and Drive client services using service account credentials."""
    if not settings.GOOGLE_CLIENT_EMAIL or not settings.GOOGLE_PRIVATE_KEY:
        raise HTTPException(
            status_code=500,
            detail="Google service account credentials (GOOGLE_CLIENT_EMAIL, GOOGLE_PRIVATE_KEY) are not configured."
        )
    
    try:
        # Standardize private key escapes from env file
        private_key = settings.GOOGLE_PRIVATE_KEY.replace('\\n', '\n')
        credentials = service_account.Credentials.from_service_account_info({
            "client_email": settings.GOOGLE_CLIENT_EMAIL,
            "private_key": private_key,
            "type": "service_account",
            "project_id": settings.GOOGLE_CLIENT_EMAIL.split("@")[-1].split(".")[0],
            "token_uri": "https://oauth2.googleapis.com/token"
        }, scopes=[
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ])
        
        sheets_service = build('sheets', 'v4', credentials=credentials)
        drive_service = build('drive', 'v3', credentials=credentials)
        return sheets_service, drive_service
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize Google API client services: {str(e)}"
        )

@router.post("/append-to-spreadsheet")
async def append_to_spreadsheet(request: AppendSpreadsheetRequest):
    """
    Appends a row to a Google Spreadsheet. If files are uploaded, 
    first uploads them to Sanity CMS and replaces the [PENDING_FILE_UPLOAD] tag with the URLs.
    """
    try:
        clean_id = clean_spreadsheet_id(request.spreadsheetId)
        
        # Upload base64 files to Sanity first if any are present
        file_links = []
        if request.files:
            for file in request.files:
                if not file.name or not file.base64:
                    continue
                try:
                    file_bytes = base64.b64decode(file.base64)
                    upload_url = f"https://{settings.SANITY_PROJECT_ID}.api.sanity.io/v1/assets/images/{settings.SANITY_DATASET}"
                    headers = {
                        "Authorization": f"Bearer {settings.SANITY_TOKEN}",
                        "Content-Type": file.type or "image/jpeg"
                    }
                    async with httpx.AsyncClient() as client:
                        response = await client.post(upload_url, headers=headers, content=file_bytes)
                        if response.status_code in [200, 201]:
                            data = response.json()
                            url = data.get("url") or data.get("document", {}).get("url")
                            if url:
                                file_links.append(url)
                        else:
                            print(f"Sanity asset upload error: {response.text}")
                except Exception as upload_err:
                    print(f"Failed to upload file '{file.name}' to Sanity: {str(upload_err)}")
        
        # Replace the placeholder in the row values with uploaded image URLs
        final_row = []
        for val in request.row:
            if val == "[PENDING_FILE_UPLOAD]":
                final_row.append(", ".join(file_links))
            else:
                final_row.append(val)
        
        # Append row to Google Sheets
        sheets, _ = get_google_services()
        sheets.spreadsheets().values().append(
            spreadsheetId=clean_id,
            range='Sheet1!A:Z',
            valueInputOption='RAW',
            body={'values': [final_row]}
        ).execute()
        
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create-spreadsheet")
async def create_spreadsheet(request: CreateSpreadsheetRequest):
    """
    Creates a new Google Spreadsheet, sets up custom headers, 
    and opens the spreadsheet to be publicly viewable by readers.
    """
    try:
        sheets, drive = get_google_services()
        
        # Create Google Spreadsheet
        spreadsheet_body = {
            'properties': {
                'title': request.title
            },
            'sheets': [
                {
                    'properties': {
                        'title': 'Sheet1'
                    }
                }
            ]
        }
        spreadsheet = sheets.spreadsheets().create(body=spreadsheet_body).execute()
        spreadsheet_id = spreadsheet.get('spreadsheetId')
        
        if not spreadsheet_id:
            raise HTTPException(status_code=500, detail="Failed to create Google Spreadsheet")
            
        # Ensure timestamp/date column is present
        headers = request.headers
        has_timestamp = any(h.lower() in ['timestamp', 'date'] for h in headers)
        final_headers = headers if has_timestamp else ['Timestamp'] + headers
        
        # Write headers to Sheet1!A1
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range='Sheet1!A1',
            valueInputOption='RAW',
            body={'values': [final_headers]}
        ).execute()
        
        # Share spreadsheet as public reader
        try:
            drive.permissions().create(
                fileId=spreadsheet_id,
                body={
                    'role': 'reader',
                    'type': 'anyone'
                }
            ).execute()
        except Exception as drive_err:
            print(f"Warning: Failed to set public read permissions on Google Spreadsheet: {str(drive_err)}")
            
        return {
            "spreadsheetId": spreadsheet_id,
            "link": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get-spreadsheet-metadata")
async def get_spreadsheet_metadata(spreadsheetId: str = Query(..., description="ID or full link of the spreadsheet")):
    """Reads the metadata of a Google Spreadsheet to obtain its title."""
    try:
        sheets, _ = get_google_services()
        clean_id = clean_spreadsheet_id(spreadsheetId)
        
        response = sheets.spreadsheets().get(spreadsheetId=clean_id).execute()
        title = response.get('properties', {}).get('title', 'Untitled Spreadsheet')
        return {"title": title}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get-spreadsheet-content")
async def get_spreadsheet_content(spreadsheetId: str = Query(..., description="ID or full link of the spreadsheet")):
    """Retrieves all rows under Sheet1!A:Z of the Google Spreadsheet."""
    try:
        sheets, _ = get_google_services()
        clean_id = clean_spreadsheet_id(spreadsheetId)
        
        response = sheets.spreadsheets().values().get(
            spreadsheetId=clean_id,
            range='Sheet1!A:Z'
        ).execute()
        
        values = response.get('values', [])
        return {"values": values}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
