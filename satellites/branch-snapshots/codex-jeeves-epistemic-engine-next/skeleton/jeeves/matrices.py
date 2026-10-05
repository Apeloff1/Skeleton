"""Jeeves self-learning matrices: SAM, CLOM, KREM — full implementations.

- SAM (Self-Adaptive Memory): per-concept mastery with exponential decay and
  spaced-repetition scheduling.
- CLOM (Cross-Learner Ontology Map): an explicit learner model — goals,
  misconceptions, preferred modality, difficulty — updated from every turn.
- KREM (Knowledge-Retrieval Effectiveness Matrix): scores which retrieval
  sources actually helped, biasing future retrieval.

All three are pure in-process structures; persistence is a store concern.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# SAM — Self-Adaptive Memory
# ---------------------------------------------------------------------------

_HALF_LIFE_S = 3 * 24 * 3600  # mastery halves every 3 days without practice


@dataclass
class MasteryRecord:
    concept: str
    mastery: float = 0.0          # 0..1
    successes: int = 0
    attempts: int = 0
    last_seen: float = field(default_factory=time.time)

    def decayed_mastery(self, now: float | None = None) -> float:
        now = now or time.time()
        elapsed = max(0.0, now - self.last_seen)
        return self.mastery * math.pow(0.5, elapsed / _HALF_LIFE_S)

    def due_for_review(self, now: float | None = None) -> bool:
        return self.decayed_mastery(now) < 0.6


class SamMatrix:
    """Per-learner concept mastery with decay and review scheduling."""

    def __init__(self) -> None:
        self._records: dict[str, MasteryRecord] = {}

    def record_attempt(self, concept: str, *, success: bool, weight: float = 0.2) -> MasteryRecord:
        rec = self._records.setdefault(concept, MasteryRecord(concept))
        current = rec.decayed_mastery()
        delta = weight if success else -weight * 0.5
        rec.mastery = min(1.0, max(0.0, current + delta))
        rec.attempts += 1
        rec.successes += int(success)
        rec.last_seen = time.time()
        return rec

    def mastery(self, concept: str) -> float:
        rec = self._records.get(concept)
        return rec.decayed_mastery() if rec else 0.0

    def review_queue(self, *, limit: int = 10) -> list[str]:
        due = [r for r in self._records.values() if r.due_for_review()]
        due.sort(key=lambda r: r.decayed_mastery())
        return [r.concept for r in due[:limit]]

    def snapshot(self) -> dict[str, float]:
        return {c: round(r.decayed_mastery(), 4) for c, r in self._records.items()}


# ---------------------------------------------------------------------------
# CLOM — Cross-Learner Ontology Map
# ---------------------------------------------------------------------------


@dataclass
class LearnerModel:
    goals: set[str] = field(default_factory=set)
    misconceptions: dict[str, int] = field(default_factory=dict)  # concept -> count
    modality_scores: dict[str, float] = field(
        default_factory=lambda: {"visual": 0.5, "verbal": 0.5, "hands_on": 0.5})
    difficulty: float = 0.5  # 0 easy .. 1 hard

    def preferred_modality(self) -> str:
        return max(self.modality_scores, key=lambda k: self.modality_scores[k])


class ClomMatrix:
    """The explicit learner model, updated from observed behaviour."""

    def __init__(self) -> None:
        self.model = LearnerModel()

    def add_goal(self, goal: str) -> None:
        if goal.strip():
            self.model.goals.add(goal.strip())

    def record_misconception(self, concept: str) -> int:
        self.model.misconceptions[concept] = self.model.misconceptions.get(concept, 0) + 1
        return self.model.misconceptions[concept]

    def resolve_misconception(self, concept: str) -> None:
        self.model.misconceptions.pop(concept, None)

    def reinforce_modality(self, modality: str, *, amount: float = 0.05) -> None:
        scores = self.model.modality_scores
        if modality in scores:
            scores[modality] = min(1.0, scores[modality] + amount)

    def adjust_difficulty(self, *, success_rate: float) -> float:
        """Keep the learner in the zone of proximal development (~75% success)."""
        if success_rate > 0.85:
            self.model.difficulty = min(1.0, self.model.difficulty + 0.1)
        elif success_rate < 0.6:
            self.model.difficulty = max(0.0, self.model.difficulty - 0.1)
        return self.model.difficulty

    def snapshot(self) -> dict[str, object]:
        return {
            "goals": sorted(self.model.goals),
            "misconceptions": dict(self.model.misconceptions),
            "preferred_modality": self.model.preferred_modality(),
            "difficulty": round(self.model.difficulty, 3),
        }


# ---------------------------------------------------------------------------
# KREM — Knowledge-Retrieval Effectiveness Matrix
# ---------------------------------------------------------------------------


@dataclass
class SourceStats:
    retrievals: int = 0
    helpful: int = 0

    @property
    def effectiveness(self) -> float:
        if self.retrievals == 0:
            return 0.5  # uninformative prior
        # Laplace smoothing keeps cold sources explorable
        return (self.helpful + 1) / (self.retrievals + 2)


class KremMatrix:
    """Scores retrieval sources by measured helpfulness."""

    def __init__(self) -> None:
        self._sources: dict[str, SourceStats] = {}

    def record_retrieval(self, source: str) -> None:
        self._sources.setdefault(source, SourceStats()).retrievals += 1

    def record_feedback(self, source: str, *, helpful: bool) -> None:
        stats = self._sources.setdefault(source, SourceStats())
        if stats.retrievals == 0:
            stats.retrievals = 1
        stats.helpful += int(helpful)

    def rank_sources(self, sources: list[str]) -> list[str]:
        """Order candidate sources best-first by effectiveness."""
        return sorted(sources,
                      key=lambda s: self._sources.get(s, SourceStats()).effectiveness,
                      reverse=True)

    def snapshot(self) -> dict[str, float]:
        return {s: round(st.effectiveness, 4) for s, st in self._sources.items()}
