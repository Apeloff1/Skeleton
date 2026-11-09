"""Live supervisor for long-horizon Jeeves execution.

This module deliberately combines several durable ideas from classical and
modern AI without pretending they are the same formalism:

* BDI-style desires and intentions provide commitment and multi-goal control.
* Belief-state summaries preserve partial observability instead of collapsing
  the world to a single guessed state.
* Options/temporal abstraction make long-running skills interruptible and
  reusable while retaining explicit initiation/termination semantics.
* A blackboard event space allows narrow specialists to publish observations
  without giving them shared mutable authority over execution.
* A deterministic supervisor observes worker progress and may continue,
  redirect, pause, replan, seek information, request confirmation, or abort.

The supervisor is a control layer, not a second autonomous model.  It never
executes tools, grants capabilities, fabricates evidence, or marks external work
successful.  Interventions are derived from typed host signals and remain fully
auditable.
"""

from __future__ import annotations

import math
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

from .action_model import ContextSignature, SkillLibrary
from .evidence import EvidenceArtifact, EvidenceLedger
from .types import (
    AgentContractError,
    AgentPhase,
    Budget,
    EvidenceRef,
    Plan,
    PlanStep,
    RiskTier,
    StepStatus,
    Usage,
    bounded_text,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)
from .world_model import BeliefGraph


class SupervisorError(RuntimeError):
    pass


class CommitmentPolicy(str, Enum):
    """How readily an adopted intention is reconsidered."""

    BLIND = "blind"
    SINGLE_MINDED = "single_minded"
    OPEN_MINDED = "open_minded"
    EVIDENCE_SENSITIVE = "evidence_sensitive"


class IntentionStatus(str, Enum):
    PROPOSED = "proposed"
    ADOPTED = "adopted"
    ACTIVE = "active"
    SATISFIED = "satisfied"
    SUSPENDED = "suspended"
    DROPPED = "dropped"
    FAILED = "failed"


class DesireStatus(str, Enum):
    CANDIDATE = "candidate"
    ELIGIBLE = "eligible"
    ADOPTED = "adopted"
    BLOCKED = "blocked"
    SATISFIED = "satisfied"
    ABANDONED = "abandoned"


class InterventionKind(str, Enum):
    CONTINUE = "continue"
    REDIRECT = "redirect"
    PAUSE = "pause"
    REPLAN = "replan"
    SEEK_INFORMATION = "seek_information"
    VERIFY = "verify"
    REQUEST_CONFIRMATION = "request_confirmation"
    SUSPEND_INTENTION = "suspend_intention"
    SWITCH_INTENTION = "switch_intention"
    ABORT_OPTION = "abort_option"
    ABORT_RUN = "abort_run"


class BlackboardTopic(str, Enum):
    PERCEPT = "percept"
    EVIDENCE = "evidence"
    HYPOTHESIS = "hypothesis"
    PLAN = "plan"
    ACTION = "action"
    VERIFICATION = "verification"
    RISK = "risk"
    CONTRADICTION = "contradiction"
    PROGRESS = "progress"
    FAILURE = "failure"
    CONTROL = "control"
    RESOURCE = "resource"


class OptionStatus(str, Enum):
    DORMANT = "dormant"
    ELIGIBLE = "eligible"
    RUNNING = "running"
    TERMINATED = "terminated"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Desire:
    desire_id: str
    objective: str
    utility: float = 0.5
    urgency: float = 0.5
    confidence: float = 0.5
    risk_tolerance: RiskTier = RiskTier.READ_ONLY
    dependencies: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    deadline_at: float | None = None
    status: DesireStatus = DesireStatus.CANDIDATE
    source: str = "runtime"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "desire_id", require_id("desire_id", self.desire_id))
        object.__setattr__(self, "objective", bounded_text("objective", self.objective, maximum=16_384))
        for name in ("utility", "urgency", "confidence"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        if not isinstance(self.risk_tolerance, RiskTier):
            object.__setattr__(self, "risk_tolerance", RiskTier(str(self.risk_tolerance)))
        object.__setattr__(self, "dependencies", tuple(require_id("dependency", item) for item in self.dependencies))
        object.__setattr__(self, "conflicts", tuple(require_id("conflict", item) for item in self.conflicts))
        if self.desire_id in self.dependencies or self.desire_id in self.conflicts:
            raise AgentContractError("desire cannot depend on or conflict with itself")
        if self.deadline_at is not None:
            deadline = finite_number("deadline_at", self.deadline_at)
            if deadline < 0:
                raise AgentContractError("deadline_at must be non-negative")
            object.__setattr__(self, "deadline_at", deadline)
        if not isinstance(self.status, DesireStatus):
            object.__setattr__(self, "status", DesireStatus(str(self.status)))
        object.__setattr__(self, "source", bounded_text("source", self.source, maximum=1024))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "objective": self.objective,
                "utility": self.utility,
                "urgency": self.urgency,
                "confidence": self.confidence,
                "risk": self.risk_tolerance.value,
                "dependencies": self.dependencies,
                "conflicts": self.conflicts,
                "deadline": self.deadline_at,
                "status": self.status.value,
            }
        )


