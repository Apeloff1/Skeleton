from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class MemberRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class TenantStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"


# role -> allowed actions
_ROLE_CAPS = {
    MemberRole.OWNER: {"read", "write", "admin", "billing"},
    MemberRole.ADMIN: {"read", "write", "admin"},
    MemberRole.OPERATOR: {"read", "write"},
    MemberRole.VIEWER: {"read"},
}


@dataclass
class Workspace:
    workspace_id: str
    name: str


@dataclass
class Tenant:
    tenant_id: str
    name: str
    status: TenantStatus = TenantStatus.ACTIVE
    members: Dict[str, MemberRole] = field(default_factory=dict)
    workspaces: Dict[str, Workspace] = field(default_factory=dict)

    def add_member(self, user_id: str, role: MemberRole):
        self.members[user_id] = role

    def can(self, user_id: str, action: str) -> bool:
        role = self.members.get(user_id)
        if not role:
            return False
        return action in _ROLE_CAPS.get(role, set())


class TenantRegistry:
    def __init__(self):
        self.tenants: Dict[str, Tenant] = {}
        self._store = None

    def get(self, tenant_id: str) -> Optional[Tenant]:
        return self.tenants.get(tenant_id)

    def upsert(self, tenant: Tenant):
        self.tenants[tenant.tenant_id] = tenant

    def require_access(self, tenant_id: str, user_id: str, action: str) -> Tenant:
        tenant = self.get(tenant_id)
        if not tenant:
            raise KeyError(f"tenant not found: {tenant_id}")
        if not tenant.can(user_id, action):
            raise PermissionError(f"user {user_id} cannot {action} on {tenant_id}")
        return tenant

    async def persist(self, tenant: Tenant):
        self.upsert(tenant)
        if self._store is not None:
            await self._store.save_tenant(tenant)


TENANT_REGISTRY = TenantRegistry()


def bootstrap_local_tenant(user_id: str = "local") -> Tenant:
    tid = "local"
    t = TENANT_REGISTRY.get(tid)
    if t is None:
        t = Tenant(
            tenant_id=tid,
            name="Local",
            members={user_id: MemberRole.OWNER},
            workspaces={"default": Workspace("default", "Default")},
        )
        TENANT_REGISTRY.upsert(t)
    elif user_id not in t.members:
        t.add_member(user_id, MemberRole.OWNER)
    return t
