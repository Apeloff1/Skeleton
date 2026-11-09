"""Epistemic world model for the Jeeves agent runtime.

This module gives Jeeves an explicit, inspectable model of what it currently
believes about the world.  It is deliberately independent from the language
model: model output may propose hypotheses, but only host-side evidence updates
belief state.

The core design is content-addressed and rollbackable:

* propositions are immutable semantic identities;
* beliefs are mutable probability assignments over propositions;
* evidence updates are append-only revision events with likelihood ratios;
* contradiction groups encode mutually incompatible propositions;
* dependency edges encode support, refutation, implication, and causality;
* snapshots and transactions make rollback/replay deterministic;
* uncertainty and entropy are first-class query targets;
* counterfactual probes estimate which observation would reduce uncertainty;
* hypothesis sets expose competing explanations without collapsing them early.

The implementation uses bounded log-odds updates rather than pretending that
model confidences are calibrated probabilities.  Evidence reliability is
converted into a conservative likelihood ratio and clipped before updating a
belief.  This is intentionally simple enough to audit while still being useful
for sequential evidence accumulation.
"""

from __future__ import annotations

import copy
import math
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

from .evidence import EvidenceArtifact, EvidenceLedger
from .types import (
    AgentContractError,
    Claim,
    EvidenceRef,
    bounded_text,
    finite_number,
    json_safe,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


class WorldModelError(RuntimeError):
    """Base class for world-model failures."""


class BeliefConflict(WorldModelError):
    """Raised when a transaction violates an explicit belief invariant."""


class RevisionKind(str, Enum):
    CREATE = "create"
    SUPPORT = "support"
    REFUTE = "refute"
    SET_PRIOR = "set_prior"
    DECAY = "decay"
    CONTRADICTION_NORMALIZE = "contradiction_normalize"
    ROLLBACK = "rollback"
    MANUAL = "manual"


class EdgeKind(str, Enum):
    SUPPORTS = "supports"
    REFUTES = "refutes"
    IMPLIES = "implies"
    CAUSES = "causes"
    ENABLES = "enables"
    INHIBITS = "inhibits"
    CORRELATES = "correlates"
    SPECIALIZES = "specializes"


class HypothesisStatus(str, Enum):
    OPEN = "open"
    LEADING = "leading"
    WEAKENED = "weakened"
    REJECTED = "rejected"
    RESOLVED = "resolved"


@dataclass(frozen=True, slots=True)
class Proposition:
    proposition_id: str
    subject: str
    predicate: str
    object: Any
    polarity: bool = True
    scope: str = "default"
    temporal_key: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposition_id", require_id("proposition_id", self.proposition_id))
        object.__setattr__(self, "subject", bounded_text("subject", self.subject, maximum=2048))
        object.__setattr__(self, "predicate", bounded_text("predicate", self.predicate, maximum=1024))
        object.__setattr__(self, "object", json_safe(self.object))
        if not isinstance(self.polarity, bool):
            raise AgentContractError("polarity must be boolean")
        object.__setattr__(self, "scope", require_id("scope", self.scope))
        if self.temporal_key is not None:
            object.__setattr__(self, "temporal_key", bounded_text("temporal_key", self.temporal_key, maximum=512))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def semantic_key(self) -> str:
        return stable_fingerprint(
            {
                "subject": self.subject,
                "predicate": self.predicate,
                "object": self.object,
                "polarity": self.polarity,
                "scope": self.scope,
                "temporal_key": self.temporal_key,
            }
        )

    @classmethod
    def create(
        cls,
        subject: str,
        predicate: str,
        object: Any,
        *,
        polarity: bool = True,
        scope: str = "default",
        temporal_key: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "Proposition":
        payload = {
            "subject": subject,
            "predicate": predicate,
            "object": json_safe(object),
            "polarity": bool(polarity),
            "scope": scope,
            "temporal_key": temporal_key,
        }
        return cls(
            proposition_id=stable_id("prop", payload),
            subject=subject,
            predicate=predicate,
            object=object,
            polarity=polarity,
            scope=scope,
            temporal_key=temporal_key,
            metadata=metadata or {},
        )


@dataclass(frozen=True, slots=True)
class BeliefRevision:
    revision_id: str
    proposition_id: str
    kind: RevisionKind
    prior_probability: float
    posterior_probability: float
    evidence_id: str | None
    likelihood_ratio: float
    reliability: float
    at: float
    reason: str
    transaction_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "revision_id", require_id("revision_id", self.revision_id))
        object.__setattr__(self, "proposition_id", require_id("proposition_id", self.proposition_id))
        if not isinstance(self.kind, RevisionKind):
            object.__setattr__(self, "kind", RevisionKind(str(self.kind)))
        object.__setattr__(self, "prior_probability", probability("prior_probability", self.prior_probability))
        object.__setattr__(self, "posterior_probability", probability("posterior_probability", self.posterior_probability))
        lr = finite_number("likelihood_ratio", self.likelihood_ratio)
        if lr <= 0:
            raise AgentContractError("likelihood_ratio must be positive")
        object.__setattr__(self, "likelihood_ratio", lr)
        object.__setattr__(self, "reliability", probability("reliability", self.reliability))
        at = finite_number("at", self.at)
        if at < 0:
            raise AgentContractError("revision time must be non-negative")
        object.__setattr__(self, "at", at)
        object.__setattr__(self, "reason", bounded_text("reason", self.reason, maximum=4096))
        if self.evidence_id is not None:
            object.__setattr__(self, "evidence_id", require_id("evidence_id", self.evidence_id))
        if self.transaction_id is not None:
            object.__setattr__(self, "transaction_id", require_id("transaction_id", self.transaction_id))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class BeliefState:
    proposition: Proposition
    probability: float
    prior_probability: float
    created_at: float
    updated_at: float
    revision_ids: tuple[str, ...] = ()
    supporting_evidence_ids: tuple[str, ...] = ()
    refuting_evidence_ids: tuple[str, ...] = ()
    contradiction_group_ids: tuple[str, ...] = ()
    locked: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.proposition, Proposition):
            raise AgentContractError("proposition must be Proposition")
        object.__setattr__(self, "probability", probability("probability", self.probability))
        object.__setattr__(self, "prior_probability", probability("prior_probability", self.prior_probability))
        created = finite_number("created_at", self.created_at)
        updated = finite_number("updated_at", self.updated_at)
        if created < 0 or updated < created:
            raise AgentContractError("invalid belief timestamps")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        object.__setattr__(self, "revision_ids", tuple(require_id("revision_id", item) for item in self.revision_ids))
        object.__setattr__(self, "supporting_evidence_ids", tuple(require_id("evidence_id", item) for item in self.supporting_evidence_ids))
        object.__setattr__(self, "refuting_evidence_ids", tuple(require_id("evidence_id", item) for item in self.refuting_evidence_ids))
        object.__setattr__(self, "contradiction_group_ids", tuple(require_id("contradiction_group_id", item) for item in self.contradiction_group_ids))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def proposition_id(self) -> str:
        return self.proposition.proposition_id

    @property
    def entropy_bits(self) -> float:
        return binary_entropy(self.probability)

    @property
    def uncertainty(self) -> float:
        return 1.0 - abs(self.probability - 0.5) * 2.0

    @property
    def odds(self) -> float:
        p = clamp_probability(self.probability)
        return p / (1.0 - p)

    @property
    def log_odds(self) -> float:
        return math.log(self.odds)

    @property
    def confidence(self) -> float:
        return max(self.probability, 1.0 - self.probability)


