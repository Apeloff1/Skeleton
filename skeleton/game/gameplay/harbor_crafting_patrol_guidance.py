"""Replay-derived, bounded patrol legal-action guidance and guard forecasts."""
from __future__ import annotations

from typing import Any

from .harbor_crafting import HarborError, DIRECTIONS, _keys, digest
from .harbor_crafting_patrol import (
    REPORT_KEYS, build_patrol, verify_patrol,
)

MAX_CANDIDATES = 80


def _candidates(report: dict[str, Any]) -> list[dict[str, str]]:
    world = report["source"]
    board = report["board"]
    actions: list[dict[str, str]] = [
        {"op": "move", "direction": direction} for direction in sorted(DIRECTIONS)
    ]
    actions += [{"op": "gather"}]
    actions += [{"op": "craft", "recipe": recipe["id"]}
                for recipe in world["recipes"]]
    actions += [{"op": "trade", "item": item} for item in sorted(world["npc"]["stock"])]
    actions += [{"op": "collect", "objective": objective["id"]}
                for objective in board["objectives"]]
    actions += [{"op": op} for op in ("deliver", "hide", "smoke", "wait", "extract")]
    if len(actions) > MAX_CANDIDATES:
        raise HarborError("patrol legal-action candidate budget exceeded")
    return actions


def _distance(a: list[int], b: list[int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _goal(report: dict[str, Any]) -> list[int]:
    remaining = [obj["at"] for obj in report["board"]["objectives"]
                 if obj["id"] not in report["state"]["collected"]]
    pos = report["bundle"]["state"]["pos"]
    if remaining:
        return min(remaining, key=lambda at: (_distance(pos, at), at[0], at[1]))
    return list(report["board"]["exit"])


def patrol_hints(report: Any) -> dict[str, Any]:
    _keys(report, REPORT_KEYS, "patrol report")
    status = verify_patrol(report)
    if report["state"]["complete"] or report["state"]["failed"]:
        return {"report_digest": status["report_digest"], "goal": None,
                "legal": [], "recommended": None, "terminal": True}
    goal = _goal(report)
    old_pos = report["bundle"]["state"]["pos"]
    options: list[dict[str, Any]] = []
    for action in _candidates(report):
        try:
            next_report = build_patrol(
                report["source"], report["board"], report["actions"] + [action],
            )
        except HarborError:
            continue
        overlay = next_report["state"]
        core = next_report["bundle"]["state"]
        options.append({
            "action": action, "position": list(core["pos"]),
            "alert": overlay["alert"], "score": overlay["score"],
            "failed": overlay["failed"], "complete": overlay["complete"],
            "guards": [list(p) for p in overlay["guards"]],
            "report_digest": next_report["report_digest"],
        })
    # A hint is advice, never an authorization token. Every option is
    # independently replayed from the exact current report action history.
    safe = [o for o in options if not o["failed"]]
    def rank(option: dict[str, Any]) -> tuple[int, int, int, int, str]:
        op = option["action"]["op"]
        priority = {"extract": 0, "collect": 1, "deliver": 2,
                    "gather": 3, "craft": 4, "trade": 5, "move": 6,
                    "hide": 7, "smoke": 8, "wait": 9}.get(op, 10)
        # Prefer reducing distance when moving, without claiming a solved path.
        movement = (_distance(option["position"], goal)
                    if op == "move" else _distance(old_pos, goal))
        return (priority, option["alert"], movement, -option["score"],
                str(option["action"]))
    chosen = min(safe, key=rank) if safe else None
    return {"report_digest": status["report_digest"], "goal": goal,
            "legal": options, "recommended": chosen["action"] if chosen else None,
            "terminal": False}
