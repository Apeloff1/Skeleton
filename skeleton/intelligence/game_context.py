"""AI-facing world and governance context distilled from game repos.

Sources: Apeloff1/Openworld and Apeloff1/gameforge-rs. The original game
transport/database code is intentionally excluded. This module supplies
portable decision primitives for agents: faction standing, relationship
signals, and safe event/novelty gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReputationLevel(str, Enum):
    HATED = "hated"
    HOSTILE = "hostile"
    UNFRIENDLY = "unfriendly"
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    HONORED = "honored"
    REVERED = "revered"
    EXALTED = "exalted"


_REPUTATION_BANDS = (
    (-500, ReputationLevel.HATED),
    (-200, ReputationLevel.HOSTILE),
    (-1, ReputationLevel.UNFRIENDLY),
    (499, ReputationLevel.NEUTRAL),
    (2999, ReputationLevel.FRIENDLY),
    (8999, ReputationLevel.HONORED),
    (20999, ReputationLevel.REVERED),
)


def reputation_level(value: int) -> ReputationLevel:
    """Convert a numeric faction standing into a stable semantic level."""
    for maximum, level in _REPUTATION_BANDS:
        if value <= maximum:
            return level
    return ReputationLevel.EXALTED


@dataclass(frozen=True)
class FactionContext:
    faction_id: str
    reputation: int = 0
    allies: tuple[str, ...] = ()
    enemies: tuple[str, ...] = ()

    @property
    def level(self) -> ReputationLevel:
        return reputation_level(self.reputation)

    def relationship_signal(self, other_faction: str) -> str:
        if other_faction in self.allies:
            return "ally"
        if other_faction in self.enemies:
            return "enemy"
        return "neutral"


class NoveltyDecision(str, Enum):
    ACCEPT = "accept"
    QUARANTINE = "quarantine"
    REJECT = "reject"


def novelty_gate(*, quorum: int, confirmations: int, trusted: bool = False) -> NoveltyDecision:
    """Apply the GameForge-RS quorum-gate idea to AI proposals.

    A proposal needs an explicit quorum before it becomes durable. Trusted
    proposals may pass with one confirmation, but never bypass a zero-quorum
    or invalid input.
    """
    if quorum < 1 or confirmations < 0 or confirmations > quorum:
        raise ValueError("invalid quorum/confirmation counts")
    if confirmations >= quorum:
        return NoveltyDecision.ACCEPT
    if trusted and confirmations >= 1:
        return NoveltyDecision.ACCEPT
    return NoveltyDecision.QUARANTINE


GAMEFORGE_DOCTRINE = {
    "durable_state": "durable state belongs behind an explicit persistence boundary",
    "bounded_memory": "keep hot AI state bounded with windows, deltas or ring buffers",
    "fail_closed": "missing security prerequisites fail closed rather than silently degrading",
    "quorum_novelty": "novel high-impact transitions require independent confirmation",
    "observable_transitions": "publish material state transitions to the event bus",
    "graceful_degradation": "degrade progressively and preserve safe read-only behavior",
}
