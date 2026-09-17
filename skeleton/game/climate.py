"""Climate ticks. Heat weather per floor. Tokens periodic."""

from __future__ import annotations

from typing import Any

from skeleton.game.token_clock import TOKEN_PERIOD


class ClimateError(ValueError):
    pass


PHASES = ("calm", "vent", "storm", "ash", "dream")


def phase_delta(phase: str, heat: int, t: int, floor: int) -> int:
    if phase == "calm":
        delta = -1 if t % 3 == 0 else 0
    elif phase == "vent":
        delta = 1 + (t % 2)
    elif phase == "storm":
        delta = 3
    elif phase == "ash":
        delta = (t % 4) - 2
    elif phase == "dream":
        return (heat + (t % 3) + floor) % 16
    else:
        raise ClimateError(phase)
    return max(0, min(16, heat + delta + (floor % 2)))


def step(nodes: list[dict[str, Any]], t: int, phase: str) -> list[dict[str, Any]]:
    if phase not in PHASES:
        raise ClimateError(phase)
    out = []
    for node in nodes:
        nxt = dict(node)
        nxt["heat"] = phase_delta(phase, int(nxt.get("heat", 0)), t, int(nxt.get("floor", 0)))
        out.append(nxt)
    return out


def run(nodes: list[dict[str, Any]], ticks: int = 12, phase: str = "vent") -> dict[str, Any]:
    if ticks < 1 or ticks > 64:
        raise ClimateError("ticks")
    cur = [dict(n) for n in nodes]
    tokens = 0
    for t in range(ticks):
        cur = step(cur, t, phase)
        if t % TOKEN_PERIOD == TOKEN_PERIOD - 1:
            tokens += 1
    peak = max((int(n.get("heat") or 0) for n in cur), default=0)
    return {
        "kind": "climate",
        "phase": phase,
        "ticks": ticks,
        "peak": peak,
        "tokens": tokens,
        "nodes": cur,
        "stored_prose": 0,
    }
