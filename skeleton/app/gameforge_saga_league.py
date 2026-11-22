"""Recovered multi-round convoy league and cross-round quest adapter.

Round identities are included in every local action. No action can skip
a round, restart its inventory, or advance after a failed championship.
The league and quest owners retain final authority over all earned outcomes.
"""
from __future__ import annotations

from typing import Any

from skeleton.app.original_quest_cli import _object, _require
from skeleton.game.gameplay import harbor_crafting as harbor
from skeleton.game.gameplay.harbor_crafting_convoy import normalize_convoy_action
from skeleton.game.gameplay.harbor_crafting_convoy_league import (
    build_league, league_status, validate_league, verify_league,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league_quests import (
    build_league_quest_report, league_quest_status, validate_league_quests,
    verify_league_quest_report,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league_solver import (
    solve_league, verify_league_plan,
)

MAX_LEAGUE_TICKS = 1024


def validate_rules(world: dict, raw: Any) -> dict:
    rules = _object(raw, {"league", "quests"})
    league = validate_league(rules["league"], world)
    _require(league["max_total_ticks"] <= MAX_LEAGUE_TICKS, "saga league tick ceiling exceeded")
    genesis = build_league(world, league, [])
    return {"league": league, "quests": validate_league_quests(rules["quests"], genesis)}


def flatten_sessions(league: dict, sessions: list) -> list:
    _require(len(sessions) <= len(league["rounds"]), "too many round sessions")
    return [{"op": "round", "round": row["id"], "action": action}
            for row, actions in zip(league["rounds"], sessions) for action in actions]


def solve_witness(world: dict, rules: dict) -> tuple[list, dict]:
    plan = solve_league(world, rules["league"])
    proof = verify_league_plan(plan)
    _require(proof["complete"], "canonical solver did not earn championship")
    report = build_league_quest_report(plan["save"], rules["quests"], require_all=True)
    verify_league_quest_report(report, require_all=True)
    return flatten_sessions(rules["league"], plan["save"]["sessions"]), proof


def replay(world: dict, rules: dict, actions: list) -> dict:
    league = rules["league"]
    names = [row["id"] for row in league["rounds"]]
    sessions: list[list] = []
    for raw in actions:
        event = _object(raw, {"op", "round", "action"})
        _require(event["op"] == "round" and type(event["round"]) is str,
                 "explicit league round event required")
        index = len(sessions) - 1
        if index < 0 or event["round"] != names[index]:
            next_index = index + 1
            _require(next_index < len(names) and event["round"] == names[next_index],
                     "league round order mismatch")
            sessions.append([])
        sessions[-1].append(normalize_convoy_action(event["action"]))
    save = build_league(world, league, sessions)
    verify_league(save)
    report = build_league_quest_report(save, rules["quests"])
    verify_league_quest_report(report)
    return report


def summarize(world: dict, rules: dict, report: dict) -> dict:
    save = report["save"]
    status = league_status(save)
    quest = league_quest_status(report)
    total_ticks = sum(row["ticks"] for row in status["standings"])
    active = None
    if status["next_round"] is not None:
        active = next(row for row in rules["league"]["rounds"] if row["id"] == status["next_round"])
    reports = save["reports"]
    current = reports[-1] if reports and not reports[-1]["state"]["complete"] else None
    if active is None:
        current = reports[-1] if reports else None
    core = current["bundle"]["state"] if current else harbor.initial_state(world)
    tactical = current["state"] if current else None
    round_limit = active["board"]["max_turns"] if active else 0
    terminal = bool(save["complete"] or save["failed"] or total_ticks >= rules["league"]["max_total_ticks"]
                    or (active is not None and core["tick"] >= round_limit))
    # The global episode tick counts all rounds, not only the current world.
    state = {**core, "tick": total_ticks}
    return {"report_digest": report["report_digest"], "gate_satisfied": quest["complete"],
            "terminal": terminal, "state": state, "round_tick": core["tick"],
            "next_round": status["next_round"], "rounds_played": status["rounds_played"],
            "rounds_total": status["rounds_total"], "standings": status["standings"],
            "score": status["score"], "target_score": status["target_score"],
            "points": quest["points"], "earned": quest["earned"], "remaining": quest["remaining"],
            "hull": tactical["hull"] if tactical else (active["board"]["hull"] if active else 0),
            "threat": tactical["threat"] if tactical else None,
            "waypoint": tactical["index"] if tactical else 0,
            "failed": save["failed"], "championship": save["complete"]}


def candidates(world: dict, rules: dict, report: dict, summary: dict) -> list:
    if summary["terminal"]:
        return []
    actions = [{"op": name} for name in ("escort", "strike", "guard", "gather", "wait")]
    actions += [{"op": "move", "direction": d} for d in sorted(harbor.DIRECTIONS)]
    actions += [{"op": "craft", "recipe": row["id"]} for row in world["recipes"]]
    actions += [{"op": "trade", "item": item} for item in sorted(world["npc"]["stock"])]
    return [{"op": "round", "round": summary["next_round"], "action": a} for a in actions]
