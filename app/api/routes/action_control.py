# Action Control Routes - Role-Based Access Control with Granular Actions
# File: app/api/routes/action_control.py

# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException, Header, Request, Depends
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime
import uuid
from app.services.security_service import security_service

router = APIRouter(prefix="/security/action-control", tags=["action-control"])

# ============================================================
# PYDANTIC MODELS
# ============================================================

class ActionControlRole(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Role name e.g. Admin, Editor, Viewer")
    description: Optional[str] = Field(None, description="Role description")
    permissions: List[str] = Field(default_factory=list, description="Default permissions")
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)

class ActionControlMatrix(BaseModel):
    matrix: Dict[str, List[str]] = Field(..., description="Key format: 'collection:role_id', Value: ['read', 'create', 'edit', 'delete']")

class RoleCreateRequest(BaseModel):
    name: str = Field(..., description="Role name")
    description: Optional[str] = Field(None)
    permissions: Optional[List[str]] = Field(default_factory=list)

class RoleUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class AuditLogEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user: str
    role: str
    action: str  # 'read', 'create', 'edit', 'delete'
    collection: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    ip_address: Optional[str] = None

# ============================================================
# DEPENDENCY: VERIFY ADMIN TOKEN
# ============================================================

async def verify_admin_token(request: Request, x_admin_token: str = Header(None, alias="X-Admin-Token")):
    """Verify admin token before allowing access"""
    if not x_admin_token:
        raise HTTPException(status_code=401, detail="Missing admin token")
    
    # Validate token via security service
    try:
        from app.api.routes.admin import decode_access_token
        claims = decode_access_token(x_admin_token)
        if not claims:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return claims
    except:
        raise HTTPException(status_code=401, detail="Unauthorized")

# ============================================================
# ENDPOINTS
# ============================================================