@dataclass(frozen=True, slots=True)
class Intention:
    intention_id: str
    desire_id: str
    objective: str
    adopted_at: float
    commitment: CommitmentPolicy = CommitmentPolicy.EVIDENCE_SENSITIVE
    status: IntentionStatus = IntentionStatus.ADOPTED
    priority: float = 0.5
    minimum_progress: float = 0.01
    reconsider_after_failures: int = 2
    maximum_stagnant_cycles: int = 4
    protected_until: float | None = None
    plan_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "intention_id", require_id("intention_id", self.intention_id))
        object.__setattr__(self, "desire_id", require_id("desire_id", self.desire_id))
        object.__setattr__(self, "objective", bounded_text("objective", self.objective, maximum=16_384))
        adopted = finite_number("adopted_at", self.adopted_at)
        if adopted < 0:
            raise AgentContractError("adopted_at must be non-negative")
        object.__setattr__(self, "adopted_at", adopted)
        if not isinstance(self.commitment, CommitmentPolicy):
            object.__setattr__(self, "commitment", CommitmentPolicy(str(self.commitment)))
        if not isinstance(self.status, IntentionStatus):
            object.__setattr__(self, "status", IntentionStatus(str(self.status)))
        object.__setattr__(self, "priority", probability("priority", self.priority))
        object.__setattr__(self, "minimum_progress", probability("minimum_progress", self.minimum_progress))
        object.__setattr__(self, "reconsider_after_failures", positive_int("reconsider_after_failures", self.reconsider_after_failures, maximum=1000))
        object.__setattr__(self, "maximum_stagnant_cycles", positive_int("maximum_stagnant_cycles", self.maximum_stagnant_cycles, maximum=1000))
        if self.protected_until is not None:
            protected = finite_number("protected_until", self.protected_until)
            if protected < adopted:
                raise AgentContractError("protected_until predates adoption")
            object.__setattr__(self, "protected_until", protected)
        if self.plan_id is not None:
            object.__setattr__(self, "plan_id", require_id("plan_id", self.plan_id))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class BlackboardEvent:
    event_id: str
    run_id: str
    topic: BlackboardTopic
    producer: str
    payload: Mapping[str, Any]
    created_at: float
    confidence: float = 1.0
    evidence: tuple[EvidenceRef, ...] = ()
    causal_parent_ids: tuple[str, ...] = ()
    ttl_seconds: float | None = None
    priority: float = 0.5

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", require_id("event_id", self.event_id))
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        if not isinstance(self.topic, BlackboardTopic):
            object.__setattr__(self, "topic", BlackboardTopic(str(self.topic)))
        object.__setattr__(self, "producer", require_id("producer", self.producer))
        object.__setattr__(self, "payload", json_safe(dict(self.payload)))
        created = finite_number("created_at", self.created_at)
        if created < 0:
            raise AgentContractError("created_at must be non-negative")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "confidence", probability("confidence", self.confidence))
        refs = tuple(self.evidence)
        if any(not isinstance(ref, EvidenceRef) for ref in refs):
            raise AgentContractError("blackboard evidence must contain EvidenceRef")
        object.__setattr__(self, "evidence", refs)
        parents = tuple(require_id("causal_parent_id", item) for item in self.causal_parent_ids)
        if self.event_id in parents:
            raise AgentContractError("blackboard event cannot parent itself")
        object.__setattr__(self, "causal_parent_ids", parents)
        if self.ttl_seconds is not None:
            ttl = finite_number("ttl_seconds", self.ttl_seconds)
            if ttl <= 0:
                raise AgentContractError("ttl_seconds must be positive")
            object.__setattr__(self, "ttl_seconds", ttl)
        object.__setattr__(self, "priority", probability("priority", self.priority))

    def expired(self, now: float) -> bool:
        return self.ttl_seconds is not None and now >= self.created_at + self.ttl_seconds


class Blackboard:
    """Append-only event board with bounded indexes and causal lookup."""

    def __init__(self, *, max_events: int = 50_000, clock: Callable[[], float] = time.time) -> None:
        self.max_events = positive_int("max_events", max_events, maximum=5_000_000)
        self._clock = clock
        self._events: dict[str, BlackboardEvent] = {}
        self._by_run: dict[str, list[str]] = defaultdict(list)
        self._by_topic: dict[BlackboardTopic, list[str]] = defaultdict(list)
        self._children: dict[str, set[str]] = defaultdict(set)
        self._lock = threading.RLock()

    def publish(self, event: BlackboardEvent) -> BlackboardEvent:
        if not isinstance(event, BlackboardEvent):
            raise TypeError("event must be BlackboardEvent")
        with self._lock:
            prior = self._events.get(event.event_id)
            if prior is not None:
                if stable_fingerprint(prior.payload) != stable_fingerprint(event.payload):
                    raise SupervisorError("blackboard event id collision")
                return prior
            if len(self._events) >= self.max_events:
                raise SupervisorError("blackboard capacity exhausted")
            missing = [parent for parent in event.causal_parent_ids if parent not in self._events]
            if missing:
                raise SupervisorError(f"blackboard causal parents missing: {missing}")
            self._events[event.event_id] = event
            self._by_run[event.run_id].append(event.event_id)
            self._by_topic[event.topic].append(event.event_id)
            for parent in event.causal_parent_ids:
                self._children[parent].add(event.event_id)
            return event

    def emit(
        self,
        *,
        run_id: str,
        topic: BlackboardTopic,
        producer: str,
        payload: Mapping[str, Any],
        confidence: float = 1.0,
        evidence: Sequence[EvidenceRef] = (),
        causal_parent_ids: Sequence[str] = (),
        ttl_seconds: float | None = None,
        priority: float = 0.5,
    ) -> BlackboardEvent:
        now = self._clock()
        normalized = json_safe(dict(payload))
        event_id = stable_id(
            "bbevent",
            {
                "run": run_id,
                "topic": topic.value if isinstance(topic, BlackboardTopic) else str(topic),
                "producer": producer,
                "payload": normalized,
                "parents": tuple(causal_parent_ids),
                "at": now,
            },
        )
        return self.publish(
            BlackboardEvent(
                event_id=event_id,
                run_id=run_id,
                topic=topic,
                producer=producer,
                payload=normalized,
                created_at=now,
                confidence=confidence,
                evidence=tuple(evidence),
                causal_parent_ids=tuple(causal_parent_ids),
                ttl_seconds=ttl_seconds,
                priority=priority,
            )
        )

    def query(
        self,
        *,
        run_id: str | None = None,
        topics: Sequence[BlackboardTopic] | None = None,
        since: float | None = None,
        minimum_confidence: float = 0.0,
        limit: int = 100,
        include_expired: bool = False,
    ) -> tuple[BlackboardEvent, ...]:
        minimum_confidence = probability("minimum_confidence", minimum_confidence)
        limit = positive_int("limit", limit, maximum=100_000)
        now = self._clock()
        topic_set = None if topics is None else {topic if isinstance(topic, BlackboardTopic) else BlackboardTopic(str(topic)) for topic in topics}
        with self._lock:
            if run_id is not None:
                ids = list(self._by_run.get(require_id("run_id", run_id), ()))
            else:
                ids = list(self._events)
            values = [self._events[item] for item in ids]
        if topic_set is not None:
            values = [event for event in values if event.topic in topic_set]
        if since is not None:
            since_value = finite_number("since", since)
            values = [event for event in values if event.created_at >= since_value]
        values = [event for event in values if event.confidence >= minimum_confidence]
        if not include_expired:
            values = [event for event in values if not event.expired(now)]
        values.sort(key=lambda event: (event.priority, event.created_at, event.event_id), reverse=True)
        return tuple(values[:limit])

    def descendants(self, event_id: str, *, limit: int = 1000) -> tuple[BlackboardEvent, ...]:
        event_id = require_id("event_id", event_id)
        limit = positive_int("limit", limit, maximum=100_000)
        with self._lock:
            if event_id not in self._events:
                raise SupervisorError(f"unknown event: {event_id}")
            queue = list(self._children.get(event_id, ()))
            seen: set[str] = set()
            values: list[BlackboardEvent] = []
            while queue and len(values) < limit:
                current = queue.pop(0)
                if current in seen:
                    continue
                seen.add(current)
                values.append(self._events[current])
                queue.extend(sorted(self._children.get(current, ())))
        return tuple(values)

    def fingerprint(self, *, run_id: str | None = None) -> str:
        events = self.query(run_id=run_id, limit=self.max_events, include_expired=True)
        return stable_fingerprint(
            [
                (
                    event.event_id,
                    event.topic.value,
                    event.producer,
                    stable_fingerprint(event.payload),
                    tuple(ref.evidence_id for ref in event.evidence),
                )
                for event in reversed(events)
            ]
        )


