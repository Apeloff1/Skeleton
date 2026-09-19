"""Speculative candidate collection and deterministic safe selection."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.critic import AIPlanCritic, CritiqueReport
from skeleton.shells.ai.types import AIIntent, AIPlanProposal


@dataclass(frozen=True)
class CandidateEvaluation:
    proposal: AIPlanProposal
    critique: CritiqueReport
    utility: float

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal.proposal_id,
            "proposal_fingerprint": self.proposal.fingerprint,
            "utility": self.utility,
            "critique": self.critique.to_dict(),
        }


@dataclass(frozen=True)
class CandidateSelection:
    candidates: tuple[CandidateEvaluation, ...]
    selected: CandidateEvaluation | None

    def to_dict(self) -> dict[str, object]:
        return {
            "selected": None if self.selected is None else self.selected.to_dict(),
            "candidates": [item.to_dict() for item in self.candidates],
        }


class CandidateSelector:
    """Choose among model proposals without executing any candidate."""

    def __init__(self, critic: AIPlanCritic) -> None:
        self.critic = critic

    @staticmethod
    def _utility(proposal: AIPlanProposal, critique: CritiqueReport) -> float:
        utility = proposal.confidence * 100.0
        utility -= proposal.uncertainty * 40.0
        utility -= critique.risk.score * 0.8
        utility -= max(0, len(proposal.actions) - 1) * 0.5
        if not critique.guardrails.ok:
            utility -= 1000
        if not critique.policy.allowed:
            utility -= 250 if critique.policy.requires_approval else 1000
        return utility

    def evaluate(
        self,
        intent: AIIntent,
        proposals: tuple[AIPlanProposal, ...],
    ) -> CandidateSelection:
        if not proposals:
            raise ValueError("at least one candidate is required")
        seen = set()
        evaluations = []
        for proposal in proposals:
            if proposal.fingerprint in seen:
                continue
            seen.add(proposal.fingerprint)
            critique = self.critic.critique(intent, proposal)
            evaluations.append(
                CandidateEvaluation(
                    proposal,
                    critique,
                    self._utility(proposal, critique),
                )
            )
        evaluations.sort(
            key=lambda item: (
                not item.critique.accepted_for_execution,
                item.critique.risk.score,
                -item.utility,
                item.proposal.fingerprint,
            )
        )
        selected = next(
            (item for item in evaluations if item.critique.accepted_for_execution),
            None,
        )
        return CandidateSelection(tuple(evaluations), selected)
