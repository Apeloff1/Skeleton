"""Policy enforcement layer — central gating for thresholds and repair toggles.

This module provides the bridge between policy_state persistence and all
verification/repair surfaces. Every verifier and repair scaffold imports
from here rather than reading policy_state directly.
"""
from __future__ import annotations

from typing import Any, Dict

from skeleton.organism.policy_state import default_policy, load_policy


def _policy(root=None) -> Dict[str, Any]:
    try:
        return load_policy(root=root)
    except Exception:
        return default_policy()


def threshold_for(surface: str, *, root=None, fallback: float = 0.7) -> float:
    """Return the quality threshold for a given surface."""
    policy = _policy(root)
    return float((policy.get("quality_thresholds") or {}).get(surface, fallback))


def repair_enabled_for(surface: str, *, root=None, fallback: bool = True) -> bool:
    """Return whether repair is enabled for a given surface."""
    policy = _policy(root)
    return bool((policy.get("repair_enabled") or {}).get(surface, fallback))


def repair_class_enabled(name: str, *, root=None, fallback: bool = True) -> bool:
    """Return whether a repair class is enabled."""
    policy = _policy(root)
    return bool((policy.get("repair_classes") or {}).get(name, fallback))


def policy_summary(*, root=None) -> Dict[str, Any]:
    """Compact policy state for embedding in operator cards."""
    policy = _policy(root)
    thresholds = dict(policy.get("quality_thresholds") or {})
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
        "strictest": min(thresholds.values()) if thresholds else 0.7,
        "mean_threshold": round(sum(thresholds.values()) / max(1, len(thresholds)), 4) if thresholds else 0.7,
    }


def gate_check(surface: str, score: float, *, root=None) -> Dict[str, Any]:
    """Return a gate result dict for a score against a surface threshold."""
    threshold = threshold_for(surface, root=root)
    passed = score >= threshold
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