@dataclass(frozen=True, slots=True)
class BeliefParticle:
    state_id: str
    probability: float
    evidence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_id", require_id("state_id", self.state_id))
        object.__setattr__(self, "probability", probability("probability", self.probability))
        object.__setattr__(self, "evidence_ids", tuple(require_id("evidence_id", item) for item in self.evidence_ids))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class BeliefStateSummary:
    particles: tuple[BeliefParticle, ...]
    entropy_bits: float
    maximum_probability: float
    effective_states: float
    unknown_mass: float
    contradiction_pressure: float
    information_gain_candidates: tuple[str, ...] = ()
    fingerprint: str = ""

    def __post_init__(self) -> None:
        particles = tuple(self.particles)
        if any(not isinstance(item, BeliefParticle) for item in particles):
            raise AgentContractError("particles must contain BeliefParticle")
        mass = sum(item.probability for item in particles)
        unknown = probability("unknown_mass", self.unknown_mass)
        if mass + unknown > 1.000001:
            raise AgentContractError("belief probability mass exceeds one")
        object.__setattr__(self, "particles", particles)
        entropy = finite_number("entropy_bits", self.entropy_bits)
        if entropy < 0:
            raise AgentContractError("entropy_bits must be non-negative")
        object.__setattr__(self, "entropy_bits", entropy)
        object.__setattr__(self, "maximum_probability", probability("maximum_probability", self.maximum_probability))
        effective = finite_number("effective_states", self.effective_states)
        if effective < 0:
            raise AgentContractError("effective_states must be non-negative")
        object.__setattr__(self, "effective_states", effective)
        object.__setattr__(self, "unknown_mass", unknown)
        object.__setattr__(self, "contradiction_pressure", probability("contradiction_pressure", self.contradiction_pressure))
        object.__setattr__(self, "information_gain_candidates", tuple(require_id("information_gain_candidate", item) for item in self.information_gain_candidates))
        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                stable_fingerprint(
                    {
                        "particles": [(item.state_id, item.probability, item.evidence_ids) for item in particles],
                        "unknown": unknown,
                        "contradiction": self.contradiction_pressure,
                    }
                ),
            )

    @property
    def uncertain(self) -> bool:
        return self.entropy_bits > 0.8 or self.maximum_probability < 0.65 or self.unknown_mass > 0.25


class BeliefStateProjector:
    """Project a rich BeliefGraph into a compact decision-facing distribution.

    This is not a generic POMDP solver.  It provides a normalized uncertainty
    interface so the supervisor can reason about ambiguity explicitly.
    """

    def __init__(self, *, maximum_particles: int = 16) -> None:
        self.maximum_particles = positive_int("maximum_particles", maximum_particles, maximum=1024)

    def project(self, graph: BeliefGraph | None) -> BeliefStateSummary:
        if graph is None:
            return BeliefStateSummary((), 0.0, 0.0, 0.0, 1.0, 0.0, ())
        beliefs = list(graph.beliefs())
        if not beliefs:
            return BeliefStateSummary((), 0.0, 0.0, 0.0, 1.0, 0.0, ())
        ranked = sorted(
            beliefs,
            key=lambda belief: (abs(belief.probability - 0.5), belief.probability, belief.proposition_id),
            reverse=True,
        )[: self.maximum_particles]
        raw = [max(1e-9, belief.probability) for belief in ranked]
        total = sum(raw)
        # Reserve probability mass for unrepresented or unknown states rather
        # than pretending the retained particles form a complete partition.
        represented_mass = min(0.95, 0.55 + 0.40 * min(1.0, len(ranked) / self.maximum_particles))
        particles = tuple(
            BeliefParticle(
                state_id=belief.proposition_id,
                probability=represented_mass * weight / total,
                evidence_ids=tuple(sorted(set(belief.supporting_evidence_ids) | set(belief.refuting_evidence_ids))),
                metadata={
                    "subject": belief.proposition.subject,
                    "predicate": belief.proposition.predicate,
                    "polarity": belief.proposition.polarity,
                },
            )
            for belief, weight in zip(ranked, raw)
        )
        unknown = max(0.0, 1.0 - sum(item.probability for item in particles))
        probs = [item.probability for item in particles if item.probability > 0]
        if unknown > 0:
            probs.append(unknown)
        entropy = -sum(value * math.log2(value) for value in probs if value > 0)
        effective = 2 ** entropy if entropy else 1.0
        contradiction = max((graph.contradiction_pressure(belief.proposition_id) for belief in ranked), default=0.0)
        probes = graph.ranked_probes(limit=8, minimum_entropy_bits=0.05)
        return BeliefStateSummary(
            particles=particles,
            entropy_bits=entropy,
            maximum_probability=max((item.probability for item in particles), default=0.0),
            effective_states=effective,
            unknown_mass=unknown,
            contradiction_pressure=contradiction,
            information_gain_candidates=tuple(probe.proposition_id for probe in probes),
        )


