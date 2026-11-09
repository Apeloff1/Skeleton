"""P1 tenant, permission, and storage classification boundary.

The contract is intentionally framework-neutral. HTTP routes, stream adapters,
desktop/web clients, and persistence code can all ask the same question:
may this verified tenant/principal use this storage surface for this data class?

This module does not grant application capabilities. It only proves that the
tenant identity, requested permission, data class, and storage surface are a
written compatible combination. Unknown combinations fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef


TENANT_STORAGE_SCHEMA_VERSION = 1
TENANT_STORAGE_TASK_ID = "P1-PROD-05"
TENANT_STORAGE_ACCOUNTABILITY_ID = "ACC-P1-PROD-05"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-]{0,255}$")
_PERMISSION_RE = re.compile(r"^[a-z][a-z0-9._:-]{0,95}$")


class TenantStorageBoundaryError(ValueError):
    """Tenant/storage input violates the written boundary contract."""


class StorageSurface(str, Enum):
    MEMORY = "memory"
    DEVICE_CACHE = "device_cache"
    CANONICAL_SERVER = "canonical_server"


class StorageDataClass(str, Enum):
    PUBLIC = "public"
    TENANT_CACHE = "tenant_cache"
    USER_DRAFT = "user_draft"
    CANONICAL_REFERENCE = "canonical_reference"
    ATTACHMENT_BYTES = "attachment_bytes"
    CREDENTIAL = "credential"


class StoragePermission(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"


def _text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TenantStorageBoundaryError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise TenantStorageBoundaryError(f"{field} must be normalized")
    return normalized


def _token(value: object, field: str, *, maximum: int = 256) -> str:
    text = _text(value, field, maximum=maximum)
    if not _TOKEN_RE.fullmatch(text):
        raise TenantStorageBoundaryError(
            f"{field} must contain only canonical identity characters"
        )
    return text


def _permission(value: object) -> str:
    if isinstance(value, StoragePermission):
        return value.value
    text = _text(value, "permission", maximum=96)
    if not _PERMISSION_RE.fullmatch(text):
        raise TenantStorageBoundaryError(
            "permission must be a canonical permission token"
        )
    return text


def _permissions(values: Iterable[str | StoragePermission]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TenantStorageBoundaryError(
            "granted_permissions must be an iterable"
        )
    result = tuple(sorted({_permission(item) for item in values}))
    if not result:
        raise TenantStorageBoundaryError(
            "granted_permissions must be non-empty"
        )
    return result


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TenantStorageBoundaryError(
            "tenant storage payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def tenant_storage_namespace(
    tenant_id: str,
    *,
    purpose: str,
) -> str:
    """Return a privacy-preserving namespace; not an authorization token."""

    tenant = _token(tenant_id, "tenant_id")
    normalized_purpose = _token(purpose, "purpose", maximum=96)
    fingerprint = hashlib.sha256(tenant.encode("utf-8")).hexdigest()[:24]
    return f"tenant:{fingerprint}:{normalized_purpose}"


@dataclass(frozen=True, slots=True)
class TenantStorageContext:
    tenant_id: str
    principal_id: str
    granted_permissions: tuple[str, ...]
    data_class: StorageDataClass
    surface: StorageSurface
    purpose: str
    schema_version: int = TENANT_STORAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tenant_id",
            _token(self.tenant_id, "tenant_id"),
        )
        object.__setattr__(
            self,
            "principal_id",
            _token(self.principal_id, "principal_id"),
        )
        object.__setattr__(
            self,
            "granted_permissions",
            _permissions(self.granted_permissions),
        )
        try:
            object.__setattr__(
                self,
                "data_class",
                StorageDataClass(self.data_class),
            )
        except ValueError as exc:
            raise TenantStorageBoundaryError(
                "unknown storage data class"
            ) from exc
        try:
            object.__setattr__(
                self,
                "surface",
                StorageSurface(self.surface),
            )
        except ValueError as exc:
            raise TenantStorageBoundaryError(
                "unknown storage surface"
            ) from exc
        object.__setattr__(
            self,
            "purpose",
            _token(self.purpose, "purpose", maximum=96),
        )
        if self.schema_version != TENANT_STORAGE_SCHEMA_VERSION:
            raise TenantStorageBoundaryError(
                "unsupported tenant storage schema"
            )

    @property
    def namespace(self) -> str:
        return tenant_storage_namespace(
            self.tenant_id,
            purpose=self.purpose,
        )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tenant_id": self.tenant_id,
            "principal_id": self.principal_id,
            "granted_permissions": list(self.granted_permissions),
            "data_class": self.data_class.value,
            "surface": self.surface.value,
            "purpose": self.purpose,
            "namespace": self.namespace,
        }

    @property
    def context_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class TenantStorageDecision:
    accepted: bool
    reasons: tuple[str, ...]
    tenant_id: str
    principal_id: str
    requested_permission: str
    data_class: StorageDataClass
    surface: StorageSurface
    namespace: str
    context_digest: str
    task_id: str = TENANT_STORAGE_TASK_ID
    accountability_id: str = TENANT_STORAGE_ACCOUNTABILITY_ID
    schema_version: int = TENANT_STORAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise TenantStorageBoundaryError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item
            for item in self.reasons
        ):
            raise TenantStorageBoundaryError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "tenant_id",
            _token(self.tenant_id, "tenant_id"),
        )
        object.__setattr__(
            self,
            "principal_id",
            _token(self.principal_id, "principal_id"),
        )
        object.__setattr__(
            self,
            "requested_permission",
            _permission(self.requested_permission),
        )
        try:
            object.__setattr__(
                self,
                "data_class",
                StorageDataClass(self.data_class),
            )
            object.__setattr__(
                self,
                "surface",
                StorageSurface(self.surface),
            )
        except ValueError as exc:
            raise TenantStorageBoundaryError(
                "decision classification drift"
            ) from exc
        object.__setattr__(
            self,
            "namespace",
            _text(self.namespace, "namespace", maximum=160),
        )
        digest = _text(
            self.context_digest,
            "context_digest",
            maximum=64,
        )
        if len(digest) != 64 or any(
            char not in "0123456789abcdef" for char in digest
        ):
            raise TenantStorageBoundaryError(
                "context_digest must be lowercase sha256"
            )
        if self.task_id != TENANT_STORAGE_TASK_ID:
            raise TenantStorageBoundaryError("task_id drift")
        if self.accountability_id != TENANT_STORAGE_ACCOUNTABILITY_ID:
            raise TenantStorageBoundaryError("accountability_id drift")
        if self.schema_version != TENANT_STORAGE_SCHEMA_VERSION:
            raise TenantStorageBoundaryError(
                "unsupported decision schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "tenant_id": self.tenant_id,
            "principal_id": self.principal_id,
            "requested_permission": self.requested_permission,
            "data_class": self.data_class.value,
            "surface": self.surface.value,
            "namespace": self.namespace,
            "context_digest": self.context_digest,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise TenantStorageBoundaryError(
                "rejected tenant storage decision cannot become evidence"
            )
        return EvidenceRef(
            source=(
                "p1:prod-05:tenant-storage:"
                f"{self.namespace}:{self.requested_permission}"
            ),
            digest=self.decision_digest,
            category="tenant_storage_boundary",
        )


_DEVICE_CACHE_ALLOWED = frozenset(
    {
        StorageDataClass.PUBLIC,
        StorageDataClass.TENANT_CACHE,
        StorageDataClass.USER_DRAFT,
        StorageDataClass.CANONICAL_REFERENCE,
    }
)
_MEMORY_ALLOWED = frozenset(StorageDataClass)
_CANONICAL_SERVER_ALLOWED = frozenset(
    {
        StorageDataClass.PUBLIC,
        StorageDataClass.TENANT_CACHE,
        StorageDataClass.USER_DRAFT,
        StorageDataClass.CANONICAL_REFERENCE,
        StorageDataClass.ATTACHMENT_BYTES,
    }
)


def evaluate_tenant_storage(
    *,
    context: TenantStorageContext,
    verified_tenant_id: str,
    requested_permission: str | StoragePermission,
) -> TenantStorageDecision:
    """Evaluate one already-authenticated storage request.

    Credential persistence is deliberately excluded from this generic contract;
    credentials require a dedicated secure credential store. Device cache also
    rejects attachment bytes so large/sensitive upload payloads remain
    visit-scoped unless an explicit canonical server flow accepts them.
    """

    if not isinstance(context, TenantStorageContext):
        raise TypeError("context must be TenantStorageContext")
    verified = _token(
        verified_tenant_id,
        "verified_tenant_id",
    )
    permission = _permission(requested_permission)
    reasons: list[str] = []

    if verified != context.tenant_id:
        reasons.append("verified-tenant-mismatch")
    if permission not in context.granted_permissions:
        reasons.append("permission-not-granted")

    allowed = {
        StorageSurface.MEMORY: _MEMORY_ALLOWED,
        StorageSurface.DEVICE_CACHE: _DEVICE_CACHE_ALLOWED,
        StorageSurface.CANONICAL_SERVER: _CANONICAL_SERVER_ALLOWED,
    }[context.surface]
    if context.data_class not in allowed:
        reasons.append(
            f"data-class-not-allowed-on-surface:"
            f"{context.data_class.value}:{context.surface.value}"
        )
    if context.data_class is StorageDataClass.CREDENTIAL:
        reasons.append("credential-requires-dedicated-secure-store")

    normalized = tuple(sorted(set(reasons)))
    return TenantStorageDecision(
        accepted=not normalized,
        reasons=normalized,
        tenant_id=context.tenant_id,
        principal_id=context.principal_id,
        requested_permission=permission,
        data_class=context.data_class,
        surface=context.surface,
        namespace=context.namespace,
        context_digest=context.context_digest,
    )


def require_tenant_storage(
    *,
    context: TenantStorageContext,
    verified_tenant_id: str,
    requested_permission: str | StoragePermission,
) -> TenantStorageDecision:
    decision = evaluate_tenant_storage(
        context=context,
        verified_tenant_id=verified_tenant_id,
        requested_permission=requested_permission,
    )
    if not decision.accepted:
        raise TenantStorageBoundaryError(
            "tenant storage boundary rejected: "
            + ",".join(decision.reasons)
        )
    return decision


__all__ = [
    "TENANT_STORAGE_ACCOUNTABILITY_ID",
    "TENANT_STORAGE_SCHEMA_VERSION",
    "TENANT_STORAGE_TASK_ID",
    "StorageDataClass",
    "StoragePermission",
    "StorageSurface",
    "TenantStorageBoundaryError",
    "TenantStorageContext",
    "TenantStorageDecision",
    "evaluate_tenant_storage",
    "require_tenant_storage",
    "tenant_storage_namespace",
]
