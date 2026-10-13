"""Bounded observation-driven replanning without autonomous infinite loops."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.ai.critic import AIPlanCritic, CritiqueReport
from skeleton.shells.ai.planner import AIPlanner, PlanningResult
from skeleton.shells.ai.types import AIIntent


class ReplanStop(str, Enum):
    ACCEPTED = "accepted"
    MAX_ROUNDS = "max_rounds"
    POLICY_DENIED = "policy_denied"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class ReplanRound:
    round_index: int
    planning: PlanningResult
    critique: CritiqueReport

    def to_dict(self) -> dict[str, object]:
        return {
            "round_index": self.round_index,
            "planning": self.planning.to_dict(),
            "critique": self.critique.to_dict(),
        }


@dataclass(frozen=True)
class ReplanReport:
    rounds: tuple[ReplanRound, ...]
    stop: ReplanStop
    selected_round: int | None

    @property
    def selected(self) -> ReplanRound | None:
        if self.selected_round is None:
            return None
        return self.rounds[self.selected_round]

    def to_dict(self) -> dict[str, object]:
        return {
            "stop": self.stop.value,
            "selected_round": self.selected_round,
            "rounds": [item.to_dict() for item in self.rounds],
        }


class BoundedReplanner:
    """Replan only from sanitized observations and with an explicit round cap."""

    def __init__(
        self,
        planner: AIPlanner,
        critic: AIPlanCritic,
        *,
        max_rounds: int = 3,
    ) -> None:
        if max_rounds <= 0 or max_rounds > 16:
            raise ValueError("max_rounds must be between 1 and 16")
        self.planner = planner
        self.critic = critic
        self.max_rounds = max_rounds

    def run(
        self,
        intent: AIIntent,
        *,
        observations: tuple[dict[str, object], ...] = (),
    ) -> ReplanReport:
        rounds = []
        seen = set()
        current_observations = tuple(observations)
        for index in range(self.max_rounds):
            planning = self.planner.propose(
                intent,
                prior_observations=current_observations,
            )
            proposal = planning.response.proposal
            if proposal.fingerprint in seen:
                return ReplanReport(tuple(rounds), ReplanStop.DUPLICATE, None)
            seen.add(proposal.fingerprint)
            critique = self.critic.critique(
                intent,
                proposal,
                request=planning.request,
                response=planning.response,
            )
            item = ReplanRound(index, planning, critique)
            rounds.append(item)
            if critique.accepted_for_execution or critique.requires_approval:
                return ReplanReport(
                    tuple(rounds),
                    ReplanStop.ACCEPTED,
                    len(rounds) - 1,
                )
            if any(
                finding.code == "policy_denial"
                for finding in critique.findings
            ):
                return ReplanReport(tuple(rounds), ReplanStop.POLICY_DENIED, None)
            current_observations = current_observations + (
                {
                    "kind": "planner_feedback",
                    "risk": critique.risk.to_dict(),
                    "guardrails": critique.guardrails.to_dict(),
                    "policy": critique.policy.to_dict(),
                },
            )
        return ReplanReport(tuple(rounds), ReplanStop.MAX_ROUNDS, None)
