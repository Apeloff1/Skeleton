"""Presentation-profile gate: FPS at 30/50/60/120 without changing sim rate."""
from __future__ import annotations

import math
from ._stats import percentile

NAME = "fps"
PARAMS = {"profiles": list, "sim_hz": int, "min_ratio": float}
ALLOWED = (30, 50, 60, 120)


def check_params(p: dict) -> str | None:
    bad = [x for x in p["profiles"] if x not in ALLOWED]
    if bad or not p["profiles"]:
        return f"profiles must be a non-empty subset of {ALLOWED}"
    if not 0 < p["min_ratio"] <= 1:
        return "min_ratio must be in (0, 1]"
    return None


def evaluate(params: dict, data: dict) -> tuple[list[str], dict]:
    reasons: list[str] = []
    metrics: dict = {}
    runs = data.get("runs")
    if not isinstance(runs, dict):
        return ["evidence missing 'runs' object keyed by target fps"], metrics
    for target in params["profiles"]:
        run = runs.get(str(target))
        if run is None:
            reasons.append(f"no run recorded for {target} fps profile")
            continue
        if not isinstance(run, dict):
            reasons.append(f"{target} fps: malformed run")
            continue
        frames = run.get("frame_ms")
        if (type(frames) is not list or not 1 <= len(frames) <= 100000
                or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
                       for v in frames)):
            reasons.append(f"{target} fps: empty or invalid frame_ms")
            continue
        if type(run.get("sim_state_hash")) is not str or not run["sim_state_hash"]:
            reasons.append(f"{target} fps: missing state identity")
            continue
        p95 = percentile(frames, 95)
        achieved = 1000.0 / p95 if p95 > 0 else 0.0
        metrics[f"{target}.p95_fps"] = round(achieved, 2)
        if achieved < target * params["min_ratio"]:
            reasons.append(f"{target} fps: p95 {achieved:.1f} fps below {target * params['min_ratio']:.1f}")
        if run.get("sim_hz") != params["sim_hz"]:
            reasons.append(f"{target} fps: sim rate {run.get('sim_hz')} != fixed {params['sim_hz']}")
    hashes = {runs[str(t)].get("sim_state_hash") for t in params["profiles"]
              if isinstance(runs.get(str(t)), dict) and runs[str(t)].get("sim_state_hash")}
    if len(hashes) > 1:
        reasons.append("simulation state diverged across presentation profiles")
    return reasons, metrics
