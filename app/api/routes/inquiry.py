import base64
import httpx
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException

from app.schemas.inquiry import InquirySubmitRequest
from app.core.config import settings
from app.services import sanity_service
from app.services.email_service import email_service
from app.api.routes.spreadsheet import clean_spreadsheet_id, get_google_services

router = APIRouter()

async def upload_file_to_sanity(file_name: str, file_type: str, file_base64: str) -> Optional[str]:
    """Helper to upload a base64 encoded file to Sanity CMS assets."""
    try:
        file_bytes = base64.b64decode(file_base64)
        is_image = file_type.startswith("image/") if file_type else file_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
        asset_type = "images" if is_image else "files"
        
        upload_url = f"https://{settings.SANITY_PROJECT_ID}.api.sanity.io/v1/assets/{asset_type}/{settings.SANITY_DATASET}"
        headers = {
            "Authorization": f"Bearer {settings.SANITY_TOKEN}",
            "Content-Type": file_type or ("image/jpeg" if is_image else "application/pdf")
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(upload_url, headers=headers, content=file_bytes)
            if response.status_code in [200, 201]:
                data = response.json()
                url = data.get("url") or data.get("document", {}).get("url")
                return url
            else:
                print(f"Sanity asset upload error: {response.text}")
    except Exception as upload_err:
        print(f"Failed to upload file '{file_name}' to Sanity: {str(upload_err)}")
    return None

@router.post("/inquiry/submit")
async def submit_inquiry(request: InquirySubmitRequest):
    """
    Unified endpoint to submit website inquiries. 
    1. Uploads files to Sanity CMS.
    2. Queries Sanity to determine recipient emails and Google Spreadsheet.
    3. Saves data to the designated Google Spreadsheet.
    4. Emails info@getmeds.ph and other configured recipients.
    """
    try:
        # 1. Upload files to Sanity CMS (if any are present)
        file_links = []
        if request.files:
            for file in request.files:
                if not file.name or not file.base64:
                    continue
                url = await upload_file_to_sanity(file.name, file.type, file.base64)
                if url:
                    file_links.append(url)

        # 2. Query Sanity for Routing Rules
        recipients = []
        spreadsheet_id = None
        
        try:
            groq_query = '*[_type == "inquiryRouting" && inquiryType == $inquiryType][0]{ recipients, "spreadsheetId": spreadsheet->spreadsheetId }'
            routing_rule = await sanity_service.query_sanity(groq_query, {"inquiryType": request.inquiryType})
            if routing_rule:
                recipients = routing_rule.get("recipients") or []
                spreadsheet_id = routing_rule.get("spreadsheetId")
        except Exception as query_err:
            print(f"WARNING: Failed to query Sanity for inquiry routing rule: {query_err}")

        # 3. Store in Designated Google Spreadsheet (if configured)
        sheets_appended = False
        if spreadsheet_id:
            try:
                sheets, _ = get_google_services()
                clean_id = clean_spreadsheet_id(spreadsheet_id)
                
                # Check spreadsheet content
                try:
                    content = sheets.spreadsheets().values().get(
                        spreadsheetId=clean_id,
                        range='Sheet1!A:Z'
                    ).execute()
                    values = content.get('values', [])
                except Exception as get_err:
                    print(f"WARNING: Could not fetch spreadsheet content: {get_err}")
                    values = []

                timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Setup Row mapping
                row = []
                inquiry_type = request.inquiryType
                if inquiry_type == "Career Inquiry":
                    row = [
                        timestamp_str,
                        request.fullName,
                        request.email,
                        request.additionalData.get("position", "") or request.subject,
                        request.message,
                        ", ".join(file_links)
                    ]
                elif inquiry_type == "Contact Us":
                    row = [
                        timestamp_str,
                        request.fullName,
                        request.email,
                        request.phone,
                        request.subject or request.additionalData.get("subject", ""),
                        request.message,
                        ", ".join(file_links)
                    ]
                elif inquiry_type == "Product Inquiry":
                    row = [
                        timestamp_str,
                        request.additionalData.get("productName", ""),
                        request.fullName,
                        request.phone,
                        request.email,
                        request.message,
                        ", ".join(file_links)
                    ]
                elif inquiry_type == "Order Medicine":
                    row = [
                        timestamp_str,
                        request.fullName,
                        request.email,
                        request.phone,
                        request.additionalData.get("dob", ""),
                        request.additionalData.get("address", ""),
                        ", ".join(file_links)
                    ]
                elif inquiry_type == "Partnership":
                    row = [
                        timestamp_str,
                        request.fullName,
                        request.email,
                        request.phone,
                        request.subject or request.additionalData.get("subject", ""),
                        request.message,
                        ", ".join(file_links)
                    ]
                else:
                    row = [
                        timestamp_str,
                        request.fullName,
                        request.email,
                        request.phone,
                        request.message,
                        ", ".join(file_links)
                    ]

                # Update Headers if the Spreadsheet is Empty
                if not values:
                    headers = []
                    if inquiry_type == "Career Inquiry":
                        headers = ['Timestamp', 'Full Name', 'Email', 'Position', 'Message', 'Attachments']
                    elif inquiry_type == "Contact Us":
                        headers = ['Timestamp', 'Full Name', 'Email', 'Phone', 'Subject', 'Message', 'Attachments']
                    elif inquiry_type == "Product Inquiry":
                        headers = ['Timestamp', 'Product Name', 'Full Name', 'Phone', 'Email', 'Message', 'Attachments']
                    elif inquiry_type == "Order Medicine":
                        headers = ['Timestamp', 'Patient Full Name', 'Email', 'Phone', 'Date of Birth', 'Delivery Address', 'Attachments']
                    elif inquiry_type == "Partnership":
                        headers = ['Timestamp', 'Full Name', 'Email', 'Phone', 'Subject', 'Message', 'Attachments']
                    else:
                        headers = ['Timestamp', 'Full Name', 'Email', 'Phone', 'Message', 'Attachments']
                    
                    try:
                        sheets.spreadsheets().values().update(
                            spreadsheetId=clean_id,
                            range='Sheet1!A1',
                            valueInputOption='RAW',
                            body={'values': [headers]}
                        ).execute()
                    except Exception as update_err:
                        print(f"ERROR: Failed to update headers: {update_err}")

                # Append Row
                sheets.spreadsheets().values().append(
                    spreadsheetId=clean_id,
                    range='Sheet1!A:Z',
                    valueInputOption='RAW',
                    body={'values': [row]}
                ).execute()
                sheets_appended = True
                print(f"INFO: Appended inquiry to spreadsheet: {clean_id}")

            except Exception as sheet_err:
                print(f"ERROR: Google Spreadsheet appending failed: {sheet_err}")

        # 4. Dispatch email to info@getmeds.ph and configured rule recipients
        # Wrap raw files in format required by email service
        raw_files = []
        if request.files:
            for file in request.files:
                raw_files.append({
                    "name": file.name,
                    "type": file.type,
                    "base64": file.base64
                })

        email_sent = email_service.send_inquiry_email(
            inquiry_type=request.inquiryType,
            full_name=request.fullName,
            email=request.email,
            phone=request.phone,
            message=request.message,
            subject=request.subject,
            additional_data=request.additionalData,
            file_links=file_links,
            files=raw_files,
            recipient_emails=recipients
        )

        return {
            "success": True,
            "sheets_appended": sheets_appended,
            "email_sent": email_sent,
            "sanity_files": file_links
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
