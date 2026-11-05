"""Bounded, deterministic crafting progression solver using canonical game transitions."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

from .crafting_runtime import (
    MAX_STACK, CraftAction, CraftEngine, CraftState, GameplayContractError,
    _id, _int,
)

MAX_SEARCH_NODES = 4096
MAX_SEARCH_DEPTH = 64


@dataclass(frozen=True)
class CraftGoal:
    """Item threshold and/or progression flag, evaluated against real state."""

    item_id: str | None = None
    minimum_count: int = 0
    required_flag: str | None = None

    def __post_init__(self) -> None:
        if self.item_id is None:
            if self.minimum_count != 0:
                raise GameplayContractError("quantity without goal item")
        else:
            _id(self.item_id, "goal item")
            _int(self.minimum_count, 1, MAX_STACK)
        if self.required_flag is not None:
            _id(self.required_flag, "goal flag")
        if self.item_id is None and self.required_flag is None:
            raise GameplayContractError("missing crafting goal")

    def reached(self, state: CraftState) -> bool:
        if self.item_id is not None:
            if dict(state.inventory).get(self.item_id, 0) < self.minimum_count:
                return False
        return self.required_flag is None or self.required_flag in state.flags

    def record(self) -> dict[str, object]:
        return {
            "item_id": self.item_id, "minimum_count": self.minimum_count,
            "required_flag": self.required_flag,
        }


@dataclass(frozen=True)
class CraftSearchResult:
    status: Literal["solved", "unreachable", "inconclusive"]
    goal: CraftGoal
    expanded: int
    visited: int
    reason: str
    state: CraftState | None = None

    def record(self) -> dict[str, object]:
        return {
            "status": self.status, "goal": self.goal.record(),
            "expanded": self.expanded, "visited": self.visited,
            "reason": self.reason,
            "actions": [a.record() for a in self.state.actions]
            if self.state is not None else [],
            "state_digest": self.state.digest if self.state is not None else None,
            "save": self.state.save_record() if self.state is not None else None,
        }


class CraftPlanner:
    """Shortest-event BFS; canonical recipe IDs deterministically break ties.

    All edges use the real CraftEngine state transition. State-only deduplication
    is safe because legal next actions depend only on inventory, funds and flags.
    Budget exhaustion is explicitly inconclusive rather than a false impossibility.
    """

    def __init__(self, engine: CraftEngine) -> None:
        if not isinstance(engine, CraftEngine):
            raise GameplayContractError("invalid canonical crafting engine")
        self.engine = engine

    def solve(
        self, goal: CraftGoal, *, max_nodes: int = 1024,
        max_depth: int = 24,
    ) -> CraftSearchResult:
        if not isinstance(goal, CraftGoal):
            raise GameplayContractError("invalid crafting goal")
        _int(max_nodes, 1, MAX_SEARCH_NODES)
        _int(max_depth, 1, MAX_SEARCH_DEPTH)
        initial = self.engine.start()
        if goal.reached(initial):
            return CraftSearchResult("solved", goal, 0, 1, "initial-state", initial)

        queue = deque([initial])
        visited = {initial.digest}
        expanded = 0
        depth_cutoff = False
        while queue:
            state = queue.popleft()
            expanded += 1
            if len(state.actions) >= max_depth:
                depth_cutoff = True
                continue
            for recipe in self.engine.plan.recipes:
                try:
                    candidate = self.engine._apply_verified(
                        state, CraftAction(len(state.actions), recipe.recipe_id),
                    )
                except GameplayContractError:
                    continue
                digest = candidate.digest
                if digest in visited:
                    continue
                if goal.reached(candidate):
                    witness = self.engine.replay(candidate.actions)
                    if witness != candidate or not goal.reached(witness):
                        raise GameplayContractError("craft route replay mismatch")
                    return CraftSearchResult(
                        "solved", goal, expanded, len(visited) + 1,
                        "replay-verified", witness,
                    )
                if len(visited) >= max_nodes:
                    return CraftSearchResult(
                        "inconclusive", goal, expanded, len(visited),
                        "node-budget-exhausted",
                    )
                visited.add(digest)
                queue.append(candidate)

        return CraftSearchResult(
            "inconclusive" if depth_cutoff else "unreachable",
            goal, expanded, len(visited),
            "depth-budget-exhausted" if depth_cutoff
            else "finite-state-space-exhausted",
        )