@dataclass(frozen=True, slots=True)
class OptionSpec:
    option_id: str
    name: str
    capabilities: tuple[str, ...]
    initiation_tags: tuple[str, ...] = ()
    termination_tags: tuple[str, ...] = ()
    interrupt_tags: tuple[str, ...] = ()
    maximum_steps: int = 16
    maximum_failures: int = 2
    maximum_wall_seconds: float = 120.0
    risk: RiskTier = RiskTier.READ_ONLY
    minimum_success_probability: float = 0.5
    skill_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "option_id", require_id("option_id", self.option_id))
        object.__setattr__(self, "name", bounded_text("name", self.name, maximum=1024))
        caps = tuple(sorted({require_id("capability", item) for item in self.capabilities}))
        if not caps:
            raise AgentContractError("option requires at least one capability")
        object.__setattr__(self, "capabilities", caps)
        for attr in ("initiation_tags", "termination_tags", "interrupt_tags"):
            value = tuple(sorted({require_id(attr, item) for item in getattr(self, attr)}))
            object.__setattr__(self, attr, value)
        object.__setattr__(self, "maximum_steps", positive_int("maximum_steps", self.maximum_steps, maximum=100_000))
        object.__setattr__(self, "maximum_failures", positive_int("maximum_failures", self.maximum_failures, maximum=10_000))
        wall = finite_number("maximum_wall_seconds", self.maximum_wall_seconds)
        if wall <= 0:
            raise AgentContractError("maximum_wall_seconds must be positive")
        object.__setattr__(self, "maximum_wall_seconds", wall)
        if not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))
        object.__setattr__(self, "minimum_success_probability", probability("minimum_success_probability", self.minimum_success_probability))
        if self.skill_id is not None:
            object.__setattr__(self, "skill_id", require_id("skill_id", self.skill_id))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class OptionExecution:
    execution_id: str
    option_id: str
    run_id: str
    started_at: float
    status: OptionStatus = OptionStatus.RUNNING
    steps: int = 0
    failures: int = 0
    last_progress: float = 0.0
    last_event_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "execution_id", require_id("execution_id", self.execution_id))
        object.__setattr__(self, "option_id", require_id("option_id", self.option_id))
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        start = finite_number("started_at", self.started_at)
        if start < 0:
            raise AgentContractError("started_at must be non-negative")
        object.__setattr__(self, "started_at", start)
        if not isinstance(self.status, OptionStatus):
            object.__setattr__(self, "status", OptionStatus(str(self.status)))
        if isinstance(self.steps, bool) or not isinstance(self.steps, int) or self.steps < 0:
            raise AgentContractError("steps must be non-negative integer")
        if isinstance(self.failures, bool) or not isinstance(self.failures, int) or self.failures < 0:
            raise AgentContractError("failures must be non-negative integer")
        object.__setattr__(self, "last_progress", probability("last_progress", self.last_progress))
        if self.last_event_id is not None:
            object.__setattr__(self, "last_event_id", require_id("last_event_id", self.last_event_id))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


class OptionLibrary:
    def __init__(self, *, skills: SkillLibrary | None = None) -> None:
        self.skills = skills
        self._specs: dict[str, OptionSpec] = {}
        self._executions: dict[str, OptionExecution] = {}
        self._lock = threading.RLock()

    def register(self, spec: OptionSpec) -> None:
        if not isinstance(spec, OptionSpec):
            raise TypeError("spec must be OptionSpec")
        with self._lock:
            prior = self._specs.get(spec.option_id)
            if prior is not None and prior != spec:
                raise SupervisorError(f"option already registered differently: {spec.option_id}")
            self._specs[spec.option_id] = spec

    def specs(self) -> tuple[OptionSpec, ...]:
        with self._lock:
            return tuple(self._specs[key] for key in sorted(self._specs))

    def get(self, option_id: str) -> OptionSpec | None:
        with self._lock:
            return self._specs.get(require_id("option_id", option_id))

    def eligible(
        self,
        *,
        tags: Sequence[str],
        maximum_risk: RiskTier,
        context: ContextSignature | None = None,
    ) -> tuple[tuple[OptionSpec, float], ...]:
        tag_set = {require_id("tag", item) for item in tags}
        risk_level = {
            RiskTier.READ_ONLY: 0,
            RiskTier.REVERSIBLE: 1,
            RiskTier.MUTATING: 2,
            RiskTier.EXTERNAL: 3,
            RiskTier.HIGH_IMPACT: 4,
        }
        values: list[tuple[OptionSpec, float]] = []
        for spec in self.specs():
            if risk_level[spec.risk] > risk_level[maximum_risk]:
                continue
            if spec.initiation_tags and not set(spec.initiation_tags).issubset(tag_set):
                continue
            empirical = 0.5
            if self.skills is not None and spec.skill_id is not None:
                profile = self.skills.profile(spec.skill_id)
                if profile is not None:
                    empirical = profile.empirical_success
            if empirical < spec.minimum_success_probability:
                continue
            match = 1.0
            if spec.initiation_tags:
                match = len(set(spec.initiation_tags) & tag_set) / len(spec.initiation_tags)
            score = empirical * 0.65 + match * 0.25 + (1.0 - risk_level[spec.risk] / 4.0) * 0.10
            values.append((spec, score))
        values.sort(key=lambda item: (item[1], item[0].option_id), reverse=True)
        return tuple(values)

    def start(self, option_id: str, *, run_id: str, at: float) -> OptionExecution:
        spec = self.get(option_id)
        if spec is None:
            raise SupervisorError(f"unknown option: {option_id}")
        execution_id = stable_id("optionrun", {"option": option_id, "run": run_id, "at": at})
        execution = OptionExecution(execution_id, option_id, run_id, at)
        with self._lock:
            self._executions[execution_id] = execution
        return execution

    def update(
        self,
        execution_id: str,
        *,
        progress: float | None = None,
        failed: bool = False,
        event_id: str | None = None,
        terminal_tags: Sequence[str] = (),
        interrupt_tags: Sequence[str] = (),
        now: float,
    ) -> OptionExecution:
        execution_id = require_id("execution_id", execution_id)
        with self._lock:
            current = self._executions.get(execution_id)
        if current is None:
            raise SupervisorError(f"unknown option execution: {execution_id}")
        spec = self.get(current.option_id)
        assert spec is not None
        if current.status is not OptionStatus.RUNNING:
            return current
        steps = current.steps + 1
        failures = current.failures + (1 if failed else 0)
        status = OptionStatus.RUNNING
        termination = set(spec.termination_tags) & {require_id("terminal_tag", item) for item in terminal_tags}
        interrupts = set(spec.interrupt_tags) & {require_id("interrupt_tag", item) for item in interrupt_tags}
        if interrupts:
            status = OptionStatus.INTERRUPTED
        elif termination:
            status = OptionStatus.TERMINATED
        elif failures >= spec.maximum_failures:
            status = OptionStatus.FAILED
        elif steps >= spec.maximum_steps:
            status = OptionStatus.TERMINATED
        elif now - current.started_at >= spec.maximum_wall_seconds:
            status = OptionStatus.TERMINATED
        updated = replace(
            current,
            status=status,
            steps=steps,
            failures=failures,
            last_progress=current.last_progress if progress is None else probability("progress", progress),
            last_event_id=event_id or current.last_event_id,
        )
        with self._lock:
            self._executions[execution_id] = updated
        return updated


