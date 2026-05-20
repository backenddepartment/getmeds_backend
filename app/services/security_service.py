import os
# pyrefly: ignore [missing-import]
import asyncpg
from datetime import datetime
from typing import List, Dict, Optional
import json
 

class SecurityService:
    def __init__(self):
        self.pool = None

    async def get_pool(self):
        if self.pool is None:
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                from app.core.config import get_settings
                database_url = get_settings().DATABASE_URL
            if not database_url:
                raise Exception("DATABASE_URL is not set in environment variables.")
            # Lazily initialize asyncpg connection pool
            self.pool = await asyncpg.create_pool(
                database_url,
                min_size=1,
                max_size=10,
                max_queries=50000,
                max_inactive_connection_lifetime=300.0
            )
            # Run automatic table creation and data seeding
            await self.initialize_database()
        return self.pool

    async def initialize_database(self):
        async with self.pool.acquire() as conn:
            # 1. Enable pgcrypto extension for gen_random_uuid()
            await conn.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
            
            # 2. Create admin_users table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS admin_users (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    username VARCHAR(100) UNIQUE NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    status VARCHAR(20) DEFAULT 'Active',
                    permissions TEXT,
                    passcode VARCHAR(50) UNIQUE NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            
            # 3. Create access_points table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS access_points (
                    id SERIAL PRIMARY KEY,
                    resource VARCHAR(255) NOT NULL,
                    allowed_roles VARCHAR(255) NOT NULL,
                    auth_type VARCHAR(50) NOT NULL
                )
            """)
            
            # 4. Create security_logs table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS security_logs (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    event TEXT NOT NULL,
                    username VARCHAR(100) NOT NULL,
                    ip_address VARCHAR(45) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    severity VARCHAR(20) NOT NULL
                )
            """)
            
            # 5. Seed default admin users if none exist
            count_users = await conn.fetchval("SELECT COUNT(*) FROM admin_users")
            if count_users == 0:
                await conn.execute("""
                    INSERT INTO admin_users (username, email, role, status, permissions, passcode)
                    VALUES 
                    ('backenddepartment@gmail.com', 'backenddepartment@gmail.com', 'Administrator', 'Active', 'Full System Access, CMS Mutations, Schema Control', 'GMP-ADMIN-2026'),
                    ('admin', 'admin@gmail.com', 'Administrator', 'Active', 'full_access', 'Getmeds@1'),
                    ('Getmeds Admin', 'admin@getmeds.com', 'Administrator', 'Active', 'Full System Access, CMS Mutations, Schema Control', 'GMP-GETMEDS-2026')
                    ON CONFLICT (username) DO NOTHING
                """)
                
            # 6. Seed default access points if none exist
            count_aps = await conn.fetchval("SELECT COUNT(*) FROM access_points")
            if count_aps == 0:
                # Default system route access points
                await conn.execute("""
                    INSERT INTO access_points (resource, allowed_roles, auth_type)
                    VALUES 
                    ('/api/admin/collection/*', 'Administrator, Editor', 'Admin Token Header Required'),
                    ('/api/admin/document/*', 'Administrator', 'Admin Token Header Required'),
                    ('/api/admin/stats', 'Administrator, Security Officer, Editor, Auditor', 'Admin Token Header Required'),
                    ('/api/security/*', 'Administrator, Security Officer', 'Admin Token Header Required'),
                    ('product', 'Administrator', 'RBAC_COLLECTION'),
                    ('category', 'Administrator', 'RBAC_COLLECTION'),
                    ('heroSlide', 'Administrator', 'RBAC_COLLECTION'),
                    ('service', 'Administrator', 'RBAC_COLLECTION'),
                    ('dealOfDay', 'Administrator', 'RBAC_COLLECTION'),
                    ('categoryBanner', 'Administrator', 'RBAC_COLLECTION'),
                    ('team', 'Administrator', 'RBAC_COLLECTION'),
                    ('faq', 'Administrator', 'RBAC_COLLECTION'),
                    ('chatSession', 'Administrator', 'RBAC_COLLECTION'),
                    ('Administrator::product', 'read,create,edit,delete', 'RBAC_COLLECTION_V2'),
                    ('Administrator::category', 'read,create,edit,delete', 'RBAC_COLLECTION_V2'),
                    ('Administrator::heroSlide', 'read,create,edit,delete', 'RBAC_COLLECTION_V2'),
                    ('Administrator::service', 'read,create,edit,delete', 'RBAC_COLLECTION_V2'),
                    ('Administrator::dealOfDay', 'read,create,edit,delete', 'RBAC_COLLECTION_V2'),
                    ('Administrator::categoryBanner', 'read,create,edit,delete', 'RBAC_COLLECTION_V2'),
                    ('Administrator::team', 'read,create,edit,delete', 'RBAC_COLLECTION_V2'),
                    ('Administrator::faq', 'read,create,edit,delete', 'RBAC_COLLECTION_V2'),
                    ('Administrator::chatSession', 'read,create,edit,delete', 'RBAC_COLLECTION_V2'),
                    ('Administrator::_security', 'read,create,edit,delete', 'RBAC_COLLECTION_V2')
                """)

    async def get_admin_users(self):
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT id as "_id", username, email, role, status, permissions, created_at FROM admin_users ORDER BY created_at ASC'
            )
            # Format row records cleanly as dictionaries with ISO string dates for UI compatibility
            results = []
            for r in rows:
                d = dict(r)
                d["_id"] = str(d["_id"])
                if isinstance(d["created_at"], datetime):
                    d["created_at"] = d["created_at"].isoformat() + "Z"
                results.append(d)
            return results

    async def get_security_logs_paginated(self, page: int = 1, limit: int = 5):
        pool = await self.get_pool()
        start = (page - 1) * limit
        async with pool.acquire() as conn:
            total_count = await conn.fetchval('SELECT COUNT(*) FROM security_logs')
            rows = await conn.fetch(
                'SELECT id as "_id", timestamp, event, username as "user", ip_address, status, severity '
                'FROM security_logs ORDER BY timestamp DESC LIMIT $1 OFFSET $2',
                limit, start
            )
            results = []
            for r in rows:
                d = dict(r)
                d["_id"] = str(d["_id"])
                if isinstance(d["timestamp"], datetime):
                    d["timestamp"] = d["timestamp"].isoformat() + "Z"
                results.append(d)
            return results, total_count

    async def get_access_points(self):
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT id as "_id", resource, allowed_roles, auth_type FROM access_points ORDER BY id ASC'
            )
            return [dict(r) for r in rows]

    async def get_security_record_by_id(self, record_id: str):
        """
        Resolves a Supabase ID to the matching record across all 3 security tables.
        Supports UUID (for admin_users) and integer (for access_points/security_logs).
        Returns the record dict with a _table hint, or None if not found.
        """
        import re
        record_id_str = str(record_id).strip()
        
        # 1. Check if it's a UUID (possibly prefixed)
        _uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        target_uuid = None
        if re.match(_uuid_pattern, record_id_str, re.IGNORECASE):
            target_uuid = record_id_str
        else:
            parts = record_id_str.split('-', 1)
            if len(parts) > 1 and re.match(_uuid_pattern, parts[1], re.IGNORECASE):
                target_uuid = parts[1]
                
        # 2. Check if it's an integer (possibly prefixed like GMAP-1 or GMAP0000-1)
        target_int = None
        if record_id_str.isdigit():
            target_int = int(record_id_str)
        else:
            parts = record_id_str.split('-', 1)
            if len(parts) > 1:
                last_part = parts[1]
                if last_part.isdigit():
                    target_int = int(last_part)
                else:
                    match = re.search(r'\d+$', record_id_str)
                    if match:
                        target_int = int(match.group())
            else:
                match = re.search(r'\d+$', record_id_str)
                if match:
                    target_int = int(match.group())

        pool = await self.get_pool()
        async with pool.acquire() as conn:
            # If target_uuid is found, query admin_users (which uses UUID)
            if target_uuid:
                row = await conn.fetchrow(
                    'SELECT id as "_id", username, email, role, status, permissions, created_at FROM admin_users WHERE id = $1::uuid',
                    target_uuid
                )
                if row:
                    d = dict(row)
                    d["_id"] = str(d["_id"])
                    d["_table"] = "admin_users"
                    if d.get("created_at"):
                        d["created_at"] = d["created_at"].isoformat() + "Z"
                    return d

            # If target_int is found, query access_points or security_logs (which use integers)
            if target_int is not None:
                # Try access_points
                row = await conn.fetchrow(
                    'SELECT id as "_id", resource, allowed_roles, auth_type FROM access_points WHERE id = $1::integer',
                    target_int
                )
                if row:
                    d = dict(row)
                    d["_id"] = str(d["_id"])
                    d["_table"] = "access_points"
                    return d

                # Try security_logs
                row = await conn.fetchrow(
                    'SELECT id as "_id", timestamp, event, username as "user", ip_address, status, severity '
                    'FROM security_logs WHERE id = $1::integer',
                    target_int
                )
                if row:
                    d = dict(row)
                    d["_id"] = str(d["_id"])
                    d["_table"] = "security_logs"
                    if isinstance(d.get("timestamp"), datetime):
                        d["timestamp"] = d["timestamp"].isoformat() + "Z"
                    return d

            return None

    async def add_security_log(self, event: str, user: str, ip_address: str, status: str, severity: str):
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO security_logs (event, username, ip_address, status, severity) '
                'VALUES ($1, $2, $3, $4, $5)',
                event, user, ip_address, status, severity
            )

    async def update_user_status(self, username: str, status: str):
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            # Check user presence by username or email
            exists = await conn.fetchval(
                'SELECT EXISTS(SELECT 1 FROM admin_users WHERE username = $1 OR email = $1)',
                username
            )
            if not exists:
                raise Exception(f"Admin user with username '{username}' not found in Supabase.")
                
            await conn.execute(
                'UPDATE admin_users SET status = $1 WHERE username = $2 OR email = $2',
                status, username
            )
            
            await self.add_security_log(
                event=f"User account status updated to {status} for {username}",
                user="System Admin",
                ip_address="127.0.0.1",
                status="SUCCESS",
                severity="WARNING"
            )

    async def update_admin_user(self, user_id: str, data: dict):
        import re
        _uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        if not re.match(_uuid_pattern, user_id, re.IGNORECASE):
            parts = user_id.split('-', 1)
            if len(parts) > 1 and re.match(_uuid_pattern, parts[1], re.IGNORECASE):
                user_id = parts[1]
            else:
                raise Exception("Invalid admin user UUID")

        pool = self.pool or await self.get_pool()
        async with pool.acquire() as conn:
            existing = await conn.fetchrow('SELECT username, email, role, status, permissions, passcode FROM admin_users WHERE id = $1::uuid', user_id)
            if not existing:
                raise Exception("Admin user not found")
            existing = dict(existing)
            
            username = data.get("username", existing.get("username"))
            email = data.get("email", existing.get("email"))
            role = data.get("role", existing.get("role"))
            status = data.get("status", existing.get("status"))
            passcode = data.get("passcode", existing.get("passcode"))
            
            perms_raw = data.get("permissions")
            if perms_raw is not None:
                if isinstance(perms_raw, str):
                    permissions = perms_raw
                elif isinstance(perms_raw, list):
                    permissions = ", ".join(perms_raw)
                else:
                    permissions = str(perms_raw)
            else:
                permissions = existing.get("permissions")

            await conn.execute(
                'UPDATE admin_users SET username = $1, email = $2, role = $3, status = $4, permissions = $5, passcode = $6 WHERE id = $7::uuid',
                username, email, role, status, permissions, passcode, user_id
            )
            await self.add_security_log(
                event=f"Admin user details updated for {username}",
                user="System Admin",
                ip_address="127.0.0.1",
                status="SUCCESS",
                severity="WARNING"
            )

    async def update_access_point(self, ap_id: str, data: dict):
        # Parse ap_id as integer
        ap_id_str = str(ap_id).strip()
        target_int = None
        if ap_id_str.isdigit():
            target_int = int(ap_id_str)
        else:
            parts = ap_id_str.split('-', 1)
            if len(parts) > 1 and parts[1].isdigit():
                target_int = int(parts[1])
            else:
                import re
                match = re.search(r'\d+$', ap_id_str)
                if match:
                    target_int = int(match.group())
                    
        if target_int is None:
            raise Exception("Invalid access point ID format (must be integer)")

        pool = self.pool or await self.get_pool()
        async with pool.acquire() as conn:
            existing = await conn.fetchrow('SELECT resource, allowed_roles, auth_type FROM access_points WHERE id = $1::integer', target_int)
            if not existing:
                raise Exception("Access point not found")
            existing = dict(existing)
            
            resource = data.get("resource", existing.get("resource"))
            allowed_roles = data.get("allowed_roles", existing.get("allowed_roles"))
            auth_type = data.get("auth_type", existing.get("auth_type"))

            if isinstance(allowed_roles, list):
                allowed_roles = ", ".join(allowed_roles)

            await conn.execute(
                'UPDATE access_points SET resource = $1, allowed_roles = $2, auth_type = $3 WHERE id = $4::integer',
                resource, allowed_roles, auth_type, target_int
            )
            await self.add_security_log(
                event=f"Access point policy updated for {resource}",
                user="System Admin",
                ip_address="127.0.0.1",
                status="SUCCESS",
                severity="WARNING"
            )

    async def authenticate_admin(self, email: str, password: str, ip_address: str = "127.0.0.1"):
        try:
            pool = await self.get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    'SELECT username, role, permissions, status FROM admin_users WHERE email = $1 AND passcode = $2',
                    email, password
                )
                if not row:
                    try:
                        await self.add_security_log(
                            event=f"Failed login attempt: Invalid credentials for email {email}",
                            user="Unknown",
                            ip_address=ip_address,
                            status="FAILED",
                            severity="CRITICAL"
                        )
                    except Exception:
                        pass
                    return {"authenticated": False, "detail": "Incorrect email or password."}
                    
                user = dict(row)
                username = user["username"]
                    
                if user["status"] != "Active":
                    try:
                        await self.add_security_log(
                            event=f"Blocked login attempt for suspended operator: {username}",
                            user=username,
                            ip_address=ip_address,
                            status="FAILED",
                            severity="WARNING"
                        )
                    except Exception:
                        pass
                    return {"authenticated": False, "detail": "Account status is suspended."}
                    
                try:
                    await self.add_security_log(
                        event="User login successful",
                        user=username,
                        ip_address=ip_address,
                        status="SUCCESS",
                        severity="INFO"
                    )
                except Exception:
                    pass
                
                return {
                    "authenticated": True,
                    "username": username,
                    "role": user["role"],
                    "permissions": user["permissions"]
                }
        except Exception as db_err:
            import sys
            print(f"WARNING: Supabase database is unreachable during authenticate_admin: {db_err}. Falling back to in-memory admin credentials.", file=sys.stderr)
            # Fallback credentials seeder match
            fallbacks = [
                {
                    "username": "admin",
                    "email": "admin@gmail.com",
                    "role": "Administrator",
                    "permissions": "full_access",
                    "passcode": "Getmeds@1"
                },
                {
                    "username": "backenddepartment@gmail.com",
                    "email": "backenddepartment@gmail.com",
                    "role": "Administrator",
                    "permissions": "Full System Access, CMS Mutations, Schema Control",
                    "passcode": "GMP-ADMIN-2026"
                },
                {
                    "username": "Getmeds Admin",
                    "email": "admin@getmeds.com",
                    "role": "Administrator",
                    "permissions": "Full System Access, CMS Mutations, Schema Control",
                    "passcode": "GMP-GETMEDS-2026"
                }
            ]
            for fb_user in fallbacks:
                if fb_user["email"] == email and fb_user["passcode"] == password:
                    return {
                        "authenticated": True,
                        "username": fb_user["username"],
                        "role": fb_user["role"],
                        "permissions": fb_user["permissions"]
                    }
            return {"authenticated": False, "detail": "Incorrect email or password (Database Offline)."}

    async def get_user_by_username(self, username: str):
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT username, role, permissions, status, passcode FROM admin_users WHERE username = $1 OR email = $1',
                username
            )
            return dict(row) if row else None

    # ─── RBAC Action Control ──────────────────────────────────────────────────

    _ALL_COLLECTIONS = [
        'product', 'category', 'heroSlide', 'service',
        'dealOfDay', 'categoryBanner', 'team', 'faq', 'chatSession',
        '_security'
    ]

    _DEFAULT_WRITE_ROLES = {
        col: ['Administrator', 'Editor'] for col in _ALL_COLLECTIONS
    }

    async def get_distinct_roles(self):
        """Returns all unique roles currently assigned to admin_users or configured in access_points."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT DISTINCT role FROM (
                    SELECT role FROM admin_users
                    UNION
                    SELECT split_part(resource, '::', 1) AS role 
                    FROM access_points 
                    WHERE auth_type = 'RBAC_COLLECTION_V2' AND resource LIKE '%::%'
                ) as combined_roles
                WHERE role IS NOT NULL AND role != ''
                ORDER BY role ASC
            ''')
            return [r['role'] for r in rows]

    async def get_role_permissions(self):
        """
        Returns permissions matrix. Supports v2 format: { role: { collection: [actions] } }
        v2 rows: resource="role::collection", allowed_roles="read,create,edit,delete"
        Falls back to legacy { collection: [roles_with_write_access] } if no v2 data.
        Auto-seeds defaults if no RBAC entries exist yet.
        """
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            # Check for v2 entries first (resource contains "::")
            v2_count = await conn.fetchval(
                "SELECT COUNT(*) FROM access_points WHERE auth_type = 'RBAC_COLLECTION_V2'"
            )
            if v2_count and v2_count > 0:
                rows = await conn.fetch(
                    "SELECT resource, allowed_roles FROM access_points WHERE auth_type = 'RBAC_COLLECTION_V2'"
                )
                # Reconstruct { role: { collection: [actions] } }
                result = {}
                for row in rows:
                    key = row['resource']       # "Administrator::product"
                    if '::' not in key:
                        continue
                    role, collection = key.split('::', 1)
                    actions = [a.strip() for a in (row['allowed_roles'] or '').split(',') if a.strip()]
                    if role not in result:
                        result[role] = {}
                    result[role][collection] = actions
                return result

            # Fall back to legacy format
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM access_points WHERE auth_type = 'RBAC_COLLECTION'"
            )
            if count == 0:
                # Seed defaults: Administrator + Editor can write all collections
                for col, roles in self._DEFAULT_WRITE_ROLES.items():
                    await conn.execute(
                        "INSERT INTO access_points (resource, allowed_roles, auth_type) "
                        "VALUES ($1, $2, 'RBAC_COLLECTION') "
                        "ON CONFLICT DO NOTHING",
                        col, ', '.join(roles)
                    )

            rows = await conn.fetch(
                "SELECT resource, allowed_roles FROM access_points "
                "WHERE auth_type = 'RBAC_COLLECTION'"
            )
            result = {}
            for row in rows:
                col = row['resource']
                roles = [r.strip() for r in (row['allowed_roles'] or '').split(',') if r.strip()]
                result[col] = roles
            return result

    async def save_role_permissions(self, permissions: dict, fmt: str = "legacy"):
        """
        Persists the full permissions matrix.
        v2: permissions = { role: { collection: [actions] } }
            Stored as one row per role+collection:
              resource = "role::collection"  (e.g. "Administrator::product")
              allowed_roles = actions CSV    (e.g. "read,create,edit,delete")
              auth_type = 'RBAC_COLLECTION_V2'
        legacy: permissions = { collection: [roles] }
        """
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                if fmt == "v2":
                    await conn.execute(
                        "DELETE FROM access_points WHERE auth_type = 'RBAC_COLLECTION_V2'"
                    )
                    for role, col_data in permissions.items():
                        if not isinstance(col_data, dict):
                            continue
                        for collection, actions in col_data.items():
                            key = f"{role}::{collection}"
                            actions_csv = ','.join(a for a in actions if a)
                            await conn.execute(
                                "INSERT INTO access_points (resource, allowed_roles, auth_type) "
                                "VALUES ($1, $2, 'RBAC_COLLECTION_V2')",
                                key, actions_csv
                            )
                else:
                    await conn.execute(
                        "DELETE FROM access_points WHERE auth_type = 'RBAC_COLLECTION'"
                    )
                    for col, roles in permissions.items():
                        allowed = ', '.join(r.strip() for r in roles if r.strip())
                        await conn.execute(
                            "INSERT INTO access_points (resource, allowed_roles, auth_type) "
                            "VALUES ($1, $2, 'RBAC_COLLECTION')",
                            col, allowed
                        )

    async def delete_security_record(self, record_id: str) -> bool:
        record = await self.get_security_record_by_id(record_id)
        if not record:
            return False
        table = record.get("_table")
        if table == "admin_users":
            raise Exception("Admin users cannot be deleted for audit/safety reasons. Please suspend them instead.")
        elif table == "access_points":
            db_id = int(record.get("_id"))
            pool = self.pool or await self.get_pool()
            async with pool.acquire() as conn:
                await conn.execute('DELETE FROM access_points WHERE id = $1::integer', db_id)
                await self.add_security_log(
                    event=f"Access point policy deleted: {record.get('resource')}",
                    user="System Admin",
                    ip_address="127.0.0.1",
                    status="SUCCESS",
                    severity="WARNING"
                )
                return True
        return False

security_service = SecurityService()