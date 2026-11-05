"""Bounded offline shortest-command planner for canonical authored NPC endings."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

from .flgb_gameplay_runtime import GameplayContractError, req_id
from .npc_schedule import (
    MAX_COMMANDS, NpcCommand, NpcSchedule, NpcSession, _integer, play,
)

MAX_ROUTE_NODES = 4096
MAX_ROUTE_DEPTH = 64
MAX_ROUTE_TICKS = 4096


@dataclass(frozen=True)
class NpcRouteResult:
    status: Literal["solved", "unreachable", "inconclusive"]
    ending_id: str
    reason: str
    expanded: int
    visited: int
    session: NpcSession | None = None

    def record(self) -> dict[str, object]:
        return {
            "status": self.status, "ending_id": self.ending_id,
            "reason": self.reason, "expanded": self.expanded,
            "visited": self.visited,
            "commands": [command.as_dict() for command in self.session.commands]
            if self.session is not None else [],
            "state_digest": self.session.state_digest
            if self.session is not None else None,
            "snapshot": self.session.snapshot()
            if self.session is not None else None,
        }


class NpcRoutePlanner:
    """Searches only authored interaction windows, not every simulation tick.

    Every candidate is executed by NpcSession.apply; no facts are minted and
    no alternate game rules are invented. Distinct histories with identical
    tick, facts and consumed interaction IDs have identical future options.
    """

    def __init__(self, schedule: NpcSchedule) -> None:
        if not isinstance(schedule, NpcSchedule):
            raise GameplayContractError("invalid canonical NPC schedule")
        self.schedule = schedule
        self.ticks = tuple(sorted({
            stop.start_tick for route in schedule.routes for stop in route.stops
            if stop.start_tick <= schedule.horizon_ticks
        }))

    @staticmethod
    def _key(session: NpcSession) -> tuple[object, ...]:
        consumed = tuple(sorted(
            (command.npc_id, command.interaction_id)
            for command in session.commands if command.kind == "interact"
        ))
        return (session.tick, session.facts, consumed)

    def solve(
        self, ending_id: str, *, player_id: str = "player",
        max_nodes: int = 1024, max_depth: int = 24,
    ) -> NpcRouteResult:
        req_id(ending_id, "ending_id")
        req_id(player_id, "player_id")
        _integer(max_nodes, "max_nodes", 1, MAX_ROUTE_NODES)
        _integer(max_depth, "max_depth", 1, MAX_ROUTE_DEPTH)
        if ending_id not in {ending.ending_id for ending in self.schedule.endings}:
            raise GameplayContractError("unknown authored ending")
        if len(self.ticks) > MAX_ROUTE_TICKS:
            return NpcRouteResult(
                "inconclusive", ending_id, "schedule-window-budget", 0, 0,
            )
        start = NpcSession.start(self.schedule)
        if start.ending == ending_id:
            return NpcRouteResult("solved", ending_id, "initial-state", 0, 1, start)
        pending = deque([start])
        visited = {self._key(start)}
        expanded = 0
        depth_cutoff = False
        while pending:
            state = pending.popleft()
            expanded += 1
            if state.ending != "in_progress":
                continue
            if len(state.commands) >= max_depth or len(state.commands) >= MAX_COMMANDS:
                depth_cutoff = True
                continue
            actions = []
            for present in self.schedule.active(state.tick):
                actions.append(NpcCommand(
                    "interact", state.tick, present["npc_id"],
                    present["interaction_id"], player_id,
                ))
            for tick in self.ticks:
                if tick > state.tick:
                    actions.append(NpcCommand("advance", tick))
            for action in actions:
                try:
                    candidate = state.apply(action)
                except GameplayContractError:
                    continue
                key = self._key(candidate)
                if key in visited:
                    continue
                if candidate.ending == ending_id:
                    witness = play(
                        self.schedule,
                        [command.as_dict() for command in candidate.commands],
                    )
                    if witness.state_digest != candidate.state_digest:
                        raise GameplayContractError("NPC ending replay mismatch")
                    if (NpcSession.restore(self.schedule, witness.snapshot()).state_digest
                            != witness.state_digest):
                        raise GameplayContractError("NPC ending snapshot mismatch")
                    return NpcRouteResult(
                        "solved", ending_id, "replay-verified",
                        expanded, len(visited) + 1, witness,
                    )
                if len(visited) >= max_nodes:
                    return NpcRouteResult(
                        "inconclusive", ending_id, "node-budget-exhausted",
                        expanded, len(visited),
                    )
                visited.add(key)
                pending.append(candidate)
        return NpcRouteResult(
            "inconclusive" if depth_cutoff else "unreachable",
            ending_id,
            "depth-budget-exhausted" if depth_cutoff
            else "finite-authored-choices-exhausted",
            expanded, len(visited),
        )
