"""Headless TurnEngine. extract / heat / sleep / dream / E / Z.

Tokens do not tick every frame. Warp extracts once. No GUI. No SSE.
"""

from __future__ import annotations

from typing import Any, Mapping

from skeleton.game.extract_loop import step as base_step
from skeleton.game.token_clock import TOKEN_PERIOD
from skeleton.game.world_graph import place, walk


MAX_TICKS = 64
VERBS = ("extract", "heat", "sleep", "dream", "e", "z", "warp")


class TurnEngineError(ValueError):
    """Turn engine contract violation."""


def _blank() -> dict[str, int]:
    return {
        "heat": 0,
        "scrap": 0,
        "sleep": 0,
        "dreams": 0,
        "tokens": 0,
        "extracts": 0,
        "warps": 0,
    }


def apply(state: Mapping[str, int], verb: str, *, tick: int) -> dict[str, int]:
    name = str(verb or "").strip().lower()
    if name not in VERBS:
        raise TurnEngineError(f"unknown turn verb: {verb}")
    nxt = dict(_blank())
    nxt.update({key: int(state.get(key, 0)) for key in nxt})
    if name in {"extract", "heat", "sleep"}:
        core = base_step(
            {"heat": nxt["heat"], "scrap": nxt["scrap"], "sleep": nxt["sleep"]},
            name,
        )
        nxt["heat"], nxt["scrap"], nxt["sleep"] = core["heat"], core["scrap"], core["sleep"]
        if name == "extract":
            nxt["extracts"] += 1
    elif name == "dream":
        if nxt["sleep"] < 8:
            raise TurnEngineError("dream requires sleep")
        nxt["sleep"] = max(0, nxt["sleep"] - 8)
        nxt["dreams"] += 1
        nxt["heat"] = max(0, nxt["heat"] - 2)
    elif name == "e":
        nxt["heat"] = min(100, nxt["heat"] + 3)
    elif name == "z":
        nxt["sleep"] = min(100, nxt["sleep"] + 3)
        nxt["heat"] = max(0, nxt["heat"] - 2)
    else:
        if nxt["warps"] >= 1:
            raise TurnEngineError("warp extracts once")
        if nxt["heat"] < 12:
            raise TurnEngineError("warp requires heat")
        nxt["warps"] += 1
        nxt["extracts"] += 1
        nxt["scrap"] += 2
        nxt["heat"] = max(0, nxt["heat"] - 12)
    if tick % TOKEN_PERIOD == TOKEN_PERIOD - 1:
        nxt["tokens"] += 1
    return nxt


def play(
    inputs: list[Mapping[str, Any]] | None = None,
    *,
    seed: int = 8847291,
    ticks: int = 20,
) -> dict[str, Any]:
    if isinstance(ticks, bool) or not isinstance(ticks, int):
        raise TurnEngineError("ticks must be an integer")
    if ticks < 1 or ticks > MAX_TICKS:
        raise TurnEngineError("ticks out of range")
    script = list(inputs or [])
    if not script:
        script = (
            [{"verb": "heat"}] * 4
            + [{"verb": "extract"}]
            + [{"verb": "sleep"}] * 2
            + [{"verb": "dream"}]
            + [{"verb": "e"}, {"verb": "z"}]
            + [{"verb": "heat"}] * 3
            + [{"verb": "warp"}]
        )
        while len(script) < ticks:
            script.append({"verb": "heat" if len(script) % 2 == 0 else "z"})
        script = script[:ticks]
    if len(script) > MAX_TICKS:
        raise TurnEngineError("too many inputs")
    state = _blank()
    frames = [dict(state)]
    for index, raw in enumerate(script):
        if not isinstance(raw, Mapping) or "verb" not in raw:
            raise TurnEngineError("step requires verb")
        state = apply(state, str(raw["verb"]), tick=index)
        frames.append(dict(state))
    graph = place(seed=int(seed), rooms=4)
    walked = walk(graph)
    if walked["extract_count"] != walked["warp_count"]:
        raise TurnEngineError("world walk extract/warp mismatch")
    return {
        "kind": "turn_engine",
        "seed": int(seed),
        "ticks": len(script),
        "frames": frames,
        "final": state,
        "tokens": state["tokens"],
        "token_period": TOKEN_PERIOD,
        "every_frame": False,
        "extract_count": state["extracts"],
        "warp_count": state["warps"],
        "dreams": state["dreams"],
        "world_extract": walked["extract_count"],
        "passed": state["warps"] <= 1 and walked["passed"],
        "stored_prose": 0,
    }