@dataclass(frozen=True, slots=True)
class BeliefEdge:
    edge_id: str
    source_id: str
    target_id: str
    kind: EdgeKind
    weight: float = 1.0
    confidence: float = 1.0
    evidence_ids: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "edge_id", require_id("edge_id", self.edge_id))
        source = require_id("source_id", self.source_id)
        target = require_id("target_id", self.target_id)
        if source == target:
            raise AgentContractError("belief edge cannot self-reference")
        object.__setattr__(self, "source_id", source)
        object.__setattr__(self, "target_id", target)
        if not isinstance(self.kind, EdgeKind):
            object.__setattr__(self, "kind", EdgeKind(str(self.kind)))
        weight = finite_number("weight", self.weight)
        if not -10.0 <= weight <= 10.0:
            raise AgentContractError("edge weight must be in [-10, 10]")
        object.__setattr__(self, "weight", weight)
        object.__setattr__(self, "confidence", probability("confidence", self.confidence))
        object.__setattr__(self, "evidence_ids", tuple(require_id("evidence_id", item) for item in self.evidence_ids))
        created = finite_number("created_at", self.created_at)
        if created < 0:
            raise AgentContractError("edge timestamp must be non-negative")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ContradictionGroup:
    group_id: str
    proposition_ids: tuple[str, ...]
    exclusive: bool = True
    normalized: bool = True
    description: str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        object.__setattr__(self, "group_id", require_id("group_id", self.group_id))
        ids = tuple(require_id("proposition_id", item) for item in self.proposition_ids)
        if len(ids) < 2 or len(set(ids)) != len(ids):
            raise AgentContractError("contradiction group requires at least two unique propositions")
        object.__setattr__(self, "proposition_ids", ids)
        object.__setattr__(self, "description", bounded_text("description", self.description, maximum=4096, allow_empty=True))
        created = finite_number("created_at", self.created_at)
        if created < 0:
            raise AgentContractError("group timestamp must be non-negative")
        object.__setattr__(self, "created_at", created)


@dataclass(frozen=True, slots=True)
class Hypothesis:
    hypothesis_id: str
    label: str
    proposition_ids: tuple[str, ...]
    prior: float = 0.5
    posterior: float = 0.5
    status: HypothesisStatus = HypothesisStatus.OPEN
    explanatory_power: float = 0.5
    complexity_penalty: float = 0.0
    evidence_coverage: float = 0.0
    contradiction_count: int = 0
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "hypothesis_id", require_id("hypothesis_id", self.hypothesis_id))
        object.__setattr__(self, "label", bounded_text("label", self.label, maximum=1024))
        ids = tuple(require_id("proposition_id", item) for item in self.proposition_ids)
        if not ids:
            raise AgentContractError("hypothesis requires propositions")
        object.__setattr__(self, "proposition_ids", ids)
        object.__setattr__(self, "prior", probability("prior", self.prior))
        object.__setattr__(self, "posterior", probability("posterior", self.posterior))
        if not isinstance(self.status, HypothesisStatus):
            object.__setattr__(self, "status", HypothesisStatus(str(self.status)))
        object.__setattr__(self, "explanatory_power", probability("explanatory_power", self.explanatory_power))
        object.__setattr__(self, "complexity_penalty", probability("complexity_penalty", self.complexity_penalty))
        object.__setattr__(self, "evidence_coverage", probability("evidence_coverage", self.evidence_coverage))
        if isinstance(self.contradiction_count, bool) or not isinstance(self.contradiction_count, int) or self.contradiction_count < 0:
            raise AgentContractError("contradiction_count must be non-negative integer")
        object.__setattr__(self, "notes", bounded_text("notes", self.notes, maximum=8192, allow_empty=True))

    @property
    def score(self) -> float:
        return max(0.0, min(1.0, self.posterior * 0.55 + self.explanatory_power * 0.25 + self.evidence_coverage * 0.2 - self.complexity_penalty * 0.15))


@dataclass(frozen=True, slots=True)
class CounterfactualProbe:
    probe_id: str
    proposition_id: str
    current_probability: float
    if_supported_probability: float
    if_refuted_probability: float
    support_information_gain_bits: float
    refute_information_gain_bits: float
    expected_information_gain_bits: float
    priority: float
    rationale: str


