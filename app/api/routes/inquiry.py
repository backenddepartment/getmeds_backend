import base64
import httpx
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException

from app.schemas.inquiry import InquirySubmitRequest
from app.core.config import settings
from app.services.sanity_service import sanity_service
from app.services.email_service import email_service
from app.api.routes.spreadsheet import clean_spreadsheet_id, get_google_services

router = APIRouter()

# Philippine Standard Time is a fixed UTC+8 offset with no DST (since 1978), so a
# fixed-offset timezone is correct here and avoids depending on the system/zoneinfo
# tz database being present (not guaranteed on every host, e.g. some Windows setups).
MANILA_TZ = timezone(timedelta(hours=8))

def format_manila_timestamp() -> str:
    """Formats the current Manila time as e.g. "6/10/2026, 12:30:55 PM" (no leading zeros
    on month/day/hour), matching the display format already used in the inquiry spreadsheets."""
    now = datetime.now(MANILA_TZ)
    hour12 = now.hour % 12 or 12
    ampm = "AM" if now.hour < 12 else "PM"
    return f"{now.month}/{now.day}/{now.year}, {hour12}:{now.minute:02d}:{now.second:02d} {ampm}"

def map_row_to_headers(headers: List[str], field_values: Dict[str, str]) -> List[str]:
    """
    Builds a spreadsheet row by matching each column's header text (trimmed,
    case-insensitive) against field_values keys, so the live sheet's header row
    is authoritative for column layout — reordering, renaming, or inserting a
    header there no longer requires a matching code change here. A header text
    that repeats (e.g. a sheet with two "Message" columns) only consumes the
    matching field once; later duplicates are left blank rather than repeating
    the same value into every column that shares that label.
    """
    used_keys = set()
    row = []
    for header in headers:
        normalized = (header or "").strip().lower()
        matched_key = None
        for key in field_values:
            if key not in used_keys and key.strip().lower() == normalized:
                matched_key = key
                break
        if matched_key is not None:
            row.append(str(field_values[matched_key]))
            used_keys.add(matched_key)
        else:
            row.append("")
    return row

