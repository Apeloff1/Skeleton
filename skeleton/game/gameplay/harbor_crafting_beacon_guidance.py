"""Replay-proven legal action guidance for original beacon rescue.

Each suggestion is admitted by executing the real canonical world and beacon
transition, never by predicting or inventing inventory, collision or victory.
"""
from __future__ import annotations

from typing import Any

from .harbor_crafting import HarborError, _keys, canonical, digest
from .harbor_crafting_beacons import (
    resume_beacon_rescue, verify_beacon_rescue, normalize_beacon_action,
)

SCHEMA = "skeleton.game.harbor.beacon-guidance.v1"
MAX_GUIDANCE_BYTES = 65536
FIELDS = {"schema", "report_digest", "candidates", "guidance_digest"}


def _candidates(report: dict[str, Any]) -> list[dict[str, str]]:
    world = report["source"]
    board = report["board"]
    choices: list[dict[str, str]] = [
        {"op": "move", "direction": direction}
        for direction in ("north", "east", "south", "west")
    ]
    choices.append({"op": "gather"})
    choices.extend({"op": "craft", "recipe": item["id"]} for item in world["recipes"])
    choices.extend({"op": "trade", "item": item} for item in sorted(world["npc"]["stock"]))
    choices.append({"op": "deliver"})
    for beacon in board["beacons"]:
        choices.append({"op": "repair", "beacon": beacon["id"]})
        choices.append({"op": "signal", "beacon": beacon["id"]})
    choices.extend(({"op": "rescue"}, {"op": "wait"}))
    if len(choices) > 128:
        raise HarborError("beacon legal action inventory exceeds budget")
    return choices


def legal_beacon_actions(report: Any) -> dict[str, Any]:
    verify_beacon_rescue(report)
    results: list[dict[str, Any]] = []
    if not report["state"]["rescued"]:
        for action in _candidates(report):
            normalized = normalize_beacon_action(action)
            try:
                next_report = resume_beacon_rescue(
                    report, [normalized], expected_digest=report["report_digest"],
                )
            except HarborError:
                continue
            results.append({
                "action": normalized, "report_digest": next_report["report_digest"],
                "rescued": next_report["state"]["rescued"],
                "signals": list(next_report["state"]["signaled"]),
                "delivered": next_report["bundle"]["state"]["delivered"],
            })
    guidance = {
        "schema": SCHEMA, "report_digest": report["report_digest"],
        "candidates": results,
    }
    guidance["guidance_digest"] = digest(guidance)
    if len(canonical(guidance)) > MAX_GUIDANCE_BYTES:
        raise HarborError("beacon guidance exceeds byte budget")
    return guidance


def verify_beacon_guidance(report: Any, guidance: Any) -> dict[str, Any]:
    _keys(guidance, FIELDS, "beacon guidance")
    if guidance["schema"] != SCHEMA or len(canonical(guidance)) > MAX_GUIDANCE_BYTES:
        raise HarborError("unsupported or oversized beacon guidance")
    if guidance["guidance_digest"] != digest({
        key: value for key, value in guidance.items() if key != "guidance_digest"
    }):
        raise HarborError("beacon guidance digest mismatch")
    rebuilt = legal_beacon_actions(report)
    if rebuilt != guidance:
        raise HarborError("beacon guidance replay mismatch")
    return {
        "verified": True, "available": len(rebuilt["candidates"]),
        "guidance_digest": rebuilt["guidance_digest"],
    }
