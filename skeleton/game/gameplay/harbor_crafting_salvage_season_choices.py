"""Earned original championship epilogues with source-bound choice consequences."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _integer, _keys, canonical, digest
from .harbor_crafting_salvage_season import (
    MAX_SEASON_SAVE_BYTES, verify_salvage_season,
)

BOARD_SCHEMA = "skeleton.game.harbor.salvage-season-choice-board.v1"
REPORT_SCHEMA = "skeleton.game.harbor.salvage-season-choice-report.v1"
MAX_BOARD_BYTES = 32768
MAX_REPORT_BYTES = MAX_SEASON_SAVE_BYTES * 2
MAX_CHOICES = 12
BOARD_KEYS = {"schema", "source_id", "choices"}
CHOICE_KEYS = {"id", "min_score", "cost", "reputation", "epilogue"}
REPORT_KEYS = {"schema", "save", "board", "choice", "outcome",
               "source_digest", "board_digest", "report_digest"}


def validate_season_choices(board: Any, save: Any) -> dict[str, Any]:
    verify_salvage_season(save)
    _keys(board, BOARD_KEYS, "salvage choice board")
    if board["schema"] != BOARD_SCHEMA or board["source_id"] != save["source"]["id"]:
        raise HarborError("salvage choice source mismatch")
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("salvage choice board exceeds byte budget")
    choices = board["choices"]
    if not isinstance(choices, list) or not 2 <= len(choices) <= MAX_CHOICES:
        raise HarborError("invalid salvage choice count")
    seen: set[str] = set()
    for choice in choices:
        _keys(choice, CHOICE_KEYS, "salvage choice")
        name = _identifier(choice["id"], "salvage choice id")
        _identifier(choice["epilogue"], "salvage epilogue id")
        _integer(choice["min_score"], 0, 10000, "salvage choice minimum score")
        _integer(choice["cost"], 0, 10000, "salvage choice cost")
        _integer(choice["reputation"], -100, 100, "salvage choice reputation")
        if choice["cost"] > choice["min_score"]:
            raise HarborError("salvage choice cost exceeds required score")
        if name in seen:
            raise HarborError("duplicate salvage choice")
        seen.add(name)
    return deepcopy(board)


def build_season_choice(save: Any, board: Any, choice_id: str) -> dict[str, Any]:
    status = verify_salvage_season(save, require_complete=True)
    authored = validate_season_choices(board, save)
    name = _identifier(choice_id, "salvage selected choice")
    selected = next((c for c in authored["choices"] if c["id"] == name), None)
    if selected is None:
        raise HarborError("unknown salvage championship choice")
    if status["score"] < selected["min_score"] or status["score"] < selected["cost"]:
        raise HarborError("salvage championship choice not earned")
    outcome = {"ending": selected["id"], "epilogue": selected["epilogue"],
               "remaining_points": status["score"] - selected["cost"],
               "reputation": selected["reputation"],
               "rounds_earned": status["rounds_earned"]}
    report = {"schema": REPORT_SCHEMA, "save": deepcopy(save), "board": authored,
              "choice": name, "outcome": outcome,
              "source_digest": digest(save["source"]),
              "board_digest": digest(authored)}
    report["report_digest"] = digest(report)
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("salvage choice report oversized")
    return report


def verify_season_choice(report: Any) -> dict[str, Any]:
    _keys(report, REPORT_KEYS, "salvage choice report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized salvage choice report")
    if report["report_digest"] != digest({k: v for k, v in report.items()
                                           if k != "report_digest"}):
        raise HarborError("salvage choice report digest mismatch")
    rebuilt = build_season_choice(report["save"], report["board"], report["choice"])
    if rebuilt != report:
        raise HarborError("salvage choice replay mismatch")
    return deepcopy(report["outcome"])


def compare_season_choices(save: Any, board: Any) -> dict[str, Any]:
    status = verify_salvage_season(save, require_complete=True)
    authored = validate_season_choices(board, save)
    available = []
    for choice in authored["choices"]:
        if status["score"] >= max(choice["min_score"], choice["cost"]):
            available.append(build_season_choice(save, authored, choice["id"])["outcome"])
    return {"score": status["score"], "available": available,
            "unavailable": [c["id"] for c in authored["choices"]
                            if c["id"] not in {a["ending"] for a in available}]}
