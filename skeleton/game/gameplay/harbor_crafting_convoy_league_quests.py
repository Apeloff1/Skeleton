"""Cross-round mission DAG: source-bound earned objectives and consequences.

Quests inspect replay-verified canonical convoy reports. They cannot mint
inventory, bypass movement, or convert an incomplete league into victory.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, _identifier, _integer, _keys, canonical, digest,
)
from .harbor_crafting_convoy_league import MAX_SAVE_BYTES, verify_league

BOARD_SCHEMA = "skeleton.game.harbor.convoy-league-quests.v1"
REPORT_SCHEMA = "skeleton.game.harbor.convoy-league-quest-report.v1"
MAX_BOARD_BYTES = 65536
MAX_REPORT_BYTES = MAX_SAVE_BYTES + MAX_BOARD_BYTES + 8192
MAX_OBJECTIVES = 24
KINDS = {"round-complete", "bounty", "hull", "craft", "defeat"}
BOARD_FIELDS = {"schema", "source_id", "objectives", "minimum_points"}
OBJECTIVE_FIELDS = {"id", "round", "kind", "target", "requires", "points", "required"}
REPORT_FIELDS = {
    "schema", "save", "board", "awards", "points", "complete", "report_digest",
}


def validate_league_quests(board: Any, save: Any) -> dict[str, Any]:
    verify_league(save)
    _keys(board, BOARD_FIELDS, "league quest board")
    if (board["schema"] != BOARD_SCHEMA
            or board["source_id"] != save["source"]["id"]
            or len(canonical(board)) > MAX_BOARD_BYTES):
        raise HarborError("league quest source/schema/size mismatch")
    objectives = board["objectives"]
    if not isinstance(objectives, list) or not 1 <= len(objectives) <= MAX_OBJECTIVES:
        raise HarborError("invalid league objective count")
    _integer(board["minimum_points"], 1, MAX_OBJECTIVES * 100, "league quest score")
    rounds = {round_["id"]: round_["board"] for round_ in save["league"]["rounds"]}
    recipes = {
        item for recipe in save["source"]["recipes"] for item in recipe["output"]
    }
    seen: set[str] = set()
    required = 0
    for objective in objectives:
        _keys(objective, OBJECTIVE_FIELDS, "league objective")
        name = _identifier(objective["id"], "league objective id")
        round_id = _identifier(objective["round"], "league objective round")
        target = _identifier(objective["target"], "league objective target")
        kind = objective["kind"]
        if name in seen or round_id not in rounds:
            raise HarborError("duplicate or unknown league objective")
        if type(kind) is not str or kind not in KINDS:
            raise HarborError("unsupported league objective kind")
        prerequisites = objective["requires"]
        if (not isinstance(prerequisites, list)
                or len(prerequisites) > MAX_OBJECTIVES
                or any(type(p) is not str for p in prerequisites)
                or len(set(prerequisites)) != len(prerequisites)
                or any(p not in seen for p in prerequisites)):
            raise HarborError("invalid or cyclic league objective prerequisites")
        if kind == "round-complete":
            if target != "dock":
                raise HarborError("invalid league completion target")
        elif kind in {"bounty", "hull"}:
            if not target.isdecimal() or str(int(target)) != target:
                raise HarborError("invalid league numeric objective target")
            _integer(int(target), 0 if kind == "bounty" else 1, 1200, "league objective threshold")
        elif kind == "craft":
            if target not in recipes:
                raise HarborError("unknown league craft objective")
        elif kind == "defeat":
            if target not in {e["id"] for e in rounds[round_id]["encounters"]}:
                raise HarborError("unknown league enemy objective")
        _integer(objective["points"], 0, 100, "league objective points")
        if type(objective["required"]) is not bool:
            raise HarborError("invalid league objective required flag")
        required += objective["required"]
        seen.add(name)
    if not required:
        raise HarborError("league quest board requires a mandatory objective")
    return deepcopy(board)


def _earned(report: dict[str, Any], kind: str, target: str) -> bool:
    state = report["state"]
    if kind == "round-complete":
        return state["complete"]
    if kind == "bounty":
        return state["bounty"] >= int(target)
    if kind == "hull":
        return state["hull"] >= int(target) and not state["failed"]
    if kind == "craft":
        recipes = {
            recipe["id"]: set(recipe["output"])
            for recipe in report["source"]["recipes"]
        }
        return any(
            action["op"] == "craft" and target in recipes[action["recipe"]]
            for action in report["actions"] if action["op"] == "craft"
        )
    encounter = next(
        e for e in report["board"]["encounters"] if e["id"] == target
    )
    index = encounter["at_index"]
    return (
        state["index"] > index
        or (state["index"] == index and state["threat"] is None)
    )


def build_league_quest_report(save: Any, board: Any, *,
                              require_all: bool = False) -> dict[str, Any]:
    verify_league(save)
    authored = validate_league_quests(board, save)
    rounds = {
        round_["id"]: index for index, round_ in enumerate(save["league"]["rounds"])
    }
    awarded: set[str] = set()
    awards = []
    points = 0
    for objective in authored["objectives"]:
        index = rounds[objective["round"]]
        if (index < len(save["reports"])
                and all(name in awarded for name in objective["requires"])
                and _earned(
                    save["reports"][index], objective["kind"], objective["target"],
                )):
            awarded.add(objective["id"])
            points += objective["points"]
            awards.append({
                "id": objective["id"], "round": objective["round"],
                "points": objective["points"],
            })
    mandatory = all(
        not objective["required"] or objective["id"] in awarded
        for objective in authored["objectives"]
    )
    complete = bool(
        save["complete"] and mandatory and points >= authored["minimum_points"]
    )
    if require_all and not complete:
        raise HarborError("league quest ending not earned")
    result = {
        "schema": REPORT_SCHEMA, "save": deepcopy(save), "board": authored,
        "awards": awards, "points": points, "complete": complete,
    }
    result["report_digest"] = digest(result)
    if len(canonical(result)) > MAX_REPORT_BYTES:
        raise HarborError("league quest report exceeds byte budget")
    return result


def verify_league_quest_report(report: Any, *,
                               require_all: bool = False) -> dict[str, Any]:
    _keys(report, REPORT_FIELDS, "league quest report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized league quest report")
    if report["report_digest"] != digest({
        key: value for key, value in report.items() if key != "report_digest"
    }):
        raise HarborError("league quest report digest mismatch")
    rebuilt = build_league_quest_report(
        report["save"], report["board"], require_all=require_all,
    )
    if rebuilt != report:
        raise HarborError("league quest replay mismatch")
    return {
        "verified": True, "complete": rebuilt["complete"],
        "points": rebuilt["points"], "awards": len(rebuilt["awards"]),
        "report_digest": rebuilt["report_digest"],
    }


def league_quest_status(report: Any) -> dict[str, Any]:
    status = verify_league_quest_report(report)
    earned = {row["id"] for row in report["awards"]}
    return {
        **status, "earned": sorted(earned),
        "remaining": [
            objective["id"] for objective in report["board"]["objectives"]
            if objective["required"] and objective["id"] not in earned
        ],
    }
