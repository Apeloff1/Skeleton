"""Headless extract-heat-sleep loop for a session. No SSE. No network."""

from __future__ import annotations

from typing import Any, Mapping


MAX_STEPS = 256
VERBS = ("extract", "heat", "sleep")


class ExtractLoopError(ValueError):
    """Extract loop contract violation."""


def step(state: Mapping[str, int], verb: str) -> dict[str, int]:
    name = str(verb or "").strip().lower()
    if name not in VERBS:
        raise ExtractLoopError(f"unknown extract verb: {verb}")
    heat = int(state.get("heat", 0))
    scrap = int(state.get("scrap", 0))
    sleep = int(state.get("sleep", 0))
    if name == "heat":
        heat = min(100, heat + 7)
        sleep = max(0, sleep - 1)
    elif name == "sleep":
        heat = max(0, heat - 5)
        sleep = min(100, sleep + 8)
    else:
        if heat < 12:
            raise ExtractLoopError("extract requires heat")
        scrap += 1 + heat // 20
        heat = max(0, heat - 12)
    return {"heat": heat, "scrap": scrap, "sleep": sleep}


def run_loop(inputs: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    pending = list(
        inputs
        or [
            {"verb": "heat"},
            {"verb": "heat"},
            {"verb": "extract"},
            {"verb": "sleep"},
        ]
    )
    if len(pending) > MAX_STEPS:
        raise ExtractLoopError("too many extract steps")
    state = {"heat": 0, "scrap": 0, "sleep": 0}
    frames = [dict(state)]
    for raw in pending:
        if not isinstance(raw, Mapping) or "verb" not in raw:
            raise ExtractLoopError("step requires verb")
        state = step(state, str(raw["verb"]))
        frames.append(dict(state))
    return {
        "kind": "extract_loop",
        "frames": frames,
        "final": state,
        "extracted": state["scrap"] > 0,
        "stored_prose": 0,
    }
