"""
Skeleton Vault — Access control and key management

Provides:
- AccessPolicy: Role-based access control
- Role: Named role with permissions
- EnvelopeKMS: Key envelope encryption
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set


class Permission(Enum):
    READ = auto()
    WRITE = auto()
    EXECUTE = auto()
    ADMIN = auto()


@dataclass(frozen=True)
class Role:
    """A named role with a set of permissions."""
    name: str
    permissions: Set[Permission] = field(default_factory=set)

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions or Permission.ADMIN in self.permissions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "permissions": [p.name for p in self.permissions],
        }


# Predefined roles
ROLE_GUEST = Role("guest", {Permission.READ})
ROLE_USER = Role("user", {Permission.READ, Permission.WRITE})
ROLE_OPERATOR = Role("operator", {Permission.READ, Permission.WRITE, Permission.EXECUTE})
ROLE_ADMIN = Role("admin", {Permission.READ, Permission.WRITE, Permission.EXECUTE, Permission.ADMIN})


@dataclass
class AccessPolicy:
    """Role-based access policy for resources."""
    resource: str
    grants: Dict[str, Role] = field(default_factory=dict)  # principal -> role

    def grant(self, principal: str, role: Role) -> None:
        self.grants[principal] = role

    def check(self, principal: str, permission: Permission) -> bool:
        role = self.grants.get(principal, ROLE_GUEST)
        return role.can(permission)

    def audit(self) -> Dict[str, Any]:
        return {
            "resource": self.resource,
            "principals": len(self.grants),
            "roles": {p: r.name for p, r in self.grants.items()},
        }


from skeleton.vault.kms import EnvelopeKMS  # compatibility export
