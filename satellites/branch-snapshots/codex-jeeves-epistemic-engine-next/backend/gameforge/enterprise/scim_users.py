from __future__ import annotations
from typing import Any, Dict, List, Optional

from gameforge.enterprise.tenancy import TenantRegistry, MemberRole
from gameforge.enterprise.audit import AUDIT, audit_now


class ScimUserDirectory:
    def __init__(self, registry: TenantRegistry):
        self.registry = registry

    def list_users(
        self,
        *,
        tenant_id: Optional[str] = None,
        start_index: int = 1,
        count: int = 100,
        filter_expr: Optional[str] = None,
    ) -> Dict[str, Any]:
        start_index = max(1, start_index)
        count = max(1, min(count, 500))
        users_map: Dict[str, Dict[str, Any]] = {}
        tenants = (
            [self.registry.get(tenant_id)] if tenant_id else list(self.registry.tenants.values())
        )
        for tenant in tenants:
            if not tenant:
                continue
            for user_id, role in tenant.members.items():
                rec = users_map.setdefault(
                    user_id,
                    {
                        "id": user_id,
                        "userName": user_id,
                        "active": True,
                        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
                        "meta": {"resourceType": "User"},
                        "roles": [],
                        "tenants": [],
                    },
                )
                rec["roles"].append({"value": role.value, "tenant_id": tenant.tenant_id})
                rec["tenants"].append(tenant.tenant_id)
        users = list(users_map.values())
        if filter_expr:
            users = [u for u in users if self._match_filter(u, filter_expr)]
        total = len(users)
        begin = start_index - 1
        page = users[begin : begin + count]
        return {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": total,
            "startIndex": start_index,
            "itemsPerPage": len(page),
            "Resources": page,
        }

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        data = self.list_users(start_index=1, count=5000)
        for u in data["Resources"]:
            if u["id"] == user_id:
                return u
        return None

    async def create_or_upsert_user(self, payload: Dict[str, Any], actor: str) -> Dict[str, Any]:
        user_id = str(payload.get("id") or payload.get("userName") or payload.get("externalId") or "")
        if not user_id:
            raise ValueError("id or userName required")
        active = bool(payload.get("active", True))
        tenant_id = payload.get("tenant_id")
        role_raw = payload.get("role")
        if tenant_id:
            tenant = self.registry.get(tenant_id)
            if not tenant:
                raise ValueError(f"tenant not found: {tenant_id}")
            if not active:
                if user_id in tenant.members:
                    if tenant.members[user_id] == MemberRole.OWNER:
                        owners = [u for u, r in tenant.members.items() if r == MemberRole.OWNER]
                        if len(owners) <= 1:
                            raise ValueError("cannot deactivate last owner")
                    del tenant.members[user_id]
                    await self.registry.persist(tenant)
            else:
                role = self._role(role_raw)
                tenant.add_member(user_id, role)
                await self.registry.persist(tenant)
            await AUDIT.emit(
                audit_now(
                    tenant_id=tenant_id,
                    workspace_id=next(iter(tenant.workspaces.keys())),
                    actor_user_id=actor,
                    action="scim.user.upsert",
                    resource_type="user",
                    resource_id=user_id,
                    details={"active": active, "role": role_raw},
                )
            )
        return self.get_user(user_id) or {
            "id": user_id,
            "userName": user_id,
            "active": active,
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "meta": {"resourceType": "User"},
            "roles": [],
            "tenants": [tenant_id] if tenant_id else [],
        }

    async def patch_user(self, user_id: str, payload: Dict[str, Any], actor: str) -> Dict[str, Any]:
        active = payload.get("active")
        tenant_id = payload.get("tenant_id")
        role_raw = payload.get("role")
        ops = payload.get("Operations") or payload.get("operations")
        if ops and isinstance(ops, list):
            for op in ops:
                name = (op.get("op") or "").lower()
                path = (op.get("path") or "").lower()
                value = op.get("value")
                if name in {"replace", "add"} and path == "active":
                    active = value
                if name in {"replace", "add"} and "role" in path:
                    role_raw = value
                if name in {"replace", "add"} and "tenant" in path:
                    tenant_id = value
        existing = self.get_user(user_id)
        if not tenant_id and existing and len(existing.get("tenants") or []) == 1:
            tenant_id = existing["tenants"][0]
        body = {
            "id": user_id,
            "userName": user_id,
            "active": True if active is None else bool(active),
            "tenant_id": tenant_id,
            "role": role_raw,
        }
        return await self.create_or_upsert_user(body, actor)

    def _role(self, role_raw: Optional[str]) -> MemberRole:
        mapping = {
            "owner": MemberRole.OWNER,
            "admin": MemberRole.ADMIN,
            "operator": MemberRole.OPERATOR,
            "viewer": MemberRole.VIEWER,
        }
        if not role_raw:
            return MemberRole.OPERATOR
        key = str(role_raw).strip().lower()
        if key not in mapping:
            raise ValueError(f"unsupported role: {role_raw}")
        return mapping[key]

    def _match_filter(self, user: Dict[str, Any], expr: str) -> bool:
        e = expr.strip()
        for field in ("userName", "id"):
            prefix = f'{field} eq "'
            if e.startswith(prefix) and e.endswith('"'):
                return str(user.get(field)) == e[len(prefix) : -1]
        needle = e.lower().strip('"')
        return needle in str(user.get("id", "")).lower()