@dataclass(frozen=True, slots=True)
class SupervisorSignals:
    run_id: str
    phase: AgentPhase
    usage: Usage
    budget: Budget
    progress: float
    failure_streak: int
    verification_failure_streak: int
    replans: int
    pending_confirmation: bool
    current_risk: RiskTier
    plan_ready_steps: int
    plan_failed_steps: int
    plan_blocked_steps: int
    belief: BeliefStateSummary
    evidence_growth: int
    stale_cycles: int
    loop_severity: float
    current_intention_id: str | None = None
    current_option_execution_id: str | None = None
    worker_action_fingerprint: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        if not isinstance(self.phase, AgentPhase):
            object.__setattr__(self, "phase", AgentPhase(str(self.phase)))
        if not isinstance(self.usage, Usage) or not isinstance(self.budget, Budget):
            raise AgentContractError("usage/budget must be typed contracts")
        object.__setattr__(self, "progress", probability("progress", self.progress))
        for name in (
            "failure_streak",
            "verification_failure_streak",
            "replans",
            "plan_ready_steps",
            "plan_failed_steps",
            "plan_blocked_steps",
            "evidence_growth",
            "stale_cycles",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be non-negative integer")
        if not isinstance(self.current_risk, RiskTier):
            object.__setattr__(self, "current_risk", RiskTier(str(self.current_risk)))
        if not isinstance(self.belief, BeliefStateSummary):
            raise AgentContractError("belief must be BeliefStateSummary")
        object.__setattr__(self, "loop_severity", probability("loop_severity", self.loop_severity))
        if self.current_intention_id is not None:
            object.__setattr__(self, "current_intention_id", require_id("current_intention_id", self.current_intention_id))
        if self.current_option_execution_id is not None:
            object.__setattr__(self, "current_option_execution_id", require_id("current_option_execution_id", self.current_option_execution_id))
        if self.worker_action_fingerprint is not None:
            object.__setattr__(self, "worker_action_fingerprint", str(self.worker_action_fingerprint).strip().lower())
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def budget_pressure(self) -> float:
        ratios = (
            self.usage.steps / self.budget.max_steps,
            self.usage.model_calls / self.budget.max_model_calls,
            self.usage.tool_calls / self.budget.max_tool_calls,
            self.usage.total_tokens / self.budget.max_tokens,
        )
        return max(0.0, min(1.0, max(ratios)))


@dataclass(frozen=True, slots=True)
class Intervention:
    intervention_id: str
    run_id: str
    kind: InterventionKind
    reason: str
    priority: float
    created_at: float
    target_intention_id: str | None = None
    target_option_execution_id: str | None = None
    directive: str = ""
    evidence_ids: tuple[str, ...] = ()
    expected_effect: str = ""
    hard: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "intervention_id", require_id("intervention_id", self.intervention_id))
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        if not isinstance(self.kind, InterventionKind):
            object.__setattr__(self, "kind", InterventionKind(str(self.kind)))
        object.__setattr__(self, "reason", bounded_text("reason", self.reason, maximum=8192))
        object.__setattr__(self, "priority", probability("priority", self.priority))
        created = finite_number("created_at", self.created_at)
        if created < 0:
            raise AgentContractError("created_at must be non-negative")
        object.__setattr__(self, "created_at", created)
        if self.target_intention_id is not None:
            object.__setattr__(self, "target_intention_id", require_id("target_intention_id", self.target_intention_id))
        if self.target_option_execution_id is not None:
            object.__setattr__(self, "target_option_execution_id", require_id("target_option_execution_id", self.target_option_execution_id))
        object.__setattr__(self, "directive", bounded_text("directive", self.directive, maximum=8192, allow_empty=True))
        object.__setattr__(self, "evidence_ids", tuple(require_id("evidence_id", item) for item in self.evidence_ids))
        object.__setattr__(self, "expected_effect", bounded_text("expected_effect", self.expected_effect, maximum=4096, allow_empty=True))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class SupervisorPolicy:
    uncertainty_seek_threshold: float = 0.58
    contradiction_replan_threshold: float = 0.45
    loop_redirect_threshold: float = 0.45
    loop_abort_threshold: float = 0.88
    budget_finalize_threshold: float = 0.84
    budget_abort_threshold: float = 0.98
    failure_replan_threshold: int = 2
    verification_abort_threshold: int = 4
    stale_seek_threshold: int = 2
    maximum_replans: int = 5
    minimum_switch_gain: float = 0.12
    intention_protection_seconds: float = 15.0
    evidence_sensitive_drop_probability: float = 0.25

    def __post_init__(self) -> None:
        for name in (
            "uncertainty_seek_threshold",
            "contradiction_replan_threshold",
            "loop_redirect_threshold",
            "loop_abort_threshold",
            "budget_finalize_threshold",
            "budget_abort_threshold",
            "minimum_switch_gain",
            "evidence_sensitive_drop_probability",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        for name in ("failure_replan_threshold", "verification_abort_threshold", "stale_seek_threshold", "maximum_replans"):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=100_000))
        protected = finite_number("intention_protection_seconds", self.intention_protection_seconds)
        if protected < 0:
            raise AgentContractError("intention_protection_seconds must be non-negative")
        object.__setattr__(self, "intention_protection_seconds", protected)
        if self.loop_abort_threshold < self.loop_redirect_threshold:
            raise AgentContractError("loop abort threshold must be >= redirect threshold")
        if self.budget_abort_threshold < self.budget_finalize_threshold:
            raise AgentContractError("budget abort threshold must be >= finalize threshold")


