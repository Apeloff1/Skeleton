"""Deterministic authenticated security-boundary decisions for VOL-169."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable


class SecurityBoundaryError(ValueError):
    """A boundary declaration or crossing violated the fail-closed contract."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 256:
        raise SecurityBoundaryError(f"{name} must be non-empty normalized text")
    return value


def _tokens(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise SecurityBoundaryError(f"{name} must be a collection")
    result = tuple(sorted({_token(name, value) for value in values}))
    if not result:
        raise SecurityBoundaryError(f"{name} must be non-empty")
    return result


def _digest(value: object) -> str:
    try:
        encoded=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    except (TypeError,ValueError) as exc:
        raise SecurityBoundaryError("boundary evidence must be canonical JSON") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SecurityBoundary:
    boundary_id: str
    source_zone: str
    target_zone: str
    required_authn: str
    required_scopes: tuple[str, ...]
    default_action: str = "deny"

    def __post_init__(self) -> None:
        for name in ("boundary_id","source_zone","target_zone","required_authn"):
            object.__setattr__(self,name,_token(name,getattr(self,name)))
        object.__setattr__(self,"required_scopes",_tokens("required_scope",self.required_scopes))
        if self.source_zone == self.target_zone:
            raise SecurityBoundaryError("security boundary must cross distinct zones")
        if self.default_action != "deny":
            raise SecurityBoundaryError("privileged boundary default action must be deny")

    @property
    def digest(self) -> str:
        return _digest({
            "boundary_id":self.boundary_id,
            "source_zone":self.source_zone,
            "target_zone":self.target_zone,
            "required_authn":self.required_authn,
            "required_scopes":list(self.required_scopes),
            "default_action":"deny",
        })


@dataclass(frozen=True, slots=True)
class BoundaryCrossing:
    crossing_id: str
    boundary_id: str
    subject_id: str
    workload_id: str
    resource_id: str
    authenticated_identity: str | None
    granted_scopes: tuple[str, ...]
    requested_action: str

    def __post_init__(self) -> None:
        for name in ("crossing_id","boundary_id","subject_id","workload_id","resource_id","requested_action"):
            object.__setattr__(self,name,_token(name,getattr(self,name)))
        if self.authenticated_identity is not None:
            object.__setattr__(
                self,
                "authenticated_identity",
                _token("authenticated_identity",self.authenticated_identity),
            )
        scopes=tuple(sorted({_token("granted_scope",value) for value in self.granted_scopes}))
        object.__setattr__(self,"granted_scopes",scopes)

    @property
    def digest(self) -> str:
        return _digest({
            "crossing_id":self.crossing_id,
            "boundary_id":self.boundary_id,
            "subject_id":self.subject_id,
            "workload_id":self.workload_id,
            "resource_id":self.resource_id,
            "authenticated_identity":self.authenticated_identity,
            "granted_scopes":list(self.granted_scopes),
            "requested_action":self.requested_action,
        })


@dataclass(frozen=True, slots=True)
class BoundaryDecision:
    boundary_digest: str
    crossing_digest: str
    allowed: bool
    reason_code: str
    effective_scopes: tuple[str, ...]
    external_side_effects: bool = False

    def __post_init__(self) -> None:
        for name in ("boundary_digest","crossing_digest"):
            value=getattr(self,name)
            if not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value):
                raise SecurityBoundaryError(f"{name} must be a lowercase sha256 digest")
        if not isinstance(self.allowed,bool):
            raise SecurityBoundaryError("allowed must be boolean")
        object.__setattr__(self,"reason_code",_token("reason_code",self.reason_code))
        scopes=tuple(sorted({_token("effective_scope",value) for value in self.effective_scopes}))
        object.__setattr__(self,"effective_scopes",scopes)
        if not self.allowed and scopes:
            raise SecurityBoundaryError("denied crossing cannot retain effective scopes")
        if self.external_side_effects is not False:
            raise SecurityBoundaryError("boundary decision is evidence-only")


def evaluate_boundary(boundary: SecurityBoundary, crossing: BoundaryCrossing) -> BoundaryDecision:
    """Authenticate then authorize one exact crossing; unknowns degrade closed."""
    if crossing.boundary_id != boundary.boundary_id:
        return BoundaryDecision(boundary.digest,crossing.digest,False,"boundary_mismatch",())
    if crossing.authenticated_identity is None:
        return BoundaryDecision(boundary.digest,crossing.digest,False,"authentication_missing",())
    required=set(boundary.required_scopes)
    granted=set(crossing.granted_scopes)
    if not required.issubset(granted):
        return BoundaryDecision(boundary.digest,crossing.digest,False,"scope_missing",())
    effective=tuple(sorted(required))
    return BoundaryDecision(boundary.digest,crossing.digest,True,"authorized",effective)
