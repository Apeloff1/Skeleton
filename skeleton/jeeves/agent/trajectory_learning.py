"""Trajectory normalization and process-level credit assignment for Jeeves.

Long-horizon agents need denser learning signals than an end-of-run success bit.
This module converts a run into an immutable, token-efficient trajectory and
assigns causal/process credit to individual decisions, steps, tools, evidence,
and verification events.  The design is intentionally harness-centric:

* normalized records are portable across runtime versions;
* authoritative host outcomes are kept distinct from model-proposed judgments;
* credit is dependency-aware and verification-aware, not merely temporal;
* replay metadata is content-addressed for deterministic audits;
* lesson extraction is staged and confidence-gated rather than self-applied;
* trajectory retrieval supports continual learning without copying raw logs into
  every prompt.

No private chain-of-thought is persisted.  Reasoning records are concise public
summaries supplied by the harness, if available.
"""

from __future__ import annotations

import math
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

from .runtime import RunCheckpoint
from .types import (
    AgentContractError,
    AgentResult,
    Claim,
    EvidenceRef,
    Plan,
    PlanStep,
    RiskTier,
    StepStatus,
    ToolObservation,
    bounded_text,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


class TrajectoryError(RuntimeError):
    pass


class RecordKind(str, Enum):
    META = "meta"
    GOAL = "goal"
    PLAN = "plan"
    STEP = "step"
    TOOL = "tool"
    EVIDENCE = "evidence"
    VERIFICATION = "verification"
    CLAIM = "claim"
    ANSWER = "answer"
    CHECKPOINT = "checkpoint"
    FAILURE = "failure"
    CONTROL = "control"


class OutcomeLabel(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class CreditSource(str, Enum):
    OUTCOME = "outcome"
    DEPENDENCY = "dependency"
    VERIFICATION = "verification"
    EVIDENCE = "evidence"
    FAILURE = "failure"
    COUNTERFACTUAL = "counterfactual"
    CENTRALITY = "centrality"
    TEMPORAL = "temporal"


@dataclass(frozen=True, slots=True)
class TrajectoryRecord:
    record_id: str
    sequence: int
    kind: RecordKind
    at: float
    payload: Mapping[str, Any]
    parent_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    authoritative: bool = True
    outcome: OutcomeLabel = OutcomeLabel.UNKNOWN
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", require_id("record_id", self.record_id))
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise AgentContractError("trajectory sequence must be non-negative integer")
        if not isinstance(self.kind, RecordKind):
            object.__setattr__(self, "kind", RecordKind(str(self.kind)))
        at = finite_number("at", self.at)
        if at < 0:
            raise AgentContractError("trajectory timestamp must be non-negative")
        object.__setattr__(self, "at", at)
        object.__setattr__(self, "payload", json_safe(dict(self.payload)))
        object.__setattr__(self, "parent_ids", tuple(require_id("parent_id", value) for value in self.parent_ids))
        object.__setattr__(self, "evidence_ids", tuple(require_id("evidence_id", value) for value in self.evidence_ids))
        if not isinstance(self.authoritative, bool):
            raise AgentContractError("authoritative must be boolean")
        if not isinstance(self.outcome, OutcomeLabel):
            object.__setattr__(self, "outcome", OutcomeLabel(str(self.outcome)))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "sequence": self.sequence,
                "kind": self.kind.value,
                "at": self.at,
                "payload": self.payload,
                "parents": self.parent_ids,
                "evidence": self.evidence_ids,
                "authoritative": self.authoritative,
                "outcome": self.outcome.value,
                "metadata": self.metadata,
            }
        )


