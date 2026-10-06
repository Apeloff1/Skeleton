"""Deterministic contracts for the dual-rival AI game-builder forge."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from hashlib import sha256
import json
import math
from typing import Iterable, Mapping, Sequence


class Rival(str, Enum):
    A = "rival_a"
    B = "rival_b"

    @property
    def other(self) -> "Rival":
        return Rival.B if self is Rival.A else Rival.A


class Stage(str, Enum):
    CONSTRUCT = "construct"
    ATTACK_AND_IMPROVE = "attack_and_improve"
    RECONCILE_AND_PROMOTE = "reconcile_and_promote"


STAGE_ORDER: tuple[Stage, Stage, Stage] = (
    Stage.CONSTRUCT,
    Stage.ATTACK_AND_IMPROVE,
    Stage.RECONCILE_AND_PROMOTE,
)


class EffortMode(IntEnum):
    FORGE_100 = 100
    FORGE_1000 = 1000
    FORGE_10000 = 10000

    @property
    def rounds(self) -> int:
        return int(self.value)

    @property
    def stage_executions(self) -> int:
        return self.rounds * len(STAGE_ORDER)

    @classmethod
    def parse(cls, value: object) -> "EffortMode":
        if isinstance(value, cls):
            return value
        aliases = {
            "forge_100": cls.FORGE_100,
            "forge_1000": cls.FORGE_1000,
            "forge_10000": cls.FORGE_10000,
            100: cls.FORGE_100,
            1000: cls.FORGE_1000,
            10000: cls.FORGE_10000,
        }
        try:
            return aliases[value]  # type: ignore[index]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"unsupported effort mode: {value!r}") from exc


QUALITY_AXES = (
    "player_value",
    "fun_engagement",
    "originality",
    "mechanical_depth",
    "clarity_readability",
    "narrative_coherence",
    "longform_consistency",
    "emotional_impact",
    "aesthetic_coherence",
    "technical_correctness",
    "performance",
    "accessibility",
    "security_privacy",
    "state_integrity",
    "reproducibility",
    "replayability",
    "maintainability",
    "testability",
    "platform_fit",
    "source_evidence_quality",
    "rights_provenance_safety",
)

PROTECTED_AXES = frozenset(
    {
        "longform_consistency",
        "technical_correctness",
        "accessibility",
        "security_privacy",
        "state_integrity",
        "reproducibility",
        "rights_provenance_safety",
    }
)


def canonical_json(value: object) -> str:
    """Serialize JSON deterministically and reject non-finite numbers."""

    def _validate(node: object, path: str = "$") -> None:
        if isinstance(node, float) and not math.isfinite(node):
            raise ValueError(f"non-finite number at {path}")
        if isinstance(node, Mapping):
            for key, item in node.items():
                if not isinstance(key, str):
                    raise ValueError(f"non-string JSON object key at {path}")
                _validate(item, f"{path}.{key}")
        elif isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                _validate(item, f"{path}[{index}]")

    _validate(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_digest(value: object) -> str:
    return sha256(canonical_json(value).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    artifact_digest: str
    canon_digest: str
    provenance_digest: str
    family_id: str
    level_id: str

    def __post_init__(self) -> None:
        for name in ("artifact_digest", "canon_digest", "provenance_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) < 16:
                raise ValueError(f"{name} must be a stable digest")
        if not self.family_id.startswith("GB"):
            raise ValueError("family_id must use GBxx identity")
        if not self.level_id.startswith("GBL-"):
            raise ValueError("level_id must use GBL-xxx identity")

    def to_payload(self) -> dict[str, str]:
        return {
            "artifact_digest": self.artifact_digest,
            "canon_digest": self.canon_digest,
            "family_id": self.family_id,
            "level_id": self.level_id,
            "provenance_digest": self.provenance_digest,
        }


def normalize_quality(values: Mapping[str, float]) -> tuple[tuple[str, float], ...]:
    unknown = set(values) - set(QUALITY_AXES)
    if unknown:
        raise ValueError(f"unknown quality axes: {sorted(unknown)}")
    missing = set(QUALITY_AXES) - set(values)
    if missing:
        raise ValueError(f"missing quality axes: {sorted(missing)}")
    normalized: list[tuple[str, float]] = []
    for axis in QUALITY_AXES:
        value = values[axis]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{axis} score must be numeric")
        score = float(value)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError(f"{axis} score must be finite and within [0,1]")
        normalized.append((axis, score))
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class Candidate:
    producer_id: str
    artifact: ArtifactIdentity
    quality: tuple[tuple[str, float], ...]
    evidence_digests: tuple[str, ...]
    assumption_digest: str
    parent_candidate_digests: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        producer_id: str,
        artifact: ArtifactIdentity,
        quality: Mapping[str, float],
        evidence_digests: Iterable[str],
        assumption_digest: str,
        parent_candidate_digests: Iterable[str] = (),
    ) -> "Candidate":
        evidence = tuple(evidence_digests)
        parents = tuple(parent_candidate_digests)
        if not producer_id.strip():
            raise ValueError("producer_id must be non-empty")
        if not evidence or any(not item.strip() or len(item) < 16 for item in evidence):
            raise ValueError("candidate requires stable evidence digests")
        if len(evidence) != len(set(evidence)):
            raise ValueError("candidate evidence digests must be unique")
        if any(not item.strip() or len(item) < 16 for item in parents):
            raise ValueError("candidate parent digests must be stable")
        if len(parents) != len(set(parents)):
            raise ValueError("candidate parent digests must be unique")
        if len(assumption_digest) < 16:
            raise ValueError("assumption_digest must be a stable digest")
        return cls(
            producer_id=producer_id,
            artifact=artifact,
            quality=normalize_quality(quality),
            evidence_digests=evidence,
            assumption_digest=assumption_digest,
            parent_candidate_digests=parents,
        )

    @property
    def quality_map(self) -> dict[str, float]:
        return dict(self.quality)

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "artifact": self.artifact.to_payload(),
            "assumption_digest": self.assumption_digest,
            "evidence_digests": list(self.evidence_digests),
            "parent_candidate_digests": list(self.parent_candidate_digests),
            "producer_id": self.producer_id,
            "quality": {key: value for key, value in self.quality},
        }


@dataclass(frozen=True, slots=True)
class Challenge:
    challenger_id: str
    target_candidate_digest: str
    attack_digest: str
    improved_candidate: Candidate
    counterexample_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.challenger_id.strip():
            raise ValueError("challenger_id must be non-empty")
        for label, value in (
            ("target_candidate_digest", self.target_candidate_digest),
            ("attack_digest", self.attack_digest),
        ):
            if len(value) < 16:
                raise ValueError(f"{label} must be a stable digest")
        if not self.counterexample_digests:
            raise ValueError("challenge requires at least one counterexample")
        if self.improved_candidate.producer_id != self.challenger_id:
            raise ValueError("improved candidate producer must equal challenger")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "attack_digest": self.attack_digest,
                "challenger_id": self.challenger_id,
                "counterexample_digests": list(self.counterexample_digests),
                "improved_candidate_digest": self.improved_candidate.digest,
                "target_candidate_digest": self.target_candidate_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class GateResult:
    gate_id: str
    passed: bool
    evidence_digest: str
    non_compensable: bool = True

    def __post_init__(self) -> None:
        if not self.gate_id.strip():
            raise ValueError("gate_id must be non-empty")
        if len(self.evidence_digest) < 16:
            raise ValueError("gate evidence must use a stable digest")


@dataclass(frozen=True, slots=True)
class PromotionReceipt:
    round_index: int
    effort_mode: EffortMode
    incumbent_digest: str
    submitted_digest: str | None
    promoted_digest: str
    evaluator_id: str
    gate_results: tuple[GateResult, ...]
    decision: str
    decision_digest: str

    def to_payload(self) -> dict[str, object]:
        return {
            "decision": self.decision,
            "decision_digest": self.decision_digest,
            "effort_mode": int(self.effort_mode),
            "evaluator_id": self.evaluator_id,
            "gate_results": [
                {
                    "evidence_digest": gate.evidence_digest,
                    "gate_id": gate.gate_id,
                    "non_compensable": gate.non_compensable,
                    "passed": gate.passed,
                }
                for gate in self.gate_results
            ],
            "incumbent_digest": self.incumbent_digest,
            "promoted_digest": self.promoted_digest,
            "round_index": self.round_index,
            "submitted_digest": self.submitted_digest,
        }


def hard_gates_pass(gates: Sequence[GateResult]) -> bool:
    if not gates:
        return False
    return all(gate.passed for gate in gates if gate.non_compensable)


def pareto_safe(
    incumbent: Candidate,
    candidate: Candidate,
    *,
    protected_axes: Iterable[str] = PROTECTED_AXES,
    epsilon: float = 1e-9,
) -> bool:
    current = incumbent.quality_map
    proposed = candidate.quality_map
    protected = tuple(protected_axes)
    if any(axis not in current or axis not in proposed for axis in protected):
        raise ValueError("protected axis missing from quality vector")
    if any(proposed[axis] + epsilon < current[axis] for axis in protected):
        return False
    return any(proposed[axis] > current[axis] + epsilon for axis in QUALITY_AXES)


def promotion_receipt(
    *,
    round_index: int,
    effort_mode: EffortMode,
    incumbent: Candidate,
    submitted: Candidate | None,
    evaluator_id: str,
    gate_results: Sequence[GateResult],
    protected_axes: Iterable[str] = PROTECTED_AXES,
) -> PromotionReceipt:
    if round_index < 1 or round_index > effort_mode.rounds:
        raise ValueError("round index outside effort-mode bounds")
    if evaluator_id in {Rival.A.value, Rival.B.value} or not evaluator_id.strip():
        raise ValueError("promotion evaluator must be independent from both rivals")

    gates = tuple(gate_results)
    promote = (
        submitted is not None
        and hard_gates_pass(gates)
        and pareto_safe(incumbent, submitted, protected_axes=protected_axes)
    )
    promoted = submitted if promote else incumbent
    decision = "promote" if promote else "retain_incumbent"
    payload = {
        "decision": decision,
        "effort_mode": int(effort_mode),
        "evaluator_id": evaluator_id,
        "gates": [
            (gate.gate_id, gate.passed, gate.non_compensable, gate.evidence_digest)
            for gate in gates
        ],
        "incumbent": incumbent.digest,
        "promoted": promoted.digest,
        "round_index": round_index,
        "submitted": submitted.digest if submitted else None,
    }
    return PromotionReceipt(
        round_index=round_index,
        effort_mode=effort_mode,
        incumbent_digest=incumbent.digest,
        submitted_digest=submitted.digest if submitted else None,
        promoted_digest=promoted.digest,
        evaluator_id=evaluator_id,
        gate_results=gates,
        decision=decision,
        decision_digest=canonical_digest(payload),
    )
