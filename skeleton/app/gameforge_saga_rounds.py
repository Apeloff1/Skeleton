"""Recover timed seasonal championships and delivery order chains into sagas.

Each explicit round action belongs to one authored course/order. Partial
runs are retained as canonical bundles. Only the original completed-save
owners may award season points or accept a completed delivery contract.
"""
from __future__ import annotations

from typing import Any

from skeleton.app.gameforge_campaign import digest
from skeleton.app.original_quest_cli import _encode, _integer, _object, _require
from skeleton.game.gameplay import harbor_crafting as harbor
from skeleton.game.gameplay import harbor_crafting_contracts as contracts
from skeleton.game.gameplay import harbor_crafting_season as season
from skeleton.game.gameplay.harbor_crafting_contract_solver import solve_contract, verify_contract_plan

KINDS = frozenset({"timed_season", "delivery_chain"})
MAX_TOTAL_TICKS = 1024
SCHEMA = "skeleton.gameforge.saga.round_report.v1"


def validate_rules(kind: str, world: dict, raw: Any) -> dict:
    if kind == "timed_season":
        rules = _object(raw, {"season", "minimum_points"})
        board = season.validate_season(rules["season"], world)
        ceiling = len(board["rounds"]) * max(board["points"].values())
        minimum = _integer(rules["minimum_points"], 0, ceiling)
        return {"season": board, "minimum_points": minimum}
    _require(kind == "delivery_chain", "unsupported round owner")
    rules = _object(raw, {"board"})
    return {"board": contracts.validate_board(rules["board"], world)}


def specs(kind: str, rules: dict) -> list:
    return rules["season"]["rounds"] if kind == "timed_season" else rules["board"]["orders"]


def action_limit(kind: str, world: dict, rules: dict) -> int:
    return min(MAX_TOTAL_TICKS, len(specs(kind, rules)) * world["max_ticks"])


def _record(kind: str, world: dict, rules: dict, bundles: list) -> dict:
    if kind == "timed_season":
        record = season.build_season(world, rules["season"], bundles)
        season.verify_season_record(record)
        return record
    record = contracts.build_save(world, rules["board"], bundles)
    contracts.verify_save(record)
    return record


def solve_delivery(world: dict, rules: dict) -> tuple[list, list]:
    """Reuse the canonical contract solver; no completion is assumed."""
    save = _record("delivery_chain", world, rules, [])
    actions, custody = [], []
    for order in rules["board"]["orders"]:
        proof = solve_contract(save)
        status = verify_contract_plan(proof)
        _require(status["order_id"] == order["id"], "canonical contract solver order mismatch")
        actions.extend({"op": "round", "round": order["id"], "action": event["action"]}
                       for event in proof["plan"]["bundle"]["events"])
        custody.append(proof["plan_digest"])
        save = proof["after"]
    _require(contracts.verify_save(save)["complete"], "delivery solver did not finish")
    return actions, custody


def replay(kind: str, world: dict, rules: dict, actions: list) -> dict:
    _require(len(actions) <= action_limit(kind, world, rules), "round ledger tick ceiling exceeded")
    rounds = specs(kind, rules)
    names = [row["id"] for row in rounds]
    sessions: list[list] = []
    for raw in actions:
        event = _object(raw, {"op", "round", "action"})
        _require(event["op"] == "round" and type(event["round"]) is str,
                 "explicit authored round event required")
        index = len(sessions) - 1
        if index < 0 or event["round"] != names[index]:
            following = index + 1
            _require(following < len(names) and event["round"] == names[following],
                     "round identity or order mismatch")
            sessions.append([])
        sessions[-1].append(harbor.normalize_action(event["action"]))
    completed = []
    record = _record(kind, world, rules, completed)
    active = None
    rejected = False
    for index, local in enumerate(sessions):
        _require(index == len(completed), "next round requires earned prior victory")
        bundle = harbor.export_bundle(world, local)
        state = harbor.verify_bundle(bundle)
        active = bundle
        if state["ending"] is None:
            _require(index == len(sessions) - 1, "partial round cannot unlock another round")
            continue
        try:
            advanced = _record(kind, world, rules, [*completed, bundle])
        except harbor.HarborError:
            # A legal core ending can fall short of its authored order/course.
            # Keep the real terminal run but never turn it into an earned result.
            rejected = True
            _require(index == len(sessions) - 1, "unearned round cannot unlock another round")
        else:
            completed.append(bundle)
            record = advanced
            active = None
    body = {"schema": SCHEMA, "kind": kind, "source_digest": harbor.digest(world),
            "rules_digest": digest(rules), "sessions": sessions, "record": record,
            "active_bundle": active, "rejected_terminal": rejected}
    return {**body, "report_digest": digest(body)}


