"""Replay/restore fidelity: per-tick state hashes after restore must match the
original run from the snapshot tick on."""
from __future__ import annotations

from ._stats import require

NAME = "replay"
PARAMS = {"min_ticks": int}


def evaluate(params: dict, data: dict) -> tuple[list[str], dict]:
    missing = require(data, "snapshot_tick", "original", "restored")
    if missing:
        return missing, {}
    orig, rest, snap = data["original"], data["restored"], data["snapshot_tick"]
    if (type(snap) is not int or type(orig) is not list or type(rest) is not list
            or not 0 <= snap <= len(orig) or len(orig) > 100000
            or len(rest) > 100000 or any(type(v) is not str or not v
            for v in orig + rest)):
        return ["invalid replay coordinates or state evidence"], {}
    tail = orig[snap:]
    metrics = {"compared": min(len(tail), len(rest))}
    reasons: list[str] = []
    if len(rest) < params["min_ticks"]:
        reasons.append(f"restored run has {len(rest)} ticks, need {params['min_ticks']}")
    if len(rest) != len(tail):
        reasons.append(f"restored tail length {len(rest)} != original tail {len(tail)}")
    for i, (a, b) in enumerate(zip(tail, rest)):
        if a != b:
            reasons.append(f"divergence at tick {snap + i}")
            metrics["first_divergence"] = snap + i
            break
    return reasons, metrics
