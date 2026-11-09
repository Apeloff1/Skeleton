"""Milestone index for the frontier game plane.

Catalogs the candidate-only milestone surfaces and their contracts.
Does not execute them. Used by operators and CI to confirm the
milestone set is present and versioned.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MilestoneEntry:
    milestone_id: str
    module: str
    contract: str
    claim: str = "candidate-only"


MILESTONES: tuple[MilestoneEntry, ...] = (
    MilestoneEntry("P0", "game_frontier_p0_runtime", "runtime admission"),
    MilestoneEntry("P1", "game_frontier_p1_worldmodel", "world-model evidence"),
    MilestoneEntry("P2", "game_frontier_p2_cognition", "cinematic cognition"),
    MilestoneEntry("P3", "game_frontier_p3_harness", "qualification harness"),
    MilestoneEntry("M4", "game_frontier_milestone_compose", "compose admission"),
    MilestoneEntry("M5", "game_frontier_replay", "durable replay"),
    MilestoneEntry("M6", "game_frontier_session", "session orchestrator"),
    MilestoneEntry("M7", "game_frontier_campaign", "campaign ledger"),
)


def milestone_ids() -> tuple[str, ...]:
    return tuple(m.milestone_id for m in MILESTONES)


def require(milestone_id: str) -> MilestoneEntry:
    for entry in MILESTONES:
        if entry.milestone_id == milestone_id:
            return entry
    raise KeyError(milestone_id)
