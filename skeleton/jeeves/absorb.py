"""Orthogonal knowledge absorption for Jeeves.

The serving path must never perform ingestion work.  This module therefore
splits a cheap append-only intake operation from independently scheduled
normalisation, novelty analysis, verification and promotion.

The implementation is deliberately dependency-light domain code.  Production
adapters can replace the journal, semantic scorer and promotion sink without
changing the state machine or promotion contract.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import math
import re
import time
from collections import deque
from dataclasses import dataclass, field, replace
from enum import Enum
from itertools import count
from typing import Callable, Iterable, Mapping, Protocol, Sequence

from skeleton.kernel.errors import JeevesError
from skeleton.kernel.events import EventBus


MAX_CONTENT_CHARS = 1_000_000
MAX_SOURCE_ID_CHARS = 512
_EPSILON = 1e-9
_TOKEN_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)


class AbsorbError(JeevesError):
    code = "JEE.ABSORB"
    http_status = 422


class AbsorbLane(str, Enum):
    FAST = "fast"
    DEEP = "deep"
    CHALLENGE = "challenge"


class KnowledgeTier(str, Enum):
    RAW = "L0"
    OBSERVATION = "L1"
    VERIFIED_FACT = "L2"
    KNOWLEDGE_GRAPH = "L3"
    DISTILLED_CONCEPT = "L4"
    OPERATIONAL_MODEL = "L5"


class Disposition(str, Enum):
    PROMOTE = "promote"
    DEFER = "defer"
    QUARANTINE = "quarantine"


def _unit(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AbsorbError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise AbsorbError(f"{name} must be finite and between 0 and 1")
    return number


def _positive(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AbsorbError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise AbsorbError(f"{name} must be finite and positive")
    return number


def _text(name: str, value: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AbsorbError(f"{name} must be a non-empty string")
    if len(value) > maximum:
        raise AbsorbError(f"{name} exceeds {maximum} characters")
    return value


def canonicalize(text: str) -> str:
    """Cheap deterministic normalisation used before all expensive work."""
    text = _text("content", text, MAX_CONTENT_CHARS)
    return " ".join(text.casefold().split())


def content_fingerprint(text: str) -> str:
    return hashlib.sha256(canonicalize(text).encode("utf-8")).hexdigest()


def _tokens(text: str) -> frozenset[str]:
    return frozenset(_TOKEN_RE.findall(canonicalize(text)))


def token_similarity(left: str, right: str) -> float:
    """Bounded dependency-free near-duplicate estimate.

    This is intentionally a cheap first-stage filter.  A semantic model can be
    injected later for candidates that survive the fast lane.
    """
    a, b = _tokens(left), _tokens(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True, slots=True)
class Provenance:
    source_id: str
    source_type: str
    observed_at: float
    uri: str | None = None
    trust: float = 0.5
    evidence: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text("source_id", self.source_id, MAX_SOURCE_ID_CHARS)
        _text("source_type", self.source_type, 128)
        if not math.isfinite(float(self.observed_at)) or self.observed_at < 0:
            raise AbsorbError("observed_at must be a non-negative finite timestamp")
        object.__setattr__(self, "trust", _unit("trust", self.trust))


@dataclass(frozen=True, slots=True)
class Observation:
    observation_id: str
    content: str
    provenance: Provenance
    urgency: float = 0.0
    estimated_compute_cost: float = 1.0
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text("observation_id", self.observation_id, 512)
        _text("content", self.content, MAX_CONTENT_CHARS)
        object.__setattr__(self, "urgency", _unit("urgency", self.urgency))
        object.__setattr__(
            self,
            "estimated_compute_cost",
            _positive("estimated_compute_cost", self.estimated_compute_cost),
        )


@dataclass(frozen=True, slots=True)
class AbsorbSignals:
    novelty: float
    relevance: float
    information_gain: float
    evidence_quality: float
    urgency: float
    downstream_utility: float
    estimated_compute_cost: float = 1.0

    def __post_init__(self) -> None:
        for name in (
            "novelty",
            "relevance",
            "information_gain",
            "evidence_quality",
            "urgency",
            "downstream_utility",
        ):
            object.__setattr__(self, name, _unit(name, getattr(self, name)))
        object.__setattr__(
            self,
            "estimated_compute_cost",
            _positive("estimated_compute_cost", self.estimated_compute_cost),
        )

    @property
    def utility_per_compute(self) -> float:
        value = (
            self.novelty * 0.25
            + self.relevance * 0.20
            + self.information_gain * 0.20
            + self.evidence_quality * 0.15
            + self.urgency * 0.10
            + self.downstream_utility * 0.10
        )
        return value / max(self.estimated_compute_cost, _EPSILON)


@dataclass(frozen=True, slots=True)
class Verification:
    confidence: float
    contradiction: float = 0.0
    integrity_risk: float = 0.0
    freshness: float = 1.0
    challenge_passed: bool = False

    def __post_init__(self) -> None:
        for name in ("confidence", "contradiction", "integrity_risk", "freshness"):
            object.__setattr__(self, name, _unit(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class Candidate:
    observation: Observation
    canonical_content: str
    fingerprint: str
    signals: AbsorbSignals
    verification: Verification
    duplicate_similarity: float
    lanes: tuple[AbsorbLane, ...]
    target_tier: KnowledgeTier = KnowledgeTier.VERIFIED_FACT

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "duplicate_similarity", _unit("duplicate_similarity", self.duplicate_similarity)
        )


@dataclass(frozen=True, slots=True)
class GateDecision:
    disposition: Disposition
    reasons: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.disposition is Disposition.PROMOTE


@dataclass(frozen=True, slots=True)
class JournalRecord:
    offset: int
    observation: Observation
    accepted_at: float


class IntakeJournal(Protocol):
    def append(self, observation: Observation) -> JournalRecord: ...

    def replay(self, start_offset: int = 0) -> Sequence[JournalRecord]: ...


class InMemoryJournal:
    """Reference append-only journal with idempotent observation IDs."""

    def __init__(self) -> None:
        self._records: list[JournalRecord] = []
        self._by_id: dict[str, JournalRecord] = {}

    def append(self, observation: Observation) -> JournalRecord:
        existing = self._by_id.get(observation.observation_id)
        if existing is not None:
            if existing.observation != observation:
                raise AbsorbError(
                    "observation_id already exists with different content",
                    context={"observation_id": observation.observation_id},
                )
            return existing
        record = JournalRecord(len(self._records), observation, time.time())
        self._records.append(record)
        self._by_id[observation.observation_id] = record
        return record

    def replay(self, start_offset: int = 0) -> Sequence[JournalRecord]:
        if start_offset < 0:
            raise AbsorbError("start_offset must be non-negative")
        return tuple(self._records[start_offset:])

    def __len__(self) -> int:
        return len(self._records)


class NoveltyIndex:
    """Fast bounded content-addressed duplicate and novelty index."""

    def __init__(self, *, max_recent: int = 2_048) -> None:
        if max_recent < 1:
            raise AbsorbError("max_recent must be positive")
        self._fingerprints: set[str] = set()
        self._recent: deque[str] = deque(maxlen=max_recent)

    def inspect(self, content: str) -> tuple[bool, float]:
        fp = content_fingerprint(content)
        if fp in self._fingerprints:
            return True, 1.0
        similarity = max((token_similarity(content, item) for item in self._recent), default=0.0)
        return False, similarity

    def add(self, content: str) -> None:
        self._fingerprints.add(content_fingerprint(content))
        self._recent.append(content)


@dataclass(frozen=True, slots=True)
class RouterConfig:
    deep_threshold: float = 0.32
    challenge_threshold: float = 0.55
    uncertainty_threshold: float = 0.30
    high_impact_threshold: float = 0.75


class AdaptiveRouter:
    """Routes expensive work by expected marginal knowledge gain."""

    def __init__(self, config: RouterConfig | None = None) -> None:
        self.config = config or RouterConfig()

    def lanes(self, signals: AbsorbSignals, verification: Verification) -> tuple[AbsorbLane, ...]:
        lanes = [AbsorbLane.FAST]
        utility = signals.utility_per_compute
        if utility >= self.config.deep_threshold or signals.information_gain >= 0.65:
            lanes.append(AbsorbLane.DEEP)
        uncertainty = 1.0 - verification.confidence
        high_impact = signals.downstream_utility >= self.config.high_impact_threshold
        if (
            utility >= self.config.challenge_threshold
            or uncertainty >= self.config.uncertainty_threshold
            or verification.contradiction > 0.15
            or verification.integrity_risk > 0.15
            or high_impact
        ):
            lanes.append(AbsorbLane.CHALLENGE)
        return tuple(lanes)


@dataclass(frozen=True, slots=True)
class GateConfig:
    min_confidence: float = 0.72
    max_contradiction: float = 0.35
    max_integrity_risk: float = 0.30
    min_freshness: float = 0.50
    max_duplicate_similarity: float = 0.90
    high_impact_threshold: float = 0.75


class PromotionGate:
    """Fail-closed gate between in-flight knowledge and serving knowledge."""

    def __init__(self, config: GateConfig | None = None) -> None:
        self.config = config or GateConfig()

    def evaluate(self, candidate: Candidate) -> GateDecision:
        reasons: list[str] = []
        p = candidate.observation.provenance
        v = candidate.verification
        s = candidate.signals
        if not p.source_id or not p.source_type:
            reasons.append("missing_provenance")
        if v.integrity_risk > self.config.max_integrity_risk:
            reasons.append("integrity_risk")
        if v.contradiction > self.config.max_contradiction:
            reasons.append("contradiction")
        if candidate.duplicate_similarity >= self.config.max_duplicate_similarity:
            reasons.append("duplicate")
        if reasons:
            return GateDecision(Disposition.QUARANTINE, tuple(reasons))

        deferred: list[str] = []
        if v.confidence < self.config.min_confidence:
            deferred.append("confidence")
        if v.freshness < self.config.min_freshness:
            deferred.append("freshness")
        if (
            s.downstream_utility >= self.config.high_impact_threshold
            and not v.challenge_passed
        ):
            deferred.append("challenge_required")
        if deferred:
            return GateDecision(Disposition.DEFER, tuple(deferred))
        return GateDecision(Disposition.PROMOTE)


@dataclass(frozen=True, slots=True)
class SnapshotEntry:
    observation_id: str
    fingerprint: str
    canonical_content: str
    target_tier: str
    confidence: float
    source_id: str
    journal_offset: int


@dataclass(frozen=True, slots=True)
class KnowledgeSnapshot:
    version: int
    parent_version: int | None
    entries: tuple[SnapshotEntry, ...]
    journal_range: tuple[int, int]
    digest: str
    created_at: float


class SnapshotStore:
    """Atomic immutable snapshot pointer with constant-time rollback."""

    def __init__(self) -> None:
        self._versions: dict[int, KnowledgeSnapshot] = {}
        self._current: int | None = None

    @property
    def current(self) -> KnowledgeSnapshot | None:
        return None if self._current is None else self._versions[self._current]

    def publish(self, entries: Iterable[SnapshotEntry]) -> KnowledgeSnapshot:
        previous = self.current
        merged: dict[str, SnapshotEntry] = {}
        if previous is not None:
            merged.update({entry.fingerprint: entry for entry in previous.entries})
        for entry in entries:
            merged[entry.fingerprint] = entry
        ordered = tuple(sorted(merged.values(), key=lambda item: (item.journal_offset, item.fingerprint)))
        version = 1 if previous is None else previous.version + 1
        offsets = [entry.journal_offset for entry in ordered]
        journal_range = (min(offsets), max(offsets)) if offsets else (0, 0)
        payload = {
            "version": version,
            "parent_version": None if previous is None else previous.version,
            "entries": [
                {
                    "id": item.observation_id,
                    "fp": item.fingerprint,
                    "tier": item.target_tier,
                    "confidence": item.confidence,
                    "source": item.source_id,
                    "offset": item.journal_offset,
                }
                for item in ordered
            ],
            "journal_range": journal_range,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        snapshot = KnowledgeSnapshot(
            version=version,
            parent_version=payload["parent_version"],
            entries=ordered,
            journal_range=journal_range,
            digest=digest,
            created_at=time.time(),
        )
        self._versions[version] = snapshot
        self._current = version
        return snapshot

    def rollback(self, version: int) -> KnowledgeSnapshot:
        if version not in self._versions:
            raise AbsorbError("unknown snapshot version", context={"version": version})
        self._current = version
        return self._versions[version]


@dataclass(slots=True)
class AbsorbMetrics:
    submitted: int = 0
    journal_replays: int = 0
    exact_duplicates: int = 0
    near_duplicates: int = 0
    processed: int = 0
    promoted: int = 0
    deferred: int = 0
    quarantined: int = 0
    challenge_routed: int = 0
    compute_spent: float = 0.0
    information_gain: float = 0.0

    @property
    def knowledge_gain_per_compute(self) -> float:
        return self.information_gain / max(self.compute_spent, _EPSILON)

    def to_dict(self) -> dict[str, float | int]:
        return {
            "submitted": self.submitted,
            "journal_replays": self.journal_replays,
            "exact_duplicates": self.exact_duplicates,
            "near_duplicates": self.near_duplicates,
            "processed": self.processed,
            "promoted": self.promoted,
            "deferred": self.deferred,
            "quarantined": self.quarantined,
            "challenge_routed": self.challenge_routed,
            "compute_spent": self.compute_spent,
            "information_gain": self.information_gain,
            "knowledge_gain_per_compute": self.knowledge_gain_per_compute,
        }


SignalEstimator = Callable[[Observation, float], AbsorbSignals]
Verifier = Callable[[Observation, AbsorbSignals], Verification]
PromotionSink = Callable[[KnowledgeSnapshot, tuple[SnapshotEntry, ...]], None]


def default_signal_estimator(observation: Observation, duplicate_similarity: float) -> AbsorbSignals:
    novelty = max(0.0, 1.0 - duplicate_similarity)
    evidence_quality = observation.provenance.trust
    evidence_bonus = min(len(observation.provenance.evidence) / 4.0, 1.0)
    return AbsorbSignals(
        novelty=novelty,
        relevance=0.50,
        information_gain=(novelty * 0.70) + (evidence_bonus * 0.30),
        evidence_quality=evidence_quality,
        urgency=observation.urgency,
        downstream_utility=0.50,
        estimated_compute_cost=observation.estimated_compute_cost,
    )


def default_verifier(observation: Observation, signals: AbsorbSignals) -> Verification:
    confidence = min(1.0, observation.provenance.trust * 0.7 + signals.evidence_quality * 0.3)
    return Verification(confidence=confidence, challenge_passed=False)


class AbsorbEngine:
    """Value-scheduled orthogonal absorb worker.

    ``submit`` is intentionally cheap: it only journals and queues work.  A
    separate worker calls ``process``; serving code only reads snapshots.
    """

    def __init__(
        self,
        *,
        journal: IntakeJournal | None = None,
        router: AdaptiveRouter | None = None,
        gate: PromotionGate | None = None,
        snapshots: SnapshotStore | None = None,
        signal_estimator: SignalEstimator | None = None,
        verifier: Verifier | None = None,
        sink: PromotionSink | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self.journal = journal or InMemoryJournal()
        self.router = router or AdaptiveRouter()
        self.gate = gate or PromotionGate()
        self.snapshots = snapshots or SnapshotStore()
        self._signals = signal_estimator or default_signal_estimator
        self._verify = verifier or default_verifier
        self._sink = sink
        self._bus = bus or EventBus()
        self._novelty = NoveltyIndex()
        self._queue: list[tuple[float, int, JournalRecord, AbsorbSignals, float]] = []
        self._sequence = count()
        self.metrics = AbsorbMetrics()

    def submit(self, observation: Observation) -> int:
        before = len(self.journal) if hasattr(self.journal, "__len__") else None
        record = self.journal.append(observation)
        after = len(self.journal) if hasattr(self.journal, "__len__") else None
        if before is not None and after == before:
            return record.offset
        exact, similarity = self._novelty.inspect(observation.content)
        if exact:
            self.metrics.exact_duplicates += 1
            return record.offset
        if similarity >= self.gate.config.max_duplicate_similarity:
            self.metrics.near_duplicates += 1
        signals = self._signals(observation, similarity)
        priority = signals.utility_per_compute
        heapq.heappush(
            self._queue,
            (-priority, next(self._sequence), record, signals, similarity),
        )
        self.metrics.submitted += 1
        self._bus.emit(
            "jeeves.absorb.submitted",
            {"observation_id": observation.observation_id, "offset": record.offset, "priority": priority},
        )
        return record.offset

    def replay(self, start_offset: int = 0) -> int:
        count_replayed = 0
        for record in self.journal.replay(start_offset):
            exact, similarity = self._novelty.inspect(record.observation.content)
            if exact:
                continue
            signals = self._signals(record.observation, similarity)
            heapq.heappush(
                self._queue,
                (-signals.utility_per_compute, next(self._sequence), record, signals, similarity),
            )
            count_replayed += 1
        self.metrics.journal_replays += count_replayed
        return count_replayed

    def process(self, *, max_items: int = 64) -> KnowledgeSnapshot | None:
        if max_items < 1:
            raise AbsorbError("max_items must be positive")
        promoted: list[SnapshotEntry] = []
        for _ in range(min(max_items, len(self._queue))):
            _, _, record, signals, similarity = heapq.heappop(self._queue)
            observation = record.observation

            # Novelty can change while work waits in the queue.  Re-check it at
            # execution time so observations submitted concurrently cannot both
            # cross the promotion boundary with stale duplicate state.
            exact, current_similarity = self._novelty.inspect(observation.content)
            self.metrics.processed += 1
            if exact:
                self.metrics.exact_duplicates += 1
                continue
            updated_similarity = max(similarity, current_similarity)
            if (
                similarity < self.gate.config.max_duplicate_similarity
                <= updated_similarity
            ):
                self.metrics.near_duplicates += 1
            if updated_similarity != similarity:
                similarity = updated_similarity
                signals = self._signals(observation, similarity)

            verification = self._verify(observation, signals)
            lanes = self.router.lanes(signals, verification)
            if AbsorbLane.CHALLENGE in lanes:
                self.metrics.challenge_routed += 1
            candidate = Candidate(
                observation=observation,
                canonical_content=canonicalize(observation.content),
                fingerprint=content_fingerprint(observation.content),
                signals=signals,
                verification=verification,
                duplicate_similarity=similarity,
                lanes=lanes,
            )
            decision = self.gate.evaluate(candidate)
            self.metrics.compute_spent += signals.estimated_compute_cost
            if decision.disposition is Disposition.QUARANTINE:
                self.metrics.quarantined += 1
                self._bus.emit(
                    "jeeves.absorb.quarantined",
                    {"observation_id": observation.observation_id, "reasons": decision.reasons},
                )
                continue
            if decision.disposition is Disposition.DEFER:
                self.metrics.deferred += 1
                self._bus.emit(
                    "jeeves.absorb.deferred",
                    {"observation_id": observation.observation_id, "reasons": decision.reasons},
                )
                continue
            self._novelty.add(observation.content)
            promoted.append(
                SnapshotEntry(
                    observation_id=observation.observation_id,
                    fingerprint=candidate.fingerprint,
                    canonical_content=candidate.canonical_content,
                    target_tier=candidate.target_tier.value,
                    confidence=verification.confidence,
                    source_id=observation.provenance.source_id,
                    journal_offset=record.offset,
                )
            )
            self.metrics.promoted += 1
            self.metrics.information_gain += signals.information_gain

        if not promoted:
            return None
        snapshot = self.snapshots.publish(promoted)
        additions = tuple(promoted)
        if self._sink is not None:
            self._sink(snapshot, additions)
        self._bus.emit(
            "jeeves.absorb.snapshot_promoted",
            {"version": snapshot.version, "digest": snapshot.digest, "entries": len(additions)},
        )
        return snapshot

    @property
    def backlog(self) -> int:
        return len(self._queue)

    def current_snapshot(self) -> KnowledgeSnapshot | None:
        return self.snapshots.current
