"""Earned stealth-patrol consequences, source-bound to replayed extraction."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _integer, _keys, canonical, digest
from .harbor_crafting_patrol import MAX_REPORT_BYTES as MAX_PATROL_REPORT_BYTES, verify_patrol

BOARD_SCHEMA = "skeleton.game.harbor.patrol-debrief-board.v1"
REPORT_SCHEMA = "skeleton.game.harbor.patrol-debrief-report.v1"
MAX_BOARD_BYTES = 32768
MAX_REPORT_BYTES = MAX_PATROL_REPORT_BYTES * 2
MAX_CHOICES = 12
BOARD_KEYS = {"schema", "source_id", "choices"}
CHOICE_KEYS = {"id", "min_score", "max_alert", "cost", "reputation",
               "credits", "epilogue"}
REPORT_KEYS = {"schema", "patrol", "board", "choice", "outcome",
               "patrol_digest", "board_digest", "report_digest"}


def validate_debrief_board(board: Any, patrol: Any) -> dict[str, Any]:
    verify_patrol(patrol, require_complete=True)
    _keys(board, BOARD_KEYS, "patrol debrief board")
    if board["schema"] != BOARD_SCHEMA or board["source_id"] != patrol["source"]["id"]:
        raise HarborError("patrol debrief source mismatch")
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("patrol debrief board exceeds byte budget")
    choices = board["choices"]
    if not isinstance(choices, list) or not 2 <= len(choices) <= MAX_CHOICES:
        raise HarborError("invalid patrol debrief choice count")
    names: set[str] = set()
    for choice in choices:
        _keys(choice, CHOICE_KEYS, "patrol debrief choice")
        name = _identifier(choice["id"], "patrol debrief choice id")
        _identifier(choice["epilogue"], "patrol debrief epilogue")
        _integer(choice["min_score"], 0, 1200, "patrol debrief minimum score")
        _integer(choice["max_alert"], 0, 12, "patrol debrief maximum alert")
        _integer(choice["cost"], 0, 1200, "patrol debrief cost")
        _integer(choice["reputation"], -100, 100, "patrol debrief reputation")
        _integer(choice["credits"], 0, 1000, "patrol debrief credits")
        if choice["cost"] > choice["min_score"]:
            raise HarborError("patrol debrief cost exceeds minimum score")
        if name in names:
            raise HarborError("duplicate patrol debrief choice")
        names.add(name)
    return deepcopy(board)


def _earned(choice: dict[str, Any], patrol: dict[str, Any]) -> bool:
    state = patrol["state"]
    return (state["score"] >= max(choice["min_score"], choice["cost"])
            and state["alert"] <= choice["max_alert"])


def build_patrol_debrief(patrol: Any, board: Any, choice_id: str) -> dict[str, Any]:
    verify_patrol(patrol, require_complete=True)
    authored = validate_debrief_board(board, patrol)
    name = _identifier(choice_id, "selected patrol debrief")
    choice = next((c for c in authored["choices"] if c["id"] == name), None)
    if choice is None:
        raise HarborError("unknown patrol debrief choice")
    if not _earned(choice, patrol):
        raise HarborError("patrol debrief choice not earned")
    outcome = {"ending": choice["id"], "epilogue": choice["epilogue"],
               "remaining_score": patrol["state"]["score"] - choice["cost"],
               "reputation": choice["reputation"], "credits": choice["credits"],
               "objectives_earned": list(patrol["state"]["collected"]),
               "alert": patrol["state"]["alert"]}
    result = {"schema": REPORT_SCHEMA, "patrol": deepcopy(patrol),
              "board": authored, "choice": name, "outcome": outcome,
              "patrol_digest": patrol["report_digest"],
              "board_digest": digest(authored)}
    result["report_digest"] = digest(result)
    if len(canonical(result)) > MAX_REPORT_BYTES:
        raise HarborError("patrol debrief report exceeds byte budget")
    return result


def verify_patrol_debrief(report: Any) -> dict[str, Any]:
    _keys(report, REPORT_KEYS, "patrol debrief report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized patrol debrief report")
    if report["report_digest"] != digest({k: v for k, v in report.items()
                                           if k != "report_digest"}):
        raise HarborError("patrol debrief digest mismatch")
    rebuilt = build_patrol_debrief(report["patrol"], report["board"], report["choice"])
    if rebuilt != report:
        raise HarborError("patrol debrief replay mismatch")
    return deepcopy(rebuilt["outcome"])


def compare_patrol_debriefs(patrol: Any, board: Any) -> dict[str, Any]:
    verify_patrol(patrol, require_complete=True)
    authored = validate_debrief_board(board, patrol)
    available = [c["id"] for c in authored["choices"] if _earned(c, patrol)]
    return {"score": patrol["state"]["score"], "alert": patrol["state"]["alert"],
            "available": available,
            "unavailable": [c["id"] for c in authored["choices"]
                            if c["id"] not in available]}
