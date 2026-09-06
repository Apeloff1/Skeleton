"""
Skeleton Vault Package

Exports:
- AccessPolicy: Role-based access control
- Role: Named role with permissions
- Permission: Permission enum
- EnvelopeKMS: Key envelope encryption
- Predefined roles: ROLE_GUEST, ROLE_USER, ROLE_OPERATOR, ROLE_ADMIN
"""

from skeleton.vault.access import (
    ROLE_ADMIN,
    ROLE_GUEST,
    ROLE_OPERATOR,
    ROLE_USER,
    AccessPolicy,
    EnvelopeKMS,
    Permission,
    Role,
)

__all__ = [
    "AccessPolicy",
    "Role",
    "Permission",
    "EnvelopeKMS",
    "ROLE_GUEST",
    "ROLE_USER",
    "ROLE_OPERATOR",
    "ROLE_ADMIN",
]
