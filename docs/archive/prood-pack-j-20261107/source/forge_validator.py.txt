"""
core/forge_validator.py — Grounded Simulation Harness (Manifest Segment 3 / Items 21-30).

2026 SOTA validates forged artifacts in a headless sandbox instead of trusting
"pretty JSON". A full Bevy/Godot/WASM runtime is not available inside this
service, so this validator runs a DETERMINISTIC, structural headless simulation:
it inspects the forged artifact for the signals a real engine would exercise
(collision configs, entity/tile density, camera keyframes, balance curves) and
derives real proxy metrics — failure_rate, engagement_proxy, stability_score.

These metrics become a THIRD judge (weight 0.25) alongside the LLM auditor and
symbolic rules, and successful traces are cached for Director reflection.
"""
from __future__ import annotations

import json
import time
from typing import Any

from core import build_ledger

SIM_WEIGHT = 0.25          # Item 24 — simulation weight in the blended score
SIM_STAGES = {"physics", "tileset", "cinematics", "procedural"}  # Item 28 gate


def _as_dict(artifact: Any) -> dict:
    if isinstance(artifact, dict):
        return artifact
    if isinstance(artifact, str):
        try:
            return json.loads(artifact)
        except Exception:
            return {}
    return {}


def _count_nested(d: Any, keys: tuple[str, ...]) -> int:
    """Rough count of how many target keys/entities appear in a nested artifact."""
    n = 0
    if isinstance(d, dict):
        for k, v in d.items():
            if k in keys:
                n += len(v) if isinstance(v, (list, dict)) else 1
            n += _count_nested(v, keys)
    elif isinstance(d, list):
        for v in d:
            n += _count_nested(v, keys)
    return n


def simulate_physics(artifact: Any) -> dict:
    """Item 22 — headless physics probe. Returns failure_rate + stability_score."""
    a = _as_dict(artifact)
    has_collision = _count_nested(a, ("collision", "colliders", "hitbox", "bodies", "rigidbody"))
    has_forces = _count_nested(a, ("gravity", "forces", "friction", "restitution", "damping"))
    has_bounds = _count_nested(a, ("bounds", "world_bounds", "constraints"))
    signals = has_collision + has_forces + has_bounds
    # More physics signals → lower failure, higher stability (saturating).
    failure_rate = round(max(0.0, 1.0 - signals / 8.0), 3)
    stability = round(min(100.0, 40 + signals * 8), 1)
    return {"failure_rate": failure_rate, "stability_score": stability,
            "signals": {"collision": has_collision, "forces": has_forces, "bounds": has_bounds}}


def simulate_camera_path(artifact: Any) -> dict:
    """Item 23 — headless camera probe. Returns cinematic_quality_proxy."""
    a = _as_dict(artifact)
    keyframes = _count_nested(a, ("keyframes", "shots", "cuts", "camera_path", "waypoints"))
    easing = _count_nested(a, ("easing", "ease", "interpolation", "smoothing"))
    framing = _count_nested(a, ("framing", "fov", "focus", "composition", "target"))
    signals = keyframes + easing + framing
    proxy = round(min(100.0, 35 + signals * 7), 1)
    return {"cinematic_quality_proxy": proxy,
            "signals": {"keyframes": keyframes, "easing": easing, "framing": framing}}


def _engagement_proxy(artifact: Any) -> float:
    a = _as_dict(artifact)
    variety = _count_nested(a, ("options", "levels", "enemies", "quests", "tiles",
                                "abilities", "events", "biomes"))
    return round(min(100.0, 30 + variety * 3.0), 1)


def simulation_metrics(kind: str, artifact: Any) -> dict:
    """Item 3/24 — unified metrics dict for any stage. Always returns
    failure_rate, engagement_proxy, stability_score (+ a 0-100 sim_score)."""
    stage = (kind or "").lower()
    phys = simulate_physics(artifact)
    engagement = _engagement_proxy(artifact)

    if "camera" in stage or "cinematic" in stage:
        cam = simulate_camera_path(artifact)
        sim_score = cam["cinematic_quality_proxy"]
        failure = round(max(0.0, 1.0 - sim_score / 100.0), 3)
        stability = sim_score
        extra = cam
    elif "physic" in stage or "tileset" in stage or "procedural" in stage:
        sim_score = phys["stability_score"]
        failure = phys["failure_rate"]
        stability = phys["stability_score"]
        extra = phys
    else:
        sim_score = engagement
        failure = round(max(0.0, 1.0 - engagement / 100.0), 3)
        stability = engagement
        extra = {}

    return {
        "failure_rate": failure,
        "engagement_proxy": engagement,
        "stability_score": stability,
        "sim_score": round(sim_score, 1),
        "weight": SIM_WEIGHT,
        "detail": extra,
    }


def cache_trace(build_id: str, stage: str, metrics: dict) -> None:
    """Item 25 — persist successful simulation traces for Director reflection."""
    try:
        build_ledger.log(build_id, "simulation_trace",
                         {"stage": stage, "metrics": metrics, "at": time.time()})
    except Exception:
        pass
