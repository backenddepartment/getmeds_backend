# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException, Depends, Header, Request, Response, UploadFile, File
# pyrefly: ignore [missing-import]
from pydantic import BaseModel
from app.services.sanity_service import sanity_service
from app.services.security_service import security_service
from app.core.config import get_settings
import uuid
import re
import base64
import time

router = APIRouter()
settings = get_settings()

class LoginRequest(BaseModel):
    passcode: str

def generate_access_token(username: str, role: str, permissions: str):
    expiry = int(time.time()) + 900  # 15 minutes
    raw_str = f"{username}:{role}:{permissions}:{expiry}"
    encoded = base64.b64encode(raw_str.encode("utf-8")).decode("utf-8")
    return f"GMP-SEC-ACCESS-{encoded}"

def decode_access_token(token: str):
    if not token.startswith("GMP-SEC-ACCESS-"):
        return None
    try:
        encoded_part = token[len("GMP-SEC-ACCESS-"):]
        decoded_str = base64.b64decode(encoded_part.encode("utf-8")).decode("utf-8")
        parts = decoded_str.split(":", 3)
        if len(parts) == 4:
            username, role, permissions, expiry = parts
            if int(time.time()) < int(expiry):
                return {"username": username, "role": role, "permissions": permissions}
    except Exception:
        pass
    return None

def generate_refresh_token(username: str, passcode: str):
    expiry = int(time.time()) + 604800  # 7 days
    raw_str = f"{username}:{passcode}:{expiry}"
    encoded = base64.b64encode(raw_str.encode("utf-8")).decode("utf-8")
    return f"GMP-SEC-REFRESH-{encoded}"

def decode_refresh_token(token: str):
    if not token.startswith("GMP-SEC-REFRESH-"):
        return None
    try:
        encoded_part = token[len("GMP-SEC-REFRESH-"):]
        decoded_str = base64.b64decode(encoded_part.encode("utf-8")).decode("utf-8")
        parts = decoded_str.split(":", 2)
        if len(parts) == 3:
            username, passcode, expiry = parts
            if int(time.time()) < int(expiry):
                return {"username": username, "passcode": passcode}
    except Exception:
        pass
    return None

async def verify_admin_token(request: Request, x_admin_token: str = Header(None, alias="X-Admin-Token")):
    expected_token = getattr(settings, "ADMIN_TOKEN", "getmeds-admin-secret-key")
    
    # 1. Fallback for the master system secret token
    if x_admin_token == expected_token:
        return
        
    # 2. Extract access token from header or fallback to cookie
    token = x_admin_token or request.cookies.get("gmp_access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing admin session token.")
        
    claims = decode_access_token(token)
    if not claims:
        raise HTTPException(status_code=401, detail="Expired or invalid admin session token.")
        
    # Query Sanity to ensure operator is Active
    from app.services.sanity_service import sanity_security_service
    username = claims["username"]
    query = '*[_type == "adminUser" && username == $username][0]'
    try:
        user = await sanity_security_service.query_sanity(query, {"$username": username})
    except Exception:
        # Security Sanity temporarily unreachable — allow access if token is structurally valid
        print(f"WARNING: Security Sanity unreachable for token validation. Allowing access for {username}.")
        return
    
    if not user:
        raise HTTPException(status_code=401, detail="Operator session is invalid.")
        
    if user.get("status") != "Active":
        raise HTTPException(status_code=403, detail="Operator account status is suspended.")

@router.post("/auth/login")
async def admin_auth_login(payload: LoginRequest, response: Response):
    """
    Authenticates operator solely by secret passcode key.
    Stores session tokens securely in cookies and returns claims for client UI state.
    """
    res = await security_service.authenticate_admin(passcode=payload.passcode)
    if not res.get("authenticated"):
        raise HTTPException(status_code=401, detail=res.get("detail", "Authentication failed."))
        
    username = res["username"]
    role = res["role"]
    permissions = res["permissions"]
    
    # Generate short-lived Access and long-lived Refresh tokens
    access_token = generate_access_token(username, role, permissions)
    refresh_token = generate_refresh_token(username, payload.passcode)
    
    # Register secure HTTP-only cookies
    response.set_cookie(
        key="gmp_access_token",
        value=access_token,
        max_age=900,  # 15 mins
        httponly=True,
        secure=False,  # localhost compatibility
        samesite="lax"
    )
    response.set_cookie(
        key="gmp_refresh_token",
        value=refresh_token,
        max_age=604800,  # 7 days
        httponly=True,
        secure=False,
        samesite="lax"
    )
    
    return {
        "status": "success",
        "username": username,
        "role": role,
        "permissions": permissions,
        "token": access_token
    }

