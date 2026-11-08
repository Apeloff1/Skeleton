"""Evidence-bound competing hypothesis calculus for canonical VOL-249.

This is an authority-neutral, process-local research component. Its plausibility
scores are *not* facts, measurements, calibration claims, or action permissions.
All source custody belongs to the existing ResearchSourceRegistry.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re

from .source_lineage import ResearchLineageError, ResearchSourceRegistry, SourceStatus

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{1,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 4096


class HypothesisError(ValueError):
    """Hypothesis or evidence cannot be admitted without weakening its bounds."""


def _id(value: str, name: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise HypothesisError(name + " must be a stable bounded identifier")
    return value


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_TEXT:
        raise HypothesisError(name + " must be nonempty bounded text")
    return value.strip()


def _sha(value: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise HypothesisError("source_digest must be a canonical sha256")
    return value


def _finite(value: float, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise HypothesisError(name + " must be a finite numeric value")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise HypothesisError(name + " outside admitted finite interval") from exc
    if not math.isfinite(number) or not low <= number <= high:
        raise HypothesisError(name + " outside admitted finite interval")
    return number


def _hash(payload: object) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class EvidenceMode(str, Enum):
    OBSERVED = "observed"
    SIMULATED = "simulated"
    INTERPRETED = "interpreted"


class EvidenceDirection(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class Hypothesis:
    hypothesis_id: str
    question_id: str
    proposition: str
    falsifier: str
    prior_plausibility: float

    def __post_init__(self) -> None:
        _id(self.hypothesis_id, "hypothesis_id")
        _id(self.question_id, "question_id")
        object.__setattr__(self, "proposition", _text(self.proposition, "proposition"))
        object.__setattr__(self, "falsifier", _text(self.falsifier, "falsifier"))
        _finite(self.prior_plausibility, "prior_plausibility", 0.001, 0.999)

    @property
    def digest(self) -> str:
        return _hash({
            "schema": "skeleton.research.hypothesis.v1",
            "id": self.hypothesis_id, "question": self.question_id,
            "proposition": self.proposition, "falsifier": self.falsifier,
            "prior": self.prior_plausibility,
        })


@dataclass(frozen=True, slots=True)
class HypothesisEvidence:
    event_id: str
    hypothesis_id: str
    source_id: str
    source_digest: str
    method: str
    mode: EvidenceMode
    direction: EvidenceDirection
    likelihood_ratio: float
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _id(self.event_id, "event_id")
        _id(self.hypothesis_id, "hypothesis_id")
        _id(self.source_id, "source_id")
        _sha(self.source_digest)
        object.__setattr__(self, "method", _text(self.method, "method"))
        if not isinstance(self.mode, EvidenceMode):
            raise HypothesisError("mode must be a typed EvidenceMode")
        if not isinstance(self.direction, EvidenceDirection):
            raise HypothesisError("direction must be typed EvidenceDirection")
        ratio = _finite(self.likelihood_ratio, "likelihood_ratio", 0.05, 20.0)
        if (self.direction is EvidenceDirection.SUPPORTS and ratio <= 1.0) or (
            self.direction is EvidenceDirection.CONTRADICTS and ratio >= 1.0
        ) or (self.direction is EvidenceDirection.NEUTRAL and ratio != 1.0):
            raise HypothesisError("likelihood ratio contradicts evidence direction")
        if not isinstance(self.limitations, tuple) or not self.limitations or (
            len(self.limitations) > 24
        ):
            raise HypothesisError("explicit bounded limitations required")
        if len(set(self.limitations)) != len(self.limitations):
            raise HypothesisError("duplicate limitations")
        for limitation in self.limitations:
            _text(limitation, "limitation")

    @property
    def digest(self) -> str:
        return _hash({
            "schema": "skeleton.research.hypothesis-evidence.v1",
            "event": self.event_id, "hypothesis": self.hypothesis_id,
            "source": self.source_id, "source_digest": self.source_digest,
            "method": self.method, "mode": self.mode.value,
            "direction": self.direction.value, "likelihood_ratio": self.likelihood_ratio,
            "limitations": self.limitations,
        })


@dataclass(frozen=True, slots=True)
class HypothesisAssessment:
    hypothesis_id: str
    question_id: str
    plausibility: float
    observed_sources: tuple[str, ...]
    excluded_events: tuple[str, ...]
    classification: str
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class HypothesisComparison:
    question_id: str
    rankings: tuple[HypothesisAssessment, ...]
    winner: str | None
    resolution: str
    receipt_digest: str


class HypothesisLedger:
    """Bounded, non-authorizing comparisons tied to live canonical source custody.

    Duplicate IDs replay idempotently; reusing a source under another event ID
    for the same hypothesis is disallowed to limit correlated-evidence inflation.
    Withdrawal is an immutable audit tombstone, not deletion or source restoration.
    """

    def __init__(
        self, sources: ResearchSourceRegistry, *,
        max_hypotheses: int = 128, max_evidence: int = 1024,
    ) -> None:
        if not isinstance(sources, ResearchSourceRegistry):
            raise HypothesisError("canonical ResearchSourceRegistry required")
        for value, name, limit in (
            (max_hypotheses, "max_hypotheses", 4096),
            (max_evidence, "max_evidence", 65536),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= limit:
                raise HypothesisError(name + " outside admitted bounds")
        self._sources = sources
        self._max_hypotheses = max_hypotheses
        self._max_evidence = max_evidence
        self._hypotheses: dict[str, Hypothesis] = {}
        self._events: dict[str, HypothesisEvidence] = {}
        self._withdrawals: dict[str, str] = {}

    @property
    def sources(self) -> ResearchSourceRegistry:
        """Canonical shared custody owner; no authority is transferred."""
        return self._sources

    def register(self, hypothesis: Hypothesis) -> str:
        if not isinstance(hypothesis, Hypothesis):
            raise HypothesisError("typed hypothesis required")
        prior = self._hypotheses.get(hypothesis.hypothesis_id)
        if prior is not None and prior != hypothesis:
            raise HypothesisError("hypothesis identity collision")
        if prior is None and len(self._hypotheses) >= self._max_hypotheses:
            raise HypothesisError("hypothesis capacity exceeded")
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis
        return hypothesis.digest

    def _live(self, event: HypothesisEvidence) -> None:
        try:
            source = self._sources.source(event.source_id)
        except ResearchLineageError as exc:
            raise HypothesisError("unregistered source of hypothesis evidence") from exc
        if source.status is not SourceStatus.ACTIVE:
            raise HypothesisError("corrected or retracted hypothesis evidence source")
        if source.content_digest != event.source_digest:
            raise HypothesisError("hypothesis evidence source digest mismatch")

    def record(self, event: HypothesisEvidence) -> str:
        if not isinstance(event, HypothesisEvidence):
            raise HypothesisError("typed evidence required")
        if event.hypothesis_id not in self._hypotheses:
            raise HypothesisError("hypothesis not registered")
        prior = self._events.get(event.event_id)
        if prior is not None:
            if prior != event:
                raise HypothesisError("immutable evidence event identity conflict")
            self._live(event)
            return event.digest
        self._live(event)
        if len(self._events) >= self._max_evidence:
            raise HypothesisError("evidence event capacity exceeded")
        if any(e.hypothesis_id == event.hypothesis_id and
               e.source_id == event.source_id for e in self._events.values()):
            raise HypothesisError("correlated source replay for same hypothesis")
        self._events[event.event_id] = event
        return event.digest

    def withdraw(self, event_id: str, *, reason: str) -> None:
        _id(event_id, "event_id")
        reason = _text(reason, "withdrawal reason")
        if event_id not in self._events:
            raise HypothesisError("cannot withdraw unknown evidence")
        previous = self._withdrawals.get(event_id)
        if previous is not None and previous != reason:
            raise HypothesisError("withdrawal reason immutable")
        self._withdrawals[event_id] = reason

    def assess(self, hypothesis_id: str) -> HypothesisAssessment:
        key = _id(hypothesis_id, "hypothesis_id")
        if key not in self._hypotheses:
            raise HypothesisError("hypothesis not registered")
        hypothesis = self._hypotheses[key]
        events = sorted(
            (e for e in self._events.values() if e.hypothesis_id == key),
            key=lambda event: event.event_id,
        )
        active = [e for e in events if e.event_id not in self._withdrawals]
        # No silent omission of retracted sources; owners must reconcile them.
        for e in active:
            self._live(e)
        observed = [e for e in active if e.mode is EvidenceMode.OBSERVED]
        prior = float(hypothesis.prior_plausibility)
        log_odds = math.log(prior / (1.0 - prior))
        for event in observed:
            log_odds += math.log(event.likelihood_ratio)
        log_odds = max(-36.0, min(36.0, log_odds))
        plausibility = 1.0 / (1.0 + math.exp(-log_odds))
        excluded = tuple(e.event_id for e in events if e not in observed)
        sources = tuple(sorted(e.source_id for e in observed))
        classification = "provisional-model-plausibility" if observed else "unassessed"
        digest = _hash({
            "hypothesis": hypothesis.digest,
            "observed": [(e.event_id, e.digest) for e in observed],
            "excluded": [(e.event_id, e.digest, self._withdrawals.get(e.event_id))
                         for e in events if e not in observed],
            "plausibility": plausibility, "classification": classification,
        })
        return HypothesisAssessment(
            key, hypothesis.question_id, plausibility, sources,
            excluded, classification, digest,
        )

    def compare(self, question_id: str) -> HypothesisComparison:
        key = _id(question_id, "question_id")
        claims = sorted(
            (h for h in self._hypotheses.values() if h.question_id == key),
            key=lambda item: item.hypothesis_id,
        )
        if len(claims) < 2:
            raise HypothesisError("at least two competing hypotheses required")
        rankings = tuple(sorted(
            (self.assess(h.hypothesis_id) for h in claims),
            key=lambda result: (-result.plausibility, result.hypothesis_id),
        ))
        # Never turn a high mathematical score into an independently verified fact.
        admitted = sum(bool(x.observed_sources) for x in rankings)
        unique_winner = (rankings[0].plausibility > rankings[1].plausibility)
        winner = rankings[0].hypothesis_id if admitted and unique_winner else None
        resolution = "tentative-preference" if winner else "unresolved"
        return HypothesisComparison(
            key, rankings, winner, resolution,
            _hash({"schema": "skeleton.research.hypothesis-comparison.v1",
                   "question": key, "ranking": [(x.hypothesis_id, x.receipt_digest)
                                              for x in rankings], "resolution": resolution}),
        )


__all__ = [
    "EvidenceDirection", "EvidenceMode", "Hypothesis", "HypothesisAssessment",
    "HypothesisComparison", "HypothesisError", "HypothesisEvidence", "HypothesisLedger",
]
