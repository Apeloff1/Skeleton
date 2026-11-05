"""Source-to-victory solver for authored convoy league, bounded by round budgets."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _keys, canonical, digest, validate_source
from .harbor_crafting_convoy_league import (
    MAX_SAVE_BYTES, build_league, validate_league, verify_league,
)
from .harbor_crafting_convoy_solver import solve_convoy, verify_convoy_plan

SCHEMA = "skeleton.game.harbor.convoy-league-plan.v1"
MAX_PLAN_BYTES = MAX_SAVE_BYTES + 262144
FIELDS = {"schema", "source", "league", "plans", "save", "plan_digest"}


def solve_league(source: Any, league: Any) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_league(league, world)
    plans = []
    sessions = []
    for round_ in authored["rounds"]:
        plan = solve_convoy(world, round_["board"])
        verify_convoy_plan(plan)
        plans.append(plan)
        sessions.append(deepcopy(plan["actions"]))
    save = build_league(world, authored, sessions, require_complete=True)
    if any(
        save["reports"][index] != plan["report"]
        for index, plan in enumerate(plans)
    ):
        raise HarborError("league planner and canonical runtime diverged")
    result = {
        "schema": SCHEMA, "source": world, "league": authored,
        "plans": plans, "save": save,
    }
    result["plan_digest"] = digest(result)
    if len(canonical(result)) > MAX_PLAN_BYTES:
        raise HarborError("league solver plan exceeds byte budget")
    return result


def verify_league_plan(plan: Any) -> dict[str, Any]:
    _keys(plan, FIELDS, "league solver plan")
    if plan["schema"] != SCHEMA or len(canonical(plan)) > MAX_PLAN_BYTES:
        raise HarborError("unsupported or oversized league solver plan")
    if plan["plan_digest"] != digest({
        key: value for key, value in plan.items() if key != "plan_digest"
    }):
        raise HarborError("league solver plan digest mismatch")
    verify_league(plan["save"], require_complete=True)
    rebuilt = solve_league(plan["source"], plan["league"])
    if rebuilt != plan:
        raise HarborError("league solver plan replay mismatch")
    return {
        "verified": True, "complete": True,
        "score": rebuilt["save"]["score"],
        "rounds": len(rebuilt["plans"]),
        "plan_digest": rebuilt["plan_digest"],
    }
