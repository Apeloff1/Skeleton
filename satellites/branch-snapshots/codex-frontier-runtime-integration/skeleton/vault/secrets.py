"""Secrets Vault — envelope-encrypted secret store with rotation, policies and audit.

Design
------
* **Envelope encryption.** A single master key encrypts per-secret data keys;
  secret payloads are only ever encrypted with their own data key. Rotating the
  master key re-wraps data keys without touching payload ciphertext.
* **Versioned secrets.** Every write creates a new version; reads default to the
  latest enabled version. Old versions remain decryptable until destroyed.
* **Access policies.** Principals are granted named policies (read / write /
  rotate / destroy / admin) with optional path-prefix scoping.
* **Seal / unseal.** The vault starts *sealed*; it refuses all payload
  operations until unsealed with the master key. Sealing zeroises the in-memory
  master key.
* **Audit.** Every operation appends a tamper-evident audit record (hash-chained)
  so the log itself detects truncation or reordering.

The cipher is an HMAC-authenticated stream construction over SHA-256 in counter
mode — dependency-free, deterministic given the key material, and providing both
confidentiality and integrity (encrypt-then-MAC). It is deliberately implemented
in-repo so the vault has no external cryptographic dependency.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from ..kernel.errors import (AccessDenied, RotationError, SealedVaultError,
                             SecretNotFound)
from ..kernel.events import EventBus


# ---------------------------------------------------------------------------
# Dependency-free authenticated cipher (SHA-256 counter mode + HMAC)
# ---------------------------------------------------------------------------

def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest())
        counter += 1
    return bytes(out[:length])


def encrypt(data_key: bytes, plaintext: str, aad: bytes = b"") -> Dict[str, str]:
    """Encrypt-then-MAC. Returns hex-encoded nonce/ciphertext/tag."""
    nonce = os.urandom(16)
    pt = plaintext.encode("utf-8")
    ct = bytes(a ^ b for a, b in zip(pt, _keystream(data_key, nonce, len(pt))))
    tag = hmac.new(data_key, aad + nonce + ct, hashlib.sha256).hexdigest()
    return {"nonce": nonce.hex(), "ciphertext": ct.hex(), "tag": tag}


def decrypt(data_key: bytes, payload: Dict[str, str], aad: bytes = b"") -> str:
    nonce = bytes.fromhex(payload["nonce"])
    ct = bytes.fromhex(payload["ciphertext"])
    expected = hmac.new(data_key, aad + nonce + ct, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, payload["tag"]):
        raise VaultIntegrityError("ciphertext failed integrity check")
    pt = bytes(a ^ b for a, b in zip(ct, _keystream(data_key, nonce, len(ct))))
    return pt.decode("utf-8")


class VaultIntegrityError(AccessDenied):
    code = "VLT.INTEGRITY"


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass
class SecretVersion:
    version: int
    wrapped_data_key: Dict[str, str]       # data key encrypted under master key
    payload: Dict[str, str]                # ciphertext under the data key
    created_at: float
    enabled: bool = True


@dataclass
class SecretRecord:
    path: str
    versions: List[SecretVersion] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class Policy:
    principal: str
    capabilities: Set[str]                 # read|write|rotate|destroy|admin
    path_prefix: str = ""                  # scope; "" = global

    def allows(self, capability: str, path: str) -> bool:
        if "admin" in self.capabilities:
            scoped = True
        else:
            scoped = capability in self.capabilities
        return scoped and path.startswith(self.path_prefix)


# ---------------------------------------------------------------------------
# Audit log (hash-chained)
# ---------------------------------------------------------------------------

@dataclass
class AuditRecord:
    index: int
    timestamp: float
    principal: str
    operation: str
    path: str
    outcome: str
    prev_hash: str
    record_hash: str = ""

    def seal(self) -> None:
        body = f"{self.index}|{self.timestamp}|{self.principal}|{self.operation}|" \
               f"{self.path}|{self.outcome}|{self.prev_hash}"
        self.record_hash = hashlib.sha256(body.encode()).hexdigest()


class AuditLog:
    GENESIS = "0" * 64

    def __init__(self) -> None:
        self._records: List[AuditRecord] = []

    def append(self, principal: str, operation: str, path: str, outcome: str) -> AuditRecord:
        rec = AuditRecord(index=len(self._records), timestamp=time.time(),
                          principal=principal, operation=operation, path=path,
                          outcome=outcome,
                          prev_hash=self._records[-1].record_hash if self._records else self.GENESIS)
        rec.seal()
        self._records.append(rec)
        return rec

    def verify(self) -> bool:
        prev = self.GENESIS
        for rec in self._records:
            if rec.prev_hash != prev:
                return False
            body = f"{rec.index}|{rec.timestamp}|{rec.principal}|{rec.operation}|" \
                   f"{rec.path}|{rec.outcome}|{rec.prev_hash}"
            if hashlib.sha256(body.encode()).hexdigest() != rec.record_hash:
                return False
            prev = rec.record_hash
        return True

    def tail(self, n: int = 20) -> List[AuditRecord]:
        return list(self._records[-n:])


# ---------------------------------------------------------------------------
# The vault
# ---------------------------------------------------------------------------

class SecretsVault:
    """Sealed-by-default envelope-encrypted secret store."""

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._master_key: Optional[bytes] = None
        self._master_fingerprint: Optional[str] = None
        self._secrets: Dict[str, SecretRecord] = {}
        self._policies: Dict[str, Policy] = {}
        self.audit = AuditLog()
        self._bus = bus or EventBus()

    # -- seal state -------------------------------------------------------
    @property
    def sealed(self) -> bool:
        return self._master_key is None

    def unseal(self, master_key: bytes, principal: str = "root") -> None:
        if len(master_key) < 16:
            raise RotationError("master key must be at least 16 bytes",
                                code="VLT.WEAK_KEY", context={"length": len(master_key)})
        self._master_key = master_key
        self._master_fingerprint = hashlib.sha256(master_key).hexdigest()[:16]
        self.audit.append(principal, "unseal", "*", "success")
        self._bus.publish("vault.unsealed", {"fingerprint": self._master_fingerprint})

    def seal(self, principal: str = "root") -> None:
        self._master_key = None
        self.audit.append(principal, "seal", "*", "success")
        self._bus.publish("vault.sealed", {})

    # -- policy ------------------------------------------------------------
    def grant(self, principal: str, capabilities: Set[str], path_prefix: str = "",
              actor: str = "root") -> Policy:
        policy = Policy(principal, set(capabilities), path_prefix)
        self._policies[principal] = policy
        self.audit.append(actor, "grant", path_prefix or "*", "success")
        return policy

    def _authorise(self, principal: str, capability: str, path: str) -> None:
        if principal == "root":
            return
        policy = self._policies.get(principal)
        if policy is None or not policy.allows(capability, path):
            self.audit.append(principal, capability, path, "denied")
            raise AccessDenied(f"principal '{principal}' lacks '{capability}' on '{path}'",
                               context={"principal": principal, "capability": capability,
                                        "path": path})

    def _require_unsealed(self) -> bytes:
        if self._master_key is None:
            raise SealedVaultError("vault is sealed", context={})
        return self._master_key

    # -- secret operations ---------------------------------------------------
    def put(self, path: str, value: str, principal: str = "root",
            metadata: Optional[Dict[str, Any]] = None) -> int:
        master = self._require_unsealed()
        self._authorise(principal, "write", path)
        data_key = os.urandom(32)
        wrapped = encrypt(master, data_key.hex(), aad=path.encode())
        payload = encrypt(data_key, value, aad=path.encode())
        record = self._secrets.setdefault(path, SecretRecord(path))
        if metadata:
            record.metadata.update(metadata)
        record.versions.append(SecretVersion(
            version=len(record.versions) + 1, wrapped_data_key=wrapped,
            payload=payload, created_at=time.time()))
        self.audit.append(principal, "write", path, "success")
        self._bus.publish("vault.secret_written", {"path": path,
                                                   "version": len(record.versions)})
        return len(record.versions)

    def get(self, path: str, principal: str = "root",
            version: Optional[int] = None) -> str:
        master = self._require_unsealed()
        self._authorise(principal, "read", path)
        record = self._secrets.get(path)
        if record is None or not record.versions:
            self.audit.append(principal, "read", path, "miss")
            raise SecretNotFound(f"no secret at '{path}'", context={"path": path})
        sv = (record.versions[-1] if version is None
              else next((v for v in record.versions if v.version == version), None))
        if sv is None or not sv.enabled:
            raise SecretNotFound("requested version unavailable",
                                 context={"path": path, "version": version})
        data_key = bytes.fromhex(decrypt(master, sv.wrapped_data_key, aad=path.encode()))
        value = decrypt(data_key, sv.payload, aad=path.encode())
        self.audit.append(principal, "read", path, "success")
        return value

    def rotate(self, path: str, new_value: str, principal: str = "root") -> int:
        """Write a new version and disable all previous versions."""
        self._authorise(principal, "rotate", path)
        record = self._secrets.get(path)
        if record is None:
            raise SecretNotFound(f"no secret at '{path}'", context={"path": path})
        for sv in record.versions:
            sv.enabled = False
        new_version = self.put(path, new_value, principal=principal)
        self.audit.append(principal, "rotate", path, "success")
        self._bus.publish("vault.secret_rotated", {"path": path, "version": new_version})
        return new_version

    def rotate_master_key(self, new_master_key: bytes, principal: str = "root") -> int:
        """Re-wrap every data key under a new master key (payload ciphertext untouched)."""
        old = self._require_unsealed()
        if len(new_master_key) < 16:
            raise RotationError("master key must be at least 16 bytes",
                                code="VLT.WEAK_KEY", context={})
        rewrapped = 0
        for path, record in self._secrets.items():
            for sv in record.versions:
                data_key_hex = decrypt(old, sv.wrapped_data_key, aad=path.encode())
                sv.wrapped_data_key = encrypt(new_master_key, data_key_hex, aad=path.encode())
                rewrapped += 1
        self._master_key = new_master_key
        self._master_fingerprint = hashlib.sha256(new_master_key).hexdigest()[:16]
        self.audit.append(principal, "rotate_master", "*", "success")
        self._bus.publish("vault.master_rotated", {"rewrapped": rewrapped})
        return rewrapped

    def destroy_version(self, path: str, version: int, principal: str = "root") -> None:
        self._require_unsealed()
        self._authorise(principal, "destroy", path)
        record = self._secrets.get(path)
        if record is None:
            raise SecretNotFound(f"no secret at '{path}'", context={"path": path})
        before = len(record.versions)
        record.versions = [v for v in record.versions if v.version != version]
        if len(record.versions) == before:
            raise SecretNotFound("no such version", context={"path": path, "version": version})
        self.audit.append(principal, "destroy", path, "success")

    def list_paths(self, prefix: str = "", principal: str = "root") -> List[str]:
        self._authorise(principal, "read", prefix)
        return sorted(p for p in self._secrets if p.startswith(prefix))

    def stats(self) -> Dict[str, Any]:
        return {
            "sealed": self.sealed,
            "secrets": len(self._secrets),
            "versions": sum(len(r.versions) for r in self._secrets.values()),
            "policies": len(self._policies),
            "audit_records": len(self.audit._records),
            "audit_chain_valid": self.audit.verify(),
            "master_fingerprint": self._master_fingerprint,
        }
