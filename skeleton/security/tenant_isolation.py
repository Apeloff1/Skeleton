"""Tenant/workspace isolation decisions for VOL-175."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


class TenantIsolationError(ValueError):
    """Tenant identity, resource scope, or decision evidence is invalid."""


def _token(name: str, value: object) -> str:
    if not isinstance(value,str) or not value or value != value.strip() or len(value)>256:
        raise TenantIsolationError(f"{name} must be non-empty normalized text")
    return value


def _digest(value: object) -> str:
    try:
        encoded=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    except (TypeError,ValueError) as exc:
        raise TenantIsolationError("tenant evidence must be canonical JSON") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TenantScope:
    tenant_id: str
    workspace_id: str
    subject_id: str
    resource_prefix: str

    def __post_init__(self) -> None:
        for name in ("tenant_id","workspace_id","subject_id","resource_prefix"):
            object.__setattr__(self,name,_token(name,getattr(self,name)))
        prefix=self.resource_prefix
        if not prefix.endswith(":"):
            raise TenantIsolationError("resource_prefix must terminate with ':'")

    @property
    def digest(self) -> str:
        return _digest({
            "tenant_id":self.tenant_id,
            "workspace_id":self.workspace_id,
            "subject_id":self.subject_id,
            "resource_prefix":self.resource_prefix,
        })


@dataclass(frozen=True, slots=True)
class TenantBoundary:
    resource_id: str
    tenant_id: str
    workspace_id: str
    classification: str

    def __post_init__(self) -> None:
        for name in ("resource_id","tenant_id","workspace_id","classification"):
            object.__setattr__(self,name,_token(name,getattr(self,name)))

    @property
    def digest(self) -> str:
        return _digest({
            "resource_id":self.resource_id,
            "tenant_id":self.tenant_id,
            "workspace_id":self.workspace_id,
            "classification":self.classification,
        })


@dataclass(frozen=True, slots=True)
class TenantAccessDecision:
    scope_digest: str
    boundary_digest: str
    operation: str
    allowed: bool
    reason_code: str

    def __post_init__(self) -> None:
        for name in ("scope_digest","boundary_digest"):
            value=getattr(self,name)
            if not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value):
                raise TenantIsolationError(f"{name} must be a lowercase sha256 digest")
        object.__setattr__(self,"operation",_token("operation",self.operation))
        object.__setattr__(self,"reason_code",_token("reason_code",self.reason_code))
        if not isinstance(self.allowed,bool):
            raise TenantIsolationError("allowed must be boolean")


def authorize_tenant_access(
    scope: TenantScope,
    boundary: TenantBoundary,
    *,
    operation: str,
) -> TenantAccessDecision:
    """Authorize lookup/execution only after tenant and workspace identity match."""
    op=_token("operation",operation)
    if scope.tenant_id != boundary.tenant_id:
        return TenantAccessDecision(scope.digest,boundary.digest,op,False,"tenant_mismatch")
    if scope.workspace_id != boundary.workspace_id:
        return TenantAccessDecision(scope.digest,boundary.digest,op,False,"workspace_mismatch")
    if not boundary.resource_id.startswith(scope.resource_prefix):
        return TenantAccessDecision(scope.digest,boundary.digest,op,False,"resource_scope_mismatch")
    return TenantAccessDecision(scope.digest,boundary.digest,op,True,"authorized")