@router.post("/auth/refresh")
async def admin_auth_refresh(request: Request, response: Response):
    """
    Seamless access token rotation using HTTP-only Refresh Token.
    """
    refresh_token = request.cookies.get("gmp_refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token.")
        
    claims = decode_refresh_token(refresh_token)
    if not claims:
        response.delete_cookie("gmp_access_token")
        response.delete_cookie("gmp_refresh_token")
        raise HTTPException(status_code=401, detail="Expired or invalid refresh token.")
        
    username = claims["username"]
    passcode = claims["passcode"]
    
    from app.services.sanity_service import sanity_security_service
    query = '*[_type == "adminUser" && username == $username][0]'
    user = await sanity_security_service.query_sanity(query, {"$username": username})
    
    if not user or user.get("passcode") != passcode or user.get("status") != "Active":
        response.delete_cookie("gmp_access_token")
        response.delete_cookie("gmp_refresh_token")
        raise HTTPException(status_code=403, detail="Operator access suspended or modified.")
        
    new_access = generate_access_token(username, user["role"], user["permissions"])
    new_refresh = generate_refresh_token(username, passcode)
    
    response.set_cookie(key="gmp_access_token", value=new_access, max_age=900, httponly=True, secure=False, samesite="lax")
    response.set_cookie(key="gmp_refresh_token", value=new_refresh, max_age=604800, httponly=True, secure=False, samesite="lax")
    
    return {
        "status": "success",
        "token": new_access
    }

@router.post("/auth/logout")
async def admin_auth_logout(response: Response):
    """
    Purges secure HTTP-only cookies and ends active administrative session.
    """
    response.delete_cookie("gmp_access_token")
    response.delete_cookie("gmp_refresh_token")
    return {"status": "success"}

SUPPORTED_TYPES = [
    "product",
    "category",
    "heroSlide",
    "service",
    "dealOfDay",
    "categoryBanner",
    "team",
    "faq",
    "chatSession"
]

