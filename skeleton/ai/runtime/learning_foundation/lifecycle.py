"""Bounded model lifecycle and migration candidates for P3-T2.

This registry is run-scoped reference control. Its ACTIVE state is local
candidate state, not a production routing change or durable promotion. The
canonical learning/evaluation planes retain production authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, fields
from enum import Enum
from functools import wraps
from threading import RLock

from skeleton.learning.model_program import ModelArtifact, TrainingReceipt


class ModelLifecycleError(RuntimeError):
    pass


def _locked(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return guarded


def _json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ModelLifecycleError("value is not deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelLifecycleError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise ModelLifecycleError(f"{name} exceeds {maximum} characters")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise ModelLifecycleError(f"{name} must be lowercase sha256")
    return result


def _refs(name: str, values: Sequence[str], *, minimum: int = 0) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ModelLifecycleError(f"{name} must be a sequence of references")
    if len(values) > 128:
        raise ModelLifecycleError(f"{name} exceeds 128 entries")
    out = []
    for raw in values:
        item = _text(name, raw)
        if item in out:
            raise ModelLifecycleError(f"{name} contains duplicate {item}")
        out.append(item)
    if len(out) < minimum:
        raise ModelLifecycleError(f"{name} requires at least {minimum} entries")
    return tuple(out)


def _positive(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ModelLifecycleError(f"{name} must be a positive integer")
    return value


def _score(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelLifecycleError("parity scores must be numeric")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ModelLifecycleError("parity scores must be in [0, 1]") from exc
    if not 0.0 <= result <= 1.0:
        raise ModelLifecycleError("parity scores must be in [0, 1]")
    return result


def _normalize_receipt(record: object) -> None:
    for item in fields(record):
        if item.name.endswith("_digest"):
            object.__setattr__(record, item.name, _sha(item.name, getattr(record, item.name)))
    object.__setattr__(record, "verifier_id", _text("verifier_id", record.verifier_id))
    for name in ("evaluation_refs", "evidence_refs"):
        if hasattr(record, name):
            object.__setattr__(record, name, _refs(name, getattr(record, name), minimum=2))


def _verify_receipt(record: object, digest_field: str, *, transitions: bool = False) -> None:
    payload = asdict(record)
    supplied = payload.pop(digest_field)
    if transitions:
        payload["transitions"] = [item.receipt_digest for item in record.transitions]
    if _digest(payload) != supplied:
        raise ModelLifecycleError(f"{digest_field} does not bind exact receipt identity")


def _migration_transitions(
    record: object, source: str, target: str, states: tuple[str, str, str, str]
) -> None:
    transitions = record.transitions
    if isinstance(transitions, (str, bytes)) or not isinstance(transitions, Sequence):
        raise ModelLifecycleError("migration transitions must be a sequence")
    items = tuple(transitions)
    if len(items) != 2 or any(not isinstance(item, LifecycleTransitionReceipt) for item in items):
        raise ModelLifecycleError("migration requires two lifecycle transition receipts")
    first, second = items
    if (
        (first.model_digest, second.model_digest) != (source, target)
        or (first.from_state, first.to_state, second.from_state, second.to_state) != states
        or any(item.verifier_id != record.verifier_id for item in items)
    ):
        raise ModelLifecycleError("migration transitions do not bind exact model/state/verifier identity")
    object.__setattr__(record, "transitions", items)


@dataclass(frozen=True, slots=True)
class ModelBillOfMaterials:
    model_id: str
    model_digest: str
    artifact_digest: str
    artifact_kind: str
    training_run_id: str
    training_receipt_digest: str
    dataset_digests: tuple[str, ...]
    trainer_id: str
    code_revision: str
    license_refs: tuple[str, ...]
    rights_refs: tuple[str, ...]
    dependency_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _text("model_id", self.model_id))
        object.__setattr__(self, "model_digest", _sha("model_digest", self.model_digest))
        object.__setattr__(self, "artifact_digest", _sha("artifact_digest", self.artifact_digest))
        object.__setattr__(self, "artifact_kind", _text("artifact_kind", self.artifact_kind))
        object.__setattr__(self, "training_run_id", _text("training_run_id", self.training_run_id))
        object.__setattr__(
            self, "training_receipt_digest", _sha("training_receipt_digest", self.training_receipt_digest)
        )
        object.__setattr__(
            self, "dataset_digests", tuple(_sha("dataset_digest", x) for x in self.dataset_digests)
        )
        if not self.dataset_digests:
            raise ModelLifecycleError("MBOM requires at least one dataset digest")
        object.__setattr__(self, "trainer_id", _text("trainer_id", self.trainer_id))
        object.__setattr__(self, "code_revision", _text("code_revision", self.code_revision, maximum=256))
        object.__setattr__(self, "license_refs", _refs("license_ref", self.license_refs, minimum=1))
        object.__setattr__(self, "rights_refs", _refs("rights_ref", self.rights_refs, minimum=1))
        object.__setattr__(self, "dependency_refs", _refs("dependency_ref", self.dependency_refs))

    @classmethod
    def from_training(
        cls,
        artifact: ModelArtifact,
        receipt: TrainingReceipt,
        *,
        license_refs: Sequence[str],
        rights_refs: Sequence[str],
        dependency_refs: Sequence[str] = (),
    ) -> ModelBillOfMaterials:
        if not isinstance(artifact, ModelArtifact) or not isinstance(receipt, TrainingReceipt):
            raise TypeError("artifact/receipt types are invalid")
        if artifact.model_id != receipt.model_id or artifact.model_digest != receipt.model_digest:
            raise ModelLifecycleError("artifact/receipt model identity drift")
        if artifact.artifact_digest != receipt.artifact_digest or artifact.training_run_id != receipt.run_id:
            raise ModelLifecycleError("artifact/receipt training identity drift")
        return cls(
            model_id=artifact.model_id,
            model_digest=artifact.model_digest,
            artifact_digest=artifact.artifact_digest,
            artifact_kind=artifact.kind,
            training_run_id=artifact.training_run_id,
            training_receipt_digest=receipt.digest,
            dataset_digests=receipt.dataset_digests,
            trainer_id=receipt.trainer_id,
            code_revision=receipt.code_revision,
            license_refs=tuple(license_refs),
            rights_refs=tuple(rights_refs),
            dependency_refs=tuple(dependency_refs),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "model_id": self.model_id,
                "model_digest": self.model_digest,
                "artifact_digest": self.artifact_digest,
                "artifact_kind": self.artifact_kind,
                "training_run_id": self.training_run_id,
                "training_receipt_digest": self.training_receipt_digest,
                "dataset_digests": list(self.dataset_digests),
                "trainer_id": self.trainer_id,
                "code_revision": self.code_revision,
                "license_refs": list(self.license_refs),
                "rights_refs": list(self.rights_refs),
                "dependency_refs": list(self.dependency_refs),
            }
        )


class ModelLifecycleState(str, Enum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


_ALLOWED = {
    ModelLifecycleState.CANDIDATE: {ModelLifecycleState.VALIDATED},
    ModelLifecycleState.VALIDATED: {ModelLifecycleState.ACTIVE},
    ModelLifecycleState.ACTIVE: {ModelLifecycleState.DEPRECATED},
    ModelLifecycleState.DEPRECATED: {ModelLifecycleState.RETIRED},
    ModelLifecycleState.RETIRED: set(),
}


@dataclass(frozen=True, slots=True)
class LifecycleTransitionReceipt:
    model_digest: str
    mbom_digest: str
    from_state: str
    to_state: str
    verifier_id: str
    evidence_refs: tuple[str, ...]
    receipt_digest: str

    def __post_init__(self) -> None:
        for name in ("model_digest", "mbom_digest", "receipt_digest"):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        object.__setattr__(self, "verifier_id", _text("verifier_id", self.verifier_id))
        object.__setattr__(self, "evidence_refs", _refs("evidence_ref", self.evidence_refs, minimum=1))
        if (
            self.from_state not in {item.value for item in ModelLifecycleState}
            or self.to_state not in {item.value for item in ModelLifecycleState}
            or self.from_state == self.to_state
        ):
            raise ModelLifecycleError("invalid lifecycle receipt states")
        _verify_receipt(self, "receipt_digest")


@dataclass(frozen=True, slots=True)
class ModelMigrationDecision:
    source_model_digest: str
    target_model_digest: str
    parity_score: float
    required_score: float
    verifier_id: str
    evaluation_refs: tuple[str, ...]
    rollback_model_digest: str
    approved: bool
    decision_digest: str

    def __post_init__(self) -> None:
        _normalize_receipt(self)
        object.__setattr__(self, "parity_score", _score("parity_score", self.parity_score))
        object.__setattr__(self, "required_score", _score("required_score", self.required_score))
        if not isinstance(self.approved, bool) or self.approved != (self.parity_score >= self.required_score):
            raise ModelLifecycleError("migration approval must match parity threshold")
        if (
            self.source_model_digest == self.target_model_digest
            or self.rollback_model_digest != self.source_model_digest
        ):
            raise ModelLifecycleError("migration must retain a distinct source rollback model")


@dataclass(frozen=True, slots=True)
class MigrationParityCase:
    """One externally observed comparison on the exact same evaluation input.

    Equality of result digests is conservative exact-output parity. Semantic
    similarity or a caller's claimed score does not substitute for equality.
    The verifier remains responsible for producing the observed results.
    """

    case_id: str
    input_digest: str
    source_output_digest: str
    target_output_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _text("case_id", self.case_id))
        for name in ("input_digest", "source_output_digest", "target_output_digest"):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))

    @property
    def matches(self) -> bool:
        return self.source_output_digest == self.target_output_digest

    def as_dict(self) -> dict[str, str]:
        return {
            name: getattr(self, name)
            for name in ("case_id", "input_digest", "source_output_digest", "target_output_digest")
        }


@dataclass(frozen=True, slots=True)
class ModelMigrationEvaluationReceipt:
    source_model_digest: str
    target_model_digest: str
    source_mbom_digest: str
    target_mbom_digest: str
    source_lifecycle_digest: str
    target_lifecycle_digest: str
    cases: tuple[MigrationParityCase, ...]
    parity_score: float
    required_score: float
    verifier_id: str
    evaluation_refs: tuple[str, ...]
    evaluation_digest: str

    def __post_init__(self) -> None:
        _normalize_receipt(self)
        if isinstance(self.cases, (str, bytes)) or not isinstance(self.cases, Sequence):
            raise ModelLifecycleError("parity cases must be a sequence")
        observations = tuple(self.cases)
        if not 1 <= len(observations) <= 1024:
            raise ModelLifecycleError("parity cases exceed bounded evaluation budget")
        if any(not isinstance(case, MigrationParityCase) for case in observations):
            raise TypeError("cases must contain MigrationParityCase")
        if len({case.case_id for case in observations}) != len(observations):
            raise ModelLifecycleError("duplicate parity case identity")
        if len({case.input_digest for case in observations}) != len(observations):
            raise ModelLifecycleError("duplicate parity input identity")
        object.__setattr__(self, "cases", observations)
        object.__setattr__(self, "parity_score", _score("parity_score", self.parity_score))
        object.__setattr__(self, "required_score", _score("required_score", self.required_score))
        if self.source_model_digest == self.target_model_digest:
            raise ModelLifecycleError("migration source and target must differ")
        if self.parity_score != sum(case.matches for case in observations) / len(observations):
            raise ModelLifecycleError("parity score does not match observed comparison cases")
        _verify_receipt(self, "evaluation_digest")


@dataclass(frozen=True, slots=True)
class ModelMigrationReceipt:
    decision_digest: str
    evaluation_digest: str
    source_model_digest: str
    target_model_digest: str
    source_mbom_digest: str
    target_mbom_digest: str
    source_lifecycle_digest: str
    target_lifecycle_digest: str
    rollback_model_digest: str
    verifier_id: str
    evaluation_refs: tuple[str, ...]
    transitions: tuple[LifecycleTransitionReceipt, ...]
    receipt_digest: str

    def __post_init__(self) -> None:
        _normalize_receipt(self)
        if (
            self.source_model_digest == self.target_model_digest
            or self.rollback_model_digest != self.source_model_digest
        ):
            raise ModelLifecycleError("migration must retain a distinct source rollback model")
        _migration_transitions(
            self,
            self.source_model_digest,
            self.target_model_digest,
            ("active", "deprecated", "validated", "active"),
        )
        if tuple(item.mbom_digest for item in self.transitions) != (
            self.source_mbom_digest,
            self.target_mbom_digest,
        ):
            raise ModelLifecycleError("migration transition MBOM identity drift")
        _verify_receipt(self, "receipt_digest", transitions=True)


@dataclass(frozen=True, slots=True)
class ModelMigrationRollbackReceipt:
    migration_receipt_digest: str
    restored_model_digest: str
    withdrawn_model_digest: str
    source_lifecycle_digest: str
    target_lifecycle_digest: str
    verifier_id: str
    evidence_refs: tuple[str, ...]
    transitions: tuple[LifecycleTransitionReceipt, ...]
    receipt_digest: str

    def __post_init__(self) -> None:
        _normalize_receipt(self)
        if self.restored_model_digest == self.withdrawn_model_digest:
            raise ModelLifecycleError("rollback models must differ")
        _migration_transitions(
            self,
            self.restored_model_digest,
            self.withdrawn_model_digest,
            ("deprecated", "active", "active", "validated"),
        )
        _verify_receipt(self, "receipt_digest", transitions=True)


@dataclass(frozen=True, slots=True)
class _MigrationBinding:
    decision: ModelMigrationDecision
    source_mbom_digest: str
    target_mbom_digest: str
    source_lifecycle_digest: str
    target_lifecycle_digest: str
    evaluation: ModelMigrationEvaluationReceipt | None


class ModelLifecycleRegistry:
    """In-memory candidate state with bounded, immutable migration evidence.

    Numeric migration decisions are retained as advisory proposals. Execution
    requires evaluate_migration's registry-issued comparison evidence. Neither
    numeric proposals nor these local receipts authorize production promotion.
    """

    def __init__(
        self,
        *,
        max_models: int = 128,
        max_transitions: int = 4096,
        max_decisions: int = 1024,
        max_parity_cases: int = 1024,
    ) -> None:
        self._max_models = _positive("max_models", max_models)
        self._max_transitions = _positive("max_transitions", max_transitions)
        self._max_decisions = _positive("max_decisions", max_decisions)
        self._max_parity_cases = _positive("max_parity_cases", max_parity_cases)
        if self._max_parity_cases > 1024:
            raise ModelLifecycleError("max_parity_cases exceeds hard evaluation bound of 1024")
        self._lock = RLock()
        self._mboms: dict[str, ModelBillOfMaterials] = {}
        self._states: dict[str, ModelLifecycleState] = {}
        self._history: list[LifecycleTransitionReceipt] = []
        self._decisions: dict[str, _MigrationBinding] = {}
        self._migrations: dict[str, ModelMigrationReceipt] = {}
        self._rollbacks: dict[str, ModelMigrationRollbackReceipt] = {}

    @_locked
    def register_candidate(self, mbom: ModelBillOfMaterials) -> ModelBillOfMaterials:
        if not isinstance(mbom, ModelBillOfMaterials):
            raise TypeError("mbom must be ModelBillOfMaterials")
        prior = self._mboms.get(mbom.model_digest)
        if prior is not None and prior != mbom:
            raise ModelLifecycleError("model digest cannot be rebound to different MBOM")
        if prior is None and len(self._mboms) >= self._max_models:
            raise ModelLifecycleError("model inventory budget exhausted")
        self._mboms[mbom.model_digest] = mbom
        self._states.setdefault(mbom.model_digest, ModelLifecycleState.CANDIDATE)
        return mbom

    @_locked
    def state(self, model_digest: str) -> ModelLifecycleState:
        digest = _sha("model_digest", model_digest)
        try:
            return self._states[digest]
        except KeyError as exc:
            raise ModelLifecycleError("unknown model") from exc

    @_locked
    def mbom(self, model_digest: str) -> ModelBillOfMaterials:
        digest = _sha("model_digest", model_digest)
        try:
            return self._mboms[digest]
        except KeyError as exc:
            raise ModelLifecycleError("unknown model") from exc

    @_locked
    def transition(
        self,
        model_digest: str,
        to_state: ModelLifecycleState,
        *,
        verifier_id: str,
        evidence_refs: Sequence[str],
    ) -> LifecycleTransitionReceipt:
        digest = _sha("model_digest", model_digest)
        current = self.state(digest)
        if not isinstance(to_state, ModelLifecycleState):
            raise TypeError("to_state must be ModelLifecycleState")
        if to_state not in _ALLOWED[current]:
            raise ModelLifecycleError(f"illegal lifecycle transition {current.value}->{to_state.value}")
        mbom = self.mbom(digest)
        verifier = _text("verifier_id", verifier_id)
        refs = _refs(
            "evidence_ref",
            evidence_refs,
            minimum=2 if to_state in {ModelLifecycleState.VALIDATED, ModelLifecycleState.ACTIVE} else 1,
        )
        if (
            to_state in {ModelLifecycleState.VALIDATED, ModelLifecycleState.ACTIVE}
            and verifier == mbom.trainer_id
        ):
            raise ModelLifecycleError("trainer cannot independently validate or activate its own model")
        self._require_history_capacity(1)
        receipt = self._transition_receipt(digest, to_state, verifier, refs)
        self._states[digest] = to_state
        self._history.append(receipt)
        return receipt

    @_locked
    def lifecycle_digest(self, model_digest: str) -> str:
        """Bind state to the exact model history, including compensations."""
        digest = _sha("model_digest", model_digest)
        return _digest(
            {
                "model_digest": digest,
                "mbom_digest": self.mbom(digest).digest,
                "state": self.state(digest).value,
                "history": [
                    receipt.receipt_digest for receipt in self._history if receipt.model_digest == digest
                ],
            }
        )

    def _require_history_capacity(self, count: int) -> None:
        reserved = 2 * sum(
            migration.receipt_digest not in self._rollbacks for migration in self._migrations.values()
        )
        if len(self._history) + reserved + count > self._max_transitions:
            raise ModelLifecycleError("lifecycle history budget exhausted")

    def _transition_receipt(
        self, digest: str, to_state: ModelLifecycleState, verifier: str, refs: tuple[str, ...]
    ) -> LifecycleTransitionReceipt:
        mbom = self.mbom(digest)
        current = self.state(digest)
        payload = {
            "model_digest": digest,
            "mbom_digest": mbom.digest,
            "from_state": current.value,
            "to_state": to_state.value,
            "verifier_id": verifier,
            "evidence_refs": list(refs),
        }
        return LifecycleTransitionReceipt(
            digest, mbom.digest, current.value, to_state.value, verifier, refs, _digest(payload)
        )

    def _migration_models(
        self, source_model_digest: str, target_model_digest: str, verifier_id: str
    ) -> tuple[str, str, str]:
        source = _sha("source_model_digest", source_model_digest)
        target = _sha("target_model_digest", target_model_digest)
        if source == target:
            raise ModelLifecycleError("migration source and target must differ")
        if self.state(source) is not ModelLifecycleState.ACTIVE:
            raise ModelLifecycleError("migration source must be active")
        if self.state(target) is not ModelLifecycleState.VALIDATED:
            raise ModelLifecycleError("migration target must be validated")
        verifier = self._independent_verifier(source, target, verifier_id)
        return source, target, verifier

    def _independent_verifier(self, source: str, target: str, verifier_id: str) -> str:
        verifier = _text("verifier_id", verifier_id)
        if verifier in {self.mbom(source).trainer_id, self.mbom(target).trainer_id}:
            raise ModelLifecycleError("migration verifier must be independent of both trainers")
        return verifier

    @_locked
    def migration_decision(
        self,
        *,
        source_model_digest: str,
        target_model_digest: str,
        parity_score: float,
        required_score: float,
        verifier_id: str,
        evaluation_refs: Sequence[str],
    ) -> ModelMigrationDecision:
        """Issue a backward-compatible numeric proposal without apply authority."""
        source, target, verifier = self._migration_models(
            source_model_digest, target_model_digest, verifier_id
        )
        score = _score("parity_score", parity_score)
        required = _score("required_score", required_score)
        refs = _refs("evaluation_ref", evaluation_refs, minimum=2)
        return self._issue_decision(source, target, score, required, verifier, refs, None)

    @_locked
    def evaluate_migration(
        self,
        *,
        source_model_digest: str,
        target_model_digest: str,
        cases: Sequence[MigrationParityCase],
        required_score: float,
        verifier_id: str,
        evaluation_refs: Sequence[str],
    ) -> ModelMigrationDecision:
        """Derive parity from bounded comparisons and bind exact candidate state.

        This records independent reported observations, rather than executing
        model inference or establishing provenance for those observations.
        Production evaluation and routing remain outside this local registry.
        """
        source, target, verifier = self._migration_models(
            source_model_digest, target_model_digest, verifier_id
        )
        required = _score("required_score", required_score)
        refs = _refs("evaluation_ref", evaluation_refs, minimum=2)
        if isinstance(cases, (str, bytes)) or not isinstance(cases, Sequence):
            raise ModelLifecycleError("parity cases must be a sequence")
        if not 1 <= len(cases) <= self._max_parity_cases:
            raise ModelLifecycleError("parity cases exceed bounded evaluation budget")
        observations = tuple(cases)
        if any(not isinstance(case, MigrationParityCase) for case in observations):
            raise TypeError("cases must contain MigrationParityCase")
        if len({case.case_id for case in observations}) != len(observations):
            raise ModelLifecycleError("duplicate parity case identity")
        if len({case.input_digest for case in observations}) != len(observations):
            raise ModelLifecycleError("duplicate parity input identity")
        score = sum(case.matches for case in observations) / len(observations)
        identity = self._migration_identity(source, target)
        payload = {
            **identity,
            "cases": [case.as_dict() for case in observations],
            "parity_score": score,
            "required_score": required,
            "verifier_id": verifier,
            "evaluation_refs": list(refs),
        }
        evaluation = ModelMigrationEvaluationReceipt(
            source,
            target,
            identity["source_mbom_digest"],
            identity["target_mbom_digest"],
            identity["source_lifecycle_digest"],
            identity["target_lifecycle_digest"],
            observations,
            score,
            required,
            verifier,
            refs,
            _digest(payload),
        )
        return self._issue_decision(source, target, score, required, verifier, refs, evaluation)

    def _migration_identity(self, source: str, target: str) -> dict[str, str]:
        return {
            "source_model_digest": source,
            "target_model_digest": target,
            "source_mbom_digest": self.mbom(source).digest,
            "target_mbom_digest": self.mbom(target).digest,
            "source_lifecycle_digest": self.lifecycle_digest(source),
            "target_lifecycle_digest": self.lifecycle_digest(target),
        }

    def _issue_decision(
        self,
        source: str,
        target: str,
        score: float,
        required: float,
        verifier: str,
        refs: tuple[str, ...],
        evaluation: ModelMigrationEvaluationReceipt | None,
    ) -> ModelMigrationDecision:
        identity = self._migration_identity(source, target)
        payload = {
            **identity,
            "parity_score": score,
            "required_score": required,
            "verifier_id": verifier,
            "evaluation_refs": list(refs),
            "rollback_model_digest": source,
            "approved": score >= required,
            "evaluation_digest": evaluation.evaluation_digest if evaluation else None,
        }
        digest = _digest(payload)
        prior = self._decisions.get(digest)
        if prior is not None:
            return prior.decision
        if len(self._decisions) >= self._max_decisions:
            raise ModelLifecycleError("migration decision budget exhausted")
        decision = ModelMigrationDecision(
            source, target, score, required, verifier, refs, source, score >= required, digest
        )
        self._decisions[digest] = _MigrationBinding(
            decision,
            identity["source_mbom_digest"],
            identity["target_mbom_digest"],
            identity["source_lifecycle_digest"],
            identity["target_lifecycle_digest"],
            evaluation,
        )
        return decision

    def _issued_decision(self, decision: ModelMigrationDecision) -> _MigrationBinding:
        if not isinstance(decision, ModelMigrationDecision):
            raise TypeError("decision must be ModelMigrationDecision")
        binding = self._decisions.get(decision.decision_digest)
        if binding is None or binding.decision is not decision:
            raise ModelLifecycleError("decision was not issued by this registry")
        payload = {
            "source_model_digest": decision.source_model_digest,
            "target_model_digest": decision.target_model_digest,
            "source_mbom_digest": binding.source_mbom_digest,
            "target_mbom_digest": binding.target_mbom_digest,
            "source_lifecycle_digest": binding.source_lifecycle_digest,
            "target_lifecycle_digest": binding.target_lifecycle_digest,
            "parity_score": decision.parity_score,
            "required_score": decision.required_score,
            "verifier_id": decision.verifier_id,
            "evaluation_refs": list(decision.evaluation_refs),
            "rollback_model_digest": decision.rollback_model_digest,
            "approved": decision.approved,
            "evaluation_digest": binding.evaluation.evaluation_digest if binding.evaluation else None,
        }
        if _digest(payload) != decision.decision_digest:
            raise ModelLifecycleError("issued migration decision identity changed")
        return binding

    @_locked
    def migration_evaluation(self, decision: ModelMigrationDecision) -> ModelMigrationEvaluationReceipt:
        binding = self._issued_decision(decision)
        if binding.evaluation is None:
            raise ModelLifecycleError("numeric migration proposal has no executable parity evidence")
        return binding.evaluation

    @_locked
    def apply_migration(self, decision: ModelMigrationDecision) -> ModelMigrationReceipt:
        """Atomically apply one evidence-bound migration in this candidate registry."""
        binding = self._issued_decision(decision)
        evaluation = self.migration_evaluation(decision)
        prior = self._migrations.get(decision.decision_digest)
        if prior is not None:
            return prior
        if not decision.approved:
            raise ModelLifecycleError("migration parity evaluation did not pass")
        source, target, verifier = self._migration_models(
            decision.source_model_digest, decision.target_model_digest, decision.verifier_id
        )
        if (
            self.mbom(source).digest != binding.source_mbom_digest
            or self.mbom(target).digest != binding.target_mbom_digest
            or self.lifecycle_digest(source) != binding.source_lifecycle_digest
            or self.lifecycle_digest(target) != binding.target_lifecycle_digest
        ):
            raise ModelLifecycleError("migration evidence identity is stale")
        # Reserve rollback history before committing either model. Ordinary
        # transitions cannot consume the reserved compensation entries.
        self._require_history_capacity(4)
        refs = (
            f"migration-evaluation:{evaluation.evaluation_digest}",
            f"migration-decision:{decision.decision_digest}",
        )
        transitions = (
            self._transition_receipt(source, ModelLifecycleState.DEPRECATED, verifier, refs),
            self._transition_receipt(target, ModelLifecycleState.ACTIVE, verifier, refs),
        )
        payload = {
            "decision_digest": decision.decision_digest,
            "evaluation_digest": evaluation.evaluation_digest,
            "source_model_digest": source,
            "target_model_digest": target,
            "source_mbom_digest": binding.source_mbom_digest,
            "target_mbom_digest": binding.target_mbom_digest,
            "source_lifecycle_digest": binding.source_lifecycle_digest,
            "target_lifecycle_digest": binding.target_lifecycle_digest,
            "rollback_model_digest": source,
            "verifier_id": verifier,
            "evaluation_refs": list(decision.evaluation_refs),
            "transitions": [item.receipt_digest for item in transitions],
        }
        receipt = ModelMigrationReceipt(
            decision.decision_digest,
            evaluation.evaluation_digest,
            source,
            target,
            binding.source_mbom_digest,
            binding.target_mbom_digest,
            binding.source_lifecycle_digest,
            binding.target_lifecycle_digest,
            source,
            verifier,
            decision.evaluation_refs,
            transitions,
            _digest(payload),
        )
        self._states.update({source: ModelLifecycleState.DEPRECATED, target: ModelLifecycleState.ACTIVE})
        self._history.extend(transitions)
        self._migrations[decision.decision_digest] = receipt
        return receipt

    @_locked
    def rollback_migration(
        self, migration: ModelMigrationReceipt, *, verifier_id: str, evidence_refs: Sequence[str]
    ) -> ModelMigrationRollbackReceipt:
        """Compensate only the exact still-current migration, preserving history."""
        if not isinstance(migration, ModelMigrationReceipt):
            raise TypeError("migration must be ModelMigrationReceipt")
        if self._migrations.get(migration.decision_digest) is not migration:
            raise ModelLifecycleError("migration receipt was not issued by this registry")
        source, target = migration.source_model_digest, migration.target_model_digest
        verifier = self._independent_verifier(source, target, verifier_id)
        refs = _refs("evidence_ref", evidence_refs, minimum=2)
        prior = self._rollbacks.get(migration.receipt_digest)
        if prior is not None:
            if prior.verifier_id != verifier or prior.evidence_refs != refs:
                raise ModelLifecycleError("rollback replay changed its verifier or evidence")
            return prior
        # Require these exact migration transitions to remain the latest model
        # receipts. A later retire/deprecate/migration cannot be undone by an
        # older rollback, even if states happen to match again.
        for digest, transition in zip((source, target), migration.transitions):
            latest = next((item for item in reversed(self._history) if item.model_digest == digest), None)
            if latest is not transition:
                raise ModelLifecycleError("migration rollback identity is stale")
        if (
            self.state(source) is not ModelLifecycleState.DEPRECATED
            or self.state(target) is not ModelLifecycleState.ACTIVE
            or self.mbom(source).digest != migration.source_mbom_digest
            or self.mbom(target).digest != migration.target_mbom_digest
        ):
            raise ModelLifecycleError("migration rollback state is stale")
        source_identity = self.lifecycle_digest(source)
        target_identity = self.lifecycle_digest(target)
        transition_refs = (
            f"rollback-migration:{migration.receipt_digest}",
            f"rollback-evidence:{_digest(list(refs))}",
        )
        transitions = (
            self._transition_receipt(source, ModelLifecycleState.ACTIVE, verifier, transition_refs),
            self._transition_receipt(target, ModelLifecycleState.VALIDATED, verifier, transition_refs),
        )
        payload = {
            "migration_receipt_digest": migration.receipt_digest,
            "restored_model_digest": source,
            "withdrawn_model_digest": target,
            "source_lifecycle_digest": source_identity,
            "target_lifecycle_digest": target_identity,
            "verifier_id": verifier,
            "evidence_refs": list(refs),
            "transitions": [item.receipt_digest for item in transitions],
        }
        receipt = ModelMigrationRollbackReceipt(
            migration.receipt_digest,
            source,
            target,
            source_identity,
            target_identity,
            verifier,
            refs,
            transitions,
            _digest(payload),
        )
        self._states.update({source: ModelLifecycleState.ACTIVE, target: ModelLifecycleState.VALIDATED})
        self._history.extend(transitions)
        self._rollbacks[migration.receipt_digest] = receipt
        return receipt

    @property
    @_locked
    def history(self) -> tuple[LifecycleTransitionReceipt, ...]:
        return tuple(self._history)

    @property
    @_locked
    def migrations(self) -> tuple[ModelMigrationReceipt, ...]:
        return tuple(self._migrations.values())

    @property
    @_locked
    def rollbacks(self) -> tuple[ModelMigrationRollbackReceipt, ...]:
        return tuple(self._rollbacks.values())


__all__ = [
    "LifecycleTransitionReceipt",
    "MigrationParityCase",
    "ModelBillOfMaterials",
    "ModelLifecycleError",
    "ModelLifecycleRegistry",
    "ModelLifecycleState",
    "ModelMigrationDecision",
    "ModelMigrationEvaluationReceipt",
    "ModelMigrationReceipt",
    "ModelMigrationRollbackReceipt",
]