class IntentionManager:
    """BDI-style desire adoption and commitment-aware reconsideration."""

    _RISK_VALUE = {
        RiskTier.READ_ONLY: 0.0,
        RiskTier.REVERSIBLE: 0.15,
        RiskTier.MUTATING: 0.40,
        RiskTier.EXTERNAL: 0.65,
        RiskTier.HIGH_IMPACT: 1.0,
    }

    def __init__(self, *, clock: Callable[[], float] = time.time, policy: SupervisorPolicy | None = None) -> None:
        self._clock = clock
        self.policy = policy or SupervisorPolicy()
        self._desires: dict[str, Desire] = {}
        self._intentions: dict[str, Intention] = {}
        self._active_by_run: dict[str, str] = {}
        self._history: list[tuple[float, str, str, str]] = []
        self._lock = threading.RLock()

    def add_desire(self, desire: Desire) -> Desire:
        if not isinstance(desire, Desire):
            raise TypeError("desire must be Desire")
        with self._lock:
            prior = self._desires.get(desire.desire_id)
            if prior is not None and prior.fingerprint != desire.fingerprint:
                raise SupervisorError("desire id collision")
            self._desires[desire.desire_id] = desire
        return desire

    def desires(self) -> tuple[Desire, ...]:
        with self._lock:
            return tuple(self._desires[key] for key in sorted(self._desires))

    def intentions(self) -> tuple[Intention, ...]:
        with self._lock:
            return tuple(self._intentions[key] for key in sorted(self._intentions))

    def active(self, run_id: str) -> Intention | None:
        run_id = require_id("run_id", run_id)
        with self._lock:
            intention_id = self._active_by_run.get(run_id)
            return self._intentions.get(intention_id) if intention_id else None

    def score_desire(self, desire: Desire, *, now: float, belief_confidence: float = 0.5) -> float:
        dependency_penalty = 0.0
        with self._lock:
            for dep in desire.dependencies:
                prior = self._desires.get(dep)
                if prior is None or prior.status is not DesireStatus.SATISFIED:
                    dependency_penalty += 0.20
            conflict_pressure = sum(
                1
                for conflict in desire.conflicts
                if (self._desires.get(conflict) is not None and self._desires[conflict].status in {DesireStatus.ADOPTED, DesireStatus.ELIGIBLE})
            ) * 0.15
        deadline_boost = 0.0
        if desire.deadline_at is not None:
            remaining = desire.deadline_at - now
            if remaining <= 0:
                deadline_boost = 0.35
            else:
                deadline_boost = 0.35 * math.exp(-remaining / 3600.0)
        risk_penalty = self._RISK_VALUE[desire.risk_tolerance] * 0.15
        return max(
            0.0,
            min(
                1.0,
                desire.utility * 0.34
                + desire.urgency * 0.26
                + desire.confidence * 0.15
                + probability("belief_confidence", belief_confidence) * 0.15
                + deadline_boost
                - dependency_penalty
                - conflict_pressure
                - risk_penalty,
            ),
        )

    def adopt_best(
        self,
        *,
        run_id: str,
        belief_confidence: float,
        commitment: CommitmentPolicy = CommitmentPolicy.EVIDENCE_SENSITIVE,
    ) -> Intention | None:
        run_id = require_id("run_id", run_id)
        now = self._clock()
        candidates = [desire for desire in self.desires() if desire.status in {DesireStatus.CANDIDATE, DesireStatus.ELIGIBLE}]
        if not candidates:
            return None
        scored = [(desire, self.score_desire(desire, now=now, belief_confidence=belief_confidence)) for desire in candidates]
        scored.sort(key=lambda item: (item[1], item[0].desire_id), reverse=True)
        desire, score = scored[0]
        current = self.active(run_id)
        if current is not None:
            current_desire = self._desires[current.desire_id]
            current_score = self.score_desire(current_desire, now=now, belief_confidence=belief_confidence)
            protected = current.protected_until is not None and now < current.protected_until
            if protected or score < current_score + self.policy.minimum_switch_gain:
                return current
            if not self._reconsiderable(current, current_desire, belief_probability=belief_confidence, failures=0, stagnant_cycles=0):
                return current
            self._set_intention_status(current.intention_id, IntentionStatus.SUSPENDED, run_id)
        intention = Intention(
            intention_id=stable_id("intention", {"run": run_id, "desire": desire.desire_id, "at": now}),
            desire_id=desire.desire_id,
            objective=desire.objective,
            adopted_at=now,
            commitment=commitment,
            status=IntentionStatus.ACTIVE,
            priority=score,
            protected_until=now + self.policy.intention_protection_seconds,
        )
        with self._lock:
            self._intentions[intention.intention_id] = intention
            self._active_by_run[run_id] = intention.intention_id
            self._desires[desire.desire_id] = replace(desire, status=DesireStatus.ADOPTED)
            self._history.append((now, run_id, intention.intention_id, "adopted"))
        return intention

    def reconsider(
        self,
        *,
        run_id: str,
        belief_probability: float,
        failures: int,
        stagnant_cycles: int,
        achieved: bool = False,
        impossible: bool = False,
    ) -> Intention | None:
        current = self.active(run_id)
        if current is None:
            return None
        desire = self._desires[current.desire_id]
        if achieved:
            self._set_intention_status(current.intention_id, IntentionStatus.SATISFIED, run_id)
            with self._lock:
                self._desires[desire.desire_id] = replace(desire, status=DesireStatus.SATISFIED)
            return None
        if impossible:
            self._set_intention_status(current.intention_id, IntentionStatus.FAILED, run_id)
            with self._lock:
                self._desires[desire.desire_id] = replace(desire, status=DesireStatus.BLOCKED)
            return None
        if self._reconsiderable(current, desire, belief_probability=belief_probability, failures=failures, stagnant_cycles=stagnant_cycles):
            return self.adopt_best(run_id=run_id, belief_confidence=belief_probability, commitment=current.commitment)
        return current

    def _reconsiderable(
        self,
        intention: Intention,
        desire: Desire,
        *,
        belief_probability: float,
        failures: int,
        stagnant_cycles: int,
    ) -> bool:
        now = self._clock()
        if intention.protected_until is not None and now < intention.protected_until:
            return False
        if intention.commitment is CommitmentPolicy.BLIND:
            return False
        if intention.commitment is CommitmentPolicy.SINGLE_MINDED:
            return failures >= intention.reconsider_after_failures * 2 or stagnant_cycles >= intention.maximum_stagnant_cycles * 2
        if intention.commitment is CommitmentPolicy.OPEN_MINDED:
            return failures >= intention.reconsider_after_failures or stagnant_cycles >= intention.maximum_stagnant_cycles
        return (
            belief_probability < self.policy.evidence_sensitive_drop_probability
            or failures >= intention.reconsider_after_failures
            or stagnant_cycles >= intention.maximum_stagnant_cycles
        )

    def _set_intention_status(self, intention_id: str, status: IntentionStatus, run_id: str) -> None:
        now = self._clock()
        with self._lock:
            current = self._intentions[intention_id]
            self._intentions[intention_id] = replace(current, status=status)
            if self._active_by_run.get(run_id) == intention_id and status is not IntentionStatus.ACTIVE:
                self._active_by_run.pop(run_id, None)
            self._history.append((now, run_id, intention_id, status.value))


