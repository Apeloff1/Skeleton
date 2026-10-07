"""Engine API delegated-authority contracts and server-side grant validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from skeleton.contracts.ai_execution import AIExecutionRequest
from skeleton.contracts.operation import OperationEnvelope


_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class EngineAuthorityError(PermissionError):
    """Engine service/delegated authority is absent, expired, or over-broad."""


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EngineAuthorityError(f"{field} must be non-empty text")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise EngineAuthorityError(f"{field} is invalid")
    return normalized


def _aware(value: object, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise EngineAuthorityError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _scopes(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise EngineAuthorityError("scopes must be a collection")
    result: list[str] = []
    for raw in values:
        item = _text(raw, "scope", maximum=256)
        if item not in result:
            result.append(item)
        if len(result) > 256:
            raise EngineAuthorityError("too many delegated scopes")
    if not result:
        raise EngineAuthorityError("at least one delegated scope is required")
    return tuple(sorted(result))


def _canonical_digest(value: Mapping[str, Any]) -> str:
    try:
        raw = json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EngineAuthorityError("authority payload must be deterministic JSON") from exc
    return hashlib.sha256(raw).hexdigest()


def engine_request_binding(
    operation: OperationEnvelope,
    execution_request: AIExecutionRequest,
) -> str:
    if not isinstance(operation, OperationEnvelope):
        raise TypeError("operation must be OperationEnvelope")
    if not isinstance(execution_request, AIExecutionRequest):
        raise TypeError("execution_request must be AIExecutionRequest")
    return _canonical_digest(
        {
            "operation_id": operation.operation_id,
            "operation_identity_digest": operation.identity_digest,
            "execution_id": execution_request.execution_id,
            "execution_identity_digest": execution_request.identity_digest,
        }
    )


@dataclass(frozen=True, slots=True)
class DelegatedAuthority:
    service_principal: str
    actor_id: str
    tenant_id: str
    scopes: tuple[str, ...]
    capability: str
    issued_at: datetime
    expires_at: datetime
    request_binding: str
    authority_digest: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        for name in ("service_principal", "actor_id", "tenant_id", "capability"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "scopes", _scopes(self.scopes))
        issued = _aware(self.issued_at, "issued_at")
        expires = _aware(self.expires_at, "expires_at")
        if expires <= issued:
            raise EngineAuthorityError("expires_at must be later than issued_at")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        binding = _text(self.request_binding, "request_binding", maximum=64)
        if _DIGEST.fullmatch(binding) is None:
            raise EngineAuthorityError("request_binding must be lowercase sha256")
        payload = self._digest_payload()
        digest = _canonical_digest(payload)
        if self.authority_digest is not None and self.authority_digest != digest:
            raise EngineAuthorityError("authority_digest does not match authority")
        object.__setattr__(self, "authority_digest", digest)
        if self.schema_version != 1:
            raise EngineAuthorityError("unsupported delegated authority schema version")

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "service_principal": self.service_principal,
            "actor_id": self.actor_id,
            "tenant_id": self.tenant_id,
            "scopes": list(self.scopes),
            "capability": self.capability,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "request_binding": self.request_binding,
        }

    def expired(self, *, now: datetime | None = None) -> bool:
        instant = _aware(now or datetime.now(timezone.utc), "now")
        return instant >= self.expires_at

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            **self._digest_payload(),
            "authority_digest": self.authority_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DelegatedAuthority":
        if not isinstance(payload, Mapping):
            raise EngineAuthorityError("delegated_authority must be an object")
        try:
            issued = datetime.fromisoformat(str(payload["issued_at"]))
            expires = datetime.fromisoformat(str(payload["expires_at"]))
            scopes = payload["scopes"]
        except (KeyError, ValueError, TypeError) as exc:
            raise EngineAuthorityError("delegated_authority is malformed") from exc
        if not isinstance(scopes, list):
            raise EngineAuthorityError("delegated authority scopes must be a list")
        return cls(
            service_principal=str(payload.get("service_principal") or ""),
            actor_id=str(payload.get("actor_id") or ""),
            tenant_id=str(payload.get("tenant_id") or ""),
            scopes=tuple(scopes),
            capability=str(payload.get("capability") or ""),
            issued_at=issued,
            expires_at=expires,
            request_binding=str(payload.get("request_binding") or ""),
            authority_digest=(
                None
                if payload.get("authority_digest") is None
                else str(payload["authority_digest"])
            ),
            schema_version=int(payload.get("schema_version", 1)),
        )


@dataclass(frozen=True, slots=True)
class EngineServiceGrant:
    service_principal: str
    scopes: frozenset[str]
    tenant_ids: frozenset[str]
    capabilities: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "service_principal",
            _text(self.service_principal, "service_principal"),
        )
        for name in ("scopes", "tenant_ids", "capabilities"):
            raw = getattr(self, name)
            if not isinstance(raw, frozenset) or not raw:
                raise EngineAuthorityError(f"{name} must be a non-empty frozenset")
            normalized = frozenset(_text(item, name) for item in raw)
            object.__setattr__(self, name, normalized)

    def allows_tenant(self, tenant_id: str) -> bool:
        return "*" in self.tenant_ids or tenant_id in self.tenant_ids

    def allows_capability(self, capability: str) -> bool:
        return "*" in self.capabilities or capability in self.capabilities


class EngineAuthorityRegistry:
    """Server-side service-principal grants. Client JSON cannot mutate this."""

    def __init__(self, grants: Iterable[EngineServiceGrant] = ()) -> None:
        self._grants: dict[str, EngineServiceGrant] = {}
        for grant in grants:
            if not isinstance(grant, EngineServiceGrant):
                raise TypeError("grants must contain EngineServiceGrant values")
            if grant.service_principal in self._grants:
                raise EngineAuthorityError("duplicate engine service principal grant")
            self._grants[grant.service_principal] = grant

    def grant_for(self, service_principal: str) -> EngineServiceGrant:
        principal = _text(service_principal, "service_principal")
        grant = self._grants.get(principal)
        if grant is None:
            raise EngineAuthorityError("engine service principal is not granted")
        return grant

    def validate(
        self,
        *,
        verified_service_principal: str,
        authority: DelegatedAuthority,
        operation: OperationEnvelope,
        execution_request: AIExecutionRequest,
        required_scope: str,
        now: datetime | None = None,
    ) -> DelegatedAuthority:
        if not isinstance(authority, DelegatedAuthority):
            raise TypeError("authority must be DelegatedAuthority")
        grant = self.grant_for(verified_service_principal)
        if authority.service_principal != grant.service_principal:
            raise EngineAuthorityError("delegated service principal does not match verified attester")
        if authority.expired(now=now):
            raise EngineAuthorityError("delegated authority is expired")
        required = _text(required_scope, "required_scope", maximum=256)
        if required not in authority.scopes:
            raise EngineAuthorityError("delegated authority is missing required scope")
        if not set(authority.scopes).issubset(grant.scopes):
            raise EngineAuthorityError("delegated scopes exceed service grant")
        if authority.tenant_id != operation.tenant_id:
            raise EngineAuthorityError("delegated tenant does not match operation")
        if authority.actor_id != operation.actor_id:
            raise EngineAuthorityError("delegated actor does not match operation")
        if authority.capability != operation.capability:
            raise EngineAuthorityError("delegated capability does not match operation")
        if not grant.allows_tenant(operation.tenant_id):
            raise EngineAuthorityError("tenant is outside service grant")
        if not grant.allows_capability(operation.capability):
            raise EngineAuthorityError("capability is outside service grant")
        if execution_request.operation_id != operation.operation_id:
            raise EngineAuthorityError("execution operation identity mismatch")
        execution_tenant = execution_request.context_policy.get("tenant_id")
        execution_capability = execution_request.context_policy.get("capability")
        if execution_tenant != operation.tenant_id:
            raise EngineAuthorityError("execution tenant does not match operation")
        if execution_capability != operation.capability:
            raise EngineAuthorityError("execution capability does not match operation")
        expected_binding = engine_request_binding(operation, execution_request)
        if authority.request_binding != expected_binding:
            raise EngineAuthorityError("delegated authority request binding mismatch")
        return authority


__all__ = [
    "DelegatedAuthority",
    "EngineAuthorityError",
    "EngineAuthorityRegistry",
    "EngineServiceGrant",
    "engine_request_binding",
]