@dataclass(frozen=True, slots=True)
class WorldSnapshot:
    snapshot_id: str
    version: int
    at: float
    beliefs: Mapping[str, BeliefState]
    edges: Mapping[str, BeliefEdge]
    contradictions: Mapping[str, ContradictionGroup]
    hypotheses: Mapping[str, Hypothesis]
    revision_count: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class TransactionResult:
    transaction_id: str
    committed: bool
    version_before: int
    version_after: int
    revision_ids: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BeliefUpdate:
    proposition_id: str
    evidence_id: str | None
    direction: int
    reliability: float
    likelihood_ratio: float | None = None
    reason: str = "evidence update"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposition_id", require_id("proposition_id", self.proposition_id))
        if self.evidence_id is not None:
            object.__setattr__(self, "evidence_id", require_id("evidence_id", self.evidence_id))
        if self.direction not in {-1, 1}:
            raise AgentContractError("direction must be -1 or 1")
        object.__setattr__(self, "reliability", probability("reliability", self.reliability))
        if self.likelihood_ratio is not None:
            lr = finite_number("likelihood_ratio", self.likelihood_ratio)
            if lr <= 0:
                raise AgentContractError("likelihood_ratio must be positive")
            object.__setattr__(self, "likelihood_ratio", lr)
        object.__setattr__(self, "reason", bounded_text("reason", self.reason, maximum=4096))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


