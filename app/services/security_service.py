import os
import asyncio
# pyrefly: ignore [missing-import]
import asyncpg
from datetime import datetime

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
        return self.pool

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
            
            # Log action to audit trails table
            await self.add_security_log(
                event=f"User account status updated to {status} for {username}",
                user="System Admin",
                ip_address="127.0.0.1",
                status="SUCCESS",
                severity="WARNING"
            )

    async def authenticate_admin(self, passcode: str, ip_address: str = "127.0.0.1"):
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT username, role, permissions, status FROM admin_users WHERE passcode = $1',
                passcode
            )
            if not row:
                await self.add_security_log(
                    event="Failed login attempt: Invalid security key/passcode",
                    user="Unknown",
                    ip_address=ip_address,
                    status="FAILED",
                    severity="CRITICAL"
                )
                return {"authenticated": False, "detail": "Incorrect security key."}
                
            user = dict(row)
            username = user["username"]
                
            if user["status"] != "Active":
                await self.add_security_log(
                    event=f"Blocked login attempt for suspended operator: {username}",
                    user=username,
                    ip_address=ip_address,
                    status="FAILED",
                    severity="WARNING"
                )
                return {"authenticated": False, "detail": "Account status is suspended."}
                
            await self.add_security_log(
                event="User login successful",
                user=username,
                ip_address=ip_address,
                status="SUCCESS",
                severity="INFO"
            )
            
            return {
                "authenticated": True,
                "username": username,
                "role": user["role"],
                "permissions": user["permissions"]
            }

    async def get_user_by_username(self, username: str):
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT username, role, permissions, status, passcode FROM admin_users WHERE username = $1 OR email = $1',
                username
            )
            return dict(row) if row else None

security_service = SecurityService()