class LiveSupervisor:
    """Evidence-sensitive supervisor over a bounded worker runtime."""

    _RISK_SCORE = {
        RiskTier.READ_ONLY: 0.05,
        RiskTier.REVERSIBLE: 0.20,
        RiskTier.MUTATING: 0.50,
        RiskTier.EXTERNAL: 0.72,
        RiskTier.HIGH_IMPACT: 1.0,
    }

    def __init__(
        self,
        *,
        policy: SupervisorPolicy | None = None,
        blackboard: Blackboard | None = None,
        intentions: IntentionManager | None = None,
        options: OptionLibrary | None = None,
        projector: BeliefStateProjector | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.policy = policy or SupervisorPolicy()
        self._clock = clock
        self.blackboard = blackboard or Blackboard(clock=clock)
        self.intentions = intentions or IntentionManager(clock=clock, policy=self.policy)
        self.options = options or OptionLibrary()
        self.projector = projector or BeliefStateProjector()
        self._history: deque[Intervention] = deque(maxlen=10_000)
        self._last_progress: dict[str, float] = {}
        self._last_evidence_fp: dict[str, str] = {}
        self._same_action_count: Counter[tuple[str, str]] = Counter()
        self._lock = threading.RLock()

    def evaluate(self, signals: SupervisorSignals) -> Intervention:
        if not isinstance(signals, SupervisorSignals):
            raise TypeError("signals must be SupervisorSignals")
        candidates = self._candidate_interventions(signals)
        candidates.sort(key=lambda item: (item.priority, self._priority(item.kind), item.intervention_id), reverse=True)
        chosen = candidates[0] if candidates else self._make(signals, InterventionKind.CONTINUE, "no supervisor intervention required", 0.1)
        with self._lock:
            self._history.append(chosen)
            self._last_progress[signals.run_id] = signals.progress
            if signals.worker_action_fingerprint:
                self._same_action_count[(signals.run_id, signals.worker_action_fingerprint)] += 1
        self.blackboard.emit(
            run_id=signals.run_id,
            topic=BlackboardTopic.CONTROL,
            producer="live-supervisor",
            payload={
                "intervention_id": chosen.intervention_id,
                "kind": chosen.kind.value,
                "reason": chosen.reason,
                "priority": chosen.priority,
                "hard": chosen.hard,
            },
            confidence=1.0,
            priority=chosen.priority,
        )
        return chosen

    def _candidate_interventions(self, s: SupervisorSignals) -> list[Intervention]:
        p = self.policy
        values: list[Intervention] = []
        budget = s.budget_pressure
        risk = self._RISK_SCORE[s.current_risk]

        if s.pending_confirmation:
            values.append(self._make(s, InterventionKind.REQUEST_CONFIRMATION, "pending capability requires explicit confirmation", 0.995, hard=True))
        if budget >= p.budget_abort_threshold:
            values.append(self._make(s, InterventionKind.ABORT_RUN, f"budget pressure {budget:.3f} exceeds hard stop", 0.99, hard=True))
        if s.loop_severity >= p.loop_abort_threshold:
            values.append(self._make(s, InterventionKind.ABORT_RUN, f"loop severity {s.loop_severity:.3f} exceeds hard stop", 0.985, hard=True))
        if s.verification_failure_streak >= p.verification_abort_threshold:
            values.append(self._make(s, InterventionKind.ABORT_OPTION if s.current_option_execution_id else InterventionKind.REPLAN, "repeated verification failures indicate worker strategy is unreliable", 0.96, hard=bool(s.current_option_execution_id)))
        if risk >= 0.72 and s.verification_failure_streak > 0:
            values.append(self._make(s, InterventionKind.VERIFY, "external/high-risk work has unresolved verification failure", 0.95))
        if s.belief.contradiction_pressure >= p.contradiction_replan_threshold:
            values.append(self._make(s, InterventionKind.SEEK_INFORMATION, "belief state contains material contradiction; collect discriminating evidence before further commitment", 0.91, evidence_ids=self._probe_evidence_ids(s)))
        if s.failure_streak >= p.failure_replan_threshold and s.replans < p.maximum_replans:
            values.append(self._make(s, InterventionKind.REPLAN, f"failure streak {s.failure_streak} invalidates current tactical path", 0.88))
        if s.plan_failed_steps or s.plan_blocked_steps:
            values.append(self._make(s, InterventionKind.REPLAN, "plan contains failed/blocked frontier", 0.86))
        if s.belief.uncertain and s.belief.maximum_probability < p.uncertainty_seek_threshold:
            values.append(self._make(s, InterventionKind.SEEK_INFORMATION, "partial observability is too high for confident action", 0.83, evidence_ids=self._probe_evidence_ids(s)))
        if s.stale_cycles >= p.stale_seek_threshold and s.evidence_growth == 0:
            values.append(self._make(s, InterventionKind.SEEK_INFORMATION, "worker is consuming cycles without adding evidence", 0.80))
        if s.loop_severity >= p.loop_redirect_threshold:
            values.append(self._make(s, InterventionKind.REDIRECT, "worker appears stuck in repeated state/action pattern", 0.79))
        if budget >= p.budget_finalize_threshold and s.progress >= 0.75:
            values.append(self._make(s, InterventionKind.REDIRECT, "remaining budget should be conserved for verification/finalization", 0.75, directive="Stop exploratory work; finish the shortest verified path to completion."))
        if s.plan_ready_steps == 0 and s.progress < 1.0 and s.replans < p.maximum_replans:
            values.append(self._make(s, InterventionKind.REPLAN, "no ready step exists while work remains", 0.74))
        if s.progress >= 1.0:
            values.append(self._make(s, InterventionKind.VERIFY, "worker reports completion; perform independent final verification", 0.93))
        if not values:
            values.append(self._make(s, InterventionKind.CONTINUE, "current intention remains viable", 0.25))
        return values

    def _probe_evidence_ids(self, signals: SupervisorSignals) -> tuple[str, ...]:
        ids: set[str] = set()
        for particle in signals.belief.particles[:4]:
            ids.update(particle.evidence_ids)
        return tuple(sorted(ids))

    def _make(
        self,
        signals: SupervisorSignals,
        kind: InterventionKind,
        reason: str,
        priority: float,
        *,
        directive: str = "",
        evidence_ids: Sequence[str] = (),
        hard: bool = False,
    ) -> Intervention:
        at = self._clock()
        if not directive:
            directive = self._default_directive(kind, signals)
        intervention_id = stable_id(
            "intervention",
            {
                "run": signals.run_id,
                "kind": kind.value,
                "reason": reason,
                "progress": signals.progress,
                "belief": signals.belief.fingerprint,
                "action": signals.worker_action_fingerprint,
                "at": at,
            },
        )
        return Intervention(
            intervention_id=intervention_id,
            run_id=signals.run_id,
            kind=kind,
            reason=reason,
            priority=priority,
            created_at=at,
            target_intention_id=signals.current_intention_id,
            target_option_execution_id=signals.current_option_execution_id,
            directive=directive,
            evidence_ids=tuple(evidence_ids),
            expected_effect=self._expected_effect(kind),
            hard=hard,
            metadata={
                "phase": signals.phase.value,
                "budget_pressure": signals.budget_pressure,
                "loop_severity": signals.loop_severity,
                "belief_entropy_bits": signals.belief.entropy_bits,
            },
        )

    @staticmethod
    def _default_directive(kind: InterventionKind, s: SupervisorSignals) -> str:
        directives = {
            InterventionKind.CONTINUE: "Continue the current verified intention and next ready step.",
            InterventionKind.REDIRECT: "Change tactic while preserving verified completed work and current safety constraints.",
            InterventionKind.PAUSE: "Pause worker execution and preserve checkpoint state before any further mutation.",
            InterventionKind.REPLAN: "Replan from the current verified state; do not replay completed mutations.",
            InterventionKind.SEEK_INFORMATION: "Acquire the cheapest independent observation that most reduces decision uncertainty.",
            InterventionKind.VERIFY: "Run independent host-side verification before trusting the worker's completion claim.",
            InterventionKind.REQUEST_CONFIRMATION: "Suspend mutation until explicit authorization is supplied.",
            InterventionKind.SUSPEND_INTENTION: "Suspend the current intention without discarding its verified progress.",
            InterventionKind.SWITCH_INTENTION: "Switch to a higher-value eligible intention after preserving current state.",
            InterventionKind.ABORT_OPTION: "Terminate the current temporal option and return control to the supervisor.",
            InterventionKind.ABORT_RUN: "Terminate the run safely and preserve checkpoint, evidence, context, and trace state.",
        }
        return directives[kind]

    @staticmethod
    def _expected_effect(kind: InterventionKind) -> str:
        effects = {
            InterventionKind.CONTINUE: "preserve momentum without extra deliberation",
            InterventionKind.REDIRECT: "escape local stagnation with minimal structural change",
            InterventionKind.PAUSE: "prevent unsafe progress while retaining resumability",
            InterventionKind.REPLAN: "replace invalid tactical assumptions while preserving verified work",
            InterventionKind.SEEK_INFORMATION: "reduce belief entropy or contradiction pressure",
            InterventionKind.VERIFY: "increase certainty that claimed state change actually occurred",
            InterventionKind.REQUEST_CONFIRMATION: "move authorization outside the probabilistic model",
            InterventionKind.SUSPEND_INTENTION: "free resources while retaining a resumable commitment",
            InterventionKind.SWITCH_INTENTION: "allocate effort to a higher-value feasible objective",
            InterventionKind.ABORT_OPTION: "stop a failing long-running skill before waste or damage compounds",
            InterventionKind.ABORT_RUN: "fail closed and preserve forensic state",
        }
        return effects[kind]

    @staticmethod
    def _priority(kind: InterventionKind) -> int:
        order = {
            InterventionKind.ABORT_RUN: 100,
            InterventionKind.REQUEST_CONFIRMATION: 95,
            InterventionKind.ABORT_OPTION: 90,
            InterventionKind.VERIFY: 85,
            InterventionKind.SEEK_INFORMATION: 80,
            InterventionKind.REPLAN: 75,
            InterventionKind.SWITCH_INTENTION: 70,
            InterventionKind.SUSPEND_INTENTION: 65,
            InterventionKind.REDIRECT: 60,
            InterventionKind.PAUSE: 55,
            InterventionKind.CONTINUE: 10,
        }
        return order[kind]

    def history(self, *, run_id: str | None = None) -> tuple[Intervention, ...]:
        with self._lock:
            values = list(self._history)
        if run_id is not None:
            run_id = require_id("run_id", run_id)
            values = [item for item in values if item.run_id == run_id]
        return tuple(values)


@dataclass(slots=True)
class SupervisorStateBuilder:
    """Translate runtime/cortex state into the compact supervisor signal set."""

    run_id: str
    phase: AgentPhase
    usage: Usage
    budget: Budget
    plan: Plan | None = None
    world: BeliefGraph | None = None
    evidence_ledger: EvidenceLedger | None = None
    failure_streak: int = 0
    verification_failure_streak: int = 0
    replans: int = 0
    pending_confirmation: bool = False
    current_risk: RiskTier = RiskTier.READ_ONLY
    stale_cycles: int = 0
    loop_severity: float = 0.0
    current_intention_id: str | None = None
    current_option_execution_id: str | None = None
    worker_action_fingerprint: str | None = None
    previous_evidence_count: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def build(self, projector: BeliefStateProjector | None = None) -> SupervisorSignals:
        projector = projector or BeliefStateProjector()
        belief = projector.project(self.world)
        total = completed = failed = blocked = ready = 0
        if self.plan is not None:
            total = len(self.plan.steps)
            for step in self.plan.steps:
                if step.status in {StepStatus.SUCCEEDED, StepStatus.SKIPPED}:
                    completed += 1
                elif step.status is StepStatus.FAILED:
                    failed += 1
                elif step.status is StepStatus.BLOCKED:
                    blocked += 1
            ready = len(self.plan.ready_steps())
        progress = completed / total if total else 0.0
        evidence_count = len(self.evidence_ledger.artifacts()) if self.evidence_ledger is not None else 0
        growth = max(0, evidence_count - self.previous_evidence_count)
        return SupervisorSignals(
            run_id=self.run_id,
            phase=self.phase,
            usage=self.usage,
            budget=self.budget,
            progress=progress,
            failure_streak=self.failure_streak,
            verification_failure_streak=self.verification_failure_streak,
            replans=self.replans,
            pending_confirmation=self.pending_confirmation,
            current_risk=self.current_risk,
            plan_ready_steps=ready,
            plan_failed_steps=failed,
            plan_blocked_steps=blocked,
            belief=belief,
            evidence_growth=growth,
            stale_cycles=self.stale_cycles,
            loop_severity=self.loop_severity,
            current_intention_id=self.current_intention_id,
            current_option_execution_id=self.current_option_execution_id,
            worker_action_fingerprint=self.worker_action_fingerprint,
            metadata=self.metadata,
        )


def desire_from_step(step: PlanStep, *, utility: float = 0.6, urgency: float = 0.5) -> Desire:
    if not isinstance(step, PlanStep):
        raise TypeError("step must be PlanStep")
    return Desire(
        desire_id=stable_id("desire", {"step": step.step_id, "title": step.title, "tool": step.tool}),
        objective=step.description,
        utility=utility,
        urgency=urgency,
        confidence=0.6,
        risk_tolerance=step.risk,
        dependencies=step.dependencies,
        source="plan-step",
        metadata={"step_id": step.step_id, "tool": step.tool, "verification": step.verification},
    )


def option_from_step(step: PlanStep) -> OptionSpec:
    if not isinstance(step, PlanStep):
        raise TypeError("step must be PlanStep")
    capability = f"tool:{step.tool}" if step.tool else "reasoning"
    return OptionSpec(
        option_id=stable_id("option", {"step": step.step_id, "capability": capability, "risk": step.risk.value}),
        name=step.title,
        capabilities=(capability,),
        initiation_tags=("step-ready",),
        termination_tags=("step-succeeded",),
        interrupt_tags=("policy-denied", "verification-failed", "contradiction", "cancelled"),
        maximum_steps=max(2, step.max_attempts * 3),
        maximum_failures=max(1, step.max_attempts),
        risk=step.risk,
        skill_id=stable_id("skill", {"tool": step.tool}) if step.tool else None,
        metadata={"step_id": step.step_id, "expected_outcome": step.expected_outcome},
    )
