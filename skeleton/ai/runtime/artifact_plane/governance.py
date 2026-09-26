"""Governed canonical artifact storage.

This module owns tenant-scoped artifact bytes under one filesystem root. Lifecycle
metadata is registered before the durable replace, while physical paths are derived
from hashes rather than caller-controlled path fragments.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import quote, unquote

from skeleton.vault.data_lifecycle import LifecycleError, LifecycleState
from skeleton.vault.governance_registry import GovernanceRegistry


class GovernedArtifactError(RuntimeError):
    """Canonical artifact ownership contract was violated."""


def _required_text(value: object, field: str, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GovernedArtifactError(f"{field} is required")
    normalized = value.strip()
    if normalized != value:
        raise GovernedArtifactError(f"{field} must be normalized")
    if len(normalized) > maximum:
        raise GovernedArtifactError(f"{field} exceeds maximum length")
    return normalized


def _digest(*values: str) -> str:
    material = "\x1f".join(values).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True, slots=True)
class GovernedArtifactRecord:
    record_id: str
    tenant_id: str
    artifact_id: str
    source_ref: str
    size_bytes: int
    sha256: str
    created_at: float

    def as_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "tenant_id": self.tenant_id,
            "artifact_id": self.artifact_id,
            "source_ref": self.source_ref,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "created_at": self.created_at,
        }


class GovernedArtifactStore:
    """Atomic file-backed artifact authority with governance-before-mutation."""

    _SOURCE_PREFIX = "artifact://"

    def __init__(
        self,
        root: str | Path,
        governance: GovernanceRegistry,
    ) -> None:
        if not isinstance(governance, GovernanceRegistry):
            raise TypeError("governance must be GovernanceRegistry")
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.governance = governance

    @classmethod
    def source_ref(cls, tenant_id: str, artifact_id: str) -> str:
        tenant = _required_text(tenant_id, "tenant_id", maximum=256)
        artifact = _required_text(artifact_id, "artifact_id", maximum=1024)
        return (
            cls._SOURCE_PREFIX
            + quote(tenant, safe="")
            + "/"
            + quote(artifact, safe="")
        )

    @classmethod
    def parse_source_ref(cls, source_ref: object) -> tuple[str, str]:
        raw = _required_text(source_ref, "source_ref", maximum=4096)
        if not raw.startswith(cls._SOURCE_PREFIX):
            raise GovernedArtifactError("artifact source_ref is invalid")
        tail = raw[len(cls._SOURCE_PREFIX):]
        tenant_raw, separator, artifact_raw = tail.partition("/")
        if not separator or not tenant_raw or not artifact_raw:
            raise GovernedArtifactError("artifact source_ref is invalid")
        tenant = unquote(tenant_raw)
        artifact = unquote(artifact_raw)
        _required_text(tenant, "tenant_id", maximum=256)
        _required_text(artifact, "artifact_id", maximum=1024)
        return tenant, artifact

    @staticmethod
    def lifecycle_record_id(tenant_id: str, artifact_id: str) -> str:
        tenant = _required_text(tenant_id, "tenant_id", maximum=256)
        artifact = _required_text(artifact_id, "artifact_id", maximum=1024)
        return "artifact-" + _digest(tenant, artifact)[:40]

    def _path(self, tenant_id: str, artifact_id: str) -> Path:
        tenant = _required_text(tenant_id, "tenant_id", maximum=256)
        artifact = _required_text(artifact_id, "artifact_id", maximum=1024)
        tenant_key = _digest("tenant", tenant)[:24]
        artifact_key = _digest("artifact", tenant, artifact)
        directory = self.root / tenant_key
        directory.mkdir(parents=True, exist_ok=True)
        return directory / (artifact_key + ".bin")

    def _register(
        self,
        *,
        tenant_id: str,
        artifact_id: str,
        data_class: str,
        purposes: tuple[str, ...],
        created_at: float | None,
        retention_until: float | None,
        exportable: bool,
    ) -> tuple[str, str, float]:
        record_id = self.lifecycle_record_id(tenant_id, artifact_id)
        source_ref = self.source_ref(tenant_id, artifact_id)
        try:
            existing = self.governance.lifecycle.get(record_id)
        except LifecycleError:
            existing = None

        if existing is not None:
            state = str(existing.get("state"))
            if state != LifecycleState.ACTIVE.value:
                raise GovernedArtifactError(
                    "non-active governed artifact cannot be rewritten"
                )
            registered_created_at = float(existing["created_at"])
            self.governance.reconcile_canonical_write(
                "artifact",
                record_id=record_id,
                tenant_id=tenant_id,
                source_ref=source_ref,
                data_class=data_class,
                purposes=purposes,
                created_at=registered_created_at,
                retention_until=retention_until,
                exportable=exportable,
            )
            return record_id, source_ref, registered_created_at

        timestamp = time.time() if created_at is None else float(created_at)
        registered = self.governance.register_canonical_write(
            "artifact",
            record_id=record_id,
            tenant_id=tenant_id,
            source_ref=source_ref,
            data_class=data_class,
            purposes=purposes,
            created_at=timestamp,
            retention_until=retention_until,
            exportable=exportable,
        )
        return record_id, source_ref, registered.created_at

    def write_bytes(
        self,
        *,
        tenant_id: str,
        artifact_id: str,
        payload: bytes,
        data_class: str = "internal",
        purposes: tuple[str, ...] = ("artifact-delivery",),
        created_at: float | None = None,
        retention_until: float | None = None,
        exportable: bool = True,
    ) -> GovernedArtifactRecord:
        tenant = _required_text(tenant_id, "tenant_id", maximum=256)
        artifact = _required_text(artifact_id, "artifact_id", maximum=1024)
        if not isinstance(payload, bytes):
            raise GovernedArtifactError("payload must be bytes")
        normalized_purposes = tuple(
            dict.fromkeys(
                _required_text(value, "purpose", maximum=256).lower()
                for value in purposes
            )
        )
        if not normalized_purposes:
            raise GovernedArtifactError("at least one purpose is required")

        record_id, source_ref, timestamp = self._register(
            tenant_id=tenant,
            artifact_id=artifact,
            data_class=data_class,
            purposes=normalized_purposes,
            created_at=created_at,
            retention_until=retention_until,
            exportable=exportable,
        )

        final_path = self._path(tenant, artifact)
        fd, pending_raw = tempfile.mkstemp(
            prefix=final_path.name + ".",
            suffix=".pending",
            dir=final_path.parent,
        )
        pending = Path(pending_raw)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(pending, final_path)
        finally:
            pending.unlink(missing_ok=True)

        return GovernedArtifactRecord(
            record_id=record_id,
            tenant_id=tenant,
            artifact_id=artifact,
            source_ref=source_ref,
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            created_at=timestamp,
        )

    def read_bytes(self, tenant_id: str, artifact_id: str) -> bytes | None:
        path = self._path(tenant_id, artifact_id)
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None

    def remove(self, tenant_id: str, artifact_id: str) -> bool:
        path = self._path(tenant_id, artifact_id)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True

    def export_record(
        self,
        tenant_id: str,
        artifact_id: str,
    ) -> dict[str, object] | None:
        tenant = _required_text(tenant_id, "tenant_id", maximum=256)
        artifact = _required_text(artifact_id, "artifact_id", maximum=1024)
        payload = self.read_bytes(tenant, artifact)
        if payload is None:
            return None
        return {
            "artifact_id": artifact,
            "tenant_id": tenant,
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "content_base64": base64.b64encode(payload).decode("ascii"),
        }


__all__ = [
    "GovernedArtifactError",
    "GovernedArtifactRecord",
    "GovernedArtifactStore",
]
