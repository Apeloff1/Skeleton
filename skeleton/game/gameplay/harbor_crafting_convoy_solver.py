"""Bounded source-to-victory convoy solver using actual world and combat transitions."""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from typing import Any, Callable

from .harbor_crafting import (
    HarborError, _keys, canonical, digest, step, validate_source,
)
from .harbor_crafting_convoy import (
    MAX_REPORT_BYTES, build_convoy, validate_convoy_board, verify_convoy,
)
from .harbor_crafting_planner import _CampaignPlanner, MOVES

SCHEMA = "skeleton.game.harbor.convoy-plan.v1"
MAX_PLAN_BYTES = MAX_REPORT_BYTES + 32768
MAX_SEARCH_STATES = 4096
PLAN_FIELDS = {"schema", "source", "board", "actions", "report", "plan_digest"}


def _distance(a: list[int], b: list[int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _navigate(world: dict[str, Any], state: dict[str, Any], blocked: list[int],
              goal: Callable[[dict[str, Any]], bool]) -> list[dict[str, str]]:
    if goal(state):
        return []
    queue = deque([(state, [])])
    period = len(world["npc"]["route"])
    seen = {(tuple(state["pos"]), tuple(state["npc_pos"]), state["tick"] % period)}
    while queue:
        current, path = queue.popleft()
        if current["tick"] >= world["max_ticks"]:
            continue
        for move in MOVES:
            try:
                after = step(world, current, move)
            except HarborError:
                continue
            if after["pos"] == blocked:
                continue
            key = (tuple(after["pos"]), tuple(after["npc_pos"]), after["tick"] % period)
            if key in seen:
                continue
            if len(seen) >= MAX_SEARCH_STATES:
                raise HarborError("convoy solver navigation budget exhausted")
            seen.add(key)
            candidate = path + [move]
            if goal(after):
                return candidate
            queue.append((after, candidate))
    raise HarborError("convoy solver cannot reach escort waypoint")


def solve_convoy(source: Any, board: Any) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_convoy_board(board, world)
    planner = _CampaignPlanner(world)
    needed = sum(encounter["strength"] for encounter in authored["encounters"])
    if needed:
        planner.ensure(authored["weapon_item"], needed)
    actions = deepcopy(planner.actions)
    report = build_convoy(world, authored, actions)
    if report["state"]["failed"]:
        raise HarborError("convoy solver lost during preparation")

    def emit(action: dict[str, str]) -> None:
        nonlocal report
        if len(actions) >= authored["max_turns"]:
            raise HarborError("convoy solver turn budget exhausted")
        next_report = build_convoy(world, authored, actions + [action])
        actions.append(deepcopy(action))
        report = next_report

    for _ in range(len(authored["route"]) + len(authored["encounters"]) + 1):
        if report["state"]["complete"]:
            break
        current = authored["route"][report["state"]["index"]]
        threat = report["state"]["threat"]
        if threat is not None:
            state = report["bundle"]["state"]
            path = _navigate(
                world, state, current,
                lambda s, at=current: _distance(s["pos"], at) <= 2,
            )
            for action in path:
                emit(action)
            while report["state"]["threat"] is not None:
                emit({"op": "strike"})
            continue
        if report["state"]["index"] + 1 >= len(authored["route"]):
            raise HarborError("convoy solver cannot complete route")
        target = authored["route"][report["state"]["index"] + 1]
        state = report["bundle"]["state"]
        path = _navigate(
            world, state, current,
            lambda s, at=current, nxt=target: (
                s["pos"] != nxt
                and _distance(s["pos"], at) <= 2
                and _distance(s["pos"], nxt) <= 2
            ),
        )
        for action in path:
            emit(action)
        emit({"op": "escort"})
    if not report["state"]["complete"]:
        raise HarborError("convoy solver did not earn dock victory")
    verify_convoy(report, require_complete=True)
    plan = {
        "schema": SCHEMA, "source": world, "board": authored,
        "actions": actions, "report": report,
    }
    plan["plan_digest"] = digest(plan)
    if len(canonical(plan)) > MAX_PLAN_BYTES:
        raise HarborError("convoy solver plan exceeds byte budget")
    return plan


def verify_convoy_plan(plan: Any) -> dict[str, Any]:
    _keys(plan, PLAN_FIELDS, "convoy plan")
    if plan["schema"] != SCHEMA or len(canonical(plan)) > MAX_PLAN_BYTES:
        raise HarborError("unsupported or oversized convoy plan")
    if plan["plan_digest"] != digest({
        key: value for key, value in plan.items() if key != "plan_digest"
    }):
        raise HarborError("convoy plan digest mismatch")
    verify_convoy(plan["report"], require_complete=True)
    rebuilt = solve_convoy(plan["source"], plan["board"])
    if rebuilt != plan:
        raise HarborError("convoy solver replay mismatch")
    return {
        "verified": True, "complete": True,
        "actions": len(rebuilt["actions"]),
        "hull": rebuilt["report"]["state"]["hull"],
        "bounty": rebuilt["report"]["state"]["bounty"],
        "plan_digest": rebuilt["plan_digest"],
    }
