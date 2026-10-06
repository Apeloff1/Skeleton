"""Fourth-generation assurance controls for the dual-rival AI Game Builder.

These controls make quality density, proof closure, external knowledge intake,
cross-system interaction coverage, rare-event tails, catastrophic recovery and
terminal evidence closure executable rather than descriptive.

The module intentionally has no wall-clock budget. Time may be used to improve
quality indefinitely within a selected Forge round budget, while all material
state and resource growth remain governed elsewhere by the resource governor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
from typing import Iterable, Mapping, Sequence

from .contracts import EvaluatorProvenance, canonical_digest


class DeepAssuranceError(RuntimeError):
    """Fail-closed error raised by fourth-generation assurance controls."""


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeepAssuranceError(f"{label} must be non-empty text")
    return value.strip()


def _digest(value: str, label: str) -> str:
    value = _text(value, label)
    if len(value) < 16:
        raise DeepAssuranceError(f"{label} must carry a durable digest-like identity")
    return value


def _stable(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class ComplexitySnapshot:
    state_nodes: int
    dependency_edges: int
    rule_count: int
    artifact_bytes: int

    def __post_init__(self) -> None:
        for name, value in (
            ("state_nodes", self.state_nodes),
            ("dependency_edges", self.dependency_edges),
            ("rule_count", self.rule_count),
            ("artifact_bytes", self.artifact_bytes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DeepAssuranceError(f"{name} must be a non-negative integer")

    @property
    def weighted_complexity(self) -> int:
        return self.state_nodes + self.dependency_edges * 2 + self.rule_count * 3 + self.artifact_bytes // 1024


@dataclass(frozen=True, slots=True)
class ComplexityDecision:
    allowed: bool
    quality_delta: float
    complexity_delta: int
    quality_per_complexity: float
    reason: str


class ComplexityGovernor:
    """OP65: maximize quality density instead of raw system size."""

    def __init__(
        self,
        *,
        max_weighted_complexity: int,
        minimum_quality_per_complexity: float = 0.0005,
    ) -> None:
        if max_weighted_complexity <= 0:
            raise DeepAssuranceError("max_weighted_complexity must be positive")
        if minimum_quality_per_complexity < 0:
            raise DeepAssuranceError("minimum_quality_per_complexity must be non-negative")
        self.max_weighted_complexity = max_weighted_complexity
        self.minimum_quality_per_complexity = minimum_quality_per_complexity

    def assess(
        self,
        before: ComplexitySnapshot,
        after: ComplexitySnapshot,
        *,
        quality_before: float,
        quality_after: float,
    ) -> ComplexityDecision:
        for name, value in (("quality_before", quality_before), ("quality_after", quality_after)):
            if not math.isfinite(value):
                raise DeepAssuranceError(f"{name} must be finite")
        if after.weighted_complexity > self.max_weighted_complexity:
            return ComplexityDecision(False, quality_after - quality_before, after.weighted_complexity - before.weighted_complexity, 0.0, "complexity ceiling exceeded")
        complexity_delta = after.weighted_complexity - before.weighted_complexity
        quality_delta = quality_after - quality_before
        if complexity_delta <= 0:
            return ComplexityDecision(quality_delta >= 0, quality_delta, complexity_delta, float("inf") if quality_delta > 0 else 0.0, "complexity did not increase")
        density = quality_delta / complexity_delta
        allowed = quality_delta > 0 and density >= self.minimum_quality_per_complexity
        return ComplexityDecision(allowed, quality_delta, complexity_delta, density, "quality density sufficient" if allowed else "complexity increase is not justified by quality gain")


@dataclass(frozen=True, slots=True)
class RequirementProof:
    requirement_id: str
    artifact_digest: str
    evidence_digests: tuple[str, ...]
    evaluator_provenance: EvaluatorProvenance
    critical: bool = False
    passed: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirement_id", _text(self.requirement_id, "requirement_id"))
        object.__setattr__(self, "artifact_digest", _digest(self.artifact_digest, "artifact_digest"))
        if not isinstance(self.evaluator_provenance, EvaluatorProvenance):
            raise TypeError("requirement proof evaluator_provenance must be EvaluatorProvenance")
        if not isinstance(self.critical, bool):
            raise TypeError("requirement proof critical state must be boolean")
        if not isinstance(self.passed, bool):
            raise TypeError("requirement proof passed state must be boolean")
        if not self.evidence_digests:
            raise DeepAssuranceError("requirement proof needs evidence")
        evidence = tuple(_digest(x, "evidence_digest") for x in self.evidence_digests)
        if len(evidence) != len(set(evidence)):
            raise DeepAssuranceError("requirement proof evidence digests must be unique")
        if set(evidence) - set(self.evaluator_provenance.output_evidence_refs):
            raise DeepAssuranceError(
                "requirement proof evidence must be referenced by evaluator authority"
            )
        object.__setattr__(self, "evidence_digests", evidence)

    @property
    def evidence_binding_digest(self) -> str:
        return canonical_digest(
            {
                "artifact_digest": self.artifact_digest,
                "critical": self.critical,
                "evaluator_provenance_digest": self.evaluator_provenance.digest,
                "evidence_digests": list(self.evidence_digests),
                "passed": self.passed,
                "requirement_id": self.requirement_id,
            }
        )


class RequirementClosureLedger:
    """OP66: every declared requirement must terminate in proof or an explicit blocker."""

    def __init__(self, required_ids: Iterable[str]) -> None:
        ids = tuple(_text(x, "required_id") for x in required_ids)
        if not ids or len(ids) != len(set(ids)):
            raise DeepAssuranceError("required_ids must be non-empty and unique")
        self._required = ids
        self._proofs: dict[str, RequirementProof] = {}

    def record(self, proof: RequirementProof) -> None:
        if proof.requirement_id not in self._required:
            raise DeepAssuranceError(f"unknown requirement: {proof.requirement_id}")
        self._proofs[proof.requirement_id] = proof

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(x for x in self._required if x not in self._proofs)

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(x for x in self._required if x in self._proofs and not self._proofs[x].passed)

    @property
    def closed(self) -> bool:
        return not self.missing and not self.failed

    @property
    def digest(self) -> str:
        return _stable({
            "required": self._required,
            "proofs": {
                key: {
                    "artifact": proof.artifact_digest,
                    "evidence": proof.evidence_digests,
                    "critical": proof.critical,
                    "passed": proof.passed,
                    "evidence_binding_digest": proof.evidence_binding_digest,
                    "evaluator_provenance_digest": proof.evaluator_provenance.digest,
                }
                for key, proof in sorted(self._proofs.items())
            },
        })


@dataclass(frozen=True, slots=True)
class ConstraintResult:
    constraint_id: str
    passed: bool
    evidence_digest: str
    evaluator_provenance: EvaluatorProvenance
    critical: bool = True
    conflict_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "constraint_id", _text(self.constraint_id, "constraint_id"))
        object.__setattr__(self, "evidence_digest", _digest(self.evidence_digest, "evidence_digest"))
        if not isinstance(self.evaluator_provenance, EvaluatorProvenance):
            raise TypeError("constraint evaluator_provenance must be EvaluatorProvenance")
        if self.evidence_digest not in self.evaluator_provenance.output_evidence_refs:
            raise DeepAssuranceError(
                "constraint evidence must be referenced by evaluator authority"
            )
        if not isinstance(self.passed, bool):
            raise TypeError("constraint passed state must be boolean")
        if not isinstance(self.critical, bool):
            raise TypeError("constraint critical state must be boolean")
        object.__setattr__(self, "conflict_ids", tuple(_text(x, "conflict_id") for x in self.conflict_ids))

    @property
    def evidence_binding_digest(self) -> str:
        return canonical_digest(
            {
                "conflict_ids": list(self.conflict_ids),
                "constraint_id": self.constraint_id,
                "critical": self.critical,
                "evaluator_provenance_digest": self.evaluator_provenance.digest,
                "evidence_digest": self.evidence_digest,
                "passed": self.passed,
            }
        )


class ConstraintProofSet:
    """OP67: fail closed on unsatisfied critical constraints and expose conflict cores."""

    def __init__(self) -> None:
        self._rows: dict[str, ConstraintResult] = {}

    def add(self, result: ConstraintResult) -> None:
        if result.constraint_id in self._rows:
            raise DeepAssuranceError(f"duplicate constraint: {result.constraint_id}")
        self._rows[result.constraint_id] = result

    @property
    def blocking(self) -> tuple[ConstraintResult, ...]:
        return tuple(row for _, row in sorted(self._rows.items()) if row.critical and not row.passed)

    @property
    def conflict_core(self) -> tuple[str, ...]:
        ids: set[str] = set()
        for row in self.blocking:
            ids.add(row.constraint_id)
            ids.update(row.conflict_ids)
        return tuple(sorted(ids))

    @property
    def promotable(self) -> bool:
        return bool(self._rows) and not self.blocking

    @property
    def evidence_root(self) -> str:
        if not self._rows:
            return canonical_digest({"constraints": []})
        return canonical_digest(
            {
                "constraints": [
                    self._rows[key].evidence_binding_digest
                    for key in sorted(self._rows)
                ]
            }
        )


@dataclass(frozen=True, slots=True)
class IntentInvariant:
    invariant_id: str
    semantic_digest: str
    protected: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "invariant_id", _text(self.invariant_id, "invariant_id"))
        object.__setattr__(self, "semantic_digest", _digest(self.semantic_digest, "semantic_digest"))


class IntentPreservationGate:
    """OP68: generated edits may not silently alter protected design intent."""

    def __init__(self, invariants: Sequence[IntentInvariant]) -> None:
        if not invariants:
            raise DeepAssuranceError("at least one intent invariant is required")
        self._baseline = {row.invariant_id: row for row in invariants}
        if len(self._baseline) != len(invariants):
            raise DeepAssuranceError("intent invariant ids must be unique")

    def verify(self, current: Sequence[IntentInvariant]) -> tuple[str, ...]:
        rows = {row.invariant_id: row for row in current}
        violations = []
        for key, expected in self._baseline.items():
            observed = rows.get(key)
            if expected.protected and (observed is None or observed.semantic_digest != expected.semantic_digest):
                violations.append(key)
        return tuple(sorted(violations))


@dataclass(frozen=True, slots=True)
class TransformReceipt:
    tool_digest: str
    input_digest: str
    config_digest: str
    output_digest: str
    environment_digest: str
    executor_provenance: EvaluatorProvenance
    execution_evidence_digest: str

    def __post_init__(self) -> None:
        for name in ("tool_digest", "input_digest", "config_digest", "output_digest", "environment_digest"):
            object.__setattr__(self, name, _digest(getattr(self, name), name))
        if not isinstance(self.executor_provenance, EvaluatorProvenance):
            raise TypeError("transform executor_provenance must be EvaluatorProvenance")
        object.__setattr__(
            self,
            "execution_evidence_digest",
            _digest(self.execution_evidence_digest, "execution_evidence_digest"),
        )
        if self.execution_evidence_digest not in self.executor_provenance.output_evidence_refs:
            raise DeepAssuranceError(
                "transform execution evidence must be referenced by executor authority"
            )

    @property
    def authority_binding_digest(self) -> str:
        return canonical_digest(
            {
                "config_digest": self.config_digest,
                "environment_digest": self.environment_digest,
                "execution_evidence_digest": self.execution_evidence_digest,
                "executor_provenance_digest": self.executor_provenance.digest,
                "input_digest": self.input_digest,
                "output_digest": self.output_digest,
                "tool_digest": self.tool_digest,
            }
        )

    @property
    def digest(self) -> str:
        return _stable({
            "tool": self.tool_digest,
            "input": self.input_digest,
            "config": self.config_digest,
            "output": self.output_digest,
            "environment": self.environment_digest,
            "authority_binding_digest": self.authority_binding_digest,
        })


class HermeticTransformRegistry:
    """OP69: bind generated assets/code to reproducible tool+input+config+environment identities."""

    def __init__(self) -> None:
        self._receipts: dict[str, TransformReceipt] = {}

    def record(self, receipt: TransformReceipt) -> None:
        prior = self._receipts.get(receipt.digest)
        if prior is not None and prior != receipt:
            raise DeepAssuranceError("transform receipt digest collision")
        self._receipts[receipt.digest] = receipt

    def reproduce(self, original_digest: str, replay: TransformReceipt) -> bool:
        original = self._receipts.get(_text(original_digest, "original_digest"))
        if original is None:
            raise DeepAssuranceError("unknown transform receipt")
        return (
            original.tool_digest == replay.tool_digest
            and original.input_digest == replay.input_digest
            and original.config_digest == replay.config_digest
            and original.environment_digest == replay.environment_digest
            and original.output_digest == replay.output_digest
        )


_ALLOWED_RIGHTS = frozenset({
    "project_owned",
    "public_domain",
    "permissive_reuse",
    "licensed_reuse",
    "facts_and_ideas_reference_only",
    "restricted_reference_only",
})
_INCORPORABLE_RIGHTS = frozenset({
    "project_owned",
    "public_domain",
    "permissive_reuse",
    "licensed_reuse",
})


@dataclass(frozen=True, slots=True)
class KnowledgeSource:
    source_id: str
    content_digest: str
    rights_state: str
    source_class: str
    snapshot_digest: str
    factual_only: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text(self.source_id, "source_id"))
        object.__setattr__(self, "content_digest", _digest(self.content_digest, "content_digest"))
        object.__setattr__(self, "snapshot_digest", _digest(self.snapshot_digest, "snapshot_digest"))
        object.__setattr__(self, "source_class", _text(self.source_class, "source_class"))
        object.__setattr__(self, "rights_state", _text(self.rights_state, "rights_state"))


class KnowledgeIngestionFirewall:
    """OP70/OP71: broad gaming research is permitted, copying unknown/restricted expression is not."""

    def __init__(self) -> None:
        self._sources: dict[str, KnowledgeSource] = {}

    def admit(self, source: KnowledgeSource) -> None:
        if source.rights_state not in _ALLOWED_RIGHTS:
            raise DeepAssuranceError(f"source rights state is quarantined or forbidden: {source.rights_state}")
        if source.source_id in self._sources and self._sources[source.source_id] != source:
            raise DeepAssuranceError("source identity reused with different snapshot")
        self._sources[source.source_id] = source

    def may_incorporate_expression(self, source_id: str) -> bool:
        source = self._sources.get(_text(source_id, "source_id"))
        if source is None:
            raise DeepAssuranceError("unknown source")
        return source.rights_state in _INCORPORABLE_RIGHTS

    def may_use_as_reference(self, source_id: str) -> bool:
        source = self._sources.get(_text(source_id, "source_id"))
        if source is None:
            raise DeepAssuranceError("unknown source")
        return source.rights_state in _ALLOWED_RIGHTS

    @property
    def snapshot_digest(self) -> str:
        return _stable({
            key: {
                "content": row.content_digest,
                "rights": row.rights_state,
                "class": row.source_class,
                "snapshot": row.snapshot_digest,
                "factual_only": row.factual_only,
            }
            for key, row in sorted(self._sources.items())
        })


class GranularityCoverage:
    """OP72/OP73: require evidence at each declared visual/narrative scale."""

    def __init__(self, required_scales: Sequence[str]) -> None:
        scales = tuple(_text(x, "scale") for x in required_scales)
        if not scales or len(scales) != len(set(scales)):
            raise DeepAssuranceError("required_scales must be non-empty and unique")
        self._required = scales
        self._evidence: dict[str, set[str]] = {scale: set() for scale in scales}

    def record(self, scale: str, evidence_digest: str) -> None:
        scale = _text(scale, "scale")
        if scale not in self._evidence:
            raise DeepAssuranceError(f"unknown scale: {scale}")
        self._evidence[scale].add(_digest(evidence_digest, "evidence_digest"))

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(scale for scale in self._required if not self._evidence[scale])

    @property
    def complete(self) -> bool:
        return not self.missing


@dataclass(frozen=True, slots=True)
class MentalModelProbe:
    concept_id: str
    expected_understanding: str
    observed_understanding: str
    critical: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "concept_id", _text(self.concept_id, "concept_id"))
        object.__setattr__(self, "expected_understanding", _text(self.expected_understanding, "expected_understanding"))
        object.__setattr__(self, "observed_understanding", _text(self.observed_understanding, "observed_understanding"))

    @property
    def passed(self) -> bool:
        return self.expected_understanding == self.observed_understanding


class PlayerMentalModelGate:
    """OP74: tutorials/UI/mechanics must teach the truth of the actual game state."""

    @staticmethod
    def blockers(probes: Iterable[MentalModelProbe]) -> tuple[str, ...]:
        return tuple(sorted(row.concept_id for row in probes if row.critical and not row.passed))


class InteractionMatrix:
    """OP75: prove declared pairwise system interactions were exercised."""

    def __init__(self, system_ids: Sequence[str]) -> None:
        ids = tuple(_text(x, "system_id") for x in system_ids)
        if len(ids) < 2 or len(ids) != len(set(ids)):
            raise DeepAssuranceError("system_ids must contain at least two unique systems")
        self._ids = ids
        self._covered: set[tuple[str, str]] = set()

    @property
    def required_pairs(self) -> tuple[tuple[str, str], ...]:
        rows = []
        for i, left in enumerate(self._ids):
            for right in self._ids[i + 1:]:
                rows.append((left, right))
        return tuple(rows)

    def cover(self, left: str, right: str) -> None:
        left, right = _text(left, "left"), _text(right, "right")
        if left == right or left not in self._ids or right not in self._ids:
            raise DeepAssuranceError("interaction pair must contain two known distinct systems")
        self._covered.add(tuple(sorted((left, right))))

    @property
    def missing_pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple(pair for pair in self.required_pairs if tuple(sorted(pair)) not in self._covered)

    @property
    def complete(self) -> bool:
        return not self.missing_pairs


@dataclass(frozen=True, slots=True)
class RareEventObservation:
    scenario_id: str
    samples: int
    critical_failures: int
    threshold: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", _text(self.scenario_id, "scenario_id"))
        if self.samples <= 0 or self.critical_failures < 0 or self.critical_failures > self.samples:
            raise DeepAssuranceError("invalid rare-event sample counts")
        if not 0.0 <= self.threshold <= 1.0:
            raise DeepAssuranceError("threshold must be in [0,1]")

    @property
    def observed_rate(self) -> float:
        return self.critical_failures / self.samples

    @property
    def conservative_upper_rate(self) -> float:
        # Rule-of-three style conservative bound; intentionally simple and deterministic.
        if self.critical_failures == 0:
            return min(1.0, 3.0 / self.samples)
        return min(1.0, self.observed_rate + 3.0 / math.sqrt(self.samples))

    @property
    def passed(self) -> bool:
        return self.conservative_upper_rate <= self.threshold


class TailRiskLab:
    """OP76: rare critical failures remain blockers even when averages look excellent."""

    @staticmethod
    def blockers(rows: Iterable[RareEventObservation]) -> tuple[str, ...]:
        return tuple(sorted(row.scenario_id for row in rows if not row.passed))


@dataclass(frozen=True, slots=True)
class TelemetryAggregate:
    metric_id: str
    cohort_digest: str
    sample_count: int
    value: float
    contains_raw_identifier: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric_id", _text(self.metric_id, "metric_id"))
        object.__setattr__(self, "cohort_digest", _digest(self.cohort_digest, "cohort_digest"))
        if self.sample_count <= 0 or not math.isfinite(self.value):
            raise DeepAssuranceError("invalid telemetry aggregate")


class TelemetryFeedbackGate:
    """OP77: telemetry may inform design only through privacy-minimized aggregates."""

    @staticmethod
    def admit(row: TelemetryAggregate, *, minimum_cohort_size: int = 20) -> bool:
        if row.contains_raw_identifier:
            return False
        return row.sample_count >= minimum_cohort_size


@dataclass(frozen=True, slots=True)
class ResurrectionPoint:
    project_digest: str
    canon_digest: str
    artifact_graph_digest: str
    event_chain_digest: str
    rights_snapshot_digest: str
    checkpoint_authority: EvaluatorProvenance
    checkpoint_evidence_digest: str

    def __post_init__(self) -> None:
        for name in (
            "project_digest",
            "canon_digest",
            "artifact_graph_digest",
            "event_chain_digest",
            "rights_snapshot_digest",
        ):
            object.__setattr__(self, name, _digest(getattr(self, name), name))
        if not isinstance(self.checkpoint_authority, EvaluatorProvenance):
            raise TypeError("resurrection checkpoint_authority must be EvaluatorProvenance")
        object.__setattr__(
            self,
            "checkpoint_evidence_digest",
            _digest(self.checkpoint_evidence_digest, "checkpoint_evidence_digest"),
        )
        if self.checkpoint_evidence_digest not in self.checkpoint_authority.output_evidence_refs:
            raise DeepAssuranceError(
                "resurrection checkpoint evidence must be referenced by checkpoint authority"
            )

    @property
    def digest(self) -> str:
        return _stable({
            "project": self.project_digest,
            "canon": self.canon_digest,
            "artifacts": self.artifact_graph_digest,
            "events": self.event_chain_digest,
            "rights": self.rights_snapshot_digest,
            "checkpoint_authority_digest": self.checkpoint_authority.digest,
            "checkpoint_evidence_digest": self.checkpoint_evidence_digest,
        })


@dataclass(frozen=True, slots=True)
class ResurrectionVerification:
    checkpoint_digest: str
    reconstructed_digest: str
    passed: bool
    verifier_provenance: EvaluatorProvenance
    verification_evidence_digest: str
    proof_digest: str

    def __post_init__(self) -> None:
        for name in ("checkpoint_digest", "reconstructed_digest", "proof_digest"):
            object.__setattr__(self, name, _digest(getattr(self, name), name))
        if not isinstance(self.passed, bool):
            raise TypeError("resurrection verification passed state must be boolean")
        if not isinstance(self.verifier_provenance, EvaluatorProvenance):
            raise TypeError("resurrection verifier_provenance must be EvaluatorProvenance")
        object.__setattr__(
            self,
            "verification_evidence_digest",
            _digest(self.verification_evidence_digest, "verification_evidence_digest"),
        )
        if self.verification_evidence_digest not in self.verifier_provenance.output_evidence_refs:
            raise DeepAssuranceError(
                "resurrection verification evidence must be referenced by verifier authority"
            )
        expected = canonical_digest(self.proof_payload())
        if self.proof_digest != expected:
            raise DeepAssuranceError("resurrection proof digest mismatch")

    def proof_payload(self) -> dict[str, object]:
        return {
            "checkpoint_digest": self.checkpoint_digest,
            "passed": self.passed,
            "reconstructed_digest": self.reconstructed_digest,
            "verification_evidence_digest": self.verification_evidence_digest,
            "verifier_provenance_digest": self.verifier_provenance.digest,
        }


class ProjectResurrectionRegistry:
    """OP78: prove the whole project can be reconstructed after catastrophic loss."""

    def __init__(self) -> None:
        self._points: dict[str, ResurrectionPoint] = {}

    def register(self, point: ResurrectionPoint) -> str:
        self._points[point.digest] = point
        return point.digest

    def verify(
        self,
        digest: str,
        reconstructed: ResurrectionPoint,
        *,
        verifier_provenance: EvaluatorProvenance,
        verification_evidence_digest: str,
    ) -> ResurrectionVerification:
        checkpoint_digest = _text(digest, "digest")
        original = self._points.get(checkpoint_digest)
        if original is None:
            raise DeepAssuranceError("unknown resurrection checkpoint")
        passed = original == reconstructed
        payload = {
            "checkpoint_digest": checkpoint_digest,
            "passed": passed,
            "reconstructed_digest": reconstructed.digest,
            "verification_evidence_digest": verification_evidence_digest,
            "verifier_provenance_digest": verifier_provenance.digest,
        }
        return ResurrectionVerification(
            checkpoint_digest=checkpoint_digest,
            reconstructed_digest=reconstructed.digest,
            passed=passed,
            verifier_provenance=verifier_provenance,
            verification_evidence_digest=verification_evidence_digest,
            proof_digest=canonical_digest(payload),
        )


class EvidenceMerkleLedger:
    """OP79: append-only evidence root over authority-bound evidence leaves."""

    def __init__(self) -> None:
        self._leaves: list[str] = []

    def append(
        self,
        evidence_digest: str,
        *,
        evaluator_provenance: EvaluatorProvenance,
    ) -> str:
        evidence = _digest(evidence_digest, "evidence_digest")
        if not isinstance(evaluator_provenance, EvaluatorProvenance):
            raise TypeError("evidence ledger evaluator_provenance must be EvaluatorProvenance")
        if evidence not in evaluator_provenance.output_evidence_refs:
            raise DeepAssuranceError(
                "evidence ledger leaf must be referenced by evaluator authority"
            )
        binding = canonical_digest(
            {
                "evaluator_provenance_digest": evaluator_provenance.digest,
                "evidence_digest": evidence,
            }
        )
        self._leaves.append(binding)
        return self.root

    @property
    def leaves(self) -> tuple[str, ...]:
        return tuple(self._leaves)

    @property
    def root(self) -> str:
        if not self._leaves:
            return sha256(b"EMPTY").hexdigest()
        layer = [sha256(x.encode("utf-8")).hexdigest() for x in self._leaves]
        while len(layer) > 1:
            if len(layer) % 2:
                layer.append(layer[-1])
            layer = [
                sha256((layer[i] + layer[i + 1]).encode("ascii")).hexdigest()
                for i in range(0, len(layer), 2)
            ]
        return layer[0]


@dataclass(frozen=True, slots=True)
class ClosureCertificate:
    artifact_digest: str
    canon_digest: str
    provenance_digest: str
    evidence_root: str
    family_ids: tuple[str, ...]
    critical_plane_ids: tuple[str, ...]
    verifier_provenance: EvaluatorProvenance
    verification_evidence_digest: str
    unresolved_critical_gaps: tuple[str, ...] = ()
    independently_verified: bool = False

    def __post_init__(self) -> None:
        for name in ("artifact_digest", "canon_digest", "provenance_digest", "evidence_root"):
            object.__setattr__(self, name, _digest(getattr(self, name), name))
        if not isinstance(self.verifier_provenance, EvaluatorProvenance):
            raise TypeError("closure verifier_provenance must be EvaluatorProvenance")
        object.__setattr__(
            self,
            "verification_evidence_digest",
            _digest(self.verification_evidence_digest, "verification_evidence_digest"),
        )
        if self.verification_evidence_digest not in self.verifier_provenance.output_evidence_refs:
            raise DeepAssuranceError(
                "closure verification evidence must be referenced by verifier authority"
            )
        if not isinstance(self.independently_verified, bool):
            raise TypeError("closure independent verification state must be boolean")
        object.__setattr__(self, "family_ids", tuple(_text(x, "family_id") for x in self.family_ids))
        object.__setattr__(self, "critical_plane_ids", tuple(_text(x, "critical_plane_id") for x in self.critical_plane_ids))
        object.__setattr__(self, "unresolved_critical_gaps", tuple(_text(x, "gap") for x in self.unresolved_critical_gaps))

    @property
    def verification_binding_digest(self) -> str:
        return canonical_digest(
            {
                "artifact_digest": self.artifact_digest,
                "canon_digest": self.canon_digest,
                "evidence_root": self.evidence_root,
                "provenance_digest": self.provenance_digest,
                "verification_evidence_digest": self.verification_evidence_digest,
                "verifier_provenance_digest": self.verifier_provenance.digest,
            }
        )

    def validate(self, *, required_critical_planes: Sequence[str]) -> None:
        expected_families = tuple(f"GB{i:02d}" for i in range(1, 51))
        if tuple(self.family_ids) != expected_families:
            raise DeepAssuranceError("closure certificate requires all GB01..GB50 families in order")
        required = tuple(_text(x, "required_critical_plane") for x in required_critical_planes)
        if not set(required).issubset(set(self.critical_plane_ids)):
            raise DeepAssuranceError("closure certificate is missing critical planes")
        if self.unresolved_critical_gaps:
            raise DeepAssuranceError("closure certificate has unresolved critical gaps")
        if not self.independently_verified:
            raise DeepAssuranceError("closure certificate requires independent verification")

    @property
    def digest(self) -> str:
        return _stable({
            "artifact": self.artifact_digest,
            "canon": self.canon_digest,
            "provenance": self.provenance_digest,
            "evidence_root": self.evidence_root,
            "families": self.family_ids,
            "critical_planes": self.critical_plane_ids,
            "gaps": self.unresolved_critical_gaps,
            "independent": self.independently_verified,
            "verification_binding_digest": self.verification_binding_digest,
            "verifier_provenance_digest": self.verifier_provenance.digest,
        })
