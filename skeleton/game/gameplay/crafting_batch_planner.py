"""Bounded, optimal-action batch crafting over canonical source-bound rules.

Unlike single-batch progression, this planner explores actual multi-batch
recipes to minimize the number of player interactions. No inventory, funds,
unlocks or rewards are fabricated: every edge is a real CraftEngine action.
"""
from __future__ import annotations

from collections import deque
from typing import Any

from .crafting_planner import CraftGoal
from .crafting_runtime import (
    MAX_BATCH, CraftAction, CraftEngine, CraftRecipe, CraftState,
    GameplayContractError, _digest, _int,
)

SCHEMA = "skeleton.crafting_batch_route.v1"
MAX_NODES = 4096
MAX_DEPTH = 64
MAX_TRANSITIONS = 16384


def _affordable(state: CraftState, recipe: CraftRecipe, cap: int) -> int:
    if not set(recipe.requires).issubset(state.flags):
        return 0
    inventory = dict(state.inventory)
    upper = cap
    for item, quantity in recipe.consumes:
        upper = min(upper, inventory.get(item, 0) // quantity)
    if recipe.currency_cost:
        upper = min(upper, state.currency // recipe.currency_cost)
    return upper


def _result(
    engine: CraftEngine, goal: CraftGoal, status: str,
    expanded: int, visited: int, transitions: int,
    state: CraftState | None, max_nodes: int,
    max_depth: int, max_batches: int,
) -> dict[str, Any]:
    save = state.save_record() if state is not None else None
    record = {
        "schema_version": SCHEMA,
        "plan_digest": engine.plan.digest,
        "goal": goal.record(),
        "max_nodes": max_nodes,
        "max_depth": max_depth,
        "max_batches": max_batches,
        "status": status,
        "expanded": expanded,
        "visited": visited,
        "transitions": transitions,
        "actions": [a.record() for a in state.actions]
        if state is not None else [],
        "state_digest": state.digest if state is not None else None,
        "save": save,
    }
    record["checksum"] = _digest(record)
    return record


def solve_batches(
    engine: CraftEngine, goal: CraftGoal, *, max_nodes: int = 1024,
    max_depth: int = 24, max_batches: int = 100,
) -> dict[str, Any]:
    """Shortest number of craft actions, with stable recipe/batch tie-breaks.

    A negative result is exhaustive only if all reachable canonical states
    were explored without hitting state, transition or depth budgets.
    """
    if not isinstance(engine, CraftEngine) or not isinstance(goal, CraftGoal):
        raise GameplayContractError("invalid crafting planner contract")
    _int(max_nodes, 1, MAX_NODES)
    _int(max_depth, 1, MAX_DEPTH)
    _int(max_batches, 1, MAX_BATCH)
    root = engine.start()
    if goal.reached(root):
        return _result(engine, goal, "solved", 0, 1, 0, root,
                       max_nodes, max_depth, max_batches)
    queue = deque([root])
    seen = {root.digest}
    expanded = 0
    transitions = 0
    incomplete = False
    while queue:
        if expanded >= max_nodes:
            incomplete = True
            break
        state = queue.popleft()
        expanded += 1
        if len(state.actions) >= max_depth:
            incomplete = True
            continue
        for recipe in engine.plan.recipes:
            upper = _affordable(state, recipe, max_batches)
            for batches in range(upper, 0, -1):
                if transitions >= MAX_TRANSITIONS:
                    incomplete = True
                    queue.clear()
                    break
                # Count attempted edges, including invalid overflow paths,
                # so adversarial recipe catalogs cannot evade the CPU budget.
                transitions += 1
                action = CraftAction(len(state.actions), recipe.recipe_id, batches)
                try:
                    candidate = engine._apply_verified(state, action)
                except GameplayContractError:
                    continue
                if candidate.digest in seen:
                    continue
                if goal.reached(candidate):
                    witness = engine.replay(candidate.actions)
                    if witness != candidate or not goal.reached(witness):
                        raise GameplayContractError("batch witness replay mismatch")
                    return _result(
                        engine, goal, "solved", expanded, len(seen) + 1,
                        transitions, witness, max_nodes, max_depth, max_batches,
                    )
                if len(seen) >= max_nodes:
                    incomplete = True
                    queue.clear()
                    break
                seen.add(candidate.digest)
                queue.append(candidate)
            if incomplete and not queue:
                break
    return _result(
        engine, goal,
        "inconclusive" if incomplete else "unreachable",
        expanded, len(seen), transitions, None,
        max_nodes, max_depth, max_batches,
    )


def verify_batch_route(
    engine: CraftEngine, payload: Any,
) -> dict[str, Any]:
    """Recompute the whole bounded search and replay any returned save."""
    keys = {
        "schema_version", "plan_digest", "goal", "max_nodes", "max_depth",
        "max_batches", "status", "expanded", "visited", "transitions",
        "actions", "state_digest", "save", "checksum",
    }
    if type(payload) is not dict or set(payload) != keys:
        raise GameplayContractError("invalid batch route fields")
    if payload["schema_version"] != SCHEMA:
        raise GameplayContractError("unsupported batch route schema")
    if payload["plan_digest"] != engine.plan.digest:
        raise GameplayContractError("batch route source mismatch")
    goal_raw = payload["goal"]
    if type(goal_raw) is not dict or set(goal_raw) != {
        "item_id", "minimum_count", "required_flag",
    }:
        raise GameplayContractError("invalid batch goal")
    goal = CraftGoal(**goal_raw)
    expected = solve_batches(
        engine, goal, max_nodes=payload["max_nodes"],
        max_depth=payload["max_depth"], max_batches=payload["max_batches"],
    )
    if payload != expected:
        raise GameplayContractError("batch route replay or checksum mismatch")
    if payload["status"] == "solved":
        restored = engine.restore(payload["save"])
        if not goal.reached(restored) or restored.digest != payload["state_digest"]:
            raise GameplayContractError("batch route witness mismatch")
    return expected
