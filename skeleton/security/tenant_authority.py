"""Tenant/workspace authority boundaries for caches, replays, and artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import hmac
from typing import Any


class TenantAuthorityError(PermissionError):
    """Tenant or workspace authority failed closed."""


def _token(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be normalized non-empty text")
    if len(value) > 256 or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError(f"invalid {field}")
    return value


def tenant_cache_key(
    *,
    tenant_id: str,
    workspace_id: str,
    namespace: str,
    logical_key: str,
) -> str:
    """Return a non-secret stable key that always includes authority identity."""
    payload = {
        "tenant_id": _token(tenant_id, "tenant_id"),
        "workspace_id": _token(workspace_id, "workspace_id"),
        "namespace": _token(namespace, "namespace"),
        "logical_key": _token(logical_key, "logical_key"),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "tenant-cache:v1:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class DeadLetterEnvelope:
    message_id: str
    tenant_id: str
    workspace_id: str
    payload_digest: str

    def __post_init__(self) -> None:
        _token(self.message_id, "message_id")
        _token(self.tenant_id, "tenant_id")
        _token(self.workspace_id, "workspace_id")
        if len(self.payload_digest) != 64:
            raise ValueError("payload_digest must be SHA-256 hex")
        try:
            bytes.fromhex(self.payload_digest)
        except ValueError as exc:
            raise ValueError("payload_digest must be hexadecimal") from exc

    def authorize_replay(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        payload_digest: str,
    ) -> None:
        if not hmac.compare_digest(self.tenant_id, _token(tenant_id, "tenant_id")):
            raise TenantAuthorityError("dead-letter tenant mismatch")
        if not hmac.compare_digest(
            self.workspace_id,
            _token(workspace_id, "workspace_id"),
        ):
            raise TenantAuthorityError("dead-letter workspace mismatch")
        if not hmac.compare_digest(self.payload_digest, payload_digest):
            raise TenantAuthorityError("dead-letter payload identity mismatch")


@dataclass(frozen=True, slots=True)
class ArtifactAuthority:
    artifact_id: str
    tenant_id: str
    workspace_id: str
    content_digest: str

    def __post_init__(self) -> None:
        _token(self.artifact_id, "artifact_id")
        _token(self.tenant_id, "tenant_id")
        _token(self.workspace_id, "workspace_id")
        if len(self.content_digest) != 64:
            raise ValueError("content_digest must be SHA-256 hex")
        try:
            bytes.fromhex(self.content_digest)
        except ValueError as exc:
            raise ValueError("content_digest must be hexadecimal") from exc

    def authorize(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
    ) -> str:
        if not hmac.compare_digest(self.tenant_id, _token(tenant_id, "tenant_id")):
            raise TenantAuthorityError("artifact tenant mismatch")
        if not hmac.compare_digest(
            self.workspace_id,
            _token(workspace_id, "workspace_id"),
        ):
            raise TenantAuthorityError("artifact workspace mismatch")
        return self.content_digest


def payload_digest(payload: Any) -> str:
    try:
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("payload must be finite canonical JSON") from exc
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "ArtifactAuthority",
    "DeadLetterEnvelope",
    "TenantAuthorityError",
    "payload_digest",
    "tenant_cache_key",
]
