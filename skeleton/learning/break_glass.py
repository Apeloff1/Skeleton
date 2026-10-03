"""Dependency-reduced safe-mode and break-glass authority for AI operations.

Break-glass is deliberately narrower than normal authority: it is time-bounded,
scope-bounded, dual-approved, non-self-approving, replay-resistant and unable to
promote/train arbitrary models. Every decision produces a deterministic receipt
that can be bound into the learning audit chain.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable


class BreakGlassError(RuntimeError):
    pass


SAFE_OPERATIONS = frozenset(
    {
        "disable_model",
        "freeze_training",
        "freeze_promotion",
        "revoke_model",
        "activate_known_good_model",
        "rollback_known_good_checkpoint",
        "disable_external_tools",
        "enter_read_only_mode",
    }
)

FORBIDDEN_OPERATIONS = frozenset(
    {
        "train_model",
        "promote_model",
        "modify_policy",
        "create_principal",
        "grant_role",
        "disable_audit",
        "delete_evidence",
        "execute_arbitrary_code",
    }
)


def _text(name: str, value: object, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BreakGlassError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise BreakGlassError(f"{name} exceeds {maximum} characters")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, 64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise BreakGlassError(f"{name} must be lowercase sha256")
    return result


def _stable_digest(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise BreakGlassError("break-glass value is not deterministic JSON") from exc
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class BreakGlassGrant:
    grant_id: str
    requester: str
    approvers: tuple[str, ...]
    allowed_operations: tuple[str, ...]
    target_scope: tuple[str, ...]
    issued_unix_s: int
    expires_unix_s: int
    nonce: str
    policy_digest: str
    incident_ref: str

    def __post_init__(self) -> None:
        for field_name in ("grant_id", "requester", "nonce", "incident_ref"):
            object.__setattr__(self, field_name, _text(field_name, getattr(self, field_name)))
        object.__setattr__(self, "policy_digest", _sha("policy_digest", self.policy_digest))
        if isinstance(self.issued_unix_s, bool) or not isinstance(self.issued_unix_s, int):
            raise BreakGlassError("issued_unix_s must be integer")
        if isinstance(self.expires_unix_s, bool) or not isinstance(self.expires_unix_s, int):
            raise BreakGlassError("expires_unix_s must be integer")
        if self.expires_unix_s <= self.issued_unix_s:
            raise BreakGlassError("grant expiry must be after issue time")
        if self.expires_unix_s - self.issued_unix_s > 3600:
            raise BreakGlassError("break-glass grant may not exceed one hour")

        approvers = tuple(_text("approver", item) for item in self.approvers)
        if len(approvers) < 2 or len(set(approvers)) != len(approvers):
            raise BreakGlassError("at least two unique approvers are required")
        if self.requester in approvers:
            raise BreakGlassError("requester may not approve own break-glass grant")
        object.__setattr__(self, "approvers", approvers)

        operations = tuple(_text("operation", item) for item in self.allowed_operations)
        if not operations or len(set(operations)) != len(operations):
            raise BreakGlassError("allowed_operations must be non-empty and unique")
        unknown = set(operations) - SAFE_OPERATIONS
        if unknown:
            raise BreakGlassError(f"unsafe break-glass operations requested: {sorted(unknown)}")
        if set(operations) & FORBIDDEN_OPERATIONS:
            raise BreakGlassError("forbidden operation included in break-glass grant")
        object.__setattr__(self, "allowed_operations", operations)

        scope = tuple(_text("target_scope", item, 1024) for item in self.target_scope)
        if not scope or len(set(scope)) != len(scope):
            raise BreakGlassError("target_scope must be non-empty and unique")
        object.__setattr__(self, "target_scope", scope)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.break_glass_grant.v1",
            "grant_id": self.grant_id,
            "requester": self.requester,
            "approvers": list(self.approvers),
            "allowed_operations": list(self.allowed_operations),
            "target_scope": list(self.target_scope),
            "issued_unix_s": self.issued_unix_s,
            "expires_unix_s": self.expires_unix_s,
            "nonce": self.nonce,
            "policy_digest": self.policy_digest,
            "incident_ref": self.incident_ref,
        }

    @property
    def digest(self) -> str:
        return _stable_digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class BreakGlassRequest:
    grant_digest: str
    operation: str
    target: str
    actor: str
    now_unix_s: int
    nonce: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "grant_digest", _sha("grant_digest", self.grant_digest))
        for field_name in ("operation", "target", "actor", "nonce"):
            object.__setattr__(self, field_name, _text(field_name, getattr(self, field_name), 1024))
        if isinstance(self.now_unix_s, bool) or not isinstance(self.now_unix_s, int):
            raise BreakGlassError("now_unix_s must be integer")


@dataclass(frozen=True, slots=True)
class BreakGlassReceipt:
    grant_id: str
    grant_digest: str
    operation: str
    target: str
    actor: str
    admitted: bool
    reason: str
    incident_ref: str
    policy_digest: str

    @property
    def digest(self) -> str:
        return _stable_digest(
            {
                "schema_version": "skeleton.break_glass_receipt.v1",
                "grant_id": self.grant_id,
                "grant_digest": self.grant_digest,
                "operation": self.operation,
                "target": self.target,
                "actor": self.actor,
                "admitted": self.admitted,
                "reason": self.reason,
                "incident_ref": self.incident_ref,
                "policy_digest": self.policy_digest,
            }
        )


class BreakGlassAuthority:
    def __init__(self) -> None:
        self._used_nonces: set[tuple[str, str]] = set()

    def evaluate(
        self,
        grant: BreakGlassGrant,
        request: BreakGlassRequest,
    ) -> BreakGlassReceipt:
        blockers: list[str] = []
        if request.grant_digest != grant.digest:
            blockers.append("grant digest mismatch")
        if request.actor != grant.requester:
            blockers.append("actor does not own grant")
        if request.operation not in grant.allowed_operations:
            blockers.append("operation is outside grant")
        if request.operation in FORBIDDEN_OPERATIONS:
            blockers.append("operation is forbidden in break-glass mode")
        if request.target not in grant.target_scope:
            blockers.append("target is outside grant scope")
        if request.now_unix_s < grant.issued_unix_s:
            blockers.append("request predates grant")
        if request.now_unix_s >= grant.expires_unix_s:
            blockers.append("grant is expired")

        replay_key = (grant.digest, request.nonce)
        if request.nonce != grant.nonce:
            blockers.append("nonce does not match grant")
        elif replay_key in self._used_nonces:
            blockers.append("break-glass grant nonce has already been consumed")

        admitted = not blockers
        if admitted:
            self._used_nonces.add(replay_key)
        return BreakGlassReceipt(
            grant_id=grant.grant_id,
            grant_digest=grant.digest,
            operation=request.operation,
            target=request.target,
            actor=request.actor,
            admitted=admitted,
            reason="admitted" if admitted else "; ".join(blockers),
            incident_ref=grant.incident_ref,
            policy_digest=grant.policy_digest,
        )

    def consumed(self, grant: BreakGlassGrant) -> bool:
        return (grant.digest, grant.nonce) in self._used_nonces


__all__ = [
    "BreakGlassAuthority",
    "BreakGlassError",
    "BreakGlassGrant",
    "BreakGlassReceipt",
    "BreakGlassRequest",
    "FORBIDDEN_OPERATIONS",
    "SAFE_OPERATIONS",
]
