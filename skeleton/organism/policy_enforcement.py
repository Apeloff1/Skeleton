"""Policy enforcement layer — central gating for thresholds and repair toggles.

This module provides the bridge between policy_state persistence and all
verification/repair surfaces. Every verifier and repair scaffold imports
from here rather than reading policy_state directly.
"""
from __future__ import annotations

from typing import Any, Dict

from skeleton.organism.policy_state import default_policy, load_policy


def _policy(root=None) -> Dict[str, Any]:
    return load_policy(root=root)


def threshold_for(surface: str, *, root=None, fallback: float = 0.7) -> float:
    """Return the quality threshold for a given surface."""
    del fallback
    thresholds = _policy(root).get("quality_thresholds")
    if not isinstance(thresholds, dict) or surface not in thresholds:
        raise ValueError(f"unknown surface {surface!r}")
    value = thresholds[surface]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < float(value) <= 1:
        raise ValueError("threshold must be in (0, 1]")
    return float(value)


def repair_enabled_for(surface: str, *, root=None, fallback: bool = True) -> bool:
    """Return whether repair is enabled for a given surface."""
    del fallback
    flags = _policy(root).get("repair_enabled")
    if not isinstance(flags, dict) or surface not in flags or not isinstance(flags[surface], bool):
        raise ValueError(f"unknown surface {surface!r}")
    return flags[surface]


def repair_class_enabled(name: str, *, root=None, fallback: bool = True) -> bool:
    """Return whether a repair class is enabled."""
    del fallback
    flags = _policy(root).get("repair_classes")
    if not isinstance(flags, dict) or name not in flags or not isinstance(flags[name], bool):
        raise ValueError(f"unknown repair class {name!r}")
    return flags[name]


def policy_summary(*, root=None) -> Dict[str, Any]:
    """Compact policy state for embedding in operator cards."""
    policy = _policy(root)
    raw = policy.get("quality_thresholds")
    if not isinstance(raw, dict) or not raw:
        raise ValueError("policy has no thresholds")
    thresholds = dict(raw)
    repair_enabled = dict(policy.get("repair_enabled") or {})
    repair_classes = dict(policy.get("repair_classes") or {})
    active_surfaces = [s for s, v in repair_enabled.items() if v]
    active_classes = [c for c, v in repair_classes.items() if v]
    return {
        "thresholds": thresholds,
        "repair_surfaces_active": active_surfaces,
        "repair_surfaces_count": len(active_surfaces),
        "repair_classes_active": active_classes,
        "repair_classes_count": len(active_classes),
        "strictest": min(float(value) for value in thresholds.values()),
        "mean_threshold": round(sum(float(value) for value in thresholds.values()) / len(thresholds), 4),
    }


def gate_check(surface: str, score: float, *, root=None) -> Dict[str, Any]:
    """Return a gate result dict for a score against a surface threshold."""
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= float(score) <= 1 or float(score) != float(score):
        raise ValueError("score must be in [0, 1]")
    threshold = threshold_for(surface, root=root)
    passed = float(score) >= threshold
    return {
        "surface": surface,
        "score": round(score, 4),
        "threshold": threshold,
        "passed": passed,
        "margin": round(score - threshold, 4),
    }


def repair_gate(surface: str, *, root=None) -> Dict[str, Any]:
    """Return whether repair may proceed for a surface, with reason."""
    enabled = repair_enabled_for(surface, root=root)
    return {
        "surface": surface,
        "repair_allowed": enabled,
        "reason": "repair-enabled" if enabled else "repair-disabled-by-policy",
    }
