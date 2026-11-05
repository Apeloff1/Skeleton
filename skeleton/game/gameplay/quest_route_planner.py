"""Canonical, bounded shortest-choice planner for offline quest endings."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

from .quest_session import (
    GameplayContractError, QuestEngine, QuestSession, QuestTrigger,
    _integer, _safe_id,
)

MAX_ROUTE_NODES = 4096
MAX_ROUTE_DEPTH = 64


@dataclass(frozen=True)
class QuestRouteResult:
    status: Literal["solved", "unreachable", "inconclusive"]
    ending_id: str
    reason: str
    expanded: int
    visited: int
    session: QuestSession | None = None

    def record(self) -> dict[str, object]:
        return {
            "status": self.status, "ending_id": self.ending_id,
            "reason": self.reason, "expanded": self.expanded,
            "visited": self.visited,
            "events": [event.as_record() for event in self.session.events]
            if self.session is not None else [],
            "state_digest": self.session.state_digest
            if self.session is not None else None,
            "save": self.session.save_record()
            if self.session is not None else None,
        }


class QuestRoutePlanner:
    """Finds minimal legal authored quest choices, not fabricated triggers.

    Search state is the completed quest set. Rewards are deterministic and
    additive, so identical completion sets have identical future choices.
    All edges execute the canonical QuestEngine transition and final witnesses
    are replayed and restored through public verification methods.
    """

    def __init__(self, engine: QuestEngine) -> None:
        if not isinstance(engine, QuestEngine):
            raise GameplayContractError("invalid quest engine")
        self.engine = engine

    def solve(
        self, ending_id: str, *, max_nodes: int = 1024,
        max_depth: int = 24,
    ) -> QuestRouteResult:
        _safe_id(ending_id, "ending_id")
        _integer(max_nodes, 1, MAX_ROUTE_NODES)
        _integer(max_depth, 1, MAX_ROUTE_DEPTH)
        if ending_id not in {
            quest.ending_id for quest in self.engine.plan.quests
            if quest.ending_id is not None
        }:
            raise GameplayContractError("unknown authored quest ending")

        start = self.engine.new_session()
        queue = deque([start])
        seen = {frozenset(start.completed)}
        expanded = 0
        depth_cutoff = False
        while queue:
            state = queue.popleft()
            expanded += 1
            if state.ending_id is not None:
                continue
            if len(state.events) >= max_depth:
                depth_cutoff = True
                continue
            for quest in self.engine.plan.quests:
                if quest.quest_id in state.completed:
                    continue
                if not set(quest.dependencies).issubset(state.completed):
                    continue
                trigger = QuestTrigger(
                    len(state.events), quest.quest_id, quest.event_type,
                    quest.source_id, quest.payload_digest,
                )
                try:
                    candidate = self.engine._apply_verified(state, trigger)
                except GameplayContractError:
                    continue
                key = frozenset(candidate.completed)
                if key in seen:
                    continue
                if candidate.ending_id == ending_id:
                    witness = self.engine.replay(candidate.events)
                    if witness != candidate:
                        raise GameplayContractError("quest route replay mismatch")
                    if self.engine.restore(witness.save_record()) != witness:
                        raise GameplayContractError("quest route save mismatch")
                    return QuestRouteResult(
                        "solved", ending_id, "replay-verified",
                        expanded, len(seen) + 1, witness,
                    )
                if len(seen) >= max_nodes:
                    return QuestRouteResult(
                        "inconclusive", ending_id, "node-budget-exhausted",
                        expanded, len(seen),
                    )
                seen.add(key)
                queue.append(candidate)
        return QuestRouteResult(
            "inconclusive" if depth_cutoff else "unreachable",
            ending_id, "depth-budget-exhausted" if depth_cutoff
            else "finite-quest-choices-exhausted",
            expanded, len(seen),
        )
