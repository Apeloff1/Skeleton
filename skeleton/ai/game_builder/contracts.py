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


def _normalized_identity_text(name: str, value: object, *, maximum: int = 192) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise ValueError(f"{name} must be normalized bounded text")
    return normalized


def _sha256_identity(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be lowercase sha256")
    if any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{name} must be lowercase sha256")
    return value


@dataclass(frozen=True, slots=True)
class ProducerProvenance:
    """Immutable bridge from canonical AI execution/model identity into a candidate."""

    project_id: str
    run_id: str
    operation_id: str
    execution_id: str
    execution_identity_digest: str
    finalization_intent_digest: str
    model_identity_digest: str
    producer_behavior_digest: str
    source_revision: str
    provider_receipt_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("project_id", "run_id", "operation_id", "execution_id"):
            object.__setattr__(
                self,
                name,
                _normalized_identity_text(name, getattr(self, name)),
            )
        for name in (
            "execution_identity_digest",
            "finalization_intent_digest",
            "model_identity_digest",
            "producer_behavior_digest",
        ):
            object.__setattr__(
                self,
                name,
                _sha256_identity(name, getattr(self, name)),
            )
        source_revision = self.source_revision
        if (
            not isinstance(source_revision, str)
            or len(source_revision) not in {40, 64}
            or any(ch not in "0123456789abcdef" for ch in source_revision)
        ):
            raise ValueError("source_revision must be a lowercase git object id")
        refs = tuple(
            _normalized_identity_text("provider_receipt_ref", ref, maximum=2048)
            for ref in self.provider_receipt_refs
        )
        if len(refs) != len(set(refs)):
            raise ValueError("provider receipt refs must be unique")
        object.__setattr__(self, "provider_receipt_refs", refs)

    def to_payload(self) -> dict[str, object]:
        return {
            "execution_id": self.execution_id,
            "execution_identity_digest": self.execution_identity_digest,
            "finalization_intent_digest": self.finalization_intent_digest,
            "model_identity_digest": self.model_identity_digest,
            "operation_id": self.operation_id,
            "producer_behavior_digest": self.producer_behavior_digest,
            "project_id": self.project_id,
            "provider_receipt_refs": list(self.provider_receipt_refs),
            "run_id": self.run_id,
            "source_revision": self.source_revision,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_payload())


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
    producer_provenance: ProducerProvenance
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
        producer_provenance: ProducerProvenance,
        artifact: ArtifactIdentity,
        quality: Mapping[str, float],
        evidence_digests: Iterable[str],
        assumption_digest: str,
        parent_candidate_digests: Iterable[str] = (),
    ) -> "Candidate":
        evidence = tuple(evidence_digests)
        parents = tuple(parent_candidate_digests)
        if not isinstance(producer_id, str) or not producer_id.strip():
            raise ValueError("producer_id must be non-empty")
        if not isinstance(producer_provenance, ProducerProvenance):
            raise TypeError("producer_provenance must be ProducerProvenance")
        if not isinstance(artifact, ArtifactIdentity):
            raise TypeError("artifact must be ArtifactIdentity")
        if not evidence or any(
            not isinstance(item, str) or not item.strip() or len(item) < 16
            for item in evidence
        ):
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
            producer_provenance=producer_provenance,
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
            "producer_provenance": self.producer_provenance.to_payload(),
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
        if not isinstance(self.gate_id, str) or not self.gate_id.strip():
            raise ValueError("gate_id must be non-empty")
        if not isinstance(self.passed, bool):
            raise TypeError("gate passed state must be boolean")
        if not isinstance(self.non_compensable, bool):
            raise TypeError("gate non_compensable state must be boolean")
        if not isinstance(self.evidence_digest, str) or len(self.evidence_digest) < 16:
            raise ValueError("gate evidence must use a stable digest")