@router.get("")
async def get_action_control_data(claims=Depends(verify_admin_token)):
    """
    GET /api/admin/security/action-control
    Retrieve all roles and the access control matrix
    """
    try:
        roles = await security_service.get_action_control_roles()
        matrix = await security_service.get_action_control_matrix()
        
        return {
            "success": True,
            "roles": roles,
            "matrix": matrix
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("")
async def update_action_control_matrix(
    payload: ActionControlMatrix,
    claims=Depends(verify_admin_token)
):
    """
    PUT /api/admin/security/action-control
    Update the entire action control matrix
    Matrix format: {"collection:role_id": ["read", "create", "edit", "delete"]}
    """
    try:
        result = await security_service.update_action_control_matrix(payload.matrix)
        
        # Log the change
        await security_service.log_action_control_change(
            user=claims.get("username", "system"),
            action="matrix_update",
            details={"updated_entries": len(payload.matrix)}
        )
        
        return {
            "success": True,
            "message": "Action control matrix updated successfully",
            "updated_count": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# ROLE MANAGEMENT ENDPOINTS
# ============================================================

@router.get("/roles")
async def get_all_roles(claims=Depends(verify_admin_token)):
    """
    GET /api/admin/security/action-control/roles
    Get all roles
    """
    try:
        roles = await security_service.get_action_control_roles()
        return {
            "success": True,
            "roles": roles,
            "count": len(roles)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/roles")
async def create_role(
    payload: RoleCreateRequest,
    claims=Depends(verify_admin_token)
):
    """
    POST /api/admin/security/action-control/roles
    Create a new role
    """
    try:
        if not payload.name.strip():
            raise HTTPException(status_code=400, detail="Role name is required")
        
        role = ActionControlRole(
            name=payload.name.strip(),
            description=payload.description,
            permissions=payload.permissions or [],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        result = await security_service.create_action_control_role(role.dict())
        
        # Log the action
        await security_service.log_action_control_change(
            user=claims.get("username", "system"),
            action="role_create",
            details={"role_id": role.id, "role_name": role.name}
        )
        
        return {
            "success": True,
            "role": result,
            "message": f"Role '{payload.name}' created successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/roles/{role_id}")
async def update_role(
    role_id: str,
    payload: RoleUpdateRequest,
    claims=Depends(verify_admin_token)
):
    """
    PUT /api/admin/security/action-control/roles/{role_id}
    Update an existing role
    """
    try:
        result = await security_service.update_action_control_role(role_id, payload.dict(exclude_unset=True))
        
        if not result:
            raise HTTPException(status_code=404, detail="Role not found")
        
        # Log the action
        await security_service.log_action_control_change(
            user=claims.get("username", "system"),
            action="role_update",
            details={"role_id": role_id, "updates": payload.dict(exclude_unset=True)}
        )
        
        return {
            "success": True,
            "role": result,
            "message": "Role updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: str,
    claims=Depends(verify_admin_token)
):
    """
    DELETE /api/admin/security/action-control/roles/{role_id}
    Delete a role and remove its access policies
    """
    try:
        result = await security_service.delete_action_control_role(role_id)
        
        if not result:
            raise HTTPException(status_code=404, detail="Role not found")
        
        # Log the action
        await security_service.log_action_control_change(
            user=claims.get("username", "system"),
            action="role_delete",
            details={"role_id": role_id}
        )
        
        return {
            "success": True,
            "message": "Role deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# AUDIT LOG ENDPOINTS
# ============================================================

@router.get("/audit")
async def get_audit_logs(
    limit: int = 100,
    claims=Depends(verify_admin_token)
):
    """
    GET /api/admin/security/action-control/audit
    Get access audit trail
    """
    try:
        logs = await security_service.get_action_control_audit_logs(limit=limit)
        
        return {
            "success": True,
            "logs": logs,
            "count": len(logs)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/audit/log")
async def log_access_attempt(
    user: str,
    role: str,
    action: str,
    collection: str,
    request: Request,
    claims=Depends(verify_admin_token)
):
    """
    POST /api/admin/security/action-control/audit/log
    Log an access attempt (internal use)
    """
    try:
        ip_address = request.client.host if request.client else None
        
        log_entry = AuditLogEntry(
            user=user,
            role=role,
            action=action,
            collection=collection,
            ip_address=ip_address
        )
        
        await security_service.create_audit_log_entry(log_entry.dict())
        
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# PERMISSION CHECKING ENDPOINTS
# ============================================================

@router.post("/check-permission")
async def check_permission(
    user: str,
    role: str,
    collection: str,
    action: str,
    claims=Depends(verify_admin_token)
):
    """
    POST /api/admin/security/action-control/check-permission
    Check if a role has permission to perform an action on a collection
    Returns: { "allowed": bool, "reason": str }
    """
    try:
        matrix = await security_service.get_action_control_matrix()
        key = f"{collection}:{role}"
        
        allowed_actions = matrix.get(key, [])
        is_allowed = action in allowed_actions
        
        return {
            "success": True,
            "allowed": is_allowed,
            "action": action,
            "collection": collection,
            "role": role,
            "available_actions": allowed_actions,
            "reason": f"Role '{role}' can {', '.join(allowed_actions) if allowed_actions else 'not'} on {collection}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/user-permissions/{user_id}")
async def get_user_permissions(
    user_id: str,
    claims=Depends(verify_admin_token)
):
    """
    GET /api/admin/security/action-control/user-permissions/{user_id}
    Get all collections and actions accessible by a user based on their role
    """
    try:
        user = await security_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_role = user.get("role")
        matrix = await security_service.get_action_control_matrix()
        
        # Filter matrix for this user's role
        user_permissions = {}
        for key, actions in matrix.items():
            collection, role = key.split(":", 1)
            if role == user_role:
                user_permissions[collection] = actions
        
        return {
            "success": True,
            "user_id": user_id,
            "user_role": user_role,
            "permissions": user_permissions,
            "accessible_collections": list(user_permissions.keys()),
            "total_collections": len(user_permissions)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))