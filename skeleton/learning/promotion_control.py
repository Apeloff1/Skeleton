"""Champion/challenger promotion control for VOL-101.

Promotion is an evidence-bearing state transition, not a boolean attached to a
candidate. Predeclared metrics, independent evaluation, independently verified
canary evidence, immutable decision identities and exact rollback restoration
are all enforced before a candidate can become active.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
import threading
from typing import Sequence


_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


class ImprovementError(ValueError):
    pass


class PromotionStatus(str, Enum):
    PROMOTE = "promote"
    REJECT = "reject"


def _id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ImprovementError(f"{field} must be stable identifier")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ImprovementError(f"{field} must be sha256")
    return value


def _scope(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImprovementError("isolated experiment scope required")
    normalized = value.strip()
    if normalized != value or len(normalized) > 512:
        raise ImprovementError("experiment_scope must be normalized")
    return normalized


def _dig(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ImprovementError("promotion evidence must be deterministic JSON") from exc
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ImprovementCandidate:
    candidate_id: str
    champion_digest: str
    challenger_digest: str
    experiment_scope: str
    metric_ids: tuple[str, ...]
    builder_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _id(self.candidate_id, "candidate_id"),
        )
        object.__setattr__(
            self,
            "builder_id",
            _id(self.builder_id, "builder_id"),
        )
        object.__setattr__(
            self,
            "champion_digest",
            _sha(self.champion_digest, "champion_digest"),
        )
        object.__setattr__(
            self,
            "challenger_digest",
            _sha(self.challenger_digest, "challenger_digest"),
        )
        if self.champion_digest == self.challenger_digest:
            raise ImprovementError("challenger must differ from champion")
        object.__setattr__(
            self,
            "experiment_scope",
            _scope(self.experiment_scope),
        )
        if not isinstance(self.metric_ids, tuple) or len(self.metric_ids) > 256:
            raise ImprovementError("metric_ids must be bounded tuple")
        metrics = tuple(_id(item, "metric_id") for item in self.metric_ids)
        if not metrics:
            raise ImprovementError("predeclared metrics required")
        if len(metrics) != len(set(metrics)):
            raise ImprovementError("duplicate predeclared metric")
        object.__setattr__(self, "metric_ids", tuple(sorted(metrics)))

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.improvement_candidate.v2",
            "candidate_id": self.candidate_id,
            "champion_digest": self.champion_digest,
            "challenger_digest": self.challenger_digest,
            "experiment_scope": self.experiment_scope,
            "metric_ids": list(self.metric_ids),
            "builder_id": self.builder_id,
        }

    @property
    def digest(self) -> str:
        return _dig(self.as_dict())


@dataclass(frozen=True, slots=True)
class EvaluationBundle:
    candidate_digest: str
    metric_values: tuple[tuple[str, float], ...]
    safety_passed: bool
    cost_passed: bool
    robustness_passed: bool
    evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_digest",
            _sha(self.candidate_digest, "candidate_digest"),
        )
        object.__setattr__(
            self,
            "evidence_digest",
            _sha(self.evidence_digest, "evidence_digest"),
        )
        if not isinstance(self.metric_values, tuple) or len(self.metric_values) > 256:
            raise ImprovementError("metric_values must be bounded tuple")
        normalized: list[tuple[str, float]] = []
        for row in self.metric_values:
            if not isinstance(row, tuple) or len(row) != 2:
                raise ImprovementError(
                    "evaluation metric entries must be (id, value) tuples"
                )
            key = _id(row[0], "metric_id")
            value = row[1]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise ImprovementError("metric value must be finite numeric")
            normalized.append((key, float(value)))
        if not normalized:
            raise ImprovementError("evaluation metrics required")
        keys = [key for key, _ in normalized]
        if len(keys) != len(set(keys)):
            raise ImprovementError("duplicate evaluation metric")
        for field_name in (
            "safety_passed",
            "cost_passed",
            "robustness_passed",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ImprovementError(f"{field_name} must be bool")
        object.__setattr__(
            self,
            "metric_values",
            tuple(sorted(normalized)),
        )

    @property
    def gates_passed(self) -> bool:
        return (
            self.safety_passed
            and self.cost_passed
            and self.robustness_passed
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.evaluation_bundle.v2",
            "candidate_digest": self.candidate_digest,
            "metric_values": [
                [metric_id, value]
                for metric_id, value in self.metric_values
            ],
            "safety_passed": self.safety_passed,
            "cost_passed": self.cost_passed,
            "robustness_passed": self.robustness_passed,
            "evidence_digest": self.evidence_digest,
        }

    @property
    def digest(self) -> str:
        return _dig(self.as_dict())


@dataclass(frozen=True, slots=True)
class CanaryEvidence:
    candidate_digest: str
    canary_digest: str
    safety_passed: bool
    quality_passed: bool
    rollback_ready: bool
    verifier_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_digest",
            _sha(self.candidate_digest, "candidate_digest"),
        )
        object.__setattr__(
            self,
            "canary_digest",
            _sha(self.canary_digest, "canary_digest"),
        )
        object.__setattr__(
            self,
            "verifier_id",
            _id(self.verifier_id, "verifier_id"),
        )
        for field_name in (
            "safety_passed",
            "quality_passed",
            "rollback_ready",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ImprovementError(f"{field_name} must be bool")

    @property
    def gates_passed(self) -> bool:
        return (
            self.safety_passed
            and self.quality_passed
            and self.rollback_ready
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.canary_evidence.v2",
            "candidate_digest": self.candidate_digest,
            "canary_digest": self.canary_digest,
            "safety_passed": self.safety_passed,
            "quality_passed": self.quality_passed,
            "rollback_ready": self.rollback_ready,
            "verifier_id": self.verifier_id,
        }

    @property
    def digest(self) -> str:
        return _dig(self.as_dict())


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    decision_id: str
    candidate_digest: str
    verifier_id: str
    status: PromotionStatus
    evaluation_digest: str
    canary_digest: str | None
    canary_verifier_id: str | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_id",
            _id(self.decision_id, "decision_id"),
        )
        object.__setattr__(
            self,
            "candidate_digest",
            _sha(self.candidate_digest, "candidate_digest"),
        )
        object.__setattr__(
            self,
            "verifier_id",
            _id(self.verifier_id, "verifier_id"),
        )
        object.__setattr__(
            self,
            "evaluation_digest",
            _sha(self.evaluation_digest, "evaluation_digest"),
        )
        if not isinstance(self.status, PromotionStatus):
            raise ImprovementError("status must be PromotionStatus")
        if self.canary_digest is not None:
            object.__setattr__(
                self,
                "canary_digest",
                _sha(self.canary_digest, "canary_digest"),
            )
        if self.canary_verifier_id is not None:
            object.__setattr__(
                self,
                "canary_verifier_id",
                _id(self.canary_verifier_id, "canary_verifier_id"),
            )
        if self.status is PromotionStatus.PROMOTE:
            if self.canary_digest is None or self.canary_verifier_id is None:
                raise ImprovementError(
                    "promotion requires verified canary evidence"
                )
        elif self.canary_digest is not None or self.canary_verifier_id is not None:
            raise ImprovementError(
                "rejected decision cannot carry promotion canary authority"
            )
        if not isinstance(self.reason, str):
            raise ImprovementError("reason must be text")
        reason = self.reason.strip()
        if reason != self.reason or len(reason) > 512:
            raise ImprovementError("reason must be normalized bounded text")
        if self.status is PromotionStatus.REJECT and not reason:
            raise ImprovementError("rejected decision requires reason")
        object.__setattr__(self, "reason", reason)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.promotion_decision.v2",
            "decision_id": self.decision_id,
            "candidate_digest": self.candidate_digest,
            "verifier_id": self.verifier_id,
            "status": self.status.value,
            "evaluation_digest": self.evaluation_digest,
            "canary_digest": self.canary_digest,
            "canary_verifier_id": self.canary_verifier_id,
            "reason": self.reason,
        }

    @property
    def digest(self) -> str:
        return _dig(self.as_dict())


@dataclass(frozen=True, slots=True)
class RollbackReceipt:
    decision_id: str
    promoted_digest: str
    restored_digest: str
    rollback_evidence_digest: str
    decision_digest: str | None = None
    verifier_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_id",
            _id(self.decision_id, "decision_id"),
        )
        for field_name in (
            "promoted_digest",
            "restored_digest",
            "rollback_evidence_digest",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha(getattr(self, field_name), field_name),
            )
        if self.promoted_digest == self.restored_digest:
            raise ImprovementError(
                "rollback must restore distinct champion"
            )
        if self.decision_digest is not None:
            object.__setattr__(
                self,
                "decision_digest",
                _sha(self.decision_digest, "decision_digest"),
            )
        if self.verifier_id is not None:
            object.__setattr__(
                self,
                "verifier_id",
                _id(self.verifier_id, "verifier_id"),
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.promotion_rollback.v2",
            "decision_id": self.decision_id,
            "promoted_digest": self.promoted_digest,
            "restored_digest": self.restored_digest,
            "rollback_evidence_digest": self.rollback_evidence_digest,
            "decision_digest": self.decision_digest,
            "verifier_id": self.verifier_id,
        }

    @property
    def digest(self) -> str:
        return _dig(self.as_dict())


def _validate_evaluation(
    candidate: ImprovementCandidate,
    evaluation: EvaluationBundle,
    verifier_id: str,
) -> str:
    if not isinstance(candidate, ImprovementCandidate):
        raise ImprovementError("candidate must be ImprovementCandidate")
    if not isinstance(evaluation, EvaluationBundle):
        raise ImprovementError("evaluation must be EvaluationBundle")
    verifier = _id(verifier_id, "verifier_id")
    if verifier == candidate.builder_id:
        raise ImprovementError(
            "promotion verifier must be independent"
        )
    if evaluation.candidate_digest != candidate.digest:
        raise ImprovementError("evaluation/candidate mismatch")
    observed = {key for key, _ in evaluation.metric_values}
    if observed != set(candidate.metric_ids):
        raise ImprovementError(
            "evaluation metrics differ from preregistration"
        )
    return verifier


def _rejection_reason(evaluation: EvaluationBundle) -> str:
    failed: list[str] = []
    if not evaluation.safety_passed:
        failed.append("safety")
    if not evaluation.cost_passed:
        failed.append("cost")
    if not evaluation.robustness_passed:
        failed.append("robustness")
    return "failed gates: " + ",".join(failed)


def decide(
    candidate: ImprovementCandidate,
    evaluation: EvaluationBundle,
    verifier_id: str,
    *,
    canary_digest: str | None,
) -> PromotionDecision:
    """Evaluate gates without accepting an untyped canary digest as authority.

    A passing candidate must use :func:`promote_with_canary`; a raw SHA cannot
    prove the canary's safety, quality, rollback-readiness, or verifier identity.
    """

    verifier = _validate_evaluation(candidate, evaluation, verifier_id)
    if evaluation.gates_passed:
        if canary_digest is not None:
            _sha(canary_digest, "canary_digest")
            raise ImprovementError(
                "raw canary digest cannot authorize promotion; "
                "use promote_with_canary"
            )
        raise ImprovementError(
            "promotion requires verified canary evidence"
        )
    if canary_digest is not None:
        raise ImprovementError(
            "rejected evaluation cannot carry canary promotion authority"
        )
    return PromotionDecision(
        decision_id="DECISION." + candidate.candidate_id,
        candidate_digest=candidate.digest,
        verifier_id=verifier,
        status=PromotionStatus.REJECT,
        evaluation_digest=evaluation.digest,
        canary_digest=None,
        canary_verifier_id=None,
        reason=_rejection_reason(evaluation),
    )


def promote_with_canary(
    candidate: ImprovementCandidate,
    evaluation: EvaluationBundle,
    verifier_id: str,
    canary: CanaryEvidence,
) -> PromotionDecision:
    verifier = _validate_evaluation(candidate, evaluation, verifier_id)
    if not evaluation.gates_passed:
        return PromotionDecision(
            decision_id="DECISION." + candidate.candidate_id,
            candidate_digest=candidate.digest,
            verifier_id=verifier,
            status=PromotionStatus.REJECT,
            evaluation_digest=evaluation.digest,
            canary_digest=None,
            canary_verifier_id=None,
            reason=_rejection_reason(evaluation),
        )
    if not isinstance(canary, CanaryEvidence):
        raise ImprovementError("canary must be CanaryEvidence")
    if canary.candidate_digest != candidate.digest:
        raise ImprovementError("canary/candidate mismatch")
    if not canary.gates_passed:
        raise ImprovementError(
            "canary gates must pass before promotion"
        )
    if canary.verifier_id == candidate.builder_id:
        raise ImprovementError(
            "canary verifier must be independent from builder"
        )
    if canary.verifier_id == verifier:
        raise ImprovementError(
            "canary verifier must differ from promotion verifier"
        )
    return PromotionDecision(
        decision_id="DECISION." + candidate.candidate_id,
        candidate_digest=candidate.digest,
        verifier_id=verifier,
        status=PromotionStatus.PROMOTE,
        evaluation_digest=evaluation.digest,
        canary_digest=canary.digest,
        canary_verifier_id=canary.verifier_id,
        reason="",
    )


def validate_rollback(
    candidate: ImprovementCandidate,
    decision: PromotionDecision,
    receipt: RollbackReceipt,
) -> None:
    if (
        not isinstance(candidate, ImprovementCandidate)
        or not isinstance(decision, PromotionDecision)
        or not isinstance(receipt, RollbackReceipt)
    ):
        raise ImprovementError("rollback inputs must be typed")
    if decision.status is not PromotionStatus.PROMOTE:
        raise ImprovementError(
            "rollback applies only to promoted candidate"
        )
    if (
        decision.candidate_digest != candidate.digest
        or receipt.decision_id != decision.decision_id
    ):
        raise ImprovementError("rollback identity mismatch")
    if (
        receipt.promoted_digest != candidate.challenger_digest
        or receipt.restored_digest != candidate.champion_digest
    ):
        raise ImprovementError(
            "rollback does not restore exact champion"
        )
    if receipt.decision_digest is None:
        raise ImprovementError(
            "rollback receipt must bind exact promotion decision digest"
        )
    if receipt.decision_digest != decision.digest:
        raise ImprovementError(
            "rollback receipt decision digest mismatch"
        )
    if receipt.verifier_id is None:
        raise ImprovementError(
            "rollback receipt requires independent verifier"
        )
    if receipt.verifier_id in {
        candidate.builder_id,
        decision.verifier_id,
        decision.canary_verifier_id,
    }:
        raise ImprovementError(
            "rollback verifier must be independently separated"
        )


class PromotionLedger:
    """Immutable candidate/decision/rollback ledger with replay-safe identities."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._candidate_bindings: dict[str, str] = {}
        self._decisions: dict[str, PromotionDecision] = {}
        self._rollbacks: dict[str, RollbackReceipt] = {}
        self._audit_digests: list[str] = []

    def register_candidate(
        self,
        candidate: ImprovementCandidate,
    ) -> str:
        if not isinstance(candidate, ImprovementCandidate):
            raise ImprovementError(
                "candidate must be ImprovementCandidate"
            )
        with self._lock:
            prior = self._candidate_bindings.get(candidate.candidate_id)
            if prior is not None and prior != candidate.digest:
                raise ImprovementError(
                    "candidate id is already bound to different content"
                )
            self._candidate_bindings[candidate.candidate_id] = candidate.digest
            return candidate.digest

    def record_decision(
        self,
        candidate: ImprovementCandidate,
        decision: PromotionDecision,
    ) -> PromotionDecision:
        if not isinstance(decision, PromotionDecision):
            raise ImprovementError(
                "decision must be PromotionDecision"
            )
        self.register_candidate(candidate)
        if decision.candidate_digest != candidate.digest:
            raise ImprovementError("decision/candidate mismatch")
        expected_id = "DECISION." + candidate.candidate_id
        if decision.decision_id != expected_id:
            raise ImprovementError(
                "decision id does not match candidate identity"
            )
        with self._lock:
            prior = self._decisions.get(decision.decision_id)
            if prior is not None:
                if prior == decision:
                    return prior
                raise ImprovementError(
                    "decision id is already bound to another decision"
                )
            self._decisions[decision.decision_id] = decision
            self._audit_digests.append(decision.digest)
            return decision

    def record_rollback(
        self,
        candidate: ImprovementCandidate,
        decision: PromotionDecision,
        *,
        rollback_evidence_digest: str,
        verifier_id: str,
    ) -> RollbackReceipt:
        self.record_decision(candidate, decision)
        if decision.status is not PromotionStatus.PROMOTE:
            raise ImprovementError(
                "rollback applies only to promoted candidate"
            )
        verifier = _id(verifier_id, "verifier_id")
        if verifier in {
            candidate.builder_id,
            decision.verifier_id,
            decision.canary_verifier_id,
        }:
            raise ImprovementError(
                "rollback verifier must be independently separated"
            )
        receipt = RollbackReceipt(
            decision_id=decision.decision_id,
            promoted_digest=candidate.challenger_digest,
            restored_digest=candidate.champion_digest,
            rollback_evidence_digest=_sha(
                rollback_evidence_digest,
                "rollback_evidence_digest",
            ),
            decision_digest=decision.digest,
            verifier_id=verifier,
        )
        validate_rollback(candidate, decision, receipt)
        with self._lock:
            prior = self._rollbacks.get(decision.decision_id)
            if prior is not None:
                if prior == receipt:
                    return prior
                raise ImprovementError(
                    "rollback decision is already bound to another receipt"
                )
            self._rollbacks[decision.decision_id] = receipt
            self._audit_digests.append(receipt.digest)
            return receipt

    def decision(self, decision_id: str) -> PromotionDecision:
        normalized = _id(decision_id, "decision_id")
        with self._lock:
            try:
                return self._decisions[normalized]
            except KeyError as exc:
                raise ImprovementError(
                    "promotion decision is unavailable"
                ) from exc

    def rollback(self, decision_id: str) -> RollbackReceipt | None:
        normalized = _id(decision_id, "decision_id")
        with self._lock:
            return self._rollbacks.get(normalized)

    @property
    def audit_chain_digest(self) -> str:
        with self._lock:
            return _dig(
                {
                    "schema_version": "skeleton.promotion_ledger.v2",
                    "entries": list(self._audit_digests),
                }
            )


__all__ = [
    "CanaryEvidence",
    "EvaluationBundle",
    "ImprovementCandidate",
    "ImprovementError",
    "PromotionDecision",
    "PromotionLedger",
    "PromotionStatus",
    "RollbackReceipt",
    "decide",
    "promote_with_canary",
    "validate_rollback",
]
