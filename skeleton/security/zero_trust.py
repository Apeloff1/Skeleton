"""Workload-identity zero-trust authorization for VOL-170.

The presented workload and grant are accepted only when a deployment verifier
checks their canonical payload. This module does not implement a cryptographic
primitive. Implementation state cannot self-grant verification.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ACTION = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
_MAX_TICK = 2_147_483_647
_MAX_SIGNATURE = 8192


class TrustError(ValueError):
    """Zero-trust identity, grant, or authority is malformed."""


def _tick(value: object, field: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= _MAX_TICK
    ):
        raise TrustError(f"{field} must be bounded nonnegative integer")
    return value


def _resource(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 4096
    ):
        raise TrustError(f"{field} must be bounded canonical resource")
    if any(ord(char) < 32 for char in value):
        raise TrustError(f"{field} contains control characters")
    return value


def _signature(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= _MAX_SIGNATURE
        or any(ord(char) < 32 for char in value)
    ):
        raise TrustError("invalid identity proof signature")
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
        if not isinstance(self.attestation_digest, str) or not _SHA.fullmatch(
            self.attestation_digest
        ):
            raise TrustError("invalid grant attestation digest")
        if not isinstance(self.actions, frozenset) or not self.actions:
            raise TrustError("grant actions must be non-empty frozenset")
        if len(self.actions) > 256 or any(
            not isinstance(item, str) or not _ACTION.fullmatch(item)
            for item in self.actions
        ):
            raise TrustError("invalid grant action")
        object.__setattr__(
            self, "resource_prefix", _resource(self.resource_prefix, "resource_prefix")
        )
        issued = _tick(self.issued_tick, "issued_tick")
        expires = _tick(self.expires_tick, "expires_tick")
        if expires <= issued:
            raise TrustError("grant expiry must follow issue tick")


@dataclass(frozen=True, slots=True)
class IdentityProof:
    key_id: str
    signature: str

    def __post_init__(self) -> None:
        if not isinstance(self.key_id, str) or not _ID.fullmatch(self.key_id):
            raise TrustError("invalid identity proof key")
        object.__setattr__(self, "signature", _signature(self.signature))


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


def binding_payload(identity: WorkloadIdentity, grant: InternalGrant) -> bytes:
    """Canonical bytes a verifier must accept for this identity and grant."""
    # internal service identity is cryptographically bound
    if not isinstance(identity, WorkloadIdentity):
        raise TypeError("identity must be WorkloadIdentity")
    if not isinstance(grant, InternalGrant):
        raise TypeError("grant must be InternalGrant")
    body = {
        "kind": "internal_service_identity",
        "identity": {
            "attestation_digest": identity.attestation_digest,
            "instance_id": identity.instance_id,
            "workload_id": identity.workload_id,
        },
        "grant": {
            "actions": sorted(grant.actions),
            "attestation_digest": grant.attestation_digest,
            "expires_tick": grant.expires_tick,
            "grant_id": grant.grant_id,
            "instance_id": grant.instance_id,
            "issued_tick": grant.issued_tick,
            "resource_prefix": grant.resource_prefix,
            "workload_id": grant.workload_id,
        },
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _require_binding(
    identity: WorkloadIdentity,
    grant: InternalGrant,
    proof: IdentityProof,
    verifier: Any,
) -> TrustDecision | None:
    if not isinstance(proof, IdentityProof):
        raise TypeError("proof must be IdentityProof")
    verify = getattr(verifier, "verify", None)
    if not callable(verify) or not hasattr(verifier, "key_id"):
        raise TrustError("identity verifier is incomplete")
    if verifier.key_id != proof.key_id:
        return _denied("identity_unbound")
    try:
        accepted = verify(binding_payload(identity, grant), proof.signature)
    except Exception:  # noqa: BLE001 — any verifier failure denies the call
        return _denied("identity_verifier_failed")
    if accepted is not True:
        return _denied("identity_unbound")
    return None


def authorize(
    identity: WorkloadIdentity,
    grant: InternalGrant,
    action: str,
    resource: str,
    now: int,
    revalidation_interval: int = 10,
    *,
    proof: IdentityProof,
    verifier: Any,
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
    unbound = _require_binding(identity, grant, proof, verifier)
    if unbound is not None:
        return unbound
    if (
        grant.workload_id != identity.workload_id
        or grant.instance_id != identity.instance_id
    ):
        return _denied("identity_mismatch")
    if grant.attestation_digest != identity.attestation_digest:
        return _denied("attestation_mismatch")
    if now < grant.issued_tick or now >= grant.expires_tick:
        return _denied("grant_expired")
    if action not in grant.actions or not _resource_in_scope(
        resource, grant.resource_prefix
    ):
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
    *,
    proof: IdentityProof,
    verifier: Any,
) -> TrustDecision:
    if not isinstance(decision, TrustDecision):
        raise TypeError("decision must be TrustDecision")
    if not decision.allowed or decision.grant_id != grant.grant_id:
        raise TrustError("invalid prior decision")
    unbound = _require_binding(identity, grant, proof, verifier)
    if unbound is not None:
        return unbound
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
        proof=proof,
        verifier=verifier,
    )


__all__ = [
    "IdentityProof",
    "InternalGrant",
    "TrustDecision",
    "TrustError",
    "WorkloadIdentity",
    "authorize",
    "binding_payload",
    "revalidate",
]