@dataclass(frozen=True, slots=True)
class Trajectory:
    trajectory_id: str
    run_id: str
    goal_id: str
    records: tuple[TrajectoryRecord, ...]
    success: bool
    termination_reason: str
    source: str = "jeeves"
    version: str = "trajectory-v1"
    created_at: float = field(default_factory=time.time)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "trajectory_id", require_id("trajectory_id", self.trajectory_id))
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        object.__setattr__(self, "goal_id", require_id("goal_id", self.goal_id))
        records = tuple(self.records)
        if any(not isinstance(record, TrajectoryRecord) for record in records):
            raise AgentContractError("trajectory records must contain TrajectoryRecord")
        sequences = [record.sequence for record in records]
        if sequences != sorted(sequences) or len(set(sequences)) != len(sequences):
            raise AgentContractError("trajectory sequences must be unique and ordered")
        ids = [record.record_id for record in records]
        if len(set(ids)) != len(ids):
            raise AgentContractError("trajectory contains duplicate record ids")
        known: set[str] = set()
        for record in records:
            missing = set(record.parent_ids) - known
            if missing:
                raise AgentContractError("trajectory parent points forward or is missing", context={"record": record.record_id, "missing": sorted(missing)})
            known.add(record.record_id)
        object.__setattr__(self, "records", records)
        if not isinstance(self.success, bool):
            raise AgentContractError("trajectory success must be boolean")
        object.__setattr__(self, "termination_reason", bounded_text("termination_reason", self.termination_reason, maximum=256))
        object.__setattr__(self, "source", require_id("source", self.source))
        object.__setattr__(self, "version", require_id("version", self.version))
        created = finite_number("created_at", self.created_at)
        if created < 0:
            raise AgentContractError("created_at must be non-negative")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "run": self.run_id,
                "goal": self.goal_id,
                "success": self.success,
                "termination": self.termination_reason,
                "version": self.version,
                "records": [(record.record_id, record.fingerprint) for record in self.records],
                "metadata": self.metadata,
            }
        )

    def records_of(self, *kinds: RecordKind) -> tuple[TrajectoryRecord, ...]:
        wanted = set(kinds)
        return tuple(record for record in self.records if not wanted or record.kind in wanted)

    def record(self, record_id: str) -> TrajectoryRecord:
        record_id = require_id("record_id", record_id)
        for record in self.records:
            if record.record_id == record_id:
                return record
        raise KeyError(record_id)

    def descendants(self, record_id: str) -> tuple[TrajectoryRecord, ...]:
        record_id = require_id("record_id", record_id)
        children: dict[str, list[TrajectoryRecord]] = defaultdict(list)
        for record in self.records:
            for parent in record.parent_ids:
                children[parent].append(record)
        visited: set[str] = set()
        queue = deque(children.get(record_id, ()))
        result: list[TrajectoryRecord] = []
        while queue:
            record = queue.popleft()
            if record.record_id in visited:
                continue
            visited.add(record.record_id)
            result.append(record)
            queue.extend(children.get(record.record_id, ()))
        result.sort(key=lambda item: item.sequence)
        return tuple(result)


