import os
from datetime import datetime
from app.services.sanity_service import sanity_security_service

class SecurityService:
    def __init__(self):
        self.seeded = False

    async def _init_db(self):
        """
        Verify if security collections are initialized in Sanity. If empty, seed mock administrative records.
        """
        if self.seeded:
            return
        
        try:
            # Check if adminUser documents exist and have passcode field
            users = await sanity_security_service.query_sanity('*[_type == "adminUser"]')
            has_passcode = len(users) > 0 and all("passcode" in u for u in users)
            if len(users) == 0 or not has_passcode:
                print("DEBUG: Security database has no passcodes or is empty in Sanity. Seeding/re-seeding mock records...")
                
                # Delete existing to prevent duplication and start fresh
                delete_mutations = []
                for doc in users:
                    delete_mutations.append({"delete": {"id": doc["_id"]}})
                
                existing_points = await sanity_security_service.query_sanity('*[_type in ["accessPoint", "securityLog"]]')
                for doc in existing_points:
                    delete_mutations.append({"delete": {"id": doc["_id"]}})
                
                if delete_mutations:
                    await sanity_security_service.mutate_sanity(delete_mutations)
                
                mutations = []
                
                # 1. Seed Admin Users with secure, custom default passcodes
                users_data = [
                    ("Jessica Parker", "Administrator", "Active", "Full System Access, CMS Mutations, Schema Control", "2026-01-15T08:30:00Z", "GMAU0000-0001", "GMP-JESSICA-2026"),
                    ("Michael Chang", "Security Officer", "Active", "Log Audit, Access Control, Policy Management", "2026-02-10T14:45:00Z", "GMAU0000-0002", "GMP-MICHAEL-2026"),
                    ("Sarah Jenkins", "Editor", "Active", "Product Mutation, Category Updates, FAQ Creation", "2026-03-01T09:15:00Z", "GMAU0000-0003", "GMP-SARAH-2026"),
                    ("Guest Auditor", "Auditor", "Suspended", "ReadOnly Logs, ReadOnly Documents", "2026-04-20T11:00:00Z", "GMAU0000-0004", "GMP-AUDITOR-2026")
                ]
                for username, role, status, permissions, created, uid, passcode in users_data:
                    mutations.append({
                        "create": {
                            "_id": uid,
                            "_type": "adminUser",
                            "username": username,
                            "role": role,
                            "status": status,
                            "permissions": permissions,
                            "passcode": passcode,
                            "created_at": created
                        }
                    })
                
                # 2. Seed Access Policies
                access_data = [
                    ("/api/admin/collection/*", "Administrator, Editor", "Admin Token Header Required", "GMAP0000-0001"),
                    ("/api/admin/document/*", "Administrator", "Admin Token Header Required", "GMAP0000-0002"),
                    ("/api/admin/stats", "Administrator, Security Officer, Editor, Auditor", "Admin Token Header Required", "GMAP0000-0003"),
                    ("/api/security/*", "Administrator, Security Officer", "Admin Token Header Required", "GMAP0000-0004")
                ]
                for path, roles, auth_type, pid in access_data:
                    mutations.append({
                        "create": {
                            "_id": pid,
                            "_type": "accessPoint",
                            "resource": path,
                            "allowed_roles": roles,
                            "auth_type": auth_type
                        }
                    })
                
                # 3. Seed Security Logs
                logs_data = [
                    ("2026-05-18T01:12:00Z", "User login successful", "Jessica Parker", "192.168.1.100", "SUCCESS", "INFO", "GMSL0000-0001"),
                    ("2026-05-18T01:15:22Z", "Document database prefix ID migration executed", "Jessica Parker", "192.168.1.100", "SUCCESS", "WARNING", "GMSL0000-0002"),
                    ("2026-05-18T01:30:45Z", "Database collection Product created (ID: GMP0000-0009)", "Sarah Jenkins", "192.168.1.104", "SUCCESS", "INFO", "GMSL0000-0003"),
                    ("2026-05-18T02:02:11Z", "Attempted login with invalid token", "Unknown", "103.55.12.88", "FAILED", "CRITICAL", "GMSL0000-0004"),
                    ("2026-05-18T02:15:00Z", "Security policy modified (Allowed roles updated)", "Michael Chang", "192.168.1.102", "SUCCESS", "HIGH", "GMSL0000-0005"),
                    ("2026-05-18T02:22:45Z", "User account 'Guest Auditor' status set to Suspended", "Michael Chang", "192.168.1.102", "SUCCESS", "WARNING", "GMSL0000-0006")
                ]
                for stamp, event, user, ip, status, severity, lid in logs_data:
                    mutations.append({
                        "create": {
                            "_id": lid,
                            "_type": "securityLog",
                            "timestamp": stamp,
                            "event": event,
                            "user": user,
                            "ip_address": ip,
                            "status": status,
                            "severity": severity
                        }
                    })
                
                await sanity_security_service.mutate_sanity(mutations)
                print("DEBUG: Mock administrative records with passcodes seeded successfully inside Sanity!")
            
            self.seeded = True
        except Exception as e:
            print(f"ERROR: Seeding security collections failed: {str(e)}")

    async def get_admin_users(self):
        await self._init_db()
        groq_query = '*[_type == "adminUser"] | order(created_at asc)'
        return await sanity_security_service.query_sanity(groq_query)

    async def get_security_logs(self):
        await self._init_db()
        groq_query = '*[_type == "securityLog"] | order(timestamp desc)'
        return await sanity_security_service.query_sanity(groq_query)

    async def get_access_points(self):
        await self._init_db()
        groq_query = '*[_type == "accessPoint"] | order(_id asc)'
        return await sanity_security_service.query_sanity(groq_query)

    async def add_security_log(self, event: str, user: str, ip_address: str, status: str, severity: str):
        await self._init_db()
        now = datetime.utcnow().isoformat() + "Z"
        
        # Calculate next index for the securityLog sequential ID
        count = await sanity_security_service.query_sanity('count(*[_type == "securityLog"])')
        new_idx = count + 1
        log_id = f"GMSL0000-{new_idx:04d}"
        
        mutations = [{
            "create": {
                "_id": log_id,
                "_type": "securityLog",
                "timestamp": now,
                "event": event,
                "user": user,
                "ip_address": ip_address,
                "status": status,
                "severity": severity
            }
        }]
        await sanity_security_service.mutate_sanity(mutations)

    async def update_user_status(self, username: str, status: str):
        await self._init_db()
        
        # Find user document ID by username matching
        query = '*[_type == "adminUser" && username == $username][0]._id'
        user_id = await sanity_security_service.query_sanity(query, {"$username": username})
        
        if not user_id:
            raise Exception(f"Admin user with username '{username}' not found in Sanity.")
            
        mutations = [{
            "patch": {
                "id": user_id,
                "set": {
                    "status": status
                }
            }
        }]
        await sanity_security_service.mutate_sanity(mutations)
        
        # Write to securityLog audit trail
        await self.add_security_log(
            event=f"User account status updated to {status} for {username}",
            user="System Admin",
            ip_address="127.0.0.1",
            status="SUCCESS",
            severity="WARNING"
        )

    async def authenticate_admin(self, passcode: str, ip_address: str = "127.0.0.1"):
        await self._init_db()
        
        # Query matching user in security dataset by passcode only
        query = '*[_type == "adminUser" && passcode == $passcode][0]'
        user = await sanity_security_service.query_sanity(query, {"$passcode": passcode})
        
        if not user:
            # Audit Trail for invalid passcode
            await self.add_security_log(
                event="Failed login attempt: Invalid security key/passcode",
                user="Unknown",
                ip_address=ip_address,
                status="FAILED",
                severity="CRITICAL"
            )
            return {"authenticated": False, "detail": "Incorrect security key."}
            
        username = user.get("username", "Unknown")
            
        if user.get("status") != "Active":
            # Audit Trail for suspended user
            await self.add_security_log(
                event=f"Blocked login attempt for suspended operator: {username}",
                user=username,
                ip_address=ip_address,
                status="FAILED",
                severity="WARNING"
            )
            return {"authenticated": False, "detail": "Account status is suspended."}
            
        # Audit Trail for successful login
        await self.add_security_log(
            event="User login successful",
            user=username,
            ip_address=ip_address,
            status="SUCCESS",
            severity="INFO"
        )
        
        return {
            "authenticated": True,
            "username": user["username"],
            "role": user["role"],
            "permissions": user["permissions"]
        }

security_service = SecurityService()
