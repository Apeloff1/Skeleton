"""Latency budget gate on recorded samples (p50/p95/p99)."""
from __future__ import annotations

from ._stats import percentile
from ._stats import require

NAME = "perf"
PARAMS = {"metric": str, "budgets_ms": dict, "min_samples": int}


def check_params(p: dict) -> str | None:
    if not p["budgets_ms"]:
        return "budgets_ms must not be empty"
    for k, v in p["budgets_ms"].items():
        if k not in ("p50", "p95", "p99") or not isinstance(v, (int, float)) or v <= 0:
            return "budgets_ms keys must be p50/p95/p99 with positive numbers"
    if p["min_samples"] < 1:
        return "min_samples must be >= 1"
    return None


def evaluate(params: dict, data: dict) -> tuple[list[str], dict]:
    missing = require(data, "samples_ms")
    if missing:
        return missing, {}
    samples = data["samples_ms"]
    if len(samples) < params["min_samples"]:
        return [f"only {len(samples)} samples, need {params['min_samples']}"], {"n": len(samples)}
    reasons, metrics = [], {"n": len(samples)}
    for key, budget in sorted(params["budgets_ms"].items()):
        val = percentile(samples, float(key[1:]))
        metrics[key] = val
        if val > budget:
            reasons.append(f"{params['metric']} {key} {val:g} ms over budget {budget:g} ms")
    return reasons, metrics