class BeliefGraph:
    """Thread-safe, rollbackable graph of propositions and probabilistic beliefs."""

    def __init__(
        self,
        *,
        evidence_ledger: EvidenceLedger | None = None,
        clock: Callable[[], float] = time.time,
        min_probability: float = 0.001,
        max_probability: float = 0.999,
        max_revisions: int = 200_000,
        max_snapshots: int = 128,
    ) -> None:
        minimum = probability("min_probability", min_probability)
        maximum = probability("max_probability", max_probability)
        if not 0 < minimum < 0.5 < maximum < 1:
            raise ValueError("probability bounds must straddle 0.5")
        if max_revisions < 1 or max_snapshots < 1:
            raise ValueError("revision and snapshot limits must be positive")
        self.evidence_ledger = evidence_ledger
        self._clock = clock
        self._min_probability = minimum
        self._max_probability = maximum
        self._max_revisions = max_revisions
        self._max_snapshots = max_snapshots
        self._beliefs: dict[str, BeliefState] = {}
        self._semantic_index: dict[str, str] = {}
        self._revisions: dict[str, BeliefRevision] = {}
        self._revision_order: list[str] = []
        self._edges: dict[str, BeliefEdge] = {}
        self._out_edges: dict[str, set[str]] = defaultdict(set)
        self._in_edges: dict[str, set[str]] = defaultdict(set)
        self._contradictions: dict[str, ContradictionGroup] = {}
        self._hypotheses: dict[str, Hypothesis] = {}
        self._snapshots: deque[WorldSnapshot] = deque(maxlen=max_snapshots)
        self._version = 0
        self._lock = threading.RLock()

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def bind_evidence_ledger(self, evidence_ledger: EvidenceLedger) -> None:
        """Rebind evidence custody only when the replacement can satisfy prior references."""

        if not isinstance(evidence_ledger, EvidenceLedger):
            raise TypeError("evidence_ledger must be EvidenceLedger")
        with self._lock:
            if self.evidence_ledger is evidence_ledger:
                return
            referenced = {
                evidence_id
                for belief in self._beliefs.values()
                for evidence_id in (
                    *belief.supporting_evidence_ids,
                    *belief.refuting_evidence_ids,
                )
            }
            missing = sorted(
                evidence_id
                for evidence_id in referenced
                if evidence_ledger.get(evidence_id) is None
            )
            if missing:
                raise WorldModelError(
                    "replacement evidence ledger is missing referenced evidence: "
                    + ", ".join(missing[:8])
                )
            self.evidence_ledger = evidence_ledger

    def upsert_proposition(self, proposition: Proposition, *, prior: float = 0.5, locked: bool = False) -> BeliefState:
        if not isinstance(proposition, Proposition):
            raise TypeError("proposition must be Proposition")
        prior = self._bound_probability(probability("prior", prior))
        with self._lock:
            semantic_existing = self._semantic_index.get(proposition.semantic_key)
            if semantic_existing is not None:
                return self._beliefs[semantic_existing]
            existing = self._beliefs.get(proposition.proposition_id)
            if existing is not None:
                if existing.proposition.semantic_key != proposition.semantic_key:
                    raise BeliefConflict("proposition id collision with different semantics")
                return existing
            now = self._clock()
            revision = self._make_revision(
                proposition_id=proposition.proposition_id,
                kind=RevisionKind.CREATE,
                prior=prior,
                posterior=prior,
                evidence_id=None,
                likelihood_ratio=1.0,
                reliability=1.0,
                reason="initial proposition prior",
            )
            state = BeliefState(
                proposition=proposition,
                probability=prior,
                prior_probability=prior,
                created_at=now,
                updated_at=now,
                revision_ids=(revision.revision_id,),
                locked=bool(locked),
            )
            self._beliefs[proposition.proposition_id] = state
            self._semantic_index[proposition.semantic_key] = proposition.proposition_id
            self._append_revision(revision)
            self._version += 1
            return state

    def belief(self, proposition_id: str) -> BeliefState | None:
        with self._lock:
            return self._beliefs.get(require_id("proposition_id", proposition_id))

    def require_belief(self, proposition_id: str) -> BeliefState:
        belief = self.belief(proposition_id)
        if belief is None:
            raise WorldModelError(f"unknown proposition {proposition_id}")
        return belief

    def beliefs(self, *, scope: str | None = None) -> tuple[BeliefState, ...]:
        with self._lock:
            values = list(self._beliefs.values())
        if scope is not None:
            scope = require_id("scope", scope)
            values = [belief for belief in values if belief.proposition.scope == scope]
        return tuple(sorted(values, key=lambda item: item.proposition_id))

    def uncertain_beliefs(self, *, limit: int = 20, minimum_entropy_bits: float = 0.4) -> tuple[BeliefState, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be positive integer")
        threshold = finite_number("minimum_entropy_bits", minimum_entropy_bits)
        values = [belief for belief in self.beliefs() if belief.entropy_bits >= threshold]
        values.sort(key=lambda belief: (belief.entropy_bits, -belief.updated_at, belief.proposition_id), reverse=True)
        return tuple(values[:limit])

    def revise(self, update: BeliefUpdate, *, transaction_id: str | None = None) -> BeliefState:
        if not isinstance(update, BeliefUpdate):
            raise TypeError("update must be BeliefUpdate")
        with self._lock:
            state = self.require_belief(update.proposition_id)
            if state.locked:
                raise BeliefConflict(f"belief {state.proposition_id} is locked")
            if update.evidence_id is not None and self.evidence_ledger is not None:
                artifact = self.evidence_ledger.require(update.evidence_id)
                if update.reliability > artifact.confidence + 1e-12:
                    raise BeliefConflict("belief update reliability exceeds evidence confidence")
            lr = update.likelihood_ratio or reliability_to_likelihood_ratio(update.reliability)
            if update.direction < 0:
                lr = 1.0 / lr
            posterior = self._posterior_from_lr(state.probability, lr)
            kind = RevisionKind.SUPPORT if update.direction > 0 else RevisionKind.REFUTE
            revision = self._make_revision(
                proposition_id=state.proposition_id,
                kind=kind,
                prior=state.probability,
                posterior=posterior,
                evidence_id=update.evidence_id,
                likelihood_ratio=lr,
                reliability=update.reliability,
                reason=update.reason,
                transaction_id=transaction_id,
                metadata=update.metadata,
            )
            supporting = state.supporting_evidence_ids
            refuting = state.refuting_evidence_ids
            if update.evidence_id is not None:
                if update.direction > 0 and update.evidence_id not in supporting:
                    supporting = supporting + (update.evidence_id,)
                if update.direction < 0 and update.evidence_id not in refuting:
                    refuting = refuting + (update.evidence_id,)
            revised = replace(
                state,
                probability=posterior,
                updated_at=self._clock(),
                revision_ids=state.revision_ids + (revision.revision_id,),
                supporting_evidence_ids=supporting,
                refuting_evidence_ids=refuting,
            )
            self._beliefs[state.proposition_id] = revised
            self._append_revision(revision)
            self._version += 1
            self._normalize_groups_for(state.proposition_id, transaction_id=transaction_id)
            self._propagate_local(state.proposition_id, transaction_id=transaction_id)
            return self._beliefs[state.proposition_id]

    def apply_transaction(self, updates: Sequence[BeliefUpdate], *, strict: bool = True) -> TransactionResult:
        if not updates:
            raise ValueError("transaction requires at least one update")
        if any(not isinstance(update, BeliefUpdate) for update in updates):
            raise TypeError("transaction updates must be BeliefUpdate")
        transaction_id = stable_id(
            "tx",
            {
                "version": self.version,
                "updates": [
                    (update.proposition_id, update.evidence_id, update.direction, update.reliability, update.likelihood_ratio)
                    for update in updates
                ],
                "time": self._clock(),
            },
        )
        with self._lock:
            version_before = self._version
            state_backup = self._transaction_backup()
            revisions_before = len(self._revision_order)
            try:
                for update in updates:
                    self.revise(update, transaction_id=transaction_id)
                if strict:
                    self._validate_invariants()
                revision_ids = tuple(self._revision_order[revisions_before:])
                return TransactionResult(transaction_id, True, version_before, self._version, revision_ids)
            except Exception as exc:
                self._restore_transaction_backup(state_backup)
                return TransactionResult(
                    transaction_id,
                    False,
                    version_before,
                    self._version,
                    (),
                    error=f"{type(exc).__name__}: {str(exc)[:2048]}",
                )

    def set_prior(self, proposition_id: str, prior: float, *, reason: str = "manual prior update") -> BeliefState:
        prior = self._bound_probability(probability("prior", prior))
        with self._lock:
            state = self.require_belief(proposition_id)
            if state.locked:
                raise BeliefConflict("locked belief prior cannot be changed")
            revision = self._make_revision(
                proposition_id=state.proposition_id,
                kind=RevisionKind.SET_PRIOR,
                prior=state.probability,
                posterior=prior,
                evidence_id=None,
                likelihood_ratio=1.0,
                reliability=1.0,
                reason=reason,
            )
            revised = replace(
                state,
                probability=prior,
                prior_probability=prior,
                updated_at=self._clock(),
                revision_ids=state.revision_ids + (revision.revision_id,),
            )
            self._beliefs[state.proposition_id] = revised
            self._append_revision(revision)
            self._version += 1
            self._normalize_groups_for(state.proposition_id)
            return revised

    def decay(self, *, half_life_seconds: float, toward: float = 0.5, now: float | None = None) -> tuple[BeliefState, ...]:
        half_life = finite_number("half_life_seconds", half_life_seconds)
        if half_life <= 0:
            raise ValueError("half_life_seconds must be positive")
        toward = self._bound_probability(probability("toward", toward))
        now = self._clock() if now is None else finite_number("now", now)
        changed: list[BeliefState] = []
        with self._lock:
            for proposition_id in sorted(self._beliefs):
                state = self._beliefs[proposition_id]
                if state.locked:
                    continue
                age = max(0.0, now - state.updated_at)
                if age <= 0:
                    continue
                retention = math.exp(-math.log(2) * age / half_life)
                posterior = toward + (state.probability - toward) * retention
                posterior = self._bound_probability(posterior)
                if abs(posterior - state.probability) < 1e-9:
                    continue
                revision = self._make_revision(
                    proposition_id=state.proposition_id,
                    kind=RevisionKind.DECAY,
                    prior=state.probability,
                    posterior=posterior,
                    evidence_id=None,
                    likelihood_ratio=1.0,
                    reliability=1.0,
                    reason=f"temporal decay half_life={half_life}",
                )
                revised = replace(
                    state,
                    probability=posterior,
                    updated_at=now,
                    revision_ids=state.revision_ids + (revision.revision_id,),
                )
                self._beliefs[state.proposition_id] = revised
                self._append_revision(revision)
                changed.append(revised)
            if changed:
                self._version += 1
                for group in self._contradictions.values():
                    if group.normalized:
                        self._normalize_group(group)
        return tuple(changed)

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        kind: EdgeKind,
        *,
        weight: float = 1.0,
        confidence: float = 1.0,
        evidence_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> BeliefEdge:
        source_id = require_id("source_id", source_id)
        target_id = require_id("target_id", target_id)
        self.require_belief(source_id)
        self.require_belief(target_id)
        if not isinstance(kind, EdgeKind):
            kind = EdgeKind(str(kind))
        payload = {
            "source": source_id,
            "target": target_id,
            "kind": kind.value,
            "weight": weight,
            "evidence": list(evidence_ids),
        }
        edge = BeliefEdge(
            edge_id=stable_id("edge", payload),
            source_id=source_id,
            target_id=target_id,
            kind=kind,
            weight=weight,
            confidence=confidence,
            evidence_ids=tuple(evidence_ids),
            created_at=self._clock(),
            metadata=metadata or {},
        )
        with self._lock:
            existing = self._edges.get(edge.edge_id)
            if existing is not None:
                return existing
            self._edges[edge.edge_id] = edge
            self._out_edges[source_id].add(edge.edge_id)
            self._in_edges[target_id].add(edge.edge_id)
            self._version += 1
            return edge

    def edges_from(self, proposition_id: str) -> tuple[BeliefEdge, ...]:
        proposition_id = require_id("proposition_id", proposition_id)
        with self._lock:
            return tuple(sorted((self._edges[edge_id] for edge_id in self._out_edges.get(proposition_id, ())), key=lambda edge: edge.edge_id))

    def edges_to(self, proposition_id: str) -> tuple[BeliefEdge, ...]:
        proposition_id = require_id("proposition_id", proposition_id)
        with self._lock:
            return tuple(sorted((self._edges[edge_id] for edge_id in self._in_edges.get(proposition_id, ())), key=lambda edge: edge.edge_id))

    def add_contradiction_group(
        self,
        proposition_ids: Sequence[str],
        *,
        exclusive: bool = True,
        normalized: bool = True,
        description: str = "",
    ) -> ContradictionGroup:
        ids = tuple(require_id("proposition_id", item) for item in proposition_ids)
        for proposition_id in ids:
            self.require_belief(proposition_id)
        group = ContradictionGroup(
            group_id=stable_id("contradiction_group", {"ids": sorted(ids), "exclusive": exclusive}),
            proposition_ids=ids,
            exclusive=exclusive,
            normalized=normalized,
            description=description,
            created_at=self._clock(),
        )
        with self._lock:
            existing = self._contradictions.get(group.group_id)
            if existing is not None:
                return existing
            self._contradictions[group.group_id] = group
            for proposition_id in ids:
                state = self._beliefs[proposition_id]
                self._beliefs[proposition_id] = replace(
                    state,
                    contradiction_group_ids=tuple(sorted(set(state.contradiction_group_ids + (group.group_id,)))),
                )
            if normalized:
                self._normalize_group(group)
            self._version += 1
            return group

    def contradiction_pressure(self, proposition_id: str) -> float:
        state = self.require_belief(proposition_id)
        pressure = 0.0
        with self._lock:
            for group_id in state.contradiction_group_ids:
                group = self._contradictions[group_id]
                competitors = [self._beliefs[item].probability for item in group.proposition_ids if item != proposition_id]
                if competitors:
                    pressure = max(pressure, max(competitors))
        return pressure

    def register_hypothesis(
        self,
        label: str,
        proposition_ids: Sequence[str],
        *,
        prior: float = 0.5,
        explanatory_power: float = 0.5,
        complexity_penalty: float = 0.0,
        notes: str = "",
    ) -> Hypothesis:
        ids = tuple(require_id("proposition_id", item) for item in proposition_ids)
        for proposition_id in ids:
            self.require_belief(proposition_id)
        hypothesis = Hypothesis(
            hypothesis_id=stable_id("hypothesis", {"label": label, "propositions": ids}),
            label=label,
            proposition_ids=ids,
            prior=prior,
            posterior=prior,
            explanatory_power=explanatory_power,
            complexity_penalty=complexity_penalty,
            notes=notes,
        )
        with self._lock:
            existing = self._hypotheses.get(hypothesis.hypothesis_id)
            if existing is not None:
                return existing
            self._hypotheses[hypothesis.hypothesis_id] = hypothesis
            self._version += 1
        return self.refresh_hypothesis(hypothesis.hypothesis_id)

    def refresh_hypothesis(self, hypothesis_id: str) -> Hypothesis:
        hypothesis_id = require_id("hypothesis_id", hypothesis_id)
        with self._lock:
            hypothesis = self._hypotheses.get(hypothesis_id)
            if hypothesis is None:
                raise WorldModelError("unknown hypothesis")
            states = [self._beliefs[item] for item in hypothesis.proposition_ids]
            geometric = math.exp(sum(math.log(clamp_probability(state.probability)) for state in states) / len(states))
            evidence_ids: set[str] = set()
            contradictions = 0
            for state in states:
                evidence_ids.update(state.supporting_evidence_ids)
                evidence_ids.update(state.refuting_evidence_ids)
                contradictions += sum(
                    1
                    for group_id in state.contradiction_group_ids
                    if self.contradiction_pressure(state.proposition_id) >= 0.55
                )
            covered = sum(1 for state in states if state.supporting_evidence_ids or state.refuting_evidence_ids)
            evidence_coverage = covered / len(states)
            posterior = max(
                0.001,
                min(
                    0.999,
                    geometric * (0.75 + hypothesis.explanatory_power * 0.25) * (1.0 - hypothesis.complexity_penalty * 0.2),
                ),
            )
            if contradictions:
                posterior *= max(0.1, 1.0 - min(0.8, contradictions * 0.15))
            if posterior >= 0.72:
                status = HypothesisStatus.LEADING
            elif posterior <= 0.18:
                status = HypothesisStatus.REJECTED
            elif posterior < hypothesis.prior * 0.75:
                status = HypothesisStatus.WEAKENED
            else:
                status = HypothesisStatus.OPEN
            revised = replace(
                hypothesis,
                posterior=max(0.0, min(1.0, posterior)),
                evidence_coverage=evidence_coverage,
                contradiction_count=contradictions,
                status=status,
            )
            self._hypotheses[hypothesis_id] = revised
            return revised

    def hypotheses(self, *, refresh: bool = True) -> tuple[Hypothesis, ...]:
        with self._lock:
            ids = list(self._hypotheses)
        values = [self.refresh_hypothesis(item) if refresh else self._hypotheses[item] for item in ids]
        values.sort(key=lambda item: (item.score, item.posterior, item.hypothesis_id), reverse=True)
        return tuple(values)

    def best_hypothesis(self) -> Hypothesis | None:
        values = self.hypotheses(refresh=True)
        return values[0] if values else None

    def from_claim(self, claim: Claim, *, scope: str = "claims", prior_strength: float = 0.5) -> BeliefState:
        if not isinstance(claim, Claim):
            raise TypeError("claim must be Claim")
        proposition = Proposition.create(
            claim.subject or "claim",
            "asserts",
            claim.text,
            scope=scope,
            metadata={"claim_id": claim.claim_id, "derived": claim.derived},
        )
        state = self.upsert_proposition(proposition, prior=prior_strength)
        if not claim.evidence:
            return state
        updates: list[BeliefUpdate] = []
        for ref in claim.evidence:
            reliability = min(claim.confidence, ref.confidence)
            updates.append(
                BeliefUpdate(
                    proposition_id=proposition.proposition_id,
                    evidence_id=ref.evidence_id,
                    direction=1,
                    reliability=reliability,
                    reason=f"grounded claim {claim.claim_id}",
                    metadata={"claim_id": claim.claim_id},
                )
            )
        result = self.apply_transaction(updates, strict=True)
        if not result.committed:
            raise BeliefConflict(result.error or "claim transaction failed")
        return self.require_belief(proposition.proposition_id)

    def counterfactual_probe(
        self,
        proposition_id: str,
        *,
        hypothetical_reliability: float = 0.8,
        observation_cost: float = 0.1,
    ) -> CounterfactualProbe:
        state = self.require_belief(proposition_id)
        reliability = probability("hypothetical_reliability", hypothetical_reliability)
        cost = probability("observation_cost", observation_cost)
        lr = reliability_to_likelihood_ratio(reliability)
        supported = self._posterior_from_lr(state.probability, lr)
        refuted = self._posterior_from_lr(state.probability, 1.0 / lr)
        current_entropy = binary_entropy(state.probability)
        support_gain = max(0.0, current_entropy - binary_entropy(supported))
        refute_gain = max(0.0, current_entropy - binary_entropy(refuted))
        expected = state.probability * support_gain + (1.0 - state.probability) * refute_gain
        contradiction_bonus = self.contradiction_pressure(proposition_id) * 0.25
        priority = max(0.0, min(1.0, expected + contradiction_bonus - cost * 0.3))
        return CounterfactualProbe(
            probe_id=stable_id("probe", {"proposition": proposition_id, "version": self.version, "reliability": reliability}),
            proposition_id=proposition_id,
            current_probability=state.probability,
            if_supported_probability=supported,
            if_refuted_probability=refuted,
            support_information_gain_bits=support_gain,
            refute_information_gain_bits=refute_gain,
            expected_information_gain_bits=expected,
            priority=priority,
            rationale=(
                f"entropy={current_entropy:.4f} bits; expected_information_gain={expected:.4f}; "
                f"contradiction_pressure={self.contradiction_pressure(proposition_id):.4f}; cost={cost:.4f}"
            ),
        )

    def ranked_probes(self, *, limit: int = 10, minimum_entropy_bits: float = 0.2) -> tuple[CounterfactualProbe, ...]:
        probes = [
            self.counterfactual_probe(belief.proposition_id)
            for belief in self.uncertain_beliefs(limit=max(limit * 4, 20), minimum_entropy_bits=minimum_entropy_bits)
        ]
        probes.sort(key=lambda probe: (probe.priority, probe.expected_information_gain_bits, probe.probe_id), reverse=True)
        return tuple(probes[:limit])

    def dependency_neighborhood(self, proposition_id: str, *, depth: int = 2, limit: int = 100) -> tuple[BeliefState, ...]:
        proposition_id = require_id("proposition_id", proposition_id)
        if depth < 0 or limit < 1:
            raise ValueError("invalid neighborhood bounds")
        self.require_belief(proposition_id)
        seen = {proposition_id}
        frontier = {proposition_id}
        for _ in range(depth):
            next_frontier: set[str] = set()
            for current in frontier:
                for edge in self.edges_from(current):
                    next_frontier.add(edge.target_id)
                for edge in self.edges_to(current):
                    next_frontier.add(edge.source_id)
            next_frontier -= seen
            if not next_frontier:
                break
            seen.update(next_frontier)
            frontier = next_frontier
            if len(seen) >= limit:
                break
        values = [self.require_belief(item) for item in sorted(seen)[:limit]]
        return tuple(values)

    def snapshot(self, *, persist: bool = True) -> WorldSnapshot:
        with self._lock:
            beliefs = copy.deepcopy(self._beliefs)
            edges = copy.deepcopy(self._edges)
            contradictions = copy.deepcopy(self._contradictions)
            hypotheses = copy.deepcopy(self._hypotheses)
            payload = {
                "version": self._version,
                "beliefs": [(key, value.probability, value.revision_ids) for key, value in sorted(beliefs.items())],
                "edges": [(key, edge.source_id, edge.target_id, edge.kind.value, edge.weight) for key, edge in sorted(edges.items())],
                "contradictions": [(key, group.proposition_ids) for key, group in sorted(contradictions.items())],
                "hypotheses": [(key, item.posterior, item.status.value) for key, item in sorted(hypotheses.items())],
                "revision_count": len(self._revision_order),
            }
            fingerprint = stable_fingerprint(payload)
            snapshot = WorldSnapshot(
                snapshot_id=stable_id("world_snapshot", {"fingerprint": fingerprint, "time": self._clock()}),
                version=self._version,
                at=self._clock(),
                beliefs=beliefs,
                edges=edges,
                contradictions=contradictions,
                hypotheses=hypotheses,
                revision_count=len(self._revision_order),
                fingerprint=fingerprint,
            )
            if persist:
                self._snapshots.append(snapshot)
            return snapshot

    def rollback(self, snapshot_id: str) -> WorldSnapshot:
        snapshot_id = require_id("snapshot_id", snapshot_id)
        with self._lock:
            snapshot = next((item for item in reversed(self._snapshots) if item.snapshot_id == snapshot_id), None)
            if snapshot is None:
                raise WorldModelError("unknown world snapshot")
            self._beliefs = copy.deepcopy(dict(snapshot.beliefs))
            self._semantic_index = {state.proposition.semantic_key: proposition_id for proposition_id, state in self._beliefs.items()}
            self._edges = copy.deepcopy(dict(snapshot.edges))
            self._out_edges = defaultdict(set)
            self._in_edges = defaultdict(set)
            for edge_id, edge in self._edges.items():
                self._out_edges[edge.source_id].add(edge_id)
                self._in_edges[edge.target_id].add(edge_id)
            self._contradictions = copy.deepcopy(dict(snapshot.contradictions))
            self._hypotheses = copy.deepcopy(dict(snapshot.hypotheses))
            self._revision_order = self._revision_order[: snapshot.revision_count]
            self._revisions = {revision_id: self._revisions[revision_id] for revision_id in self._revision_order if revision_id in self._revisions}
            self._version = snapshot.version + 1
            return self.snapshot(persist=True)

    def revisions_for(self, proposition_id: str) -> tuple[BeliefRevision, ...]:
        state = self.require_belief(proposition_id)
        with self._lock:
            return tuple(self._revisions[item] for item in state.revision_ids if item in self._revisions)

    def world_entropy_bits(self) -> float:
        values = self.beliefs()
        return sum(state.entropy_bits for state in values)

    def summary(self, *, top_uncertain: int = 8, top_hypotheses: int = 5) -> dict[str, Any]:
        uncertain = self.uncertain_beliefs(limit=top_uncertain, minimum_entropy_bits=0.0)
        hypotheses = self.hypotheses(refresh=True)[:top_hypotheses]
        return {
            "version": self.version,
            "belief_count": len(self.beliefs()),
            "edge_count": len(self._edges),
            "contradiction_group_count": len(self._contradictions),
            "hypothesis_count": len(self._hypotheses),
            "world_entropy_bits": self.world_entropy_bits(),
            "uncertain": [
                {
                    "proposition_id": state.proposition_id,
                    "subject": state.proposition.subject,
                    "predicate": state.proposition.predicate,
                    "object": state.proposition.object,
                    "probability": state.probability,
                    "entropy_bits": state.entropy_bits,
                    "contradiction_pressure": self.contradiction_pressure(state.proposition_id),
                }
                for state in uncertain
            ],
            "hypotheses": [
                {
                    "hypothesis_id": item.hypothesis_id,
                    "label": item.label,
                    "posterior": item.posterior,
                    "score": item.score,
                    "status": item.status.value,
                    "evidence_coverage": item.evidence_coverage,
                    "contradiction_count": item.contradiction_count,
                }
                for item in hypotheses
            ],
            "fingerprint": self.snapshot(persist=False).fingerprint,
        }

    def _make_revision(
        self,
        *,
        proposition_id: str,
        kind: RevisionKind,
        prior: float,
        posterior: float,
        evidence_id: str | None,
        likelihood_ratio: float,
        reliability: float,
        reason: str,
        transaction_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> BeliefRevision:
        at = self._clock()
        payload = {
            "proposition_id": proposition_id,
            "kind": kind.value,
            "prior": prior,
            "posterior": posterior,
            "evidence_id": evidence_id,
            "likelihood_ratio": likelihood_ratio,
            "reliability": reliability,
            "reason": reason,
            "transaction_id": transaction_id,
            "at": at,
            "sequence": len(self._revision_order),
        }
        return BeliefRevision(
            revision_id=stable_id("revision", payload),
            proposition_id=proposition_id,
            kind=kind,
            prior_probability=prior,
            posterior_probability=posterior,
            evidence_id=evidence_id,
            likelihood_ratio=likelihood_ratio,
            reliability=reliability,
            at=at,
            reason=reason,
            transaction_id=transaction_id,
            metadata=metadata or {},
        )

    def _append_revision(self, revision: BeliefRevision) -> None:
        if len(self._revision_order) >= self._max_revisions:
            raise WorldModelError("belief revision budget exhausted")
        self._revisions[revision.revision_id] = revision
        self._revision_order.append(revision.revision_id)

    def _posterior_from_lr(self, prior: float, likelihood_ratio: float) -> float:
        prior = self._bound_probability(prior)
        lr = max(1e-6, min(1e6, float(likelihood_ratio)))
        odds = prior / (1.0 - prior)
        posterior_odds = odds * lr
        posterior = posterior_odds / (1.0 + posterior_odds)
        return self._bound_probability(posterior)

    def _bound_probability(self, value: float) -> float:
        return max(self._min_probability, min(self._max_probability, float(value)))

    def _normalize_groups_for(self, proposition_id: str, *, transaction_id: str | None = None) -> None:
        state = self._beliefs[proposition_id]
        for group_id in state.contradiction_group_ids:
            group = self._contradictions[group_id]
            if group.normalized:
                self._normalize_group(group, transaction_id=transaction_id)

    def _normalize_group(self, group: ContradictionGroup, *, transaction_id: str | None = None) -> None:
        if not group.exclusive:
            return
        states = [self._beliefs[item] for item in group.proposition_ids]
        total = sum(state.probability for state in states)
        if total <= 0:
            return
        if total <= 1.0 + 1e-9:
            return
        for state in states:
            if state.locked:
                continue
            posterior = self._bound_probability(state.probability / total)
            if abs(posterior - state.probability) < 1e-12:
                continue
            revision = self._make_revision(
                proposition_id=state.proposition_id,
                kind=RevisionKind.CONTRADICTION_NORMALIZE,
                prior=state.probability,
                posterior=posterior,
                evidence_id=None,
                likelihood_ratio=1.0,
                reliability=1.0,
                reason=f"normalize exclusive contradiction group {group.group_id}",
                transaction_id=transaction_id,
            )
            self._beliefs[state.proposition_id] = replace(
                state,
                probability=posterior,
                updated_at=self._clock(),
                revision_ids=state.revision_ids + (revision.revision_id,),
            )
            self._append_revision(revision)

    def _propagate_local(self, source_id: str, *, transaction_id: str | None = None) -> None:
        source = self._beliefs[source_id]
        for edge in self.edges_from(source_id):
            if edge.kind not in {EdgeKind.SUPPORTS, EdgeKind.REFUTES, EdgeKind.IMPLIES, EdgeKind.CAUSES, EdgeKind.INHIBITS}:
                continue
            target = self._beliefs[edge.target_id]
            if target.locked:
                continue
            source_strength = abs(source.probability - 0.5) * 2.0
            if source_strength < 0.05:
                continue
            signed = edge.weight * edge.confidence * source_strength
            if edge.kind in {EdgeKind.REFUTES, EdgeKind.INHIBITS}:
                signed *= -1.0
            elif source.probability < 0.5:
                signed *= -1.0
            lr = math.exp(max(-2.0, min(2.0, signed * 0.35)))
            posterior = self._posterior_from_lr(target.probability, lr)
            if abs(posterior - target.probability) < 1e-6:
                continue
            revision = self._make_revision(
                proposition_id=target.proposition_id,
                kind=RevisionKind.MANUAL,
                prior=target.probability,
                posterior=posterior,
                evidence_id=None,
                likelihood_ratio=lr,
                reliability=edge.confidence,
                reason=f"local propagation via edge {edge.edge_id}",
                transaction_id=transaction_id,
                metadata={"source_id": source_id, "edge_id": edge.edge_id},
            )
            self._beliefs[target.proposition_id] = replace(
                target,
                probability=posterior,
                updated_at=self._clock(),
                revision_ids=target.revision_ids + (revision.revision_id,),
            )
            self._append_revision(revision)

    def _validate_invariants(self) -> None:
        for proposition_id, state in self._beliefs.items():
            if proposition_id != state.proposition.proposition_id:
                raise BeliefConflict("belief dictionary key mismatch")
            if not self._min_probability <= state.probability <= self._max_probability:
                raise BeliefConflict("belief probability outside configured bounds")
            for group_id in state.contradiction_group_ids:
                if group_id not in self._contradictions:
                    raise BeliefConflict("belief references missing contradiction group")
        for edge in self._edges.values():
            if edge.source_id not in self._beliefs or edge.target_id not in self._beliefs:
                raise BeliefConflict("edge references missing proposition")
        for group in self._contradictions.values():
            if any(item not in self._beliefs for item in group.proposition_ids):
                raise BeliefConflict("contradiction group references missing proposition")
            if group.exclusive and group.normalized:
                total = sum(self._beliefs[item].probability for item in group.proposition_ids)
                if total > 1.000001:
                    raise BeliefConflict("exclusive normalized contradiction group exceeds probability mass 1")

    def _transaction_backup(self) -> dict[str, Any]:
        return {
            "beliefs": copy.deepcopy(self._beliefs),
            "semantic_index": copy.deepcopy(self._semantic_index),
            "revisions": copy.deepcopy(self._revisions),
            "revision_order": list(self._revision_order),
            "edges": copy.deepcopy(self._edges),
            "out_edges": copy.deepcopy(self._out_edges),
            "in_edges": copy.deepcopy(self._in_edges),
            "contradictions": copy.deepcopy(self._contradictions),
            "hypotheses": copy.deepcopy(self._hypotheses),
            "version": self._version,
        }

    def _restore_transaction_backup(self, backup: Mapping[str, Any]) -> None:
        self._beliefs = backup["beliefs"]
        self._semantic_index = backup["semantic_index"]
        self._revisions = backup["revisions"]
        self._revision_order = backup["revision_order"]
        self._edges = backup["edges"]
        self._out_edges = backup["out_edges"]
        self._in_edges = backup["in_edges"]
        self._contradictions = backup["contradictions"]
        self._hypotheses = backup["hypotheses"]
        self._version = backup["version"]


class WorldModel:
    """Higher-level facade combining scoped belief graphs and evidence custody."""

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._graphs: dict[str, BeliefGraph] = {}
        self._lock = threading.RLock()

    def graph(self, scope: str, *, evidence_ledger: EvidenceLedger | None = None) -> BeliefGraph:
        scope = require_id("scope", scope)
        with self._lock:
            graph = self._graphs.get(scope)
            if graph is None:
                graph = BeliefGraph(evidence_ledger=evidence_ledger, clock=self._clock)
                self._graphs[scope] = graph
            elif evidence_ledger is not None:
                graph.bind_evidence_ledger(evidence_ledger)
            return graph

    def discard(self, scope: str) -> bool:
        """Release a scoped graph from the model registry."""

        scope = require_id("scope", scope)
        with self._lock:
            return self._graphs.pop(scope, None) is not None

    def scopes(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._graphs))

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {scope: graph.summary() for scope, graph in sorted(self._graphs.items())}

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(self.summary())


def clamp_probability(value: float, epsilon: float = 1e-9) -> float:
    value = float(value)
    return max(epsilon, min(1.0 - epsilon, value))


def binary_entropy(probability_value: float) -> float:
    p = clamp_probability(probability_value)
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


def reliability_to_likelihood_ratio(reliability: float, *, max_lr: float = 20.0) -> float:
    """Convert evidence reliability into a conservative likelihood ratio.

    Reliability <= 0.5 is intentionally weak evidence and returns LR near 1.
    Above 0.5 the curve grows smoothly but is capped, preventing one observation
    from forcing posterior probability to 0 or 1.
    """

    r = probability("reliability", reliability)
    maximum = finite_number("max_lr", max_lr)
    if maximum <= 1.0:
        raise ValueError("max_lr must be > 1")
    if r <= 0.5:
        return 1.0 + (r / 0.5) * 0.15
    normalized = (r - 0.5) / 0.5
    return min(maximum, math.exp(normalized * math.log(maximum)))


def proposition_from_artifact(
    artifact: EvidenceArtifact,
    *,
    subject: str,
    predicate: str,
    scope: str = "evidence",
    temporal_key: str | None = None,
) -> Proposition:
    if not isinstance(artifact, EvidenceArtifact):
        raise TypeError("artifact must be EvidenceArtifact")
    return Proposition.create(
        subject,
        predicate,
        artifact.payload,
        scope=scope,
        temporal_key=temporal_key,
        metadata={
            "evidence_id": artifact.evidence_id,
            "source": artifact.source,
            "confidence": artifact.confidence,
            "observed_at": artifact.observed_at,
        },
    )
