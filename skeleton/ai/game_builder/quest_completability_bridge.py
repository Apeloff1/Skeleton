"""Stand-in seam for a quest completability / softlock solver.

Øystein's solver is not posted yet.  This module fixes only the call shape
(rooms plus keys held) so quest tooling can depend on it now; the real solver
will implement :class:`CompletabilitySolver`.  No solving happens here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

from skeleton.ai.game_builder.quest_scene_engine import DirectorState


@dataclass(frozen=True, slots=True)
class Door:
    to: str
    requires: str | None = None  # key id, or None for an open passage


@dataclass(frozen=True, slots=True)
class Room:
    key: str
    doors: tuple[Door, ...] = ()
    keys: tuple[str, ...] = ()  # keys that can be picked up here
    goal: bool = False


@dataclass(frozen=True, slots=True)
class CompletabilityVerdict:
    completable: bool
    softlocked: bool
    reason: str = ""


@runtime_checkable
class CompletabilitySolver(Protocol):
    def check(self, rooms: Sequence[Room], start: str,
              keys_held: frozenset[str]) -> CompletabilityVerdict: ...


def keys_held(state: DirectorState) -> frozenset[str]:
    """Keys the player holds, read from the Director's acquired items."""
    return frozenset(state.acquired)


__all__ = ["CompletabilitySolver", "CompletabilityVerdict", "Door", "Room", "keys_held"]