def _promotion_decision_payload(
    *,
    round_index: int,
    effort_mode: EffortMode,
    incumbent_digest: str,
    submitted_digest: str | None,
    promoted_digest: str,
    evaluator_id: str,
    gate_results: Sequence[GateResult],
    evaluated_submitted_quality: tuple[tuple[str, float], ...] | None,
    decision: str,
) -> dict[str, object]:
    return {
        "decision": decision,
        "effort_mode": int(effort_mode),
        "evaluator_id": evaluator_id,
        "gates": [
            (gate.gate_id, gate.passed, gate.non_compensable, gate.evidence_digest)
            for gate in gate_results
        ],
        "incumbent": incumbent_digest,
        "promoted": promoted_digest,
        "evaluated_submitted_quality": (
            dict(evaluated_submitted_quality)
            if evaluated_submitted_quality is not None
            else None
        ),
        "round_index": round_index,
        "submitted": submitted_digest,
    }


@dataclass(frozen=True, slots=True)
class PromotionReceipt:
    round_index: int
    effort_mode: EffortMode
    incumbent_digest: str
    submitted_digest: str | None
    promoted_digest: str
    evaluator_id: str
    gate_results: tuple[GateResult, ...]
    evaluated_submitted_quality: tuple[tuple[str, float], ...] | None
    decision: str
    decision_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.effort_mode, EffortMode):
            raise TypeError("promotion receipt effort_mode must be EffortMode")
        if self.round_index < 1 or self.round_index > self.effort_mode.rounds:
            raise ValueError("promotion receipt round index outside effort-mode bounds")
        for name in ("incumbent_digest", "promoted_digest", "decision_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) < 16:
                raise ValueError(f"{name} must be a stable digest")
        if self.submitted_digest is not None and (
            not isinstance(self.submitted_digest, str) or len(self.submitted_digest) < 16
        ):
            raise ValueError("submitted_digest must be a stable digest when present")
        if not isinstance(self.evaluator_id, str) or not self.evaluator_id.strip():
            raise ValueError("promotion receipt evaluator_id must be non-empty")
        if self.evaluator_id in {Rival.A.value, Rival.B.value}:
            raise ValueError("promotion receipt evaluator must be independent from both rivals")
        if any(not isinstance(gate, GateResult) for gate in self.gate_results):
            raise TypeError("promotion receipt gate_results must contain GateResult values")
        gate_ids = [gate.gate_id for gate in self.gate_results]
        if len(gate_ids) != len(set(gate_ids)):
            raise ValueError("promotion receipt gate ids must be unique")
        quality = self.evaluated_submitted_quality
        if quality is not None:
            quality = normalize_quality(dict(quality))
            object.__setattr__(self, "evaluated_submitted_quality", quality)
        if self.decision not in {"promote", "retain_incumbent"}:
            raise ValueError("promotion receipt decision is invalid")
        if self.decision == "promote":
            if self.submitted_digest is None or self.promoted_digest != self.submitted_digest:
                raise ValueError("promote receipt must promote the submitted candidate")
        elif self.promoted_digest != self.incumbent_digest:
            raise ValueError("retain receipt must preserve the incumbent")
        expected_digest = canonical_digest(self.decision_payload())
        if self.decision_digest != expected_digest:
            raise ValueError("promotion receipt decision digest mismatch")

    def decision_payload(self) -> dict[str, object]:
        return _promotion_decision_payload(
            round_index=self.round_index,
            effort_mode=self.effort_mode,
            incumbent_digest=self.incumbent_digest,
            submitted_digest=self.submitted_digest,
            promoted_digest=self.promoted_digest,
            evaluator_id=self.evaluator_id,
            gate_results=self.gate_results,
            evaluated_submitted_quality=self.evaluated_submitted_quality,
            decision=self.decision,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "decision": self.decision,
            "decision_digest": self.decision_digest,
            "effort_mode": int(self.effort_mode),
            "evaluated_submitted_quality": (
                dict(self.evaluated_submitted_quality)
                if self.evaluated_submitted_quality is not None
                else None
            ),
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
    normalized = tuple(gates)
    if not normalized:
        return False
    if any(not isinstance(gate, GateResult) for gate in normalized):
        raise TypeError("gate_results must contain GateResult values")
    hard_gates = tuple(gate for gate in normalized if gate.non_compensable)
    if not hard_gates:
        return False
    return all(gate.passed for gate in hard_gates)


def pareto_safe_scores(
    current: Mapping[str, float],
    proposed: Mapping[str, float],
    *,
    protected_axes: Iterable[str] = PROTECTED_AXES,
    epsilon: float = 1e-9,
) -> bool:
    current_norm = dict(normalize_quality(current))
    proposed_norm = dict(normalize_quality(proposed))
    protected = tuple(protected_axes)
    if any(axis not in current_norm or axis not in proposed_norm for axis in protected):
        raise ValueError("protected axis missing from quality vector")
    if any(
        proposed_norm[axis] + epsilon < current_norm[axis]
        for axis in protected
    ):
        return False
    return any(
        proposed_norm[axis] > current_norm[axis] + epsilon
        for axis in QUALITY_AXES
    )


def pareto_safe(
    incumbent: Candidate,
    candidate: Candidate,
    *,
    protected_axes: Iterable[str] = PROTECTED_AXES,
    epsilon: float = 1e-9,
) -> bool:
    return pareto_safe_scores(
        incumbent.quality_map,
        candidate.quality_map,
        protected_axes=protected_axes,
        epsilon=epsilon,
    )


def promotion_receipt(
    *,
    round_index: int,
    effort_mode: EffortMode,
    incumbent: Candidate,
    submitted: Candidate | None,
    evaluator_id: str,
    gate_results: Sequence[GateResult],
    protected_axes: Iterable[str] = PROTECTED_AXES,
    submitted_quality_override: Mapping[str, float] | None = None,
) -> PromotionReceipt:
    if round_index < 1 or round_index > effort_mode.rounds:
        raise ValueError("round index outside effort-mode bounds")
    if evaluator_id in {Rival.A.value, Rival.B.value} or not evaluator_id.strip():
        raise ValueError("promotion evaluator must be independent from both rivals")

    gates = tuple(gate_results)
    if any(not isinstance(gate, GateResult) for gate in gates):
        raise TypeError("gate_results must contain GateResult values")
    gate_ids = [gate.gate_id for gate in gates]
    if len(gate_ids) != len(set(gate_ids)):
        raise ValueError("gate_results must use unique gate ids")
    proposed_quality = (
        submitted.quality_map
        if submitted is not None and submitted_quality_override is None
        else submitted_quality_override
    )
    promote = (
        submitted is not None
        and proposed_quality is not None
        and hard_gates_pass(gates)
        and pareto_safe_scores(
            incumbent.quality_map,
            proposed_quality,
            protected_axes=protected_axes,
        )
    )
    promoted = submitted if promote else incumbent
    decision = "promote" if promote else "retain_incumbent"
    evaluated_quality = (
        normalize_quality(proposed_quality)
        if proposed_quality is not None
        else None
    )
    payload = _promotion_decision_payload(
        round_index=round_index,
        effort_mode=effort_mode,
        incumbent_digest=incumbent.digest,
        submitted_digest=submitted.digest if submitted else None,
        promoted_digest=promoted.digest,
        evaluator_id=evaluator_id,
        gate_results=gates,
        evaluated_submitted_quality=evaluated_quality,
        decision=decision,
    )
    return PromotionReceipt(
        round_index=round_index,
        effort_mode=effort_mode,
        incumbent_digest=incumbent.digest,
        submitted_digest=submitted.digest if submitted else None,
        promoted_digest=promoted.digest,
        evaluator_id=evaluator_id,
        gate_results=gates,
        evaluated_submitted_quality=evaluated_quality,
        decision=decision,
        decision_digest=canonical_digest(payload),
    )