def build_field_values(
    inquiry_type: str,
    request: InquirySubmitRequest,
    file_links_by_category: Dict[str, List[str]],
    timestamp_str: str,
):
    """
    Returns (default_headers, field_values) for an inquiry type: default_headers
    is only used to seed a brand-new/empty spreadsheet, while field_values is the
    header-name -> value mapping that map_row_to_headers() matches against
    whatever header row the live sheet actually has.
    """
    def links(*categories: str) -> str:
        combined: List[str] = []
        for category in categories:
            combined.extend(file_links_by_category.get(category, []))
        return ", ".join(combined)

    if inquiry_type == "Career Inquiry":
        headers = ['Full Name', 'Email Address', 'Mobile Number', 'Position', 'Cover Letter', 'Resume Link', 'Timestamp']
        field_values = {
            'Full Name': request.fullName,
            'Email Address': request.email,
            'Mobile Number': request.phone,
            'Position': request.additionalData.get("position", "") or request.subject,
            'Cover Letter': request.message,
            'Resume Link': links('resume', 'file'),
            'Timestamp': timestamp_str,
        }
    elif inquiry_type == "Contact Us":
        headers = ['Timestamp', 'Full Name', 'Email Address', 'Phone Number', 'Subject', 'Message']
        field_values = {
            'Timestamp': timestamp_str,
            'Full Name': request.fullName,
            'Email Address': request.email,
            'Phone Number': request.phone,
            'Subject': request.subject or request.additionalData.get("subject", ""),
            'Message': request.message,
        }
    elif inquiry_type == "Product Inquiry":
        # The live sheet has a duplicate "Message" header (columns D and F) with
        # nothing mapping to a second message-like field; map_row_to_headers()
        # leaves the second occurrence blank rather than repeating the value.
        headers = ['Full Name', 'Phone Number', 'Email Address', 'Message', 'Product', 'Message', 'Prescription Link', 'Timestamp']
        field_values = {
            'Full Name': request.fullName,
            'Phone Number': request.phone,
            'Email Address': request.email,
            'Message': request.message,
            'Product': request.additionalData.get("productName", ""),
            'Prescription Link': links('prescription', 'file'),
            'Timestamp': timestamp_str,
        }
    elif inquiry_type == "Order Medicine":
        # The frontend blocks submission unless the "information is authentic"
        # checkbox is checked and doesn't send it as a field, so "Confirmed" is
        # always correct here (same pattern as Partnership's consent column).
        headers = ['Full Name', 'Email Address', 'Phone Number', 'Age', 'Delivery Address', 'Valid ID Link', 'Prescription Link', 'Credentials Confirmation', 'Timestamp']
        field_values = {
            'Full Name': request.fullName,
            'Email Address': request.email,
            'Phone Number': request.phone,
            'Age': request.additionalData.get("age", ""),
            'Delivery Address': request.additionalData.get("address", ""),
            'Valid ID Link': links('id'),
            'Prescription Link': links('prescription', 'file'),
            'Credentials Confirmation': "Confirmed",
            'Timestamp': timestamp_str,
        }
    elif inquiry_type == "Partnership":
        # The frontend blocks submission unless the consent checkbox is checked
        # and doesn't send it as a field, so "Agreed" is always correct here.
        headers = ['Name', 'Company/Organization', 'Email', 'Mobile Number', 'Inquiry', 'Data Privacy Agreement', 'Timestamp']
        field_values = {
            'Name': request.fullName,
            'Company/Organization': request.subject or request.additionalData.get("company", ""),
            'Email': request.email,
            'Mobile Number': request.phone,
            'Inquiry': request.message,
            'Data Privacy Agreement': "Agreed",
            'Timestamp': timestamp_str,
        }
    else:
        headers = ['Timestamp', 'Full Name', 'Email', 'Phone', 'Message', 'Attachments']
        field_values = {
            'Timestamp': timestamp_str,
            'Full Name': request.fullName,
            'Email': request.email,
            'Phone': request.phone,
            'Message': request.message,
            'Attachments': links('id', 'prescription', 'resume', 'file'),
        }

    return headers, field_values

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
        # 1. Upload files to Sanity CMS (if any are present), grouping the resulting
        # links by category (e.g. "id" vs "prescription") so each can be routed to
        # its own spreadsheet column instead of merging every upload into one link.
        file_links = []
        file_links_by_category: Dict[str, List[str]] = {}
        if request.files:
            for file in request.files:
                if not file.name or not file.base64:
                    continue
                url = await upload_file_to_sanity(file.name, file.type, file.base64)
                if url:
                    file_links.append(url)
                    category = (file.category or "file").strip().lower() or "file"
                    file_links_by_category.setdefault(category, []).append(url)

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
        sheets_error = None
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

                timestamp_str = format_manila_timestamp()
                inquiry_type = request.inquiryType

                # Build header-name -> value mapping for this inquiry type, then match
                # it against the sheet's own header row (read first) rather than
                # assuming a fixed column order — see map_row_to_headers/build_field_values.
                default_headers, field_values = build_field_values(
                    inquiry_type, request, file_links_by_category, timestamp_str
                )

                # Update Headers if the Spreadsheet is Empty
                if not values:
                    try:
                        sheets.spreadsheets().values().update(
                            spreadsheetId=clean_id,
                            range='Sheet1!A1',
                            valueInputOption='RAW',
                            body={'values': [default_headers]}
                        ).execute()
                    except Exception as update_err:
                        print(f"ERROR: Failed to update headers: {update_err}")
                    sheet_headers = default_headers
                else:
                    sheet_headers = values[0]

                row = map_row_to_headers(sheet_headers, field_values)

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
                sheets_error = str(sheet_err)
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
            "sheets_error": sheets_error,
            "email_sent": email_sent,
            "spreadsheet_link": spreadsheet_link,
            "email_recipients": all_emails,
            "sanity_files": file_links
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
