import base64
import httpx
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException

from app.schemas.inquiry import InquirySubmitRequest
from app.core.config import settings
from app.services.sanity_service import sanity_service
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
            routing_rule = await sanity_service.query_sanity(groq_query, {"$inquiryType": request.inquiryType})
            if routing_rule:
                recipients = routing_rule.get("recipients") or []
                spreadsheet_id = routing_rule.get("spreadsheetId")
        except Exception as query_err:
            print(f"WARNING: Failed to query Sanity for inquiry routing rule: {query_err}")

        # Fallback to query googleSpreadsheet document directly if no routing rule exists
        if not spreadsheet_id:
            slug_map = {
                "Career Inquiry": "careers-inquiry-list",
                "Contact Us": "contact-us-list",
                "Product Inquiry": "product-inquiry-list",
                "Order Medicine": "order-medicine-list",
                "Partnership": "partnership-list"
            }
            slug = slug_map.get(request.inquiryType)
            if slug:
                try:
                    sheet_query = '*[_type == "googleSpreadsheet" && id.current == $slug][0]{ spreadsheetId }'
                    sheet_doc = await sanity_service.query_sanity(sheet_query, {"$slug": slug})
                    if sheet_doc:
                        spreadsheet_id = sheet_doc.get("spreadsheetId")
                        print(f"INFO: Resolved fallback spreadsheet for '{request.inquiryType}' matching slug '{slug}': {spreadsheet_id}")
                except Exception as fallback_err:
                    print(f"WARNING: Failed to query fallback googleSpreadsheet by slug: {fallback_err}")

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
                    # Column order matches the sheet's existing header row:
                    # Full Name, Email, Mobile, Position, Cover Letter, Resume Link, Timestamp
                    row = [
                        request.fullName,
                        request.email,
                        request.phone,
                        request.additionalData.get("position", "") or request.subject,
                        request.message,
                        ", ".join(file_links),
                        timestamp_str
                    ]
                elif inquiry_type == "Contact Us":
                    # Column order matches the sheet's header hierarchy:
                    # Full Name, Email Address, Phone Number, Subject, Message, Timestamp
                    # (this form never collects attachments, so there's no attachments column)
                    # NOTE: as of this change the live sheet's columns still need to be manually
                    # reordered to match (previously Timestamp was column A) — existing rows must
                    # have their cells physically moved, not just the header labels, or historical
                    # data will be mislabeled. See conversation for the exact column mapping.
                    row = [
                        request.fullName,
                        request.email,
                        request.phone,
                        request.subject or request.additionalData.get("subject", ""),
                        request.message,
                        timestamp_str
                    ]
                elif inquiry_type == "Product Inquiry":
                    # Column order matches the sheet's existing header row:
                    # Full Name, Phone, Email, Message, Product, Message (dupe — unused, see note below),
                    # Prescription Link, Timestamp
                    # The sheet has a duplicate "Message" header (columns D and F) with nothing in the
                    # form mapping to a second message-like field, so column F is left blank rather than
                    # guessing — worth fixing the header row directly in the sheet if it's a mistake.
                    row = [
                        request.fullName,
                        request.phone,
                        request.email,
                        request.message,
                        request.additionalData.get("productName", ""),
                        "",
                        ", ".join(file_links),
                        timestamp_str
                    ]
                elif inquiry_type == "Order Medicine":
                    # Column order matches the sheet's header hierarchy:
                    # Full Name, Email Address, Phone Number, Age, Delivery Address,
                    # Prescription Link, Credentials Confirmation, Timestamp
                    # The frontend blocks submission unless the "information is authentic"
                    # checkbox is checked and doesn't send it as a field, so "Confirmed" is
                    # always correct here (same pattern as Partnership's consent column).
                    row = [
                        request.fullName,
                        request.email,
                        request.phone,
                        request.additionalData.get("age", ""),
                        request.additionalData.get("address", ""),
                        ", ".join(file_links),
                        "Confirmed",
                        timestamp_str
                    ]
                elif inquiry_type == "Partnership":
                    # Column order matches the sheet's existing header row:
                    # Name, Company/Organization, Email, Mobile Number, Inquiry, Data Privacy Agreement, Timestamp
                    # The frontend blocks submission unless the consent checkbox is checked and doesn't
                    # send it as a field, so "Agreed" is always correct here.
                    row = [
                        request.fullName,
                        request.subject or request.additionalData.get("company", ""),
                        request.email,
                        request.phone,
                        request.message,
                        "Agreed",
                        timestamp_str
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
                        headers = ['Full Name', 'Email Address', 'Mobile Number', 'Position', 'Cover Letter', 'Resume Link', 'Timestamp']
                    elif inquiry_type == "Contact Us":
                        headers = ['Timestamp', 'Full Name', 'Email Address', 'Phone Number', 'Subject', 'Message']
                    elif inquiry_type == "Product Inquiry":
                        headers = ['Full Name', 'Phone Number', 'Email Address', 'Message', 'Product', 'Message', 'Prescription Link', 'Timestamp']
                    elif inquiry_type == "Order Medicine":
                        headers = ['Full Name', 'Email Address', 'Phone Number', 'Age', 'Delivery Address', 'Prescription Link', 'Credentials Confirmation', 'Timestamp']
                    elif inquiry_type == "Partnership":
                        headers = ['Name', 'Company/Organization', 'Email', 'Mobile Number', 'Inquiry', 'Data Privacy Agreement', 'Timestamp']
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

        spreadsheet_link = f"https://docs.google.com/spreadsheets/d/{clean_spreadsheet_id(spreadsheet_id)}" if spreadsheet_id else "N/A - No designated spreadsheet in Sanity"
        all_emails = list(set(["info@getmeds.ph"] + [r.strip() for r in recipients if r.strip()]))

        # Verbose terminal print logs
        print("==============================================================")
        print("                   GETMEDS INQUIRY SUBMITTED                  ")
        print("==============================================================")
        print(f"Inquiry Type:      {request.inquiryType}")
        print(f"Full Name:         {request.fullName}")
        print(f"Email Address:     {request.email}")
        print(f"Phone Number:      {request.phone or 'N/A'}")
        print(f"Subject / Context: {request.subject or 'N/A'}")
        print(f"Spreadsheet Link:  {spreadsheet_link}")
        print(f"Email Recipients:  {', '.join(all_emails)}")
        print(f"Attached Files:    {[f.name for f in request.files] if request.files else 'None'}")
        print(f"Sanity File Links: {file_links if file_links else 'None'}")
        print(f"Sheets Appended:   {sheets_appended}")
        print(f"Email Sent:        {email_sent}")
        print("==============================================================")

        return {
            "success": True,
            "sheets_appended": sheets_appended,
            "email_sent": email_sent,
            "spreadsheet_link": spreadsheet_link,
            "email_recipients": all_emails,
            "sanity_files": file_links
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
