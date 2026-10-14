"""Workload-identity zero-trust authorization for VOL-170."""
from __future__ import annotations

from dataclasses import dataclass
import re

_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ACTION = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
_MAX_TICK = 2_147_483_647


class TrustError(ValueError):
    """Zero-trust identity, grant, or authority is malformed."""


def _tick(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_TICK:
        raise TrustError(f"{field} must be bounded nonnegative integer")
    return value


def _resource(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 4096:
        raise TrustError(f"{field} must be bounded canonical resource")
    if any(ord(char) < 32 for char in value):
        raise TrustError(f"{field} contains control characters")
    return value


@dataclass(frozen=True, slots=True)
class WorkloadIdentity:
    workload_id: str
    instance_id: str
    attestation_digest: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.workload_id, str)
            or not _ID.fullmatch(self.workload_id)
            or not isinstance(self.instance_id, str)
            or not _ID.fullmatch(self.instance_id)
            or not isinstance(self.attestation_digest, str)
            or not _SHA.fullmatch(self.attestation_digest)
        ):
            raise TrustError("invalid workload identity")


@dataclass(frozen=True, slots=True)
class InternalGrant:
    grant_id: str
    workload_id: str
    instance_id: str
    attestation_digest: str
    actions: frozenset[str]
    resource_prefix: str
    issued_tick: int
    expires_tick: int

    def __post_init__(self) -> None:
        if not isinstance(self.grant_id, str) or not _ID.fullmatch(self.grant_id):
            raise TrustError("invalid grant id")
        if not isinstance(self.workload_id, str) or not _ID.fullmatch(self.workload_id):
            raise TrustError("invalid grant workload id")
        if not isinstance(self.instance_id, str) or not _ID.fullmatch(self.instance_id):
            raise TrustError("invalid grant instance id")
        if (
            not isinstance(self.attestation_digest, str)
            or not _SHA.fullmatch(self.attestation_digest)
        ):
            raise TrustError("invalid grant attestation digest")
        if not isinstance(self.actions, frozenset) or not self.actions:
            raise TrustError("grant actions must be non-empty frozenset")
        if len(self.actions) > 256 or any(
            not isinstance(item, str) or not _ACTION.fullmatch(item)
            for item in self.actions
        ):
            raise TrustError("invalid grant action")
        object.__setattr__(self, "resource_prefix", _resource(self.resource_prefix, "resource_prefix"))
        issued = _tick(self.issued_tick, "issued_tick")
        expires = _tick(self.expires_tick, "expires_tick")
        if expires <= issued:
            raise TrustError("grant expiry must follow issue tick")


@dataclass(frozen=True, slots=True)
class TrustDecision:
    allowed: bool
    reason: str
    grant_id: str | None
    attestation_digest: str | None
    action: str | None
    resource: str | None
    revalidate_at: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise TrustError("decision allowed must be boolean")
        if not isinstance(self.reason, str) or not self.reason:
            raise TrustError("decision reason required")
        if self.allowed:
            if (
                self.grant_id is None
                or self.attestation_digest is None
                or self.action is None
                or self.resource is None
                or self.revalidate_at is None
            ):
                raise TrustError("allowed decision requires complete authority")
        elif any(
            value is not None
            for value in (
                self.grant_id,
                self.attestation_digest,
                self.action,
                self.resource,
                self.revalidate_at,
            )
        ):
            raise TrustError("denied decision cannot carry authority")


def _denied(reason: str) -> TrustDecision:
    return TrustDecision(False, reason, None, None, None, None, None)


def _resource_in_scope(resource: str, prefix: str) -> bool:
    if resource == prefix:
        return True
    boundary = prefix if prefix.endswith("/") else prefix + "/"
    return resource.startswith(boundary)


def authorize(
    identity: WorkloadIdentity,
    grant: InternalGrant,
    action: str,
    resource: str,
    now: int,
    revalidation_interval: int = 10,
) -> TrustDecision:
    if not isinstance(identity, WorkloadIdentity):
        raise TypeError("identity must be WorkloadIdentity")
    if not isinstance(grant, InternalGrant):
        raise TypeError("grant must be InternalGrant")
    if not isinstance(action, str) or not _ACTION.fullmatch(action):
        raise TrustError("invalid requested action")
    resource = _resource(resource, "resource")
    now = _tick(now, "now")
    interval = _tick(revalidation_interval, "revalidation_interval")
    if interval < 1:
        raise TrustError("revalidation interval must be positive")
    if grant.workload_id != identity.workload_id or grant.instance_id != identity.instance_id:
        return _denied("identity_mismatch")
    if grant.attestation_digest != identity.attestation_digest:
        return _denied("attestation_mismatch")
    if now < grant.issued_tick or now >= grant.expires_tick:
        return _denied("grant_expired")
    if action not in grant.actions or not _resource_in_scope(resource, grant.resource_prefix):
        return _denied("least_privilege_denied")
    return TrustDecision(
        True,
        "authorized",
        grant.grant_id,
        identity.attestation_digest,
        action,
        resource,
        min(grant.expires_tick, now + interval),
    )


def revalidate(
    identity: WorkloadIdentity,
    grant: InternalGrant,
    decision: TrustDecision,
    now: int,
    revalidation_interval: int = 10,
) -> TrustDecision:
    if not isinstance(decision, TrustDecision):
        raise TypeError("decision must be TrustDecision")
    if not decision.allowed or decision.grant_id != grant.grant_id:
        raise TrustError("invalid prior decision")
    if decision.attestation_digest != identity.attestation_digest:
        return _denied("attestation_mismatch")
    assert decision.action is not None and decision.resource is not None
    return authorize(
        identity,
        grant,
        decision.action,
        decision.resource,
        now,
        revalidation_interval,
    )


__all__ = [
    "InternalGrant",
    "TrustDecision",
    "TrustError",
    "WorkloadIdentity",
    "authorize",
    "revalidate",
]
