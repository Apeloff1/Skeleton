"""Evidence-preserving consensus and disagreement control for VOL-206."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class ConsensusError(ValueError):
    pass


class DecisionStatus(str, Enum):
    CONSENSUS = "consensus"
    ESCALATE = "escalate"
    INSUFFICIENT_INDEPENDENCE = "insufficient_independence"


@dataclass(frozen=True)
class ConsensusProposal:
    reviewer_id: str
    independence_group: str
    choice: str
    confidence: float
    evidence_refs: tuple[str, ...]
    impact: str = "normal"

    def __post_init__(self) -> None:
        if any(not x.strip() for x in (self.reviewer_id, self.independence_group, self.choice)):
            raise ConsensusError("reviewer, independence group, and choice are required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ConsensusError("confidence must be within [0,1]")
        if not self.evidence_refs or any(not x.strip() for x in self.evidence_refs):
            raise ConsensusError("proposal requires concrete evidence")
        if self.impact not in {"normal", "high", "critical"}:
            raise ConsensusError("invalid impact")


@dataclass(frozen=True)
class Dissent:
    reviewer_id: str
    choice: str
    evidence_refs: tuple[str, ...]
    high_impact: bool


@dataclass(frozen=True)
class ConsensusDecision:
    status: DecisionStatus
    selected_choice: str | None
    proposals: tuple[ConsensusProposal, ...]
    dissent: tuple[Dissent, ...]
    reason: str


def decide(
    proposals: Iterable[ConsensusProposal],
    *,
    min_independent_groups: int = 2,
    consensus_ratio: float = 2 / 3,
) -> ConsensusDecision:
    items = tuple(sorted(proposals, key=lambda p: (p.reviewer_id, p.choice)))
    if not items:
        raise ConsensusError("at least one proposal is required")
    reviewer_ids = [p.reviewer_id for p in items]
    if len(set(reviewer_ids)) != len(reviewer_ids):
        raise ConsensusError("reviewer identity may vote only once")
    groups = {p.independence_group for p in items}
    if len(groups) < min_independent_groups:
        return ConsensusDecision(
            DecisionStatus.INSUFFICIENT_INDEPENDENCE, None, items, (),
            "reviewer independence requirement not met",
        )
    counts: dict[str, int] = {}
    for p in items:
        counts[p.choice] = counts.get(p.choice, 0) + 1
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    winner, votes = ranked[0]
    dissent = tuple(
        Dissent(p.reviewer_id, p.choice, p.evidence_refs, p.impact in {"high", "critical"})
        for p in items if p.choice != winner
    )
    if any(d.high_impact for d in dissent):
        return ConsensusDecision(
            DecisionStatus.ESCALATE, None, items, dissent,
            "unresolved high-impact dissent must not be averaged away",
        )
    if votes / len(items) < consensus_ratio:
        return ConsensusDecision(
            DecisionStatus.ESCALATE, None, items, dissent,
            "consensus threshold not met",
        )
    return ConsensusDecision(
        DecisionStatus.CONSENSUS, winner, items, dissent,
        "independent evidence threshold satisfied",
    )
