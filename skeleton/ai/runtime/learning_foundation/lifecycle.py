"""Bounded model lifecycle and migration candidates for P3-T2.

The default registry is run-scoped reference control; optional SQLite storage
preserves candidate evidence across restart. Its ACTIVE state is local candidate
state, not a production routing change or promotion. The canonical
learning/evaluation planes retain production authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, fields, replace
from enum import Enum
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING

from skeleton.learning.model_program import ModelArtifact, TrainingReceipt

if TYPE_CHECKING:
    from .lifecycle_repository import (
        LifecycleBackupReceipt,
        SQLiteModelLifecycleRepository,
    )


class ModelLifecycleError(RuntimeError):
    pass


def _locked(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self._lock:
            if self._repository is None or self._transaction_depth:
                return method(self, *args, **kwargs)
            before = None
            before_version = self._snapshot_version
            before_digest = self._snapshot_digest
            try:
                with self._repository.transaction() as transaction:
                    if transaction.snapshot is None:
                        raise ModelLifecycleError("durable lifecycle registry snapshot is missing")
                    if transaction.version < self._snapshot_version or (
                        transaction.version == self._snapshot_version
                        and transaction.snapshot_digest != self._snapshot_digest
                    ):
                        raise ModelLifecycleError("durable lifecycle snapshot sequence or digest regressed")
                    self._load_snapshot(transaction.snapshot, require_extension=True)
                    before = transaction.snapshot
                    before_version = transaction.version
                    before_digest = transaction.snapshot_digest
                    self._snapshot_version = transaction.version
                    self._snapshot_digest = transaction.snapshot_digest
                    self._transaction_depth = 1
                    result = method(self, *args, **kwargs)
                    transaction.save(self._snapshot())
                    self._snapshot_version = transaction.version
                    self._snapshot_digest = transaction.snapshot_digest
                    return result
            except BaseException:
                if before is not None:
                    self._load_snapshot(before)
                    self._snapshot_version = before_version
                    self._snapshot_digest = before_digest
                raise
            finally:
                self._transaction_depth = 0

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


def _record(record_type, value: object):
    if not isinstance(value, dict) or set(value) != {item.name for item in fields(record_type)}:
        raise ModelLifecycleError(f"persisted {record_type.__name__} has unknown or missing fields")
    try:
        arguments = dict(value)
        if record_type is ModelMigrationEvaluationReceipt:
            if not isinstance(arguments["cases"], list) or not 1 <= len(arguments["cases"]) <= 1024:
                raise ModelLifecycleError("persisted parity cases must be a list")
            arguments["cases"] = tuple(_record(MigrationParityCase, item) for item in arguments["cases"])
        if record_type in {ModelMigrationReceipt, ModelMigrationRollbackReceipt}:
            if not isinstance(arguments["transitions"], list) or len(arguments["transitions"]) != 2:
                raise ModelLifecycleError("persisted migration transitions must be a list")
            arguments["transitions"] = tuple(
                _record(LifecycleTransitionReceipt, item) for item in arguments["transitions"]
            )
        record = record_type(**arguments)
        if _json(asdict(record)) != _json(value):
            raise ModelLifecycleError(f"persisted {record_type.__name__} is not normalized")
        return record
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise ModelLifecycleError(f"invalid persisted {record_type.__name__}") from exc


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
        if (
            isinstance(self.dataset_digests, (str, bytes))
            or not isinstance(self.dataset_digests, Sequence)
            or not 1 <= len(self.dataset_digests) <= 1024
        ):
            raise ModelLifecycleError("MBOM requires between 1 and 1024 dataset digests")
        object.__setattr__(
            self, "dataset_digests", tuple(_sha("dataset_digest", x) for x in self.dataset_digests)
        )
        if len(set(self.dataset_digests)) != len(self.dataset_digests):
            raise ModelLifecycleError("MBOM dataset digests must be unique")
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
    issued_sequence: int = 0


class ModelLifecycleRegistry:
    """Candidate state with bounded evidence and optional SQLite durability.

    Numeric migration decisions are retained as advisory proposals. Execution
    requires evaluate_migration's registry-issued comparison evidence. Neither
    numeric proposals nor these local receipts authorize production promotion.
    """

    def __init__(
        self,
        *,
        max_models: int | None = None,
        max_transitions: int | None = None,
        max_decisions: int | None = None,
        max_parity_cases: int | None = None,
        path: str | Path | None = None,
        repository: SQLiteModelLifecycleRepository | None = None,
    ) -> None:
        requested = {
            "max_models": max_models,
            "max_transitions": max_transitions,
            "max_decisions": max_decisions,
            "max_parity_cases": max_parity_cases,
        }
        defaults = {
            "max_models": 128,
            "max_transitions": 4096,
            "max_decisions": 1024,
            "max_parity_cases": 1024,
        }
        hard_bounds = {
            "max_models": 4096,
            "max_transitions": 65536,
            "max_decisions": 8192,
            "max_parity_cases": 1024,
        }
        for name, value in requested.items():
            actual = _positive(name, defaults[name] if value is None else value)
            if actual > hard_bounds[name]:
                raise ModelLifecycleError(f"{name} exceeds hard lifecycle bound of {hard_bounds[name]}")
            setattr(self, "_" + name, actual)
        self._lock = RLock()
        self._repository = None
        self._transaction_depth = 0
        self._snapshot_version = 0
        self._snapshot_digest = None
        self._mboms: dict[str, ModelBillOfMaterials] = {}
        self._states: dict[str, ModelLifecycleState] = {}
        self._history: list[LifecycleTransitionReceipt] = []
        self._decisions: dict[str, _MigrationBinding] = {}
        self._migrations: dict[str, ModelMigrationReceipt] = {}
        self._rollbacks: dict[str, ModelMigrationRollbackReceipt] = {}
        if path is not None and repository is not None:
            raise ModelLifecycleError("supply path or repository, not both")
        if path is not None or repository is not None:
            from .lifecycle_repository import SQLiteModelLifecycleRepository

            if repository is not None and not isinstance(repository, SQLiteModelLifecycleRepository):
                raise TypeError("repository must be SQLiteModelLifecycleRepository")
            self._repository = (
                repository
                if repository is not None
                else SQLiteModelLifecycleRepository(path, initial_snapshot=self._snapshot())
            )
            with self._repository.transaction() as transaction:
                if transaction.snapshot is None:
                    transaction.save(self._snapshot())
                else:
                    self._load_snapshot(transaction.snapshot)
                    for name, value in requested.items():
                        if value is not None and value != getattr(self, "_" + name):
                            raise ModelLifecycleError(
                                "explicit lifecycle budget conflicts with persisted budget"
                            )
                self._snapshot_version = transaction.version
                self._snapshot_digest = transaction.snapshot_digest

    def _snapshot(self) -> dict[str, object]:
        sequence_by_identity = {id(receipt): index + 1 for index, receipt in enumerate(self._history)}

        def action(receipt):
            return {
                "start_sequence": sequence_by_identity[id(receipt.transitions[0])],
                "receipt": asdict(receipt),
            }

        return {
            "schema_version": 1,
            "budgets": {
                name: getattr(self, "_" + name)
                for name in ("max_models", "max_transitions", "max_decisions", "max_parity_cases")
            },
            "mboms": [asdict(self._mboms[digest]) for digest in sorted(self._mboms)],
            "states": {digest: state.value for digest, state in self._states.items()},
            "history": [
                {"sequence": index + 1, "receipt": asdict(receipt)}
                for index, receipt in enumerate(self._history)
            ],
            "decisions": [asdict(binding) for binding in self._decisions.values()],
            "migrations": [action(receipt) for receipt in self._migrations.values()],
            "rollbacks": [action(receipt) for receipt in self._rollbacks.values()],
        }

    @classmethod
    def _validate_snapshot(cls, snapshot: object) -> ModelLifecycleRegistry:
        """Reconstruct issued authority solely by replaying validated operations."""
        expected_fields = {
            "schema_version",
            "budgets",
            "mboms",
            "states",
            "history",
            "decisions",
            "migrations",
            "rollbacks",
        }
        if not isinstance(snapshot, dict) or set(snapshot) != expected_fields:
            raise ModelLifecycleError("lifecycle snapshot has unknown or missing fields")
        if type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1:
            raise ModelLifecycleError("unsupported lifecycle snapshot version")
        budgets = snapshot["budgets"]
        budget_names = {"max_models", "max_transitions", "max_decisions", "max_parity_cases"}
        if not isinstance(budgets, dict) or set(budgets) != budget_names:
            raise ModelLifecycleError("invalid persisted lifecycle budgets")
        registry = cls(**budgets)
        limits = {
            "mboms": registry._max_models,
            "history": registry._max_transitions,
            "decisions": registry._max_decisions,
            "migrations": registry._max_decisions,
            "rollbacks": registry._max_decisions,
        }
        for name, maximum in limits.items():
            if not isinstance(snapshot[name], list) or len(snapshot[name]) > maximum:
                raise ModelLifecycleError(f"persisted {name} exceed bounded record budget")
        for value in snapshot["mboms"]:
            mbom = _record(ModelBillOfMaterials, value)
            if mbom.model_digest in registry._mboms:
                raise ModelLifecycleError("duplicate persisted model identity")
            registry.register_candidate(mbom)
        history = []
        for index, row in enumerate(snapshot["history"]):
            if (
                not isinstance(row, dict)
                or set(row) != {"sequence", "receipt"}
                or type(row["sequence"]) is not int
                or row["sequence"] != index + 1
            ):
                raise ModelLifecycleError("persisted lifecycle history sequence is not contiguous")
            history.append(_record(LifecycleTransitionReceipt, row["receipt"]))
        decisions_at: dict[int, list[_MigrationBinding]] = {}
        decision_ids = set()
        for value in snapshot["decisions"]:
            if not isinstance(value, dict) or set(value) != {item.name for item in fields(_MigrationBinding)}:
                raise ModelLifecycleError("persisted migration binding has unknown or missing fields")
            arguments = dict(value)
            arguments["decision"] = _record(ModelMigrationDecision, arguments["decision"])
            if arguments["evaluation"] is not None:
                arguments["evaluation"] = _record(ModelMigrationEvaluationReceipt, arguments["evaluation"])
            binding = _MigrationBinding(**arguments)
            sequence = binding.issued_sequence
            if type(sequence) is not int or not 0 <= sequence <= len(history):
                raise ModelLifecycleError("persisted migration issuance sequence is invalid")
            if binding.decision.decision_digest in decision_ids:
                raise ModelLifecycleError("duplicate persisted migration decision")
            decision_ids.add(binding.decision.decision_digest)
            decisions_at.setdefault(sequence, []).append(binding)
        actions: dict[int, tuple[str, ModelMigrationReceipt | ModelMigrationRollbackReceipt]] = {}
        action_ids = set()
        for name, record_type in (
            ("migrations", ModelMigrationReceipt),
            ("rollbacks", ModelMigrationRollbackReceipt),
        ):
            for value in snapshot[name]:
                if not isinstance(value, dict) or set(value) != {"start_sequence", "receipt"}:
                    raise ModelLifecycleError("persisted migration action has unknown or missing fields")
                sequence = value["start_sequence"]
                if type(sequence) is not int or not 1 <= sequence < len(history):
                    raise ModelLifecycleError("persisted migration action sequence is invalid")
                receipt = _record(record_type, value["receipt"])
                if sequence in actions or receipt.receipt_digest in action_ids:
                    raise ModelLifecycleError("duplicate persisted migration action")
                if tuple(history[sequence - 1 : sequence + 1]) != receipt.transitions:
                    raise ModelLifecycleError("persisted migration is not an atomic history pair")
                actions[sequence] = (name, receipt)
                action_ids.add(receipt.receipt_digest)
        cursor = 0
        while cursor <= len(history):
            for binding in decisions_at.pop(cursor, ()):
                decision = binding.decision
                arguments = {
                    "source_model_digest": decision.source_model_digest,
                    "target_model_digest": decision.target_model_digest,
                    "required_score": decision.required_score,
                    "verifier_id": decision.verifier_id,
                    "evaluation_refs": decision.evaluation_refs,
                }
                if binding.evaluation is None:
                    issued = registry.migration_decision(**arguments, parity_score=decision.parity_score)
                else:
                    issued = registry.evaluate_migration(**arguments, cases=binding.evaluation.cases)
                if issued != decision or registry._decisions[issued.decision_digest] != binding:
                    raise ModelLifecycleError("persisted decision does not bind exact issuance evidence")
            if cursor == len(history):
                break
            action = actions.pop(cursor + 1, None)
            if action is not None:
                name, expected = action
                if name == "migrations":
                    binding = registry._decisions.get(expected.decision_digest)
                    if binding is None:
                        raise ModelLifecycleError("persisted migration has no issued decision")
                    actual = registry.apply_migration(binding.decision)
                else:
                    migration = next(
                        (
                            item
                            for item in registry._migrations.values()
                            if item.receipt_digest == expected.migration_receipt_digest
                        ),
                        None,
                    )
                    if migration is None:
                        raise ModelLifecycleError("persisted rollback has no applied migration")
                    actual = registry.rollback_migration(
                        migration, verifier_id=expected.verifier_id, evidence_refs=expected.evidence_refs
                    )
                if actual != expected:
                    raise ModelLifecycleError("persisted migration action identity drift")
                cursor += 2
            else:
                expected = history[cursor]
                actual = registry.transition(
                    expected.model_digest,
                    ModelLifecycleState(expected.to_state),
                    verifier_id=expected.verifier_id,
                    evidence_refs=expected.evidence_refs,
                )
                if actual != expected:
                    raise ModelLifecycleError("persisted lifecycle transition identity drift")
                cursor += 1
        if decisions_at or actions:
            raise ModelLifecycleError("persisted lifecycle has orphaned evidence or actions")
        if not isinstance(snapshot["states"], dict) or snapshot["states"] != {
            digest: state.value for digest, state in registry._states.items()
        }:
            raise ModelLifecycleError("persisted lifecycle states do not match replayed history")
        registry._require_history_capacity(0)
        # This catches reordered, duplicate or omitted records as well as field
        # normalization that would otherwise silently repair corruption.
        if _json(registry._snapshot()) != _json(snapshot):
            raise ModelLifecycleError("persisted lifecycle snapshot does not match complete replay")
        return registry

    def _load_snapshot(self, snapshot: object, *, require_extension: bool = False) -> None:
        try:
            restored = self._validate_snapshot(snapshot)
        except (TypeError, ValueError, KeyError, AttributeError, RecursionError) as exc:
            raise ModelLifecycleError("durable lifecycle evidence is corrupt") from exc
        if require_extension:
            if restored._history[: len(self._history)] != self._history:
                raise ModelLifecycleError("durable lifecycle rewrote immutable history")
            for name in ("_mboms", "_decisions", "_migrations", "_rollbacks"):
                current = getattr(restored, name)
                if any(current.get(key) != value for key, value in getattr(self, name).items()):
                    raise ModelLifecycleError("durable lifecycle removed or rebound immutable evidence")
            if any(
                getattr(restored, name) != getattr(self, name)
                for name in ("_max_models", "_max_transitions", "_max_decisions", "_max_parity_cases")
            ):
                raise ModelLifecycleError("durable lifecycle rebound its immutable budgets")
        # Keep genuine handles already issued to this registry when the durable
        # record is unchanged. Equivalent caller-created objects remain denied.
        restored._history = [
            (
                self._history[index]
                if index < len(self._history) and self._history[index] == receipt
                else receipt
            )
            for index, receipt in enumerate(restored._history)
        ]
        for name in ("_migrations", "_rollbacks"):
            previous = getattr(self, name)
            current = getattr(restored, name)
            for key, receipt in list(current.items()):
                position = next(
                    index for index, item in enumerate(restored._history) if item == receipt.transitions[0]
                )
                reconstructed = replace(
                    receipt, transitions=tuple(restored._history[position : position + 2])
                )
                prior = previous.get(key)
                current[key] = prior if prior == reconstructed else reconstructed
        for key, binding in list(restored._decisions.items()):
            prior = self._decisions.get(key)
            if prior == binding:
                restored._decisions[key] = prior
        restored._mboms = {
            key: self._mboms.get(key) if self._mboms.get(key) == mbom else mbom
            for key, mbom in restored._mboms.items()
        }
        for name in (
            "_mboms",
            "_states",
            "_history",
            "_decisions",
            "_migrations",
            "_rollbacks",
            "_max_models",
            "_max_transitions",
            "_max_decisions",
            "_max_parity_cases",
        ):
            setattr(self, name, getattr(restored, name))

    @_locked
    def decision(self, decision_digest: str) -> ModelMigrationDecision:
        """Retrieve an issued handle, including after durable reconstruction."""
        digest = _sha("decision_digest", decision_digest)
        try:
            return self._decisions[digest].decision
        except KeyError as exc:
            raise ModelLifecycleError("unknown migration decision") from exc

    @property
    @_locked
    def durable(self) -> bool:
        return self._repository is not None

    @property
    @_locked
    def snapshot_version(self) -> int:
        return self._snapshot_version

    @_locked
    def backup(self, destination: str | Path) -> LifecycleBackupReceipt:
        if self._repository is None:
            raise ModelLifecycleError("memory lifecycle registry cannot create a durable backup")
        return self._repository.backup(destination, validate=self._validate_snapshot)

    @classmethod
    def restore_backup(
        cls, *, backup_path: str | Path, path: str | Path
    ) -> tuple[ModelLifecycleRegistry, LifecycleBackupReceipt]:
        from .lifecycle_repository import SQLiteModelLifecycleRepository

        repository, receipt = SQLiteModelLifecycleRepository.restore(
            backup_path, path, validate=cls._validate_snapshot
        )
        return cls(repository=repository), receipt

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
        reserved_prefixes = (
            "migration-evaluation:",
            "migration-decision:",
            "rollback-migration:",
            "rollback-evidence:",
        )
        if any(ref.startswith(reserved_prefixes) for ref in refs):
            raise ModelLifecycleError("ordinary lifecycle transition cannot claim migration evidence")
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
            len(self._history),
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