class TrajectoryBuilder:
    """Normalize runtime checkpoints and final results into one causal record stream."""

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock

    def build(
        self,
        result: AgentResult,
        *,
        checkpoints: Sequence[RunCheckpoint] = (),
        verification_scores: Mapping[str, float] | None = None,
        public_reasoning_summaries: Mapping[str, str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Trajectory:
        if not isinstance(result, AgentResult):
            raise TypeError("result must be AgentResult")
        if any(not isinstance(checkpoint, RunCheckpoint) for checkpoint in checkpoints):
            raise TypeError("checkpoints must contain RunCheckpoint")
        scores = {require_id("verification id", key): probability("verification score", value) for key, value in dict(verification_scores or {}).items()}
        summaries = {require_id("summary id", key): bounded_text("summary", value, maximum=8192) for key, value in dict(public_reasoning_summaries or {}).items()}
        records: list[TrajectoryRecord] = []
        sequence = 0

        def append(kind: RecordKind, payload: Mapping[str, Any], *, parents: Sequence[str] = (), evidence: Sequence[str] = (), authoritative: bool = True, outcome: OutcomeLabel = OutcomeLabel.UNKNOWN, at: float | None = None, meta: Mapping[str, Any] | None = None) -> TrajectoryRecord:
            nonlocal sequence
            sequence += 1
            timestamp = self._clock() if at is None else float(at)
            record_id = stable_id("tr", {"run": result.run_id, "seq": sequence, "kind": kind.value, "payload": payload, "parents": tuple(parents)})
            record = TrajectoryRecord(record_id, sequence, kind, timestamp, payload, tuple(parents), tuple(evidence), authoritative, outcome, meta or {})
            records.append(record)
            return record

        meta_record = append(
            RecordKind.META,
            {
                "source": "jeeves",
                "trace_fingerprint": result.trace_fingerprint,
                "success": result.success,
                "termination_reason": result.reason.value,
                "usage": {
                    "steps": result.usage.steps,
                    "model_calls": result.usage.model_calls,
                    "tool_calls": result.usage.tool_calls,
                    "prompt_tokens": result.usage.prompt_tokens,
                    "completion_tokens": result.usage.completion_tokens,
                },
            },
            outcome=OutcomeLabel.POSITIVE if result.success else OutcomeLabel.NEGATIVE,
        )
        goal_record = append(RecordKind.GOAL, {"goal_id": result.goal_id}, parents=(meta_record.record_id,))

        checkpoint_parent = goal_record.record_id
        for checkpoint in sorted(checkpoints, key=lambda value: value.sequence):
            if checkpoint.run_id != result.run_id:
                raise TrajectoryError("checkpoint run does not match result")
            checkpoint_record = append(
                RecordKind.CHECKPOINT,
                {
                    "checkpoint_sequence": checkpoint.sequence,
                    "phase": checkpoint.phase.value,
                    "usage": {
                        "steps": checkpoint.usage.steps,
                        "model_calls": checkpoint.usage.model_calls,
                        "tool_calls": checkpoint.usage.tool_calls,
                        "tokens": checkpoint.usage.total_tokens,
                    },
                    "replans": checkpoint.replan_count,
                    "trace": checkpoint.current_trace_fingerprint,
                    "error": checkpoint.last_error,
                },
                parents=(checkpoint_parent,),
                at=checkpoint.updated_at,
                outcome=OutcomeLabel.NEGATIVE if checkpoint.last_error else OutcomeLabel.NEUTRAL,
            )
            checkpoint_parent = checkpoint_record.record_id

        step_records: dict[str, TrajectoryRecord] = {}
        if result.plan is not None:
            plan_record = append(
                RecordKind.PLAN,
                {"plan_id": result.plan.plan_id, "version": result.plan.version, "rationale": result.plan.rationale},
                parents=(checkpoint_parent,),
                outcome=OutcomeLabel.POSITIVE if result.plan.complete else OutcomeLabel.NEGATIVE if result.plan.failed else OutcomeLabel.NEUTRAL,
            )
            for step in result.plan.steps:
                parents = [plan_record.record_id]
                parents.extend(step_records[dependency].record_id for dependency in step.dependencies if dependency in step_records)
                label = OutcomeLabel.POSITIVE if step.status in {StepStatus.SUCCEEDED, StepStatus.SKIPPED} else OutcomeLabel.NEGATIVE if step.status in {StepStatus.FAILED, StepStatus.BLOCKED} else OutcomeLabel.NEUTRAL
                payload = {
                    "step_id": step.step_id,
                    "title": step.title,
                    "description": step.description,
                    "tool": step.tool,
                    "risk": step.risk.value,
                    "status": step.status.value,
                    "attempts": step.attempts,
                    "max_attempts": step.max_attempts,
                    "expected_outcome": step.expected_outcome,
                    "verification": step.verification,
                    "reasoning_summary": summaries.get(step.step_id),
                }
                step_records[step.step_id] = append(RecordKind.STEP, payload, parents=parents, outcome=label, authoritative=True)

        observation_records: dict[str, TrajectoryRecord] = {}
        for observation in result.observations:
            parent_candidates = [record.record_id for record in step_records.values() if record.payload.get("tool") == observation.tool_name]
            parent = parent_candidates[-1:] or [checkpoint_parent]
            evidence_ids = tuple(ref.evidence_id for ref in observation.evidence)
            tool_record = append(
                RecordKind.TOOL,
                {
                    "call_id": observation.call_id,
                    "tool": observation.tool_name,
                    "ok": observation.ok,
                    "payload": observation.payload,
                    "error": observation.error,
                    "latency_ms": observation.latency_ms,
                    "cached": observation.cached,
                },
                parents=parent,
                evidence=evidence_ids,
                outcome=OutcomeLabel.POSITIVE if observation.ok else OutcomeLabel.NEGATIVE,
            )
            observation_records[observation.call_id] = tool_record
            score = scores.get(observation.call_id)
            if score is not None:
                append(
                    RecordKind.VERIFICATION,
                    {"target_call_id": observation.call_id, "score": score, "passed": score >= 0.6},
                    parents=(tool_record.record_id,),
                    evidence=evidence_ids,
                    outcome=OutcomeLabel.POSITIVE if score >= 0.6 else OutcomeLabel.NEGATIVE,
                )
            for ref in observation.evidence:
                append(
                    RecordKind.EVIDENCE,
                    {
                        "evidence_id": ref.evidence_id,
                        "kind": ref.kind.value,
                        "source": ref.source,
                        "fingerprint": ref.fingerprint,
                        "confidence": ref.confidence,
                        "observed_at": ref.observed_at,
                        "uri": ref.uri,
                    },
                    parents=(tool_record.record_id,),
                    evidence=(ref.evidence_id,),
                    outcome=OutcomeLabel.POSITIVE if observation.ok else OutcomeLabel.UNKNOWN,
                )

        claim_parent = tuple(observation_records.values())[-1].record_id if observation_records else checkpoint_parent
        for claim in result.claims:
            append(
                RecordKind.CLAIM,
                {
                    "claim_id": claim.claim_id,
                    "text": claim.text,
                    "confidence": claim.confidence,
                    "derived": claim.derived,
                    "subject": claim.subject,
                },
                parents=(claim_parent,),
                evidence=tuple(ref.evidence_id for ref in claim.evidence),
                authoritative=False,
                outcome=OutcomeLabel.POSITIVE if claim.evidence else OutcomeLabel.UNKNOWN,
            )

        answer_parent = records[-1].record_id if records else checkpoint_parent
        append(
            RecordKind.ANSWER,
            {"answer": result.answer, "claim_count": len(result.claims)},
            parents=(answer_parent,),
            authoritative=False,
            outcome=OutcomeLabel.POSITIVE if result.success else OutcomeLabel.NEGATIVE,
        )
        trajectory_id = stable_id("trajectory", {"run": result.run_id, "records": [(record.record_id, record.fingerprint) for record in records]})
        return Trajectory(
            trajectory_id=trajectory_id,
            run_id=result.run_id,
            goal_id=result.goal_id,
            records=tuple(records),
            success=result.success,
            termination_reason=result.reason.value,
            created_at=self._clock(),
            metadata=metadata or {},
        )


@dataclass(frozen=True, slots=True)
class CreditConfig:
    outcome_weight: float = 0.22
    dependency_weight: float = 0.18
    verification_weight: float = 0.20
    evidence_weight: float = 0.14
    failure_weight: float = 0.10
    centrality_weight: float = 0.10
    temporal_weight: float = 0.06
    temporal_half_life_records: float = 12.0
    minimum_credit: float = -1.0
    maximum_credit: float = 1.0

    def __post_init__(self) -> None:
        names = ("outcome_weight", "dependency_weight", "verification_weight", "evidence_weight", "failure_weight", "centrality_weight", "temporal_weight")
        values = [finite_number(name, getattr(self, name)) for name in names]
        if any(value < 0 for value in values) or sum(values) <= 0:
            raise AgentContractError("credit weights must be non-negative and non-zero")
        total = sum(values)
        for name, value in zip(names, values):
            object.__setattr__(self, name, value / total)
        half_life = finite_number("temporal_half_life_records", self.temporal_half_life_records)
        if half_life <= 0:
            raise AgentContractError("temporal_half_life_records must be positive")
        object.__setattr__(self, "temporal_half_life_records", half_life)
        low = finite_number("minimum_credit", self.minimum_credit)
        high = finite_number("maximum_credit", self.maximum_credit)
        if low >= high:
            raise AgentContractError("minimum_credit must be below maximum_credit")
        object.__setattr__(self, "minimum_credit", low)
        object.__setattr__(self, "maximum_credit", high)


@dataclass(frozen=True, slots=True)
class CreditComponent:
    source: CreditSource
    value: float
    explanation: str

    def __post_init__(self) -> None:
        if not isinstance(self.source, CreditSource):
            object.__setattr__(self, "source", CreditSource(str(self.source)))
        object.__setattr__(self, "value", finite_number("credit component", self.value))
        object.__setattr__(self, "explanation", bounded_text("credit explanation", self.explanation, maximum=2048))


@dataclass(frozen=True, slots=True)
class StepCredit:
    record_id: str
    raw_credit: float
    normalized_credit: float
    confidence: float
    components: tuple[CreditComponent, ...]
    downstream_count: int
    evidence_count: int
    verification_count: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class CreditReport:
    trajectory_id: str
    success: bool
    credits: tuple[StepCredit, ...]
    positive_total: float
    negative_total: float
    unexplained_outcome_mass: float
    fingerprint: str

    def credit_for(self, record_id: str) -> StepCredit:
        record_id = require_id("record_id", record_id)
        for value in self.credits:
            if value.record_id == record_id:
                return value
        raise KeyError(record_id)


class CausalCreditAssigner:
    """Dependency-aware process credit with bounded deterministic heuristics.

    This is deliberately not claimed to be causal identification.  It is a
    transparent approximation that combines process evidence, DAG structure,
    verification, failure propagation, and proximity to the terminal outcome.
    """

    def __init__(self, config: CreditConfig | None = None) -> None:
        self.config = config or CreditConfig()

    def assign(self, trajectory: Trajectory) -> CreditReport:
        if not isinstance(trajectory, Trajectory):
            raise TypeError("trajectory must be Trajectory")
        records = [record for record in trajectory.records if record.kind in {RecordKind.STEP, RecordKind.TOOL, RecordKind.EVIDENCE, RecordKind.VERIFICATION, RecordKind.CLAIM, RecordKind.CONTROL}]
        if not records:
            return CreditReport(trajectory.trajectory_id, trajectory.success, (), 0.0, 0.0, 1.0, stable_fingerprint((trajectory.trajectory_id, "empty")))
        children = self._children(trajectory.records)
        terminal_sequence = max(record.sequence for record in trajectory.records)
        outcome_sign = 1.0 if trajectory.success else -1.0
        raw: list[tuple[TrajectoryRecord, float, list[CreditComponent], float, int, int, int]] = []
        for record in records:
            descendants = self._descendants(record.record_id, children)
            downstream_count = len(descendants)
            verification_records = [value for value in descendants if value.kind is RecordKind.VERIFICATION]
            evidence_records = [value for value in descendants if value.kind is RecordKind.EVIDENCE]
            components: list[CreditComponent] = []

            outcome = outcome_sign * self._outcome_alignment(record)
            components.append(CreditComponent(CreditSource.OUTCOME, outcome, "alignment with authoritative terminal outcome"))

            dependency = self._dependency_credit(record, descendants, trajectory.success)
            components.append(CreditComponent(CreditSource.DEPENDENCY, dependency, "downstream successful/failed dependency propagation"))

            verification = self._verification_credit(record, verification_records)
            components.append(CreditComponent(CreditSource.VERIFICATION, verification, "host verification results reachable from this record"))

            evidence = self._evidence_credit(record, evidence_records)
            components.append(CreditComponent(CreditSource.EVIDENCE, evidence, "evidence production and confidence contribution"))

            failure = self._failure_credit(record, descendants, trajectory.success)
            components.append(CreditComponent(CreditSource.FAILURE, failure, "failure and blocked-descendant attribution"))

            centrality = self._centrality_credit(record, downstream_count, len(trajectory.records))
            components.append(CreditComponent(CreditSource.CENTRALITY, centrality, "causal-graph reachability centrality"))

            distance = max(0, terminal_sequence - record.sequence)
            temporal = outcome_sign * math.exp(-math.log(2) * distance / self.config.temporal_half_life_records)
            components.append(CreditComponent(CreditSource.TEMPORAL, temporal, "temporal proximity to terminal outcome"))

            weighted = (
                outcome * self.config.outcome_weight
                + dependency * self.config.dependency_weight
                + verification * self.config.verification_weight
                + evidence * self.config.evidence_weight
                + failure * self.config.failure_weight
                + centrality * self.config.centrality_weight * outcome_sign
                + temporal * self.config.temporal_weight
            )
            weighted = max(self.config.minimum_credit, min(self.config.maximum_credit, weighted))
            confidence = self._credit_confidence(record, verification_records, evidence_records, downstream_count)
            raw.append((record, weighted, components, confidence, downstream_count, len(evidence_records), len(verification_records)))

        scale = max(1.0, sum(abs(item[1]) for item in raw))
        credits: list[StepCredit] = []
        for record, value, components, confidence, downstream, evidence_count, verification_count in raw:
            normalized = value / scale
            fingerprint = stable_fingerprint(
                {
                    "trajectory": trajectory.trajectory_id,
                    "record": record.record_id,
                    "raw": value,
                    "normalized": normalized,
                    "confidence": confidence,
                    "components": [(item.source.value, item.value) for item in components],
                }
            )
            credits.append(StepCredit(record.record_id, value, normalized, confidence, tuple(components), downstream, evidence_count, verification_count, fingerprint))
        positive = sum(max(0.0, item.raw_credit) for item in credits)
        negative = sum(min(0.0, item.raw_credit) for item in credits)
        explained = min(1.0, sum(abs(item.normalized_credit) * item.confidence for item in credits))
        report_fp = stable_fingerprint((trajectory.trajectory_id, trajectory.success, [(item.record_id, item.fingerprint) for item in credits]))
        return CreditReport(trajectory.trajectory_id, trajectory.success, tuple(credits), positive, negative, max(0.0, 1.0 - explained), report_fp)

    @staticmethod
    def _children(records: Sequence[TrajectoryRecord]) -> Mapping[str, tuple[TrajectoryRecord, ...]]:
        mapping: dict[str, list[TrajectoryRecord]] = defaultdict(list)
        for record in records:
            for parent in record.parent_ids:
                mapping[parent].append(record)
        return {key: tuple(sorted(values, key=lambda item: item.sequence)) for key, values in mapping.items()}

    @staticmethod
    def _descendants(record_id: str, children: Mapping[str, Sequence[TrajectoryRecord]]) -> tuple[TrajectoryRecord, ...]:
        result: list[TrajectoryRecord] = []
        seen: set[str] = set()
        queue = deque(children.get(record_id, ()))
        while queue:
            current = queue.popleft()
            if current.record_id in seen:
                continue
            seen.add(current.record_id)
            result.append(current)
            queue.extend(children.get(current.record_id, ()))
        return tuple(result)

    @staticmethod
    def _outcome_alignment(record: TrajectoryRecord) -> float:
        if record.outcome is OutcomeLabel.POSITIVE:
            return 1.0
        if record.outcome is OutcomeLabel.NEGATIVE:
            return -1.0
        if record.outcome is OutcomeLabel.NEUTRAL:
            return 0.1
        return 0.0

    @staticmethod
    def _dependency_credit(record: TrajectoryRecord, descendants: Sequence[TrajectoryRecord], success: bool) -> float:
        if not descendants:
            return 0.0
        positive = sum(1 for child in descendants if child.outcome is OutcomeLabel.POSITIVE)
        negative = sum(1 for child in descendants if child.outcome is OutcomeLabel.NEGATIVE)
        total = positive + negative
        if not total:
            return 0.0
        balance = (positive - negative) / total
        return balance if success else -balance

    @staticmethod
    def _verification_credit(record: TrajectoryRecord, verifications: Sequence[TrajectoryRecord]) -> float:
        if record.kind is RecordKind.VERIFICATION:
            score = record.payload.get("score")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                return max(-1.0, min(1.0, float(score) * 2.0 - 1.0))
        if not verifications:
            return 0.0
        values: list[float] = []
        for item in verifications:
            score = item.payload.get("score")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                values.append(float(score) * 2.0 - 1.0)
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _evidence_credit(record: TrajectoryRecord, evidence_records: Sequence[TrajectoryRecord]) -> float:
        if record.kind is RecordKind.EVIDENCE:
            confidence = record.payload.get("confidence", 0.0)
            return max(0.0, min(1.0, float(confidence))) if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else 0.0
        if not evidence_records:
            return 0.0
        confidences = [float(item.payload.get("confidence", 0.0)) for item in evidence_records if isinstance(item.payload.get("confidence"), (int, float)) and not isinstance(item.payload.get("confidence"), bool)]
        if not confidences:
            return min(1.0, len(evidence_records) / 4.0)
        return min(1.0, sum(confidences) / max(1.0, len(confidences)))

    @staticmethod
    def _failure_credit(record: TrajectoryRecord, descendants: Sequence[TrajectoryRecord], success: bool) -> float:
        failed = sum(1 for item in descendants if item.outcome is OutcomeLabel.NEGATIVE)
        if record.outcome is OutcomeLabel.NEGATIVE:
            failed += 1
        if not failed:
            return 0.0
        penalty = -min(1.0, failed / max(1, len(descendants) + 1))
        return penalty if not success else penalty * 0.5

    @staticmethod
    def _centrality_credit(record: TrajectoryRecord, downstream_count: int, total_records: int) -> float:
        if total_records <= 1:
            return 0.0
        return min(1.0, downstream_count / (total_records - 1))

    @staticmethod
    def _credit_confidence(record: TrajectoryRecord, verifications: Sequence[TrajectoryRecord], evidence: Sequence[TrajectoryRecord], downstream_count: int) -> float:
        confidence = 0.20
        if record.authoritative:
            confidence += 0.20
        if verifications:
            confidence += min(0.30, 0.12 * len(verifications))
        if evidence or record.evidence_ids:
            confidence += min(0.20, 0.06 * (len(evidence) + len(record.evidence_ids)))
        if downstream_count:
            confidence += min(0.10, downstream_count / 100.0)
        return min(1.0, confidence)


@dataclass(frozen=True, slots=True)
class ReplaySignature:
    trajectory_id: str
    trajectory_fingerprint: str
    plan_fingerprint: str | None
    tool_sequence_fingerprint: str
    evidence_fingerprint: str
    terminal_fingerprint: str


class ReplayAuditor:
    """Produce and compare deterministic replay signatures without raw secrets."""

    def signature(self, trajectory: Trajectory) -> ReplaySignature:
        plan_records = trajectory.records_of(RecordKind.PLAN, RecordKind.STEP)
        tool_records = trajectory.records_of(RecordKind.TOOL)
        evidence_records = trajectory.records_of(RecordKind.EVIDENCE)
        terminal_records = trajectory.records[-3:]
        return ReplaySignature(
            trajectory_id=trajectory.trajectory_id,
            trajectory_fingerprint=trajectory.fingerprint,
            plan_fingerprint=stable_fingerprint([(record.kind.value, record.payload) for record in plan_records]) if plan_records else None,
            tool_sequence_fingerprint=stable_fingerprint([(record.payload.get("tool"), record.payload.get("ok"), record.payload.get("cached")) for record in tool_records]),
            evidence_fingerprint=stable_fingerprint([(record.payload.get("evidence_id"), record.payload.get("fingerprint")) for record in evidence_records]),
            terminal_fingerprint=stable_fingerprint([(record.kind.value, record.outcome.value, record.payload) for record in terminal_records]),
        )

    def compare(self, left: Trajectory, right: Trajectory) -> Mapping[str, Any]:
        a = self.signature(left)
        b = self.signature(right)
        return {
            "exact": a.trajectory_fingerprint == b.trajectory_fingerprint,
            "plan_equal": a.plan_fingerprint == b.plan_fingerprint,
            "tool_sequence_equal": a.tool_sequence_fingerprint == b.tool_sequence_fingerprint,
            "evidence_equal": a.evidence_fingerprint == b.evidence_fingerprint,
            "terminal_equal": a.terminal_fingerprint == b.terminal_fingerprint,
            "left": a.trajectory_fingerprint,
            "right": b.trajectory_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ExperienceQuery:
    goal_tokens: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    termination_reasons: tuple[str, ...] = ()
    success: bool | None = None
    minimum_similarity: float = 0.0
    limit: int = 8

    def __post_init__(self) -> None:
        object.__setattr__(self, "goal_tokens", tuple(sorted(set(str(value).casefold() for value in self.goal_tokens if str(value).strip()))))
        object.__setattr__(self, "tools", tuple(sorted(set(str(value).casefold() for value in self.tools if str(value).strip()))))
        object.__setattr__(self, "termination_reasons", tuple(sorted(set(str(value) for value in self.termination_reasons if str(value).strip()))))
        object.__setattr__(self, "minimum_similarity", probability("minimum_similarity", self.minimum_similarity))
        object.__setattr__(self, "limit", positive_int("limit", self.limit, maximum=1000))


@dataclass(frozen=True, slots=True)
class ExperienceHit:
    trajectory: Trajectory
    similarity: float
    goal_similarity: float
    tool_similarity: float
    outcome_match: float


class ExperienceStore:
    """Thread-safe bounded trajectory store with lightweight retrieval index."""

    def __init__(self, *, max_trajectories: int = 10_000) -> None:
        self.max_trajectories = positive_int("max_trajectories", max_trajectories, maximum=1_000_000)
        self._trajectories: dict[str, Trajectory] = {}
        self._run_to_id: dict[str, str] = {}
        self._insert_order: deque[str] = deque()
        self._lock = threading.RLock()

    def put(self, trajectory: Trajectory) -> Trajectory:
        if not isinstance(trajectory, Trajectory):
            raise TypeError("trajectory must be Trajectory")
        with self._lock:
            existing_id = self._run_to_id.get(trajectory.run_id)
            if existing_id is not None:
                existing = self._trajectories[existing_id]
                if existing.fingerprint != trajectory.fingerprint:
                    raise TrajectoryError("run id already has a different trajectory")
                return existing
            self._trajectories[trajectory.trajectory_id] = trajectory
            self._run_to_id[trajectory.run_id] = trajectory.trajectory_id
            self._insert_order.append(trajectory.trajectory_id)
            while len(self._trajectories) > self.max_trajectories:
                victim = self._insert_order.popleft()
                value = self._trajectories.pop(victim, None)
                if value is not None:
                    self._run_to_id.pop(value.run_id, None)
        return trajectory

    def get(self, trajectory_id: str) -> Trajectory | None:
        with self._lock:
            return self._trajectories.get(require_id("trajectory_id", trajectory_id))

    def by_run(self, run_id: str) -> Trajectory | None:
        run_id = require_id("run_id", run_id)
        with self._lock:
            trajectory_id = self._run_to_id.get(run_id)
            return self._trajectories.get(trajectory_id) if trajectory_id else None

    def search(self, query: ExperienceQuery) -> tuple[ExperienceHit, ...]:
        if not isinstance(query, ExperienceQuery):
            raise TypeError("query must be ExperienceQuery")
        with self._lock:
            values = tuple(self._trajectories.values())
        hits: list[ExperienceHit] = []
        for trajectory in values:
            if query.success is not None and trajectory.success is not query.success:
                continue
            if query.termination_reasons and trajectory.termination_reason not in query.termination_reasons:
                continue
            goal_terms = self._goal_terms(trajectory)
            tool_terms = self._tool_terms(trajectory)
            goal_score = self._jaccard(set(query.goal_tokens), goal_terms) if query.goal_tokens else 0.5
            tool_score = self._jaccard(set(query.tools), tool_terms) if query.tools else 0.5
            outcome_match = 1.0 if query.success is None or trajectory.success is query.success else 0.0
            score = goal_score * 0.55 + tool_score * 0.30 + outcome_match * 0.15
            if score >= query.minimum_similarity:
                hits.append(ExperienceHit(trajectory, score, goal_score, tool_score, outcome_match))
        hits.sort(key=lambda item: (item.similarity, item.trajectory.created_at, item.trajectory.trajectory_id), reverse=True)
        return tuple(hits[: query.limit])

    @staticmethod
    def _goal_terms(trajectory: Trajectory) -> set[str]:
        terms: set[str] = {trajectory.goal_id.casefold()}
        for record in trajectory.records_of(RecordKind.GOAL, RecordKind.PLAN, RecordKind.STEP):
            for value in record.payload.values():
                if isinstance(value, str):
                    terms.update(token.casefold() for token in value.replace("/", " ").replace("_", " ").split() if token)
        return terms

    @staticmethod
    def _tool_terms(trajectory: Trajectory) -> set[str]:
        return {str(record.payload.get("tool", "")).casefold() for record in trajectory.records_of(RecordKind.TOOL) if record.payload.get("tool")}

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        if not left and not right:
            return 1.0
        union = left | right
        return len(left & right) / len(union) if union else 0.0

    @property
    def fingerprint(self) -> str:
        with self._lock:
            return stable_fingerprint(sorted((trajectory.trajectory_id, trajectory.fingerprint) for trajectory in self._trajectories.values()))


@dataclass(frozen=True, slots=True)
class LessonCandidate:
    lesson_id: str
    statement: str
    confidence: float
    support_trajectory_ids: tuple[str, ...]
    opposing_trajectory_ids: tuple[str, ...]
    average_credit: float
    scope_key: str
    promote: bool
    fingerprint: str


@dataclass(frozen=True, slots=True)
class LessonPolicy:
    minimum_support_runs: int = 3
    minimum_confidence: float = 0.72
    minimum_average_credit: float = 0.10
    maximum_opposition_fraction: float = 0.25

    def __post_init__(self) -> None:
        object.__setattr__(self, "minimum_support_runs", positive_int("minimum_support_runs", self.minimum_support_runs, maximum=100_000))
        object.__setattr__(self, "minimum_confidence", probability("minimum_confidence", self.minimum_confidence))
        value = finite_number("minimum_average_credit", self.minimum_average_credit)
        if not -1 <= value <= 1:
            raise AgentContractError("minimum_average_credit must be in [-1,1]")
        object.__setattr__(self, "minimum_average_credit", value)
        object.__setattr__(self, "maximum_opposition_fraction", probability("maximum_opposition_fraction", self.maximum_opposition_fraction))


class TrajectoryLearner:
    """Extract conservative, auditable lesson candidates from repeated experience."""

    def __init__(self, assigner: CausalCreditAssigner | None = None, policy: LessonPolicy | None = None) -> None:
        self.assigner = assigner or CausalCreditAssigner()
        self.policy = policy or LessonPolicy()

    def extract(self, trajectories: Sequence[Trajectory]) -> tuple[LessonCandidate, ...]:
        reports = {trajectory.trajectory_id: self.assigner.assign(trajectory) for trajectory in trajectories}
        buckets: dict[str, list[tuple[Trajectory, TrajectoryRecord, StepCredit]]] = defaultdict(list)
        for trajectory in trajectories:
            report = reports[trajectory.trajectory_id]
            by_record = {credit.record_id: credit for credit in report.credits}
            for record in trajectory.records_of(RecordKind.TOOL, RecordKind.STEP):
                credit = by_record.get(record.record_id)
                if credit is None:
                    continue
                key = self._scope_key(record)
                buckets[key].append((trajectory, record, credit))
        candidates: list[LessonCandidate] = []
        for scope_key, examples in buckets.items():
            support = [item for item in examples if item[2].raw_credit >= self.policy.minimum_average_credit]
            opposition = [item for item in examples if item[2].raw_credit <= -self.policy.minimum_average_credit]
            if len(support) < self.policy.minimum_support_runs:
                continue
            unique_support_runs = tuple(sorted({item[0].trajectory_id for item in support}))
            unique_opposition_runs = tuple(sorted({item[0].trajectory_id for item in opposition}))
            average_credit = sum(item[2].raw_credit for item in support) / len(support)
            mean_credit_confidence = sum(item[2].confidence for item in support) / len(support)
            support_fraction = len(support) / max(1, len(examples))
            opposition_fraction = len(opposition) / max(1, len(examples))
            confidence = max(0.0, min(1.0, mean_credit_confidence * 0.55 + support_fraction * 0.45))
            record = support[0][1]
            statement = self._lesson_statement(record, average_credit, len(unique_support_runs))
            promote = (
                confidence >= self.policy.minimum_confidence
                and opposition_fraction <= self.policy.maximum_opposition_fraction
                and average_credit >= self.policy.minimum_average_credit
            )
            payload = {
                "scope": scope_key,
                "statement": statement,
                "support": unique_support_runs,
                "opposition": unique_opposition_runs,
                "average_credit": average_credit,
                "confidence": confidence,
                "promote": promote,
            }
            lesson_id = stable_id("lesson", payload)
            candidates.append(
                LessonCandidate(
                    lesson_id,
                    statement,
                    confidence,
                    unique_support_runs,
                    unique_opposition_runs,
                    average_credit,
                    scope_key,
                    promote,
                    stable_fingerprint(payload),
                )
            )
        candidates.sort(key=lambda item: (item.promote, item.confidence, item.average_credit, len(item.support_trajectory_ids)), reverse=True)
        return tuple(candidates)

    @staticmethod
    def _scope_key(record: TrajectoryRecord) -> str:
        if record.kind is RecordKind.TOOL:
            return f"tool:{record.payload.get('tool', 'unknown')}"
        return f"step:{record.payload.get('title', record.payload.get('step_id', 'unknown'))}"

    @staticmethod
    def _lesson_statement(record: TrajectoryRecord, average_credit: float, support_runs: int) -> str:
        if record.kind is RecordKind.TOOL:
            tool = record.payload.get("tool", "unknown")
            return f"Using tool {tool} in matching contexts has repeatedly produced verified positive contribution (mean credit {average_credit:.3f} across {support_runs} runs)."
        title = record.payload.get("title", record.payload.get("step_id", "step"))
        return f"Strategy step {title!r} has repeatedly contributed positively in matching trajectories (mean credit {average_credit:.3f} across {support_runs} runs)."


@dataclass(frozen=True, slots=True)
class ProcessDatasetRow:
    trajectory_id: str
    record_id: str
    kind: str
    input_fingerprint: str
    target_credit: float
    confidence: float
    terminal_success: bool
    features: Mapping[str, Any]


class ProcessDatasetBuilder:
    """Create model-agnostic step-level supervision rows from audited trajectories."""

    def __init__(self, assigner: CausalCreditAssigner | None = None) -> None:
        self.assigner = assigner or CausalCreditAssigner()

    def build(self, trajectories: Sequence[Trajectory]) -> tuple[ProcessDatasetRow, ...]:
        rows: list[ProcessDatasetRow] = []
        for trajectory in trajectories:
            report = self.assigner.assign(trajectory)
            by_record = {credit.record_id: credit for credit in report.credits}
            for record in trajectory.records:
                credit = by_record.get(record.record_id)
                if credit is None:
                    continue
                features = {
                    "sequence_fraction": record.sequence / max(1, len(trajectory.records)),
                    "authoritative": record.authoritative,
                    "parent_count": len(record.parent_ids),
                    "evidence_count": len(record.evidence_ids),
                    "outcome": record.outcome.value,
                    "downstream_count": credit.downstream_count,
                    "verification_count": credit.verification_count,
                    "kind": record.kind.value,
                }
                rows.append(
                    ProcessDatasetRow(
                        trajectory.trajectory_id,
                        record.record_id,
                        record.kind.value,
                        stable_fingerprint({"payload": record.payload, "parents": record.parent_ids, "evidence": record.evidence_ids}),
                        credit.raw_credit,
                        credit.confidence,
                        trajectory.success,
                        json_safe(features),
                    )
                )
        return tuple(rows)
