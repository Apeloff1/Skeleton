"""Observability retention gate: each signal kept at least its minimum days,
and nothing with PII kept beyond its maximum."""
from __future__ import annotations

from ._stats import require

NAME = "retention"
PARAMS = {"min_days": dict, "pii_max_days": int}


def evaluate(params: dict, data: dict) -> tuple[list[str], dict]:
    missing = require(data, "signals")
    if missing:
        return missing, {}
    reasons: list[str] = []
    signals = data["signals"]
    for name, need in sorted(params["min_days"].items()):
        cfg = signals.get(name)
        if cfg is None:
            reasons.append(f"signal '{name}' has no retention policy")
        elif cfg.get("days", 0) < need:
            reasons.append(f"signal '{name}' kept {cfg.get('days', 0)} d < {need} d")
    for name, cfg in sorted(signals.items()):
        if cfg.get("pii") and cfg.get("days", 0) > params["pii_max_days"]:
            reasons.append(f"signal '{name}' holds PII for {cfg['days']} d > {params['pii_max_days']} d")
    return reasons, {"signals": len(signals)}
