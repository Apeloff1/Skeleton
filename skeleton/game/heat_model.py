"""Discrete heat / sleep / dream model. Tokens not every frame."""

from __future__ import annotations

from typing import Any

from skeleton.game.token_clock import TOKEN_PERIOD


MAX_HEAT = 100
MAX_SLEEP = 100


class HeatModelError(ValueError):
    """Heat model contract violation."""


def clamp(heat: int, sleep: int) -> tuple[int, int]:
    return max(0, min(MAX_HEAT, heat)), max(0, min(MAX_SLEEP, sleep))


def pulse(heat: int, sleep: int, verb: str) -> tuple[int, int]:
    name = str(verb or "").strip().lower()
    if name == "heat":
        return clamp(heat + 7, sleep - 1)
    if name == "sleep":
        return clamp(heat - 5, sleep + 8)
    if name == "dream":
        if sleep < 8:
            raise HeatModelError("dream requires sleep")
        return clamp(heat - 2, sleep - 8)
    if name == "extract":
        if heat < 12:
            raise HeatModelError("extract requires heat")
        return clamp(heat - 12, sleep)
    if name == "wait":
        return clamp(heat - 1, sleep)
    raise HeatModelError(f"unknown heat verb {verb}")


def run(verbs: list[str], *, period: int = TOKEN_PERIOD) -> dict[str, Any]:
    if period != TOKEN_PERIOD:
        raise HeatModelError("token period is pinned")
    heat, sleep = 0, 0
    tokens = 0
    frames = [{"t": 0, "heat": heat, "sleep": sleep, "tokens": tokens}]
    for index, verb in enumerate(verbs):
        heat, sleep = pulse(heat, sleep, verb)
        if index % period == period - 1:
            tokens += 1
        frames.append({"t": index + 1, "heat": heat, "sleep": sleep, "tokens": tokens})
    return {
        "kind": "heat_model",
        "final_heat": heat,
        "final_sleep": sleep,
        "tokens": tokens,
        "every_frame": False,
        "frames": frames,
        "stored_prose": 0,
    }
