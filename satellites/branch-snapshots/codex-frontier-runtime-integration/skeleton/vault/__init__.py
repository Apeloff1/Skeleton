"""
Skeleton Vault Package

Exports:
- AccessPolicy: Role-based access control
- Role: Named role with permissions
- Permission: Permission enum
- EnvelopeKMS: Key envelope encryption
- Predefined roles: ROLE_GUEST, ROLE_USER, ROLE_OPERATOR, ROLE_ADMIN
- AuditLog / WORM refuse-on-boot helpers (AuditChainBroken, verify_chain_or_refuse)
- ShamirSeal: secret sharing seal
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
from skeleton.vault.audit import (
    AuditChainBroken,
    AuditEntry,
    AuditError,
    AuditLog,
    verify_chain_or_refuse,
)
from skeleton.vault.shamir import ShamirSeal

__all__ = [
    "AccessPolicy",
    "Role",
    "Permission",
    "EnvelopeKMS",
    "ROLE_GUEST",
    "ROLE_USER",
    "ROLE_OPERATOR",
    "ROLE_ADMIN",
    "AuditChainBroken",
    "AuditEntry",
    "AuditError",
    "AuditLog",
    "verify_chain_or_refuse",
    "ShamirSeal",
]