def flatten(kind: str, rules: dict, report: dict) -> list:
    return [{"op": "round", "round": item["id"], "action": action}
            for item, actions in zip(specs(kind, rules), report["sessions"])
            for action in actions]


def summarize(kind: str, world: dict, rules: dict, report: dict) -> dict:
    record = report["record"]
    timed = kind == "timed_season"
    status = season.verify_season_record(record) if timed else contracts.verify_save(record)
    rows = specs(kind, rules)
    earned = status["next_round"] if timed else status["next_order"]
    points = status["total_points"] if timed else earned
    complete = bool(status["complete"])
    satisfied = complete and (not timed or points >= rules["minimum_points"])
    active = report["active_bundle"]
    state = harbor.verify_bundle(active) if active else harbor.initial_state(world)
    local_tick = state["tick"]
    total = sum(len(actions) for actions in report["sessions"])
    terminal = bool(complete or report["rejected_terminal"]
                    or local_tick >= world["max_ticks"] or total >= action_limit(kind, world, rules))
    standings = []
    for row in record["results"]:
        if timed:
            standings.append({"round": row["id"], "points": row["points"],
                              "medal": row["report"]["medal"], "tick": row["report"]["finish_tick"]})
        else:
            standings.append({"round": row["id"], "ending": row["ending"],
                              "tick": row["tick"], "coins": row["coins"],
                              "reputation": row["reputation"]})
    course_progress = None
    if timed and active is not None and earned < len(rows):
        from skeleton.game.gameplay.harbor_crafting_time_trials import time_trial_report, verify_time_trial_report
        trial = time_trial_report(active, rows[earned]["course"])
        verified = verify_time_trial_report(trial)
        course_progress = {"visits": verified["visits"], "medal": verified["medal"],
                           "deadline": trial["course"]["deadline"]}
    return {"report_digest": report["report_digest"], "gate_satisfied": satisfied,
            "terminal": terminal, "state": {**state, "tick": total}, "round_tick": local_tick,
            "next_round": None if terminal else rows[earned]["id"],
            "rounds_played": earned, "rounds_total": len(rows),
            "points": points, "score": points,
            "target_score": rules["minimum_points"] if timed else len(rows),
            "earned": [row["id"] for row in rows[:earned]],
            "remaining": [row["id"] for row in rows[earned:]],
            "standings": standings, "championship": complete,
            "course_progress": course_progress, "failed": terminal and not satisfied}


def candidates(world: dict, summary: dict) -> list:
    if summary["terminal"]:
        return []
    actions = [{"op": "move", "direction": d} for d in sorted(harbor.DIRECTIONS)]
    actions += [{"op": op} for op in ("wait", "gather", "deliver")]
    actions += [{"op": "craft", "recipe": row["id"]} for row in world["recipes"]]
    actions += [{"op": "trade", "item": item} for item in sorted(world["npc"]["stock"])]
    actions += [{"op": "choose", "choice": choice} for choice in ("signal", "shelter")]
    return [{"op": "round", "round": summary["next_round"], "action": action} for action in actions]
