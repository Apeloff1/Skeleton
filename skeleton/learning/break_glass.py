"""Dependency-reduced safe-mode and break-glass authority for AI operations.

Break-glass is deliberately narrower than normal authority: it is time-bounded,
scope-bounded, dual-approved, non-self-approving, replay-resistant and unable to
promote/train arbitrary models. Every decision is serialized through a
concurrency-safe authority and appended to a hash-linked audit receipt chain.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import threading


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
    if result != value or len(result) > maximum:
        raise BreakGlassError(f"{name} must be normalized text")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, 64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise BreakGlassError(f"{name} must be lowercase sha256")
    return result


def _nonnegative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BreakGlassError(f"{name} must be a non-negative integer")
    return value


def _positive_int(name: str, value: object) -> int:
    result = _nonnegative_int(name, value)
    if result == 0:
        raise BreakGlassError(f"{name} must be positive")
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
            object.__setattr__(
                self,
                field_name,
                _text(field_name, getattr(self, field_name)),
            )
        object.__setattr__(
            self,
            "policy_digest",
            _sha("policy_digest", self.policy_digest),
        )
        issued = _nonnegative_int("issued_unix_s", self.issued_unix_s)
        expires = _nonnegative_int("expires_unix_s", self.expires_unix_s)
        if expires <= issued:
            raise BreakGlassError("grant expiry must be after issue time")
        if expires - issued > 3600:
            raise BreakGlassError("break-glass grant may not exceed one hour")
        object.__setattr__(self, "issued_unix_s", issued)
        object.__setattr__(self, "expires_unix_s", expires)

        approvers = tuple(sorted(_text("approver", item) for item in self.approvers))
        if len(approvers) < 2 or len(set(approvers)) != len(approvers):
            raise BreakGlassError("at least two unique approvers are required")
        if self.requester in approvers:
            raise BreakGlassError("requester may not approve own break-glass grant")
        object.__setattr__(self, "approvers", approvers)

        operations = tuple(
            sorted(_text("operation", item) for item in self.allowed_operations)
        )
        if not operations or len(set(operations)) != len(operations):
            raise BreakGlassError(
                "allowed_operations must be non-empty and unique"
            )
        unknown = set(operations) - SAFE_OPERATIONS
        if unknown:
            raise BreakGlassError(
                f"unsafe break-glass operations requested: {sorted(unknown)}"
            )
        if set(operations) & FORBIDDEN_OPERATIONS:
            raise BreakGlassError(
                "forbidden operation included in break-glass grant"
            )
        object.__setattr__(self, "allowed_operations", operations)

        scope = tuple(
            sorted(_text("target_scope", item, 1024) for item in self.target_scope)
        )
        if not scope or len(set(scope)) != len(scope):
            raise BreakGlassError("target_scope must be non-empty and unique")
        object.__setattr__(self, "target_scope", scope)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.break_glass_grant.v2",
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
        object.__setattr__(
            self,
            "grant_digest",
            _sha("grant_digest", self.grant_digest),
        )
        for field_name in ("operation", "target", "actor", "nonce"):
            object.__setattr__(
                self,
                field_name,
                _text(field_name, getattr(self, field_name), 1024),
            )
        object.__setattr__(
            self,
            "now_unix_s",
            _nonnegative_int("now_unix_s", self.now_unix_s),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.break_glass_request.v2",
            "grant_digest": self.grant_digest,
            "operation": self.operation,
            "target": self.target,
            "actor": self.actor,
            "now_unix_s": self.now_unix_s,
            "nonce": self.nonce,
        }

    @property
    def digest(self) -> str:
        return _stable_digest(self.as_dict())


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
    request_digest: str | None = None
    sequence: int = 0
    previous_receipt_digest: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "grant_id",
            "operation",
            "target",
            "actor",
            "reason",
            "incident_ref",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(field_name, getattr(self, field_name), 2048),
            )
        object.__setattr__(
            self,
            "grant_digest",
            _sha("grant_digest", self.grant_digest),
        )
        object.__setattr__(
            self,
            "policy_digest",
            _sha("policy_digest", self.policy_digest),
        )
        if not isinstance(self.admitted, bool):
            raise BreakGlassError("admitted must be boolean")
        if self.admitted and self.reason != "admitted":
            raise BreakGlassError("admitted receipt reason must be 'admitted'")
        if not self.admitted and self.reason == "admitted":
            raise BreakGlassError(
                "rejected receipt cannot claim admitted reason"
            )
        if self.request_digest is not None:
            object.__setattr__(
                self,
                "request_digest",
                _sha("request_digest", self.request_digest),
            )
        sequence = _nonnegative_int("sequence", self.sequence)
        object.__setattr__(self, "sequence", sequence)
        if self.previous_receipt_digest is not None:
            object.__setattr__(
                self,
                "previous_receipt_digest",
                _sha(
                    "previous_receipt_digest",
                    self.previous_receipt_digest,
                ),
            )
        if sequence == 0 and self.previous_receipt_digest is not None:
            raise BreakGlassError(
                "unsequenced receipt cannot have previous digest"
            )
        if sequence > 1 and self.previous_receipt_digest is None:
            raise BreakGlassError(
                "sequenced receipt after first requires previous digest"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.break_glass_receipt.v2",
            "grant_id": self.grant_id,
            "grant_digest": self.grant_digest,
            "operation": self.operation,
            "target": self.target,
            "actor": self.actor,
            "admitted": self.admitted,
            "reason": self.reason,
            "incident_ref": self.incident_ref,
            "policy_digest": self.policy_digest,
            "request_digest": self.request_digest,
            "sequence": self.sequence,
            "previous_receipt_digest": self.previous_receipt_digest,
        }

    @property
    def digest(self) -> str:
        return _stable_digest(self.as_dict())


class BreakGlassAuthority:
    """Concurrency-safe one-shot emergency authority with hash-linked audit."""

    def __init__(self, *, max_receipts: int = 4096) -> None:
        self._max_receipts = _positive_int("max_receipts", max_receipts)
        self._lock = threading.RLock()
        self._grant_bindings: dict[str, str] = {}
        self._nonce_bindings: dict[str, str] = {}
        self._used_nonces: set[tuple[str, str]] = set()
        self._receipts: list[BreakGlassReceipt] = []

    def register_grant(self, grant: BreakGlassGrant) -> str:
        if not isinstance(grant, BreakGlassGrant):
            raise TypeError("grant must be BreakGlassGrant")
        with self._lock:
            prior = self._grant_bindings.get(grant.grant_id)
            if prior is not None and prior != grant.digest:
                raise BreakGlassError(
                    "grant id is already bound to different immutable content"
                )
            nonce_prior = self._nonce_bindings.get(grant.nonce)
            if nonce_prior is not None and nonce_prior != grant.digest:
                raise BreakGlassError(
                    "grant nonce is already bound to another grant"
                )
            self._grant_bindings[grant.grant_id] = grant.digest
            self._nonce_bindings[grant.nonce] = grant.digest
            return grant.digest

    def evaluate(
        self,
        grant: BreakGlassGrant,
        request: BreakGlassRequest,
    ) -> BreakGlassReceipt:
        if not isinstance(grant, BreakGlassGrant):
            raise TypeError("grant must be BreakGlassGrant")
        if not isinstance(request, BreakGlassRequest):
            raise TypeError("request must be BreakGlassRequest")

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
        if request.nonce != grant.nonce:
            blockers.append("nonce does not match grant")

        replay_key = (grant.digest, request.nonce)
        with self._lock:
            prior_grant = self._grant_bindings.get(grant.grant_id)
            if prior_grant is not None and prior_grant != grant.digest:
                blockers.append("grant id was rebound to different content")
            prior_nonce = self._nonce_bindings.get(grant.nonce)
            if prior_nonce is not None and prior_nonce != grant.digest:
                blockers.append("grant nonce is bound to another grant")
            if replay_key in self._used_nonces:
                blockers.append(
                    "break-glass grant nonce has already been consumed"
                )
            if len(self._receipts) >= self._max_receipts:
                blockers.append("break-glass audit receipt capacity exhausted")

            admitted = not blockers
            if admitted:
                self._grant_bindings[grant.grant_id] = grant.digest
                self._nonce_bindings[grant.nonce] = grant.digest
                self._used_nonces.add(replay_key)

            sequence = len(self._receipts) + 1
            previous = self._receipts[-1].digest if self._receipts else None
            receipt = BreakGlassReceipt(
                grant_id=grant.grant_id,
                grant_digest=grant.digest,
                operation=request.operation,
                target=request.target,
                actor=request.actor,
                admitted=admitted,
                reason="admitted" if admitted else "; ".join(blockers),
                incident_ref=grant.incident_ref,
                policy_digest=grant.policy_digest,
                request_digest=request.digest,
                sequence=sequence,
                previous_receipt_digest=previous,
            )
            if len(self._receipts) < self._max_receipts:
                self._receipts.append(receipt)
            return receipt

    def consumed(self, grant: BreakGlassGrant) -> bool:
        if not isinstance(grant, BreakGlassGrant):
            raise TypeError("grant must be BreakGlassGrant")
        with self._lock:
            return (grant.digest, grant.nonce) in self._used_nonces

    def receipts(self) -> tuple[BreakGlassReceipt, ...]:
        with self._lock:
            return tuple(self._receipts)

    @property
    def audit_chain_digest(self) -> str:
        with self._lock:
            return _stable_digest(
                [receipt.digest for receipt in self._receipts]
            )

    def assert_audit_integrity(self) -> None:
        with self._lock:
            previous: str | None = None
            for index, receipt in enumerate(self._receipts, start=1):
                if receipt.sequence != index:
                    raise BreakGlassError(
                        "break-glass audit sequence is not contiguous"
                    )
                if receipt.previous_receipt_digest != previous:
                    raise BreakGlassError(
                        "break-glass audit hash chain is broken"
                    )
                previous = receipt.digest


__all__ = [
    "BreakGlassAuthority",
    "BreakGlassError",
    "BreakGlassGrant",
    "BreakGlassReceipt",
    "BreakGlassRequest",
    "FORBIDDEN_OPERATIONS",
    "SAFE_OPERATIONS",
]
