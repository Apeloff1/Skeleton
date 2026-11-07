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
    tail = orig[snap:]
    metrics = {"compared": min(len(tail), len(rest))}
    reasons: list[str] = []
    if len(rest) < params["min_ticks"]:
        reasons.append(f"restored run has {len(rest)} ticks, need {params['min_ticks']}")
    for i, (a, b) in enumerate(zip(tail, rest)):
        if a != b:
            reasons.append(f"divergence at tick {snap + i}")
            metrics["first_divergence"] = snap + i
            break
    return reasons, metrics
