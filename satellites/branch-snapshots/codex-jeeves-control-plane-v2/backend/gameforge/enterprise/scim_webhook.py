from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from gameforge.enterprise.tenancy import MemberRole, TENANT_REGISTRY
from gameforge.enterprise.audit import AUDIT, audit_now


class ScimOp(str, Enum):
    UPSERT_USER = "upsert_user"
    DEACTIVATE_USER = "deactivate_user"
    ADD_TO_TENANT = "add_to_tenant"
    REMOVE_FROM_TENANT = "remove_from_tenant"
    SET_ROLE = "set_role"


@dataclass
class ScimEvent:
    op: ScimOp
    user_id: str
    email: Optional[str] = None
    tenant_id: Optional[str] = None
    role: Optional[str] = None
    active: bool = True
    raw: Optional[Dict[str, Any]] = None


class ScimWebhookProcessor:
    ROLE_MAP = {
        "owner": MemberRole.OWNER,
        "admin": MemberRole.ADMIN,
        "operator": MemberRole.OPERATOR,
        "viewer": MemberRole.VIEWER,
        "gf-owner": MemberRole.OWNER,
        "gf-admin": MemberRole.ADMIN,
        "gf-operator": MemberRole.OPERATOR,
        "gf-viewer": MemberRole.VIEWER,
    }

    def normalize_payload(self, payload: Dict[str, Any]) -> List[ScimEvent]:
        if "ops" in payload and isinstance(payload["ops"], list):
            return [
                ScimEvent(
                    op=ScimOp(item["op"]),
                    user_id=str(item["user_id"]),
                    email=item.get("email"),
                    tenant_id=item.get("tenant_id"),
                    role=item.get("role"),
                    active=bool(item.get("active", True)),
                    raw=item,
                )
                for item in payload["ops"]
            ]
        user_id = str(payload.get("user_id") or payload.get("id") or payload.get("sub") or "")
        if not user_id:
            raise ValueError("user_id required")
        op = payload.get("op") or ("upsert_user" if payload.get("active", True) else "deactivate_user")
        return [
            ScimEvent(
                op=ScimOp(op),
                user_id=user_id,
                email=payload.get("email"),
                tenant_id=payload.get("tenant_id"),
                role=payload.get("role"),
                active=bool(payload.get("active", True)),
                raw=payload,
            )
        ]

    def _parse_role(self, role: Optional[str]) -> MemberRole:
        if not role:
            return MemberRole.OPERATOR
        key = role.strip().lower()
        if key not in self.ROLE_MAP:
            raise ValueError(f"Unsupported role: {role}")
        return self.ROLE_MAP[key]

    async def apply(self, event: ScimEvent, actor_user_id: str = "scim-webhook") -> Dict[str, Any]:
        result: Dict[str, Any] = {"op": event.op.value, "user_id": event.user_id, "status": "ok"}

        if event.op in (ScimOp.ADD_TO_TENANT, ScimOp.SET_ROLE, ScimOp.UPSERT_USER):
            if not event.tenant_id:
                if event.op == ScimOp.UPSERT_USER:
                    result["note"] = "user upsert acknowledged (no tenant mapping)"
                    return result
                raise ValueError("tenant_id required for this op")
            tenant = TENANT_REGISTRY.get(event.tenant_id)
            if not tenant:
                raise ValueError(f"tenant not found: {event.tenant_id}")
            role = self._parse_role(event.role)
            tenant.add_member(event.user_id, role)
            await TENANT_REGISTRY.persist(tenant)
            await AUDIT.emit(
                audit_now(
                    tenant_id=event.tenant_id,
                    workspace_id=next(iter(tenant.workspaces.keys())),
                    actor_user_id=actor_user_id,
                    action="scim.member.upsert",
                    resource_type="member",
                    resource_id=event.user_id,
                    details={"role": role.value, "email": event.email, "op": event.op.value},
                )
            )
            result["tenant_id"] = event.tenant_id
            result["role"] = role.value
            return result

        if event.op in (ScimOp.REMOVE_FROM_TENANT, ScimOp.DEACTIVATE_USER):
            if not event.tenant_id:
                result["note"] = "deactivate acknowledged (no tenant mapping)"
                return result
            tenant = TENANT_REGISTRY.get(event.tenant_id)
            if not tenant:
                raise ValueError(f"tenant not found: {event.tenant_id}")
            if event.user_id in tenant.members:
                if tenant.members[event.user_id] == MemberRole.OWNER:
                    owners = [u for u, r in tenant.members.items() if r == MemberRole.OWNER]
                    if len(owners) <= 1:
                        raise ValueError("cannot remove last owner via SCIM")
                del tenant.members[event.user_id]
                await TENANT_REGISTRY.persist(tenant)
                await AUDIT.emit(
                    audit_now(
                        tenant_id=event.tenant_id,
                        workspace_id=next(iter(tenant.workspaces.keys())),
                        actor_user_id=actor_user_id,
                        action="scim.member.remove",
                        resource_type="member",
                        resource_id=event.user_id,
                        details={"op": event.op.value},
                    )
                )
                result["removed"] = True
            else:
                result["removed"] = False
                result["note"] = "user not in tenant"
            return result

        raise ValueError(f"unsupported op: {event.op}")
