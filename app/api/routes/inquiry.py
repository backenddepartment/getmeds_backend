import base64
import httpx
import re
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

def normalize_header(header: str) -> str:
    """Lowercases and strips everything but letters/digits, so 'FULLNAME',
    'Full Name', and 'full_name' all normalize to the same 'fullname' — live
    sheets are hand-edited and drift in spacing/casing/punctuation shouldn't
    break the mapping. Matches the same normalization pattern used by
    getmeds_database's studio/lib/excelImport.ts."""
    return re.sub(r"[^a-z0-9]+", "", (header or "").lower())

# Used only to seed a brand-new/empty spreadsheet that has no admin-parsed headers yet
# (see the "headers" field on the googleSpreadsheet Sanity document). Once an admin
# pastes/re-generates the spreadsheet link in Studio, the parsed live header row takes
# over as the authoritative column layout — see resolve_field_value/build_row_from_headers.
FALLBACK_HEADERS = ['Timestamp', 'Full Name', 'Email', 'Phone', 'Message', 'Attachments']

def resolve_field_value(normalized_header: str, request: InquirySubmitRequest,
                         file_links_by_category: Dict[str, List[str]], timestamp_str: str) -> str:
    """
    Maps a single normalized header (see normalize_header) to the value it should
    hold for this submission, purely by what the header text means — independent
    of inquiryType. This is what lets a brand-new column an admin adds to a live
    sheet (e.g. "Valid ID Uploaded of Patient") get filled automatically as long
    as its wording matches one of the rules below, with no backend redeploy.
    Checks are ordered most-specific first so e.g. "Email Address" (contains
    "email") is claimed before a generic "address" rule could see it.
    """
    def links(*categories: str) -> str:
        combined: List[str] = []
        for category in categories:
            combined.extend(file_links_by_category.get(category, []))
        return ", ".join(combined)

    h = normalized_header
    contact_same_as_patient = bool(request.additionalData.get("contactSameAsPatient"))

    if "validid" in h:
        return links("id")
    if "relationship" in h:
        return "Self" if contact_same_as_patient else request.additionalData.get("contactRelationship", "")
    if "contactperson" in h or ("contact" in h and "fullname" in h):
        return request.fullName if contact_same_as_patient else request.additionalData.get("contactName", "")
    if "resume" in h:
        return links("resume", "file")
    if "prescription" in h:
        return links("prescription", "file")
    if "coverletter" in h:
        return request.message
    if "credential" in h:
        return "Confirmed"
    if "privacy" in h or "agreement" in h:
        return "Agreed"
    if h in ("timestamp", "date", "datetime"):
        return timestamp_str
    if "company" in h or "organization" in h:
        return request.subject or request.additionalData.get("company", "")
    if "position" in h:
        return request.additionalData.get("position", "") or request.subject
    if "product" in h:
        return request.additionalData.get("productName", "")
    if "email" in h:
        return request.email
    if "deliveryaddress" in h or h == "address":
        return request.additionalData.get("address", "")
    if h == "age":
        return request.additionalData.get("age", "")
    if "phone" in h or "mobile" in h:
        return request.phone
    if "message" in h or "inquiry" in h:
        return request.message
    if "fullname" in h or h == "name":
        return request.fullName
    if "subject" in h:
        return request.subject or ""
    if "attachment" in h or "link" in h or "file" in h:
        return links("id", "prescription", "resume", "file")
    return ""

def build_row_from_headers(headers: List[str], request: InquirySubmitRequest,
                            file_links_by_category: Dict[str, List[str]], timestamp_str: str) -> List[str]:
    """
    Builds a spreadsheet row by resolving a value for each column's header text
    (see resolve_field_value). A header that repeats after normalization (e.g. a
    sheet with two "Message" columns) only gets filled once; later duplicates are
    left blank rather than repeating the same value into every column that shares
    that label. Any column whose header doesn't match a known field (e.g. a
    staff-managed "Status"/"RR" tracking column) is also left blank, not guessed.
    """
    used = set()
    row = []
    for header in headers:
        normalized = normalize_header(header)
        if normalized and normalized not in used:
            row.append(resolve_field_value(normalized, request, file_links_by_category, timestamp_str))
            used.add(normalized)
        else:
            row.append("")
    return row

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
        if request.files:
            for file in request.files:
                if not file.name or not file.base64:
                    continue
                url = await upload_file_to_sanity(file.name, file.type, file.base64)
                if url:
                    file_links.append(url)
                    if file.category == "id":
                        id_verification_link = url
                    else:
                        prescription_links.append(url)

        # 2. Query Sanity for Routing Rules — also pull the admin-parsed "headers" field
        # off the linked googleSpreadsheet doc (populated in Studio when an admin pastes/
        # re-generates the spreadsheet link — see SpreadsheetLinkInput.tsx), which is what
        # determines the column layout below rather than a hardcoded per-type list.
        recipients = []
        spreadsheet_id = None
        sanity_headers: List[str] = []

        try:
            groq_query = '*[_type == "inquiryRouting" && inquiryType == $inquiryType][0]{ recipients, "spreadsheetId": spreadsheet->spreadsheetId, "headers": spreadsheet->headers }'
            routing_rule = await sanity_service.query_sanity(groq_query, {"$inquiryType": request.inquiryType})
            if routing_rule:
                recipients = routing_rule.get("recipients") or []
                spreadsheet_id = routing_rule.get("spreadsheetId")
                sanity_headers = routing_rule.get("headers") or []
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
                    sheet_query = '*[_type == "googleSpreadsheet" && id.current == $slug][0]{ spreadsheetId, headers }'
                    sheet_doc = await sanity_service.query_sanity(sheet_query, {"$slug": slug})
                    if sheet_doc:
                        spreadsheet_id = sheet_doc.get("spreadsheetId")
                        sanity_headers = sheet_doc.get("headers") or []
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
                    sheet_headers = FALLBACK_HEADERS

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
                            body={'values': [sheet_headers]}
                        ).execute()
                    except Exception as update_err:
                        print(f"ERROR: Failed to update headers: {update_err}")

                row = build_row_from_headers(sheet_headers, request, file_links_by_category, timestamp_str)

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
