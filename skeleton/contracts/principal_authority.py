"""Unified authenticated principal, tenancy, capability and delegation authority.

This contract composes identity facts that previously existed in separate
authentication, tenant-storage and delegation planes.  It is framework neutral:
an edge verifier supplies the already-authenticated principal identity and a
digest of its authentication context; side-effecting runtimes consume this
authority envelope and fail closed on tenant/session/policy/capability drift.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Iterable


class PrincipalAuthorityError(RuntimeError):
    """Authenticated authority is malformed, widened, stale, or mismatched."""


_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,255}$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _text(name: str, value: object, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PrincipalAuthorityError(f"{name} must be non-empty text")
    result = value.strip()
    if result != value or len(result) > maximum:
        raise PrincipalAuthorityError(f"{name} must be normalized bounded text")
    return result


def _token(name: str, value: object) -> str:
    result = _text(name, value)
    if _TOKEN.fullmatch(result) is None:
        raise PrincipalAuthorityError(f"{name} is not a canonical identity token")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if _SHA256.fullmatch(result) is None:
        raise PrincipalAuthorityError(f"{name} must be lowercase sha256")
    return result


def _time(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PrincipalAuthorityError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise PrincipalAuthorityError(f"{name} must be finite and non-negative")
    return result


def _capabilities(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise PrincipalAuthorityError("capabilities must be an iterable of tokens")
    normalized: list[str] = []
    for raw in values:
        value = _text("capability", raw, maximum=128)
        if _CAPABILITY.fullmatch(value) is None:
            raise PrincipalAuthorityError(f"invalid capability {value!r}")
        normalized.append(value)
    result = tuple(sorted(set(normalized)))
    if not result:
        raise PrincipalAuthorityError("capabilities must not be empty")
    return result


def _canonical_digest(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PrincipalAuthorityError("authority payload must be canonical JSON") from exc
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class DelegationHop:
    delegator_id: str
    delegate_id: str
    tenant_id: str
    capabilities: tuple[str, ...]
    issued_at: float
    expires_at: float
    grant_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "delegator_id", _token("delegator_id", self.delegator_id))
        object.__setattr__(self, "delegate_id", _token("delegate_id", self.delegate_id))
        object.__setattr__(self, "tenant_id", _token("tenant_id", self.tenant_id))
        object.__setattr__(self, "grant_id", _token("grant_id", self.grant_id))
        object.__setattr__(self, "capabilities", _capabilities(self.capabilities))
        issued = _time("issued_at", self.issued_at)
        expires = _time("expires_at", self.expires_at)
        if expires <= issued:
            raise PrincipalAuthorityError("delegation expiry must be after issuance")
        if self.delegator_id == self.delegate_id:
            raise PrincipalAuthorityError("delegation cannot target the delegator")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)

    def as_dict(self) -> dict[str, object]:
        return {
            "delegator_id": self.delegator_id,
            "delegate_id": self.delegate_id,
            "tenant_id": self.tenant_id,
            "capabilities": list(self.capabilities),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "grant_id": self.grant_id,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {"schema_version": "skeleton.delegation_hop.v1", **self.as_dict()}
        )


@dataclass(frozen=True, slots=True)
class PrincipalAuthority:
    principal_id: str
    principal_type: str
    tenant_id: str
    authentication_context_digest: str
    capabilities: tuple[str, ...]
    delegation_chain: tuple[DelegationHop, ...]
    session_id: str
    issued_at: float
    expires_at: float
    policy_version: str
    authority_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "principal_id", _token("principal_id", self.principal_id))
        object.__setattr__(self, "principal_type", _token("principal_type", self.principal_type))
        object.__setattr__(self, "tenant_id", _token("tenant_id", self.tenant_id))
        object.__setattr__(
            self,
            "authentication_context_digest",
            _sha("authentication_context_digest", self.authentication_context_digest),
        )
        object.__setattr__(self, "capabilities", _capabilities(self.capabilities))
        object.__setattr__(self, "session_id", _token("session_id", self.session_id))
        object.__setattr__(self, "policy_version", _token("policy_version", self.policy_version))
        object.__setattr__(self, "authority_id", _token("authority_id", self.authority_id))
        issued = _time("issued_at", self.issued_at)
        expires = _time("expires_at", self.expires_at)
        if expires <= issued:
            raise PrincipalAuthorityError("authority expiry must be after issuance")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)

        chain = tuple(self.delegation_chain)
        if any(not isinstance(hop, DelegationHop) for hop in chain):
            raise TypeError("delegation_chain must contain DelegationHop values")
        self._validate_chain(chain)
        object.__setattr__(self, "delegation_chain", chain)

    def _validate_chain(self, chain: tuple[DelegationHop, ...]) -> None:
        if not chain:
            return
        seen_principals: set[str] = set()
        prior_capabilities: set[str] | None = None
        prior_expiry: float | None = None
        prior_issued: float | None = None
        previous_delegate: str | None = None

        for index, hop in enumerate(chain):
            if hop.tenant_id != self.tenant_id:
                raise PrincipalAuthorityError("delegation tenant must remain invariant")
            if previous_delegate is not None and hop.delegator_id != previous_delegate:
                raise PrincipalAuthorityError("delegation chain identity is discontinuous")
            if index == 0:
                seen_principals.add(hop.delegator_id)
            if hop.delegate_id in seen_principals:
                raise PrincipalAuthorityError("delegation chain contains an identity cycle")
            seen_principals.add(hop.delegate_id)

            current = set(hop.capabilities)
            if prior_capabilities is not None and not current <= prior_capabilities:
                raise PrincipalAuthorityError("delegation capabilities cannot widen")
            if prior_expiry is not None and hop.expires_at > prior_expiry:
                raise PrincipalAuthorityError("delegation expiry cannot widen parent authority")
            if prior_issued is not None and hop.issued_at < prior_issued:
                raise PrincipalAuthorityError("delegation issuance cannot move backward")
            if prior_expiry is not None and hop.issued_at >= prior_expiry:
                raise PrincipalAuthorityError("delegation issued after parent expiry")

            prior_capabilities = current
            prior_expiry = hop.expires_at
            prior_issued = hop.issued_at
            previous_delegate = hop.delegate_id

        if chain[-1].delegate_id != self.principal_id:
            raise PrincipalAuthorityError("delegation chain must terminate at principal")
        if not set(self.capabilities) <= set(chain[-1].capabilities):
            raise PrincipalAuthorityError("principal capabilities exceed final delegation")
        if self.expires_at > chain[-1].expires_at:
            raise PrincipalAuthorityError("principal expiry exceeds final delegation")
        if self.issued_at != chain[-1].issued_at:
            raise PrincipalAuthorityError("principal issuance must match final delegation")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.principal_authority.v1",
            "principal_id": self.principal_id,
            "principal_type": self.principal_type,
            "tenant_id": self.tenant_id,
            "authentication_context_digest": self.authentication_context_digest,
            "capabilities": list(self.capabilities),
            "delegation_chain": [hop.as_dict() for hop in self.delegation_chain],
            "session_id": self.session_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "policy_version": self.policy_version,
            "authority_id": self.authority_id,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.as_dict())

    def delegate(
        self,
        *,
        delegate_id: str,
        capabilities: Iterable[str],
        issued_at: float,
        expires_at: float,
        grant_id: str,
        authority_id: str,
    ) -> "PrincipalAuthority":
        child_id = _token("delegate_id", delegate_id)
        child_capabilities = _capabilities(capabilities)
        if not set(child_capabilities) <= set(self.capabilities):
            raise PrincipalAuthorityError("child capabilities cannot widen parent authority")
        child_issued = _time("issued_at", issued_at)
        child_expiry = _time("expires_at", expires_at)
        if child_issued < self.issued_at:
            raise PrincipalAuthorityError("child issuance cannot precede parent authority")
        if child_issued >= self.expires_at:
            raise PrincipalAuthorityError("child issuance must precede parent expiry")
        if child_expiry > self.expires_at:
            raise PrincipalAuthorityError("child expiry cannot exceed parent authority")
        if child_expiry <= child_issued:
            raise PrincipalAuthorityError("child expiry must be after child issuance")

        hop = DelegationHop(
            delegator_id=self.principal_id,
            delegate_id=child_id,
            tenant_id=self.tenant_id,
            capabilities=child_capabilities,
            issued_at=child_issued,
            expires_at=child_expiry,
            grant_id=grant_id,
        )
        return PrincipalAuthority(
            principal_id=child_id,
            principal_type="delegated-agent",
            tenant_id=self.tenant_id,
            authentication_context_digest=self.authentication_context_digest,
            capabilities=child_capabilities,
            delegation_chain=self.delegation_chain + (hop,),
            session_id=self.session_id,
            issued_at=child_issued,
            expires_at=child_expiry,
            policy_version=self.policy_version,
            authority_id=authority_id,
        )


@dataclass(frozen=True, slots=True)
class SideEffectAuthorityReceipt:
    action_id: str
    action_digest: str
    principal_id: str
    tenant_id: str
    session_id: str
    policy_version: str
    authority_digest: str
    required_capabilities: tuple[str, ...]
    accepted: bool
    reasons: tuple[str, ...]

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {
                "schema_version": "skeleton.side_effect_authority_receipt.v1",
                "action_id": self.action_id,
                "action_digest": self.action_digest,
                "principal_id": self.principal_id,
                "tenant_id": self.tenant_id,
                "session_id": self.session_id,
                "policy_version": self.policy_version,
                "authority_digest": self.authority_digest,
                "required_capabilities": list(self.required_capabilities),
                "accepted": self.accepted,
                "reasons": list(self.reasons),
            }
        )

    def require_accepted(self) -> "SideEffectAuthorityReceipt":
        if not self.accepted:
            raise PrincipalAuthorityError(
                "side effect is not authorized: " + ",".join(self.reasons)
            )
        return self


def authorize_side_effect(
    *,
    authority: PrincipalAuthority,
    action_id: str,
    action_payload: object,
    required_capabilities: Iterable[str],
    tenant_id: str,
    session_id: str,
    policy_version: str,
    observed_at: float,
) -> SideEffectAuthorityReceipt:
    if not isinstance(authority, PrincipalAuthority):
        raise TypeError("authority must be PrincipalAuthority")
    action = _token("action_id", action_id)
    tenant = _token("tenant_id", tenant_id)
    session = _token("session_id", session_id)
    policy = _token("policy_version", policy_version)
    required = _capabilities(required_capabilities)
    observed = _time("observed_at", observed_at)
    action_digest = _canonical_digest(action_payload)

    reasons: list[str] = []
    if observed < authority.issued_at:
        reasons.append("authority-not-yet-valid")
    if observed >= authority.expires_at:
        reasons.append("authority-expired")
    if tenant != authority.tenant_id:
        reasons.append("tenant-mismatch")
    if session != authority.session_id:
        reasons.append("session-mismatch")
    if policy != authority.policy_version:
        reasons.append("policy-version-mismatch")
    if not set(required) <= set(authority.capabilities):
        reasons.append("capability-not-granted")

    return SideEffectAuthorityReceipt(
        action_id=action,
        action_digest=action_digest,
        principal_id=authority.principal_id,
        tenant_id=authority.tenant_id,
        session_id=authority.session_id,
        policy_version=authority.policy_version,
        authority_digest=authority.digest,
        required_capabilities=required,
        accepted=not reasons,
        reasons=tuple(reasons),
    )


__all__ = [
    "DelegationHop",
    "PrincipalAuthority",
    "PrincipalAuthorityError",
    "SideEffectAuthorityReceipt",
    "authorize_side_effect",
]
