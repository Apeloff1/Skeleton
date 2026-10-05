"""Deterministic counterfactual policy competition for Jeeves.

Candidates are evaluated as alternatives, not as claims about outcomes that
have not happened. This lets the control plane explain why an action won while
keeping rejected actions available for audit and replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class CandidateAction(str, Enum):
    REPAIR = "repair"
    RETRIEVE = "retrieve"
    PRACTICE = "practice"
    CHALLENGE = "challenge"
    TRANSFER = "transfer"
    PAUSE = "pause"


@dataclass(frozen=True)
class PolicyCandidate:
    action: CandidateAction
    learning_value: float
    evidence_fit: float
    risk: float
    effort: float
    rationale: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("learning_value", "evidence_fit", "risk", "effort"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")

    @property
    def score(self) -> float:
        return 0.40 * self.learning_value + 0.35 * self.evidence_fit - 0.20 * self.risk - 0.05 * self.effort


@dataclass(frozen=True)
class CounterfactualResult:
    selected: PolicyCandidate
    rejected: tuple[PolicyCandidate, ...]
    margin: float
    rationale: tuple[str, ...]


def compete(candidates: Sequence[PolicyCandidate]) -> CounterfactualResult:
    """Rank alternatives without pretending rejected outcomes actually occurred."""
    if not candidates:
        raise ValueError("at least one policy candidate is required")
    ranked = sorted(candidates, key=lambda item: (-item.score, item.action.value))
    selected = ranked[0]
    second = ranked[1].score if len(ranked) > 1 else selected.score
    margin = selected.score - second
    rationale = selected.rationale + (f"selected by deterministic score={selected.score:.4f}",)
    if len(ranked) > 1:
        rationale += (f"selection margin={margin:.4f}",)
    return CounterfactualResult(selected, tuple(ranked[1:]), margin, rationale)


def default_candidates(*, mastery: float, contradiction: float, energy: float, transfer_ready: bool) -> tuple[PolicyCandidate, ...]:
    """Construct a bounded alternative set from normalized observable signals."""
    mastery = max(0.0, min(1.0, mastery))
    contradiction = max(0.0, min(1.0, contradiction))
    energy = max(0.0, min(1.0, energy))
    return (
        PolicyCandidate(CandidateAction.REPAIR, 0.75 * contradiction, 0.95 * contradiction, 0.05, 0.45, ("repair is favored by conflicting evidence",)),
        PolicyCandidate(CandidateAction.RETRIEVE, 0.55 * (1 - mastery), 0.70, 0.10, 0.30, ("retrieval strengthens uncertain retention",)),
        PolicyCandidate(CandidateAction.PRACTICE, 0.80 * (1 - mastery), 0.75, 0.15, 0.50, ("practice consolidates the current skill",)),
        PolicyCandidate(CandidateAction.CHALLENGE, mastery, 0.80 * mastery * (1 - contradiction), 0.55, 0.85, ("challenge tests the upper boundary of mastery",)),
        PolicyCandidate(CandidateAction.TRANSFER, 0.90 * mastery if transfer_ready else 0.25 * mastery, 0.90 * mastery * (1 - contradiction), 0.45, 0.75, ("transfer tests generalization",)),
        PolicyCandidate(CandidateAction.PAUSE, 0.25 * (1 - energy), 0.90 if energy < 0.25 else 0.20, 0.02, 0.05, ("pause protects learning quality when energy is low",)),
    )
