"""Typed contracts for governed AI side effects.

The model may propose effects, but proposal text is never authority. Authority is
represented by a separate EffectAuthorization bound to the exact proposal
digest and issued by a host-side policy boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_CAP_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_ALLOWED_RISKS = frozenset({"low", "medium", "high", "critical"})


class EffectContractError(ValueError):
    """Raised when an effect object violates the host contract."""


class EffectState(str, Enum):
    PROPOSED = "proposed"
    AUTHORIZED = "authorized"
    APPLYING = "applying"
    APPLIED = "applied"
    VERIFYING = "verifying"
    COMMITTED = "committed"
    COMPENSATING = "compensating"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"
    FAILED = "failed"
    PARTIAL_FAILURE = "partial_failure"
    DRY_RUN = "dry_run"


class BatchState(str, Enum):
    CREATED = "created"
    AUTHORIZING = "authorizing"
    AUTHORIZED = "authorized"
    APPLYING = "applying"
    VERIFYING = "verifying"
    COMMITTED = "committed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"
    FAILED = "failed"
    PARTIAL_FAILURE = "partial_failure"
    DRY_RUN = "dry_run"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise EffectContractError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise EffectContractError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def format_instant(value: datetime) -> str:
    return ensure_aware(value, "instant").isoformat().replace("+00:00", "Z")


def parse_instant(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise EffectContractError("instant must be non-empty text")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise EffectContractError("invalid ISO-8601 instant") from exc
    return ensure_aware(parsed, "instant")


def _freeze_json(value: Any, *, depth: int = 0) -> Any:
    if depth > 32:
        raise EffectContractError("JSON value exceeds maximum nesting depth")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EffectContractError("non-finite numbers are forbidden")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise EffectContractError("JSON object keys must be strings")
            frozen[key] = _freeze_json(child, depth=depth + 1)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(child, depth=depth + 1) for child in value)
    raise EffectContractError(f"unsupported JSON value: {type(value).__name__}")


def thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): thaw_json(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(v) for v in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        thaw_json(_freeze_json(value)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def require_digest(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise EffectContractError(f"{field_name} must be lowercase sha256")
    return value


def require_id(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise EffectContractError(f"{field_name} must be text")
    text = value.strip()
    if not _ID_RE.fullmatch(text):
        raise EffectContractError(f"{field_name} has invalid syntax")
    return text


def require_capability(value: str) -> str:
    if not isinstance(value, str):
        raise EffectContractError("required_capability must be text")
    text = value.strip().lower()
    if not _CAP_RE.fullmatch(text):
        raise EffectContractError("required_capability has invalid syntax")
    return text


def require_nonempty(value: str, field_name: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str):
        raise EffectContractError(f"{field_name} must be text")
    text = value.strip()
    if not text:
        raise EffectContractError(f"{field_name} must be non-empty")
    if len(text) > maximum:
        raise EffectContractError(f"{field_name} exceeds {maximum} characters")
    return text


@dataclass(frozen=True, slots=True)
class EffectPostcondition:
    name: str
    description: str
    required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_id(self.name, "postcondition.name"))
        object.__setattr__(
            self,
            "description",
            require_nonempty(self.description, "postcondition.description", maximum=1024),
        )
        if not isinstance(self.required, bool):
            raise EffectContractError("postcondition.required must be bool")

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "required": self.required}


@dataclass(frozen=True, slots=True)
class EffectProposal:
    proposal_id: str
    tenant_id: str
    operation_id: str
    kind: str
    target: str
    payload: Mapping[str, Any]
    required_capability: str
    idempotency_key: str
    postconditions: tuple[EffectPostcondition, ...]
    reversible: bool = True
    risk_class: str = "medium"
    timeout_ms: int = 30_000
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_id", require_id(self.proposal_id, "proposal_id"))
        object.__setattr__(self, "tenant_id", require_id(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "operation_id", require_id(self.operation_id, "operation_id"))
        object.__setattr__(self, "kind", require_id(self.kind, "kind"))
        object.__setattr__(self, "target", require_nonempty(self.target, "target", maximum=2048))
        object.__setattr__(self, "required_capability", require_capability(self.required_capability))
        object.__setattr__(self, "idempotency_key", require_id(self.idempotency_key, "idempotency_key"))
        object.__setattr__(self, "payload", _freeze_json(self.payload))
        object.__setattr__(self, "metadata", _freeze_json(self.metadata))
        pcs = tuple(self.postconditions)
        if not all(isinstance(item, EffectPostcondition) for item in pcs):
            raise EffectContractError("postconditions must contain EffectPostcondition values")
        if len({item.name for item in pcs}) != len(pcs):
            raise EffectContractError("postcondition names must be unique")
        object.__setattr__(self, "postconditions", pcs)
        if not isinstance(self.reversible, bool):
            raise EffectContractError("reversible must be bool")
        risk = str(self.risk_class).strip().lower()
        if risk not in _ALLOWED_RISKS:
            raise EffectContractError("unsupported risk_class")
        object.__setattr__(self, "risk_class", risk)
        if isinstance(self.timeout_ms, bool) or not isinstance(self.timeout_ms, int):
            raise EffectContractError("timeout_ms must be int")
        if not 1 <= self.timeout_ms <= 600_000:
            raise EffectContractError("timeout_ms must be in [1, 600000]")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "skeleton.ai.effect.proposal.v1",
            "proposal_id": self.proposal_id,
            "tenant_id": self.tenant_id,
            "operation_id": self.operation_id,
            "kind": self.kind,
            "target": self.target,
            "payload": thaw_json(self.payload),
            "required_capability": self.required_capability,
            "idempotency_key": self.idempotency_key,
            "postconditions": [item.as_dict() for item in self.postconditions],
            "reversible": self.reversible,
            "risk_class": self.risk_class,
            "timeout_ms": self.timeout_ms,
            "metadata": thaw_json(self.metadata),
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())


@dataclass(frozen=True, slots=True)
class EffectAuthorization:
    authorization_id: str
    proposal_digest: str
    subject_id: str
    decision: str
    capabilities: tuple[str, ...]
    policy_id: str
    reason: str
    issued_at: datetime
    expires_at: datetime
    approval_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "authorization_id", require_id(self.authorization_id, "authorization_id"))
        object.__setattr__(self, "proposal_digest", require_digest(self.proposal_digest, "proposal_digest"))
        object.__setattr__(self, "subject_id", require_id(self.subject_id, "subject_id"))
        decision = str(self.decision).strip().lower()
        if decision not in {"allow", "deny"}:
            raise EffectContractError("decision must be allow or deny")
        object.__setattr__(self, "decision", decision)
        caps = tuple(dict.fromkeys(require_capability(cap) for cap in self.capabilities))
        object.__setattr__(self, "capabilities", caps)
        object.__setattr__(self, "policy_id", require_id(self.policy_id, "policy_id"))
        object.__setattr__(self, "reason", require_nonempty(self.reason, "reason", maximum=2048))
        issued = ensure_aware(self.issued_at, "issued_at")
        expires = ensure_aware(self.expires_at, "expires_at")
        if expires <= issued:
            raise EffectContractError("expires_at must be after issued_at")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        refs = tuple(require_id(ref, "approval_ref") for ref in self.approval_refs)
        if len(set(refs)) != len(refs):
            raise EffectContractError("approval_refs must be unique")
        object.__setattr__(self, "approval_refs", refs)

    def permits(self, proposal: EffectProposal, *, subject_id: str, now: datetime) -> bool:
        instant = ensure_aware(now, "now")
        return (
            self.decision == "allow"
            and self.proposal_digest == proposal.digest
            and self.subject_id == subject_id
            and self.issued_at <= instant < self.expires_at
            and proposal.required_capability in self.capabilities
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "skeleton.ai.effect.authorization.v1",
            "authorization_id": self.authorization_id,
            "proposal_digest": self.proposal_digest,
            "subject_id": self.subject_id,
            "decision": self.decision,
            "capabilities": list(self.capabilities),
            "policy_id": self.policy_id,
            "reason": self.reason,
            "issued_at": format_instant(self.issued_at),
            "expires_at": format_instant(self.expires_at),
            "approval_refs": list(self.approval_refs),
        }


@dataclass(frozen=True, slots=True)
class ApplyResult:
    executor_id: str
    status: str
    output: Mapping[str, Any]
    compensation_token: Mapping[str, Any] | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "executor_id", require_id(self.executor_id, "executor_id"))
        status = str(self.status).strip().lower()
        if status not in {"applied", "noop"}:
            raise EffectContractError("apply status must be applied or noop")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "output", _freeze_json(self.output))
        if self.compensation_token is not None:
            object.__setattr__(self, "compensation_token", _freeze_json(self.compensation_token))
        object.__setattr__(self, "evidence_refs", tuple(require_id(ref, "evidence_ref") for ref in self.evidence_refs))


@dataclass(frozen=True, slots=True)
class EffectExecutionReceipt:
    receipt_id: str
    proposal_digest: str
    executor_id: str
    status: str
    started_at: datetime
    completed_at: datetime
    output: Mapping[str, Any]
    compensation_token: Mapping[str, Any] | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "receipt_id", require_id(self.receipt_id, "receipt_id"))
        object.__setattr__(self, "proposal_digest", require_digest(self.proposal_digest, "proposal_digest"))
        object.__setattr__(self, "executor_id", require_id(self.executor_id, "executor_id"))
        status = str(self.status).strip().lower()
        if status not in {"applied", "noop"}:
            raise EffectContractError("receipt status must be applied or noop")
        object.__setattr__(self, "status", status)
        started = ensure_aware(self.started_at, "started_at")
        completed = ensure_aware(self.completed_at, "completed_at")
        if completed < started:
            raise EffectContractError("completed_at precedes started_at")
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "completed_at", completed)
        object.__setattr__(self, "output", _freeze_json(self.output))
        if self.compensation_token is not None:
            object.__setattr__(self, "compensation_token", _freeze_json(self.compensation_token))
        object.__setattr__(self, "evidence_refs", tuple(require_id(ref, "evidence_ref") for ref in self.evidence_refs))

    @property
    def output_digest(self) -> str:
        return digest_json(self.output)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "skeleton.ai.effect.execution.v1",
            "receipt_id": self.receipt_id,
            "proposal_digest": self.proposal_digest,
            "executor_id": self.executor_id,
            "status": self.status,
            "started_at": format_instant(self.started_at),
            "completed_at": format_instant(self.completed_at),
            "output": thaw_json(self.output),
            "output_digest": self.output_digest,
            "compensation_token": None if self.compensation_token is None else thaw_json(self.compensation_token),
            "evidence_refs": list(self.evidence_refs),
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())


@dataclass(frozen=True, slots=True)
class VerificationResult:
    verifier_id: str
    passed: bool
    postconditions: Mapping[str, bool]
    observed: Mapping[str, Any]
    reason: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "verifier_id", require_id(self.verifier_id, "verifier_id"))
        if not isinstance(self.passed, bool):
            raise EffectContractError("passed must be bool")
        pcs: dict[str, bool] = {}
        for key, value in self.postconditions.items():
            name = require_id(str(key), "postcondition result name")
            if not isinstance(value, bool):
                raise EffectContractError("postcondition results must be bool")
            pcs[name] = value
        object.__setattr__(self, "postconditions", MappingProxyType(pcs))
        object.__setattr__(self, "observed", _freeze_json(self.observed))
        object.__setattr__(self, "reason", require_nonempty(self.reason, "reason", maximum=2048))
        object.__setattr__(self, "evidence_refs", tuple(require_id(ref, "evidence_ref") for ref in self.evidence_refs))


@dataclass(frozen=True, slots=True)
class EffectVerificationReceipt:
    proposal_digest: str
    execution_digest: str
    verifier_id: str
    passed: bool
    postconditions: Mapping[str, bool]
    observed: Mapping[str, Any]
    reason: str
    verified_at: datetime
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposal_digest", require_digest(self.proposal_digest, "proposal_digest"))
        object.__setattr__(self, "execution_digest", require_digest(self.execution_digest, "execution_digest"))
        object.__setattr__(self, "verifier_id", require_id(self.verifier_id, "verifier_id"))
        if not isinstance(self.passed, bool):
            raise EffectContractError("passed must be bool")
        pcs: dict[str, bool] = {}
        for key, value in self.postconditions.items():
            pcs[require_id(str(key), "postcondition result name")] = bool(value)
        object.__setattr__(self, "postconditions", MappingProxyType(pcs))
        object.__setattr__(self, "observed", _freeze_json(self.observed))
        object.__setattr__(self, "reason", require_nonempty(self.reason, "reason", maximum=2048))
        object.__setattr__(self, "verified_at", ensure_aware(self.verified_at, "verified_at"))
        object.__setattr__(self, "evidence_refs", tuple(require_id(ref, "evidence_ref") for ref in self.evidence_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "skeleton.ai.effect.verification.v1",
            "proposal_digest": self.proposal_digest,
            "execution_digest": self.execution_digest,
            "verifier_id": self.verifier_id,
            "passed": self.passed,
            "postconditions": dict(self.postconditions),
            "observed": thaw_json(self.observed),
            "reason": self.reason,
            "verified_at": format_instant(self.verified_at),
            "evidence_refs": list(self.evidence_refs),
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())


@dataclass(frozen=True, slots=True)
class CompensationResult:
    executor_id: str
    compensated: bool
    output: Mapping[str, Any]
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "executor_id", require_id(self.executor_id, "executor_id"))
        if not isinstance(self.compensated, bool):
            raise EffectContractError("compensated must be bool")
        object.__setattr__(self, "output", _freeze_json(self.output))
        object.__setattr__(self, "evidence_refs", tuple(require_id(ref, "evidence_ref") for ref in self.evidence_refs))


@dataclass(frozen=True, slots=True)
class CoreExecution:
    execution_id: str
    operation_id: str
    tenant_id: str
    output_text: str
    evidence_digest: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "execution_id", require_id(self.execution_id, "execution_id"))
        object.__setattr__(self, "operation_id", require_id(self.operation_id, "operation_id"))
        object.__setattr__(self, "tenant_id", require_id(self.tenant_id, "tenant_id"))
        if not isinstance(self.output_text, str):
            raise EffectContractError("output_text must be text")
        object.__setattr__(self, "evidence_digest", require_digest(self.evidence_digest, "evidence_digest"))
        object.__setattr__(self, "evidence_refs", tuple(require_id(ref, "evidence_ref") for ref in self.evidence_refs))


@dataclass(frozen=True, slots=True)
class CommittedEffect:
    proposal: EffectProposal
    authorization: EffectAuthorization
    execution: EffectExecutionReceipt
    verification: EffectVerificationReceipt

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposal": self.proposal.as_dict(),
            "proposal_digest": self.proposal.digest,
            "authorization": self.authorization.as_dict(),
            "execution": self.execution.as_dict(),
            "verification": self.verification.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class EffectBatchResult:
    transaction_id: str
    state: BatchState
    core: CoreExecution
    effects: tuple[CommittedEffect, ...] = ()
    rejected_proposal_ids: tuple[str, ...] = ()
    rolled_back_proposal_ids: tuple[str, ...] = ()
    reason: str = ""
    replayed: bool = False
    event_chain_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "transaction_id", require_id(self.transaction_id, "transaction_id"))
        if not isinstance(self.state, BatchState):
            raise EffectContractError("state must be BatchState")
        if not isinstance(self.core, CoreExecution):
            raise EffectContractError("core must be CoreExecution")
        object.__setattr__(self, "effects", tuple(self.effects))
        object.__setattr__(self, "rejected_proposal_ids", tuple(self.rejected_proposal_ids))
        object.__setattr__(self, "rolled_back_proposal_ids", tuple(self.rolled_back_proposal_ids))
        if self.event_chain_digest is not None:
            object.__setattr__(self, "event_chain_digest", require_digest(self.event_chain_digest, "event_chain_digest"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "skeleton.ai.effect.batch_result.v1",
            "transaction_id": self.transaction_id,
            "state": self.state.value,
            "core": {
                "execution_id": self.core.execution_id,
                "operation_id": self.core.operation_id,
                "tenant_id": self.core.tenant_id,
                "evidence_digest": self.core.evidence_digest,
                "evidence_refs": list(self.core.evidence_refs),
            },
            "effects": [effect.as_dict() for effect in self.effects],
            "rejected_proposal_ids": list(self.rejected_proposal_ids),
            "rolled_back_proposal_ids": list(self.rolled_back_proposal_ids),
            "reason": self.reason,
            "replayed": self.replayed,
            "event_chain_digest": self.event_chain_digest,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())


def postconditions_from_json(value: Sequence[Mapping[str, Any]]) -> tuple[EffectPostcondition, ...]:
    return tuple(
        EffectPostcondition(
            name=str(item["name"]),
            description=str(item["description"]),
            required=bool(item.get("required", True)),
        )
        for item in value
    )
