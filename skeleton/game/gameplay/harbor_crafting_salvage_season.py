"""Original multi-round salvage championship with CAS, earned points and replay."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, _identifier, _integer, _keys, canonical, digest, validate_source,
)
from .harbor_crafting_salvage import (
    MAX_BOARD_BYTES, MAX_REPORT_BYTES, build_salvage,
    validate_salvage_board, verify_salvage,
)

BOARD_SCHEMA = "skeleton.game.harbor.salvage-season-board.v1"
SAVE_SCHEMA = "skeleton.game.harbor.salvage-season-save.v1"
MAX_SEASON_BOARD_BYTES = 262144
MAX_SEASON_SAVE_BYTES = MAX_REPORT_BYTES * 8
MAX_ROUNDS = 8
BOARD_KEYS = {"schema", "source_id", "rounds"}
ROUND_KEYS = {"id", "board", "min_reward", "min_hull", "points"}
SAVE_KEYS = {"schema", "source", "board", "reports", "score", "tip", "save_digest"}


def validate_salvage_season(board: Any, source: Any) -> dict[str, Any]:
    world = validate_source(source)
    _keys(board, BOARD_KEYS, "salvage season board")
    if board["schema"] != BOARD_SCHEMA or board["source_id"] != world["id"]:
        raise HarborError("salvage season source mismatch")
    if len(canonical(board)) > MAX_SEASON_BOARD_BYTES:
        raise HarborError("salvage season board oversized")
    rounds = board["rounds"]
    if not isinstance(rounds, list) or not 1 <= len(rounds) <= MAX_ROUNDS:
        raise HarborError("invalid salvage season round count")
    names: set[str] = set()
    for item in rounds:
        _keys(item, ROUND_KEYS, "salvage season round")
        name = _identifier(item["id"], "salvage round id")
        if name in names:
            raise HarborError("duplicate salvage round")
        names.add(name)
        authored = validate_salvage_board(item["board"], world)
        _integer(item["min_reward"], 1, sum(s["reward"] for s in authored["sites"]),
                 "salvage round reward requirement")
        _integer(item["min_hull"], 1, authored["hull"], "salvage round hull requirement")
        _integer(item["points"], 1, 100, "salvage round points")
    return deepcopy(board)


def _seal(save: dict[str, Any]) -> dict[str, Any]:
    save["save_digest"] = digest({k: v for k, v in save.items() if k != "save_digest"})
    if len(canonical(save)) > MAX_SEASON_SAVE_BYTES:
        raise HarborError("salvage season save exceeds byte budget")
    return save


def _tip(source: Any, board: Any, reports: list[Any]) -> str:
    return digest({"source": digest(source), "board": digest(board),
                   "rounds": [r["report_digest"] for r in reports]})


def _points(item: dict[str, Any], report: dict[str, Any]) -> int:
    status = verify_salvage(report, require_complete=True)
    if status["reward"] < item["min_reward"] or status["hull"] < item["min_hull"]:
        raise HarborError("salvage season round requirements not earned")
    return item["points"] + status["reward"] + status["hull"]


def start_salvage_season(source: Any, board: Any) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_salvage_season(board, world)
    return _seal({"schema": SAVE_SCHEMA, "source": world, "board": authored,
                  "reports": [], "score": 0, "tip": _tip(world, authored, [])})


def verify_salvage_season(save: Any, *, require_complete: bool = False) -> dict[str, Any]:
    _keys(save, SAVE_KEYS, "salvage season save")
    if save["schema"] != SAVE_SCHEMA or len(canonical(save)) > MAX_SEASON_SAVE_BYTES:
        raise HarborError("unsupported or oversized salvage season save")
    if save["save_digest"] != digest({k: v for k, v in save.items()
                                      if k != "save_digest"}):
        raise HarborError("salvage season save digest mismatch")
    world = validate_source(save["source"])
    board = validate_salvage_season(save["board"], world)
    reports = save["reports"]
    if not isinstance(reports, list) or len(reports) > len(board["rounds"]):
        raise HarborError("salvage season report count invalid")
    score = 0
    for index, report in enumerate(reports):
        rebuilt = build_salvage(world, board["rounds"][index]["board"],
                                report["actions"], require_complete=True)
        if rebuilt != report:
            raise HarborError("salvage season round replay mismatch")
        score += _points(board["rounds"][index], report)
    if score != save["score"] or _tip(world, board, reports) != save["tip"]:
        raise HarborError("salvage season score or custody mismatch")
    complete = len(reports) == len(board["rounds"])
    if require_complete and not complete:
        raise HarborError("salvage season not complete")
    return {"complete": complete, "rounds_earned": len(reports),
            "rounds_total": len(board["rounds"]), "score": score,
            "tip": save["tip"], "save_digest": save["save_digest"]}


def append_salvage_round(save: Any, actions: Any, *, expected_tip: str) -> dict[str, Any]:
    status = verify_salvage_season(save)
    if type(expected_tip) is not str or expected_tip != status["tip"]:
        raise HarborError("stale salvage season CAS lease")
    if status["complete"]:
        raise HarborError("salvage season already complete")
    item = save["board"]["rounds"][status["rounds_earned"]]
    report = build_salvage(save["source"], item["board"], actions, require_complete=True)
    points = _points(item, report)
    updated = deepcopy(save)
    updated["reports"].append(report)
    updated["score"] += points
    updated["tip"] = _tip(updated["source"], updated["board"], updated["reports"])
    _seal(updated)
    verify_salvage_season(updated)
    return updated


def salvage_season_at(save: Any, index: int) -> dict[str, Any]:
    status = verify_salvage_season(save)
    _integer(index, 0, status["rounds_earned"], "salvage season index")
    result = start_salvage_season(save["source"], save["board"])
    for report in save["reports"][:index]:
        result = append_salvage_round(result, report["actions"], expected_tip=result["tip"])
    return result


def compare_salvage_seasons(ancestor: Any, descendant: Any) -> dict[str, Any]:
    left = verify_salvage_season(ancestor)
    right = verify_salvage_season(descendant)
    if (ancestor["source"] != descendant["source"]
            or ancestor["board"] != descendant["board"]
            or ancestor["reports"] != descendant["reports"][:left["rounds_earned"]]):
        raise HarborError("salvage season history conflict")
    return {"ancestor": left["tip"], "descendant": right["tip"],
            "advanced_rounds": right["rounds_earned"] - left["rounds_earned"]}


def fast_forward_salvage_season(ancestor: Any, descendant: Any) -> dict[str, Any]:
    compare_salvage_seasons(ancestor, descendant)
    return deepcopy(descendant)
