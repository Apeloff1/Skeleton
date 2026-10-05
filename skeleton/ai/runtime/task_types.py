"""Authority-neutral semantic task contracts for VOL-311."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from typing import Iterable

from skeleton.contracts.canonical import canonical_json_bytes


class TaskTypeError(ValueError):
    pass


class TaskKind(str, Enum):
    RESEARCH = "research"
    REASONING = "reasoning"
    CODING = "coding"
    REVIEW = "review"
    VERIFICATION = "verification"
    PLANNING = "planning"
    EXECUTION = "execution"
    COMMUNICATION = "communication"


class SideEffectClass(str, Enum):
    NONE = "none"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"


def _token(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or any(ch.isspace() for ch in value):
        raise TaskTypeError(f"{field} entries must be canonical non-whitespace tokens")
    return value


def _tokens(values: Iterable[str], *, field: str) -> tuple[str, ...]:
    checked = tuple(_token(value, field=field) for value in values)
    if len(set(checked)) != len(checked):
        raise TaskTypeError(f"{field} must not contain duplicates")
    return tuple(sorted(checked))


@dataclass(frozen=True, slots=True)
class SemanticTaskType:
    kind: TaskKind
    capabilities: tuple[str, ...] = ()
    side_effect: SideEffectClass = SideEffectClass.NONE
    requires_independent_verification: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TaskKind) or not isinstance(self.side_effect, SideEffectClass):
            raise TaskTypeError("kind and side_effect must use declared enums")
        if not isinstance(self.requires_independent_verification, bool):
            raise TaskTypeError("requires_independent_verification must be bool")
        if _tokens(self.capabilities, field="capabilities") != self.capabilities:
            raise TaskTypeError("capabilities must be unique and sorted")
        if self.side_effect is SideEffectClass.IRREVERSIBLE and not self.requires_independent_verification:
            raise TaskTypeError("irreversible tasks require independent verification")

    @property
    def identity(self) -> str:
        payload = {"kind": self.kind.value, "capabilities": list(self.capabilities), "side_effect": self.side_effect.value, "requires_independent_verification": self.requires_independent_verification}
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class TaskClassification:
    task_type: SemanticTaskType
    evidence_ids: tuple[str, ...]
    classifier: str
    confidence_ppm: int

    def __post_init__(self) -> None:
        if not isinstance(self.task_type, SemanticTaskType):
            raise TaskTypeError("task_type must be SemanticTaskType")
        if not self.evidence_ids or _tokens(self.evidence_ids, field="evidence_ids") != self.evidence_ids:
            raise TaskTypeError("evidence_ids must be non-empty, unique, and sorted")
        _token(self.classifier, field="classifier")
        if isinstance(self.confidence_ppm, bool) or not isinstance(self.confidence_ppm, int) or not 0 <= self.confidence_ppm <= 1_000_000:
            raise TaskTypeError("confidence_ppm must be an integer from 0 through 1000000")

    @property
    def identity(self) -> str:
        payload = {"task_type_id": self.task_type.identity, "evidence_ids": list(self.evidence_ids), "classifier": self.classifier, "confidence_ppm": self.confidence_ppm, "authority": "classification-evidence-only"}
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

    def receipt(self) -> dict[str, object]:
        return {"kind": "semantic_task_classification", "task_type_id": self.task_type.identity, "classification_id": self.identity, "evidence_ids": list(self.evidence_ids), "classifier": self.classifier, "confidence_ppm": self.confidence_ppm, "authority": "classification-evidence-only", "grants_execution_authority": False}


def semantic_task_type(kind: TaskKind, *, capabilities: Iterable[str] = (), side_effect: SideEffectClass = SideEffectClass.NONE, requires_independent_verification: bool = False) -> SemanticTaskType:
    return SemanticTaskType(kind=kind, capabilities=_tokens(capabilities, field="capabilities"), side_effect=side_effect, requires_independent_verification=requires_independent_verification)


__all__ = ["SemanticTaskType", "SideEffectClass", "TaskClassification", "TaskKind", "TaskTypeError", "semantic_task_type"]
