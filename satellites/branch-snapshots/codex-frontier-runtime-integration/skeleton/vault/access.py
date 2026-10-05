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


class EnvelopeKMS:
    """Simple envelope encryption for data at rest."""

    def __init__(self, master_key: Optional[bytes] = None):
        self._master_key = master_key or secrets.token_bytes(32)

    def derive_key(self, context: str) -> bytes:
        """Derive a data encryption key from master key and context."""
        return hashlib.blake2b(self._master_key + context.encode(), digest_size=32).digest()

    def encrypt(self, plaintext: bytes, context: str) -> Dict[str, Any]:
        """Encrypt data with envelope encryption."""
        dek = self.derive_key(context)
        # Simple XOR-based encryption for demonstration
        # In production, use proper AES-GCM or ChaCha20-Poly1305
        ciphertext = bytes(p ^ dek[i % len(dek)] for i, p in enumerate(plaintext))
        return {
            "ciphertext": ciphertext.hex(),
            "context": context,
            "algorithm": "envelope-xor-v1",
        }

    def decrypt(self, envelope: Dict[str, Any]) -> bytes:
        """Decrypt envelope-encrypted data."""
        dek = self.derive_key(envelope["context"])
        ciphertext = bytes.fromhex(envelope["ciphertext"])
        return bytes(c ^ dek[i % len(dek)] for i, c in enumerate(ciphertext))

    def rotate(self) -> None:
        """Rotate the master key."""
        self._master_key = secrets.token_bytes(32)

    def stats(self) -> Dict[str, Any]:
        return {"algorithm": "envelope-xor-v1", "key_rotations": 0}