@router.get("/documents", dependencies=[Depends(verify_admin_token)])
async def get_documents(collection: str = "product", page: int = 1, limit: int = 5):
    """
    Returns a server-side paginated list of existing documents for a specific active collection schema.
    """
    if collection not in SUPPORTED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported collection type: {collection}")
        
    try:
        # 1. Fetch only the active collection's total count
        count_query = f'count(*[_type == "{collection}"])'
        total_count = await sanity_service.query_sanity(count_query)
        
        # 2. Query target paginated slice using type-specific projection
        start = (page - 1) * limit
        end = page * limit
        
        projection = GROQ_PROJECTIONS.get(collection, '{ _id, _type, _createdAt }')
        groq_query = f'*[_type == "{collection}"] {projection} | order(_createdAt desc) [{start}...{end}]'
        results = await sanity_service.query_sanity(groq_query)
        
        return {
            "status": "success",
            "documents": results,
            "total": total_count,
            "page": page,
            "limit": limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

PREFIX_MAP = {
    "product": "GMP0000-",
    "category": "GMC0000-",
    "heroSlide": "GMH0000-",
    "service": "GMS0000-",
    "dealOfDay": "GMD0000-",
    "categoryBanner": "GMB0000-",
    "team": "GMT0000-",
    "faq": "GMF0000-",
    "chatSession": "GMX0000-",
    "adminUser": "GMAU0000-",
    "securityLog": "GMSL0000-",
    "accessPoint": "GMAP0000-"
}

# Per-collection GROQ field projections for the dynamic table
GROQ_PROJECTIONS = {
    "product":       '{ _id, _type, _createdAt, name, description, price, availability, strength, packaging, category, subCategory }',
    "category":      '{ _id, _type, _createdAt, title, subtitle, description, icon, subCategories }',
    "heroSlide":     '{ _id, _type, _createdAt, title, subtitle, primaryButtonText, primaryButtonLink, secondaryButtonText, secondaryButtonLink }',
    "service":       '{ _id, _type, _createdAt, title, description, link, icon }',
    "dealOfDay":     '{ _id, _type, _createdAt, subtitle, backgroundText, priceOverride }',
    "categoryBanner":'{ _id, _type, _createdAt, title, subtitle, buttonText, buttonLink }',
    "team":          '{ _id, _type, _createdAt, name, role, bio }',
    "faq":           '{ _id, _type, _createdAt, question, answer, keywords }',
    "chatSession":   '{ _id, _type, _createdAt, sessionId, userName, lastSubject, sessionSummary }',
}

@router.post("/collection/{doc_type}", dependencies=[Depends(verify_admin_token)])
async def create_collection_document(doc_type: str, data: dict):
    """
    Unified dynamic creator endpoint. Accepts custom payloads for ANY active database collection schema,
    generates clean custom sequential prefix IDs (e.g. GMP0000-0001), performs auto-slugification,
    and executes Sanity mutations cleanly.
    """
    if doc_type not in SUPPORTED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported document type: {doc_type}")
    
    try:
        # Query existing count in database to form next sequential custom ID
        count_query = f'count(*[_type == "{doc_type}"])'
        count = await sanity_service.query_sanity(count_query)
        new_idx = count + 1
        prefix = PREFIX_MAP.get(doc_type, f"{doc_type}0000-")
        doc_id = f"{prefix}{new_idx:04d}"
        
        # Build base document mutation payload
        doc_payload = {
            "_id": doc_id,
            "_type": doc_type,
            **data
        }

        # Auto slugify products based on name
        if doc_type == "product" and "name" in data:
            slug_val = re.sub(r'[^a-z0-9\-]', '', data["name"].lower().replace(' ', '-'))
            doc_payload["slug"] = {"_type": "slug", "current": slug_val}

        # Auto slugify categories based on title
        elif doc_type == "category" and "title" in data:
            slug_val = re.sub(r'[^a-z0-9\-]', '', data["title"].lower().replace(' ', '-'))
            doc_payload["slug"] = {"_type": "slug", "current": slug_val}

        mutations = [{"create": doc_payload}]
        result = await sanity_service.mutate_sanity(mutations)
        return {"status": "success", "id": doc_id, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/document/{doc_id}", dependencies=[Depends(verify_admin_token)])
async def get_document_detail(doc_id: str):
    """
    Fetches the complete raw document from Sanity by _id for the detail panel view.
    """
    try:
        groq_query = f'*[_id == "{doc_id}"][0]'
        if doc_id.startswith(("GMAU", "GMAP", "GMSL")):
            from app.services.sanity_service import sanity_security_service
            result = await sanity_security_service.query_sanity(groq_query)
        else:
            result = await sanity_service.query_sanity(groq_query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sanity error: {str(e)}")
    
    if not result:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
    
    return {"status": "success", "document": result}

@router.patch("/document/{doc_id}", dependencies=[Depends(verify_admin_token)])
async def update_document(doc_id: str, data: dict):
    """
    Patches specific fields of an existing document. Only provided fields are updated.
    """
    if not data:
        raise HTTPException(status_code=400, detail="No fields provided to update.")
    try:
        # Remove internal Sanity fields that should not be patched
        for key in ("_id", "_type", "_rev", "_createdAt", "_updatedAt"):
            data.pop(key, None)
        mutations = [{"patch": {"id": doc_id, "set": data}}]
        if doc_id.startswith(("GMAU", "GMAP", "GMSL")):
            from app.services.sanity_service import sanity_security_service
            result = await sanity_security_service.mutate_sanity(mutations)
        else:
            result = await sanity_service.mutate_sanity(mutations)
        return {"status": "success", "id": doc_id, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/document/{doc_id}/image", dependencies=[Depends(verify_admin_token)])
async def upload_document_image(doc_id: str, request: Request):
    """
    Uploads a raw image file to Sanity assets, then patches the document's image field.
    Expects raw binary body with Content-Type: image/*, e.g. image/jpeg or image/png.
    """
    from app.core.config import get_settings
    _settings = get_settings()
    content_type = request.headers.get("content-type", "image/jpeg")
    image_bytes = await request.body()

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image body.")

    # Determine file extension from content-type
    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
    ext = ext_map.get(content_type.split(";")[0].strip(), "jpg")

    try:
        # pyrefly: ignore [missing-import]
        import httpx
        asset_url = (
            f"https://{_settings.SANITY_PROJECT_ID}.api.sanity.io"
            f"/v{_settings.SANITY_API_VERSION}/assets/images/{_settings.SANITY_DATASET}"
            f"?filename=upload.{ext}"
        )
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            asset_res = await client.post(
                asset_url,
                content=image_bytes,
                headers={
                    "Authorization": f"Bearer {_settings.SANITY_TOKEN}",
                    "Content-Type": content_type,
                }
            )
        if asset_res.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=f"Sanity asset upload failed: {asset_res.text}")

        asset_data = asset_res.json()
        asset_ref = asset_data["document"]["_id"]

        # Patch the document's image field with the new asset reference
        mutations = [{"patch": {"id": doc_id, "set": {
            "image": {"_type": "image", "asset": {"_type": "reference", "_ref": asset_ref}}
        }}}]
        await sanity_service.mutate_sanity(mutations)

        return {"status": "success", "assetRef": asset_ref}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/document/{doc_id}", dependencies=[Depends(verify_admin_token)])
async def delete_document(doc_id: str):
    """
    Unified document deletion endpoint.
    """
    try:
        mutations = [{"delete": {"id": doc_id}}]
        if doc_id.startswith(("GMAU", "GMAP", "GMSL")):
            from app.services.sanity_service import sanity_security_service
            result = await sanity_security_service.mutate_sanity(mutations)
        else:
            result = await sanity_service.mutate_sanity(mutations)
        return {"status": "success", "id": doc_id, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========== BULK ACTIONS ==========

class BulkDeletePayload(BaseModel):
    ids: list

@router.delete("/bulk", dependencies=[Depends(verify_admin_token)])
async def bulk_delete_documents(payload: BulkDeletePayload):
    """Deletes multiple documents in a single Sanity mutation batch."""
    if not payload.ids:
        raise HTTPException(status_code=400, detail="No IDs provided.")
    try:
        mutations = [{"delete": {"id": doc_id}} for doc_id in payload.ids]
        result = await sanity_service.mutate_sanity(mutations)
        return {"status": "success", "deleted": len(payload.ids)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _coerce_field(key: str, value: str):
    """Best-effort type coercion for imported field values."""
    if value is None or str(value).strip() == '':
        return None
    v = str(value).strip()
    if key in ('price', 'priceOverride'):
        try: return float(v)
        except: return None
    if key == 'availability':
        return v.lower() not in ('false', '0', 'no', 'out of stock')
    if key == 'keywords':
        return [k.strip() for k in v.split(',') if k.strip()]
    return v


@router.post("/bulk/import/{collection}", dependencies=[Depends(verify_admin_token)])
async def bulk_import_documents(collection: str, file: UploadFile = File(...)):
    """
    Parses CSV, XLSX, or JSON file and bulk-creates documents in the given collection.
    Columns/keys are matched to schema field names (case-insensitive).
    """
    if collection not in SUPPORTED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported collection: {collection}")

    content = await file.read()
    filename = (file.filename or '').lower()
    rows = []

    try:
        if filename.endswith('.json'):
            import json
            parsed = json.loads(content)
            rows = parsed if isinstance(parsed, list) else [parsed]

        elif filename.endswith('.csv'):
            import csv, io
            reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
            rows = [dict(r) for r in reader]

        elif filename.endswith(('.xlsx', '.xls')):
            import openpyxl, io
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            ws = wb.active
            headers = [str(c.value).strip() for c in next(ws.iter_rows(max_row=1))]
            for row in ws.iter_rows(min_row=2, values_only=True):
                rows.append({headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))})
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type. Use CSV, XLSX, or JSON.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")

    if not rows:
        raise HTTPException(status_code=400, detail="File is empty or contains no data rows.")

    prefix = PREFIX_MAP.get(collection, 'GM-')
    count_query = f'count(*[_type == "{collection}"])'
    try:
        existing_count = await sanity_service.query_sanity(count_query) or 0
    except:
        existing_count = 0

    created, failed, errors = 0, 0, []
    BATCH_SIZE = 15
    mutation_batch = []

    for idx, row in enumerate(rows):
        try:
            # Normalize keys to lowercase for matching
            norm = {k.lower().strip(): v for k, v in row.items()}
            doc_payload = {"_type": collection}
            seq = existing_count + created + 1
            doc_id = f"{prefix}{str(seq).zfill(4)}"
            doc_payload["_id"] = doc_id

            for key, raw_val in norm.items():
                if key in ('_id', '_type', '_rev', '_createdat', '_updatedat', 'id'): continue
                coerced = _coerce_field(key, raw_val)
                if coerced is not None:
                    doc_payload[key] = coerced

            # Auto-slug from name or title
            if collection == 'product' and 'name' in doc_payload:
                slug_val = re.sub(r'[^a-z0-9-]', '', doc_payload['name'].lower().replace(' ', '-'))
                doc_payload['slug'] = {'_type': 'slug', 'current': slug_val}
            elif 'title' in doc_payload:
                slug_val = re.sub(r'[^a-z0-9-]', '', doc_payload['title'].lower().replace(' ', '-'))
                doc_payload['slug'] = {'_type': 'slug', 'current': slug_val}

            mutation_batch.append({"create": doc_payload})
            created += 1

            # Flush batch
            if len(mutation_batch) >= BATCH_SIZE:
                await sanity_service.mutate_sanity(mutation_batch)
                mutation_batch = []
        except Exception as e:
            failed += 1
            errors.append({"row": idx + 1, "error": str(e)})

    # Flush remaining
    if mutation_batch:
        try:
            await sanity_service.mutate_sanity(mutation_batch)
        except Exception as e:
            failed += len(mutation_batch)
            created -= len(mutation_batch)
            errors.append({"row": "batch", "error": str(e)})

    return {
        "status": "success",
        "imported": created,
        "failed": failed,
        "total": len(rows),
        "errors": errors[:10]
    }


@router.get("/bulk/export/{collection}", dependencies=[Depends(verify_admin_token)])
async def export_documents(collection: str, fmt: str = "csv"):
    """Exports all documents from a collection as CSV or JSON."""
    if collection not in SUPPORTED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported collection: {collection}")
    try:
        projection = GROQ_PROJECTIONS.get(collection, '{ _id, _type, _createdAt }')
        groq_query = f'*[_type == "{collection}"] {projection} | order(_createdAt desc)'
        docs = await sanity_service.query_sanity(groq_query)
        if not docs:
            docs = []

        if fmt == 'json':
            import json
            # pyrefly: ignore [missing-import]
            from fastapi.responses import Response as FR
            return FR(content=json.dumps(docs, default=str, indent=2),
                      media_type='application/json',
                      headers={"Content-Disposition": f"attachment; filename={collection}.json"})
        else:
            import csv, io
            output = io.StringIO()
            if docs:
                keys = list(docs[0].keys())
                writer = csv.DictWriter(output, fieldnames=keys, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(docs)
            # pyrefly: ignore [missing-import]
            from fastapi.responses import Response as FR
            return FR(content=output.getvalue(),
                      media_type='text/csv',
                      headers={"Content-Disposition": f"attachment; filename={collection}.csv"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/security/users", dependencies=[Depends(verify_admin_token)])
async def get_security_users():
    """
    Exposes admin users stored in the Sanity CMS security collection.
    """
    try:
        return await security_service.get_admin_users()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/security/logs", dependencies=[Depends(verify_admin_token)])
async def get_security_logs(page: int = 1, limit: int = 5):
    """
    Exposes a server-side paginated list of security audit logs.
    """
    try:
        from app.services.sanity_service import sanity_security_service
        
        # 1. Fetch total count of security logs
        count_query = 'count(*[_type == "securityLog"])'
        total_count = await sanity_security_service.query_sanity(count_query)
        
        # 2. Query target paginated slice
        start = (page - 1) * limit
        end = page * limit
        
        groq_query = f'*[_type == "securityLog"] | order(timestamp desc) [{start}...{end}]'
        results = await sanity_security_service.query_sanity(groq_query)
        
        return {
            "status": "success",
            "logs": results,
            "total": total_count,
            "page": page,
            "limit": limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/security/access", dependencies=[Depends(verify_admin_token)])
async def get_security_access():
    """
    Exposes security access points stored in the Sanity CMS security collection.
    """
    try:
        return await security_service.get_access_points()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/security/user/status", dependencies=[Depends(verify_admin_token)])
async def update_user_status(payload: dict):
    """
    Toggles admin user active/suspended status in the Sanity CMS security collection.
    """
    username = payload.get("username")
    status = payload.get("status")
    if not username or not status:
        raise HTTPException(status_code=400, detail="Missing username or status in payload")
    try:
        await security_service.update_user_status(username, status)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
