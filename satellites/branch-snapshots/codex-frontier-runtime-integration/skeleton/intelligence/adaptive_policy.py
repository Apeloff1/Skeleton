"""Adaptive policy engine — self-tuning thresholds based on quality history.

This module closes the feedback loop between quality outcomes and
policy thresholds. It analyzes historical quality pressure and
adjusts thresholds to maintain a target accept rate.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.organism.policy_state import load_policy, save_policy
from skeleton.organism.quality_state import load_quality, quality_pressure, summarize_quality


# Default adaptive parameters
DEFAULT_TARGET_ACCEPT_RATE = 0.85
DEFAULT_MIN_THRESHOLD = 0.3
DEFAULT_MAX_THRESHOLD = 0.95
DEFAULT_ADJUSTMENT_RATE = 0.05
DEFAULT_WINDOW_SIZE = 16


def _adaptive_config_path(root=None) -> Path:
    from skeleton.organism.paths import organism_dir
    return organism_dir(root) / "adaptive_policy.json"


def default_adaptive_config() -> Dict[str, Any]:
    return {
        "version": 1,
        "enabled": True,
        "target_accept_rate": DEFAULT_TARGET_ACCEPT_RATE,
        "min_threshold": DEFAULT_MIN_THRESHOLD,
        "max_threshold": DEFAULT_MAX_THRESHOLD,
        "adjustment_rate": DEFAULT_ADJUSTMENT_RATE,
        "window_size": DEFAULT_WINDOW_SIZE,
        "surface_configs": {},
    }


def load_adaptive_config(root=None) -> Dict[str, Any]:
    path = _adaptive_config_path(root)
    if not path.exists():
        return default_adaptive_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default_adaptive_config()
    base = default_adaptive_config()
    base.update(data)
    return base


def save_adaptive_config(config: Dict[str, Any], root=None) -> None:
    path = _adaptive_config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")


def _compute_surface_pressure(surface: str, window_size: int, root=None) -> Dict[str, Any]:
    """Compute quality pressure for a surface over the last N records."""
    rows = load_quality(root=root, limit=window_size * 2, surface=surface)
    if not rows:
        return {"pressure": 0.0, "accept_rate": 1.0, "count": 0, "rejected": 0}
    rollup = summarize_quality(rows)
    pressure = quality_pressure(rollup)
    return {
        "pressure": pressure,
        "accept_rate": rollup.get("accept_rate", 1.0),
        "count": rollup.get("count", 0),
        "rejected": rollup.get("rejected", 0),
    }


def _suggest_threshold_adjustment(
    current_threshold: float,
    accept_rate: float,
    target_accept_rate: float,
    adjustment_rate: float,
    min_threshold: float,
    max_threshold: float,
) -> Dict[str, Any]:
    """Suggest a threshold adjustment to move accept_rate toward target."""
    delta = accept_rate - target_accept_rate
    # If accept_rate is too low (below target), lower threshold
    # If accept_rate is too high (above target), raise threshold
    adjustment = 0.0
    if abs(delta) > 0.05:  # Only adjust if deviation is significant
        if delta < 0:
            # Accept rate too low — lower threshold to be more permissive
            adjustment = -adjustment_rate
        else:
            # Accept rate too high — raise threshold to be more strict
            adjustment = adjustment_rate

    new_threshold = max(min_threshold, min(max_threshold, current_threshold + adjustment))
    return {
        "current": round(current_threshold, 4),
        "suggested": round(new_threshold, 4),
        "adjustment": round(adjustment, 4),
        "accept_rate": round(accept_rate, 4),
        "target": target_accept_rate,
        "would_change": abs(new_threshold - current_threshold) > 0.001,
    }


def adapt_surface(surface: str, *, root=None, dry_run: bool = False) -> Dict[str, Any]:
    """Analyze quality history for a surface and adjust its threshold
    if adaptive policy is enabled.

    Returns a dict with the analysis and any adjustment made."""
    config = load_adaptive_config(root)
    if not config.get("enabled", True):
        return {
            "kind": "adaptive-policy-skip",
            "surface": surface,
            "reason": "adaptive-policy-disabled",
            "stored_prose": 0,
        }

    policy = load_policy(root=root)
    current_threshold = float((policy.get("quality_thresholds") or {}).get(surface, 0.7))

    window_size = int(config.get("window_size", DEFAULT_WINDOW_SIZE))
    target_rate = float(config.get("target_accept_rate", DEFAULT_TARGET_ACCEPT_RATE))
    adj_rate = float(config.get("adjustment_rate", DEFAULT_ADJUSTMENT_RATE))
    min_thresh = float(config.get("min_threshold", DEFAULT_MIN_THRESHOLD))
    max_thresh = float(config.get("max_threshold", DEFAULT_MAX_THRESHOLD))

    # Surface-specific overrides
    surface_config = config.get("surface_configs", {}).get(surface, {})
    if surface_config:
        target_rate = float(surface_config.get("target_accept_rate", target_rate))
        adj_rate = float(surface_config.get("adjustment_rate", adj_rate))
        min_thresh = float(surface_config.get("min_threshold", min_thresh))
        max_thresh = float(surface_config.get("max_threshold", max_thresh))

    pressure_info = _compute_surface_pressure(surface, window_size, root=root)
    accept_rate = pressure_info["accept_rate"]
    count = pressure_info["count"]

    if count < 3:
        return {
            "kind": "adaptive-policy-insufficient-data",
            "surface": surface,
            "count": count,
            "needed": 3,
            "stored_prose": 0,
        }

    suggestion = _suggest_threshold_adjustment(
        current_threshold, accept_rate, target_rate, adj_rate, min_thresh, max_thresh
    )

    result = {
        "kind": "adaptive-policy-analysis",
        "surface": surface,
        "current_threshold": suggestion["current"],
        "suggested_threshold": suggestion["suggested"],
        "would_change": suggestion["would_change"],
        "accept_rate": suggestion["accept_rate"],
        "target_accept_rate": target_rate,
        "pressure": pressure_info["pressure"],
        "count": count,
        "dry_run": dry_run,
        "stored_prose": 0,
    }

    if suggestion["would_change"] and not dry_run:
        from skeleton.organism.policy_state import set_threshold
        set_threshold(surface, suggestion["suggested"], root=root)
        result["applied"] = True
        result["kind"] = "adaptive-policy-adjusted"
    else:
        result["applied"] = False

    return result


def adapt_all_surfaces(*, root=None, dry_run: bool = False) -> Dict[str, Any]:
    """Run adaptive policy analysis on all known surfaces."""
    policy = load_policy(root=root)
    thresholds = policy.get("quality_thresholds", {})
    results = {}
    any_applied = False

    for surface in thresholds:
        result = adapt_surface(surface, root=root, dry_run=dry_run)
        results[surface] = result
        if result.get("applied"):
            any_applied = True

    return {
        "kind": "adaptive-policy-batch",
        "dry_run": dry_run,
        "surfaces_analyzed": len(results),
        "any_applied": any_applied,
        "results": results,
        "stored_prose": 0,
    }


def set_adaptive_config(
    *,
    enabled: Optional[bool] = None,
    target_accept_rate: Optional[float] = None,
    min_threshold: Optional[float] = None,
    max_threshold: Optional[float] = None,
    adjustment_rate: Optional[float] = None,
    window_size: Optional[int] = None,
    root=None,
) -> Dict[str, Any]:
    """Update the adaptive policy configuration."""
    config = load_adaptive_config(root)
    if enabled is not None:
        config["enabled"] = bool(enabled)
    if target_accept_rate is not None:
        config["target_accept_rate"] = float(target_accept_rate)
    if min_threshold is not None:
        config["min_threshold"] = float(min_threshold)
    if max_threshold is not None:
        config["max_threshold"] = float(max_threshold)
    if adjustment_rate is not None:
        config["adjustment_rate"] = float(adjustment_rate)
    if window_size is not None:
        config["window_size"] = int(window_size)
    save_adaptive_config(config, root=root)
    return {
        "kind": "adaptive-config-set",
        "config": config,
        "stored_prose": 0,
    }


def set_surface_adaptive_config(
    surface: str,
    *,
    target_accept_rate: Optional[float] = None,
    min_threshold: Optional[float] = None,
    max_threshold: Optional[float] = None,
    adjustment_rate: Optional[float] = None,
    root=None,
) -> Dict[str, Any]:
    """Set adaptive config overrides for a specific surface."""
    config = load_adaptive_config(root)
    surface_configs = config.setdefault("surface_configs", {})
    surface_config = surface_configs.setdefault(surface, {})

    if target_accept_rate is not None:
        surface_config["target_accept_rate"] = float(target_accept_rate)
    if min_threshold is not None:
        surface_config["min_threshold"] = float(min_threshold)
    if max_threshold is not None:
        surface_config["max_threshold"] = float(max_threshold)
    if adjustment_rate is not None:
        surface_config["adjustment_rate"] = float(adjustment_rate)

    save_adaptive_config(config, root=root)
    return {
        "kind": "adaptive-surface-config-set",
        "surface": surface,
        "config": surface_config,
        "stored_prose": 0,
    }


def adaptive_policy_card(*, root=None) -> Dict[str, Any]:
    """Operator card showing adaptive policy state and recent adjustments."""
    config = load_adaptive_config(root)
    policy = load_policy(root=root)
    thresholds = policy.get("quality_thresholds", {})

    surface_status = {}
    for surface in thresholds:
        pressure_info = _compute_surface_pressure(
            surface, int(config.get("window_size", DEFAULT_WINDOW_SIZE)), root=root
        )
        surface_status[surface] = {
            "current_threshold": thresholds.get(surface, 0.7),
            "accept_rate": pressure_info["accept_rate"],
            "pressure": pressure_info["pressure"],
            "count": pressure_info["count"],
        }

    return {
        "kind": "adaptive-policy-card",
        "enabled": config.get("enabled", True),
        "target_accept_rate": config.get("target_accept_rate", DEFAULT_TARGET_ACCEPT_RATE),
        "adjustment_rate": config.get("adjustment_rate", DEFAULT_ADJUSTMENT_RATE),
        "window_size": config.get("window_size", DEFAULT_WINDOW_SIZE),
        "min_threshold": config.get("min_threshold", DEFAULT_MIN_THRESHOLD),
        "max_threshold": config.get("max_threshold", DEFAULT_MAX_THRESHOLD),
        "surfaces": surface_status,
        "stored_prose": 0,
    }
