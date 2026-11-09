"""Policy card for operator steering."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.organism.policy_state import load_policy, set_repair_class, set_repair_enabled, set_threshold


def policy_card(*, root=None) -> Dict[str, Any]:
    policy = load_policy(root=root)
    return {
        "kind": "policy-card",
        "thresholds": dict(policy.get("quality_thresholds") or {}),
        "repair_enabled": dict(policy.get("repair_enabled") or {}),
        "repair_classes": dict(policy.get("repair_classes") or {}),
        "stored_prose": 0,
    }


def threshold_card(*, root=None, surface: str = "") -> Dict[str, Any]:
    policy = load_policy(root=root)
    thresholds = dict(policy.get("quality_thresholds") or {})
    return {
        "kind": "threshold-card",
        "surface": surface or "all",
        "threshold": thresholds.get(surface) if surface else None,
        "thresholds": thresholds,
        "stored_prose": 0,
    }


def set_threshold_card(surface: str, value: float, *, root=None) -> Dict[str, Any]:
    policy = set_threshold(surface, value, root=root)
    return {
        "kind": "threshold-set",
        "surface": surface,
        "threshold": float(policy.get("quality_thresholds", {}).get(surface, value)),
        "stored_prose": 0,
    }


def set_repair_enabled_card(surface: str, enabled: bool, *, root=None) -> Dict[str, Any]:
    policy = set_repair_enabled(surface, enabled, root=root)
    return {
        "kind": "repair-toggle-set",
        "surface": surface,
        "enabled": bool(policy.get("repair_enabled", {}).get(surface, enabled)),
        "stored_prose": 0,
    }


def set_repair_class_card(name: str, enabled: bool, *, root=None) -> Dict[str, Any]:
    policy = set_repair_class(name, enabled, root=root)
    return {
        "kind": "repair-class-set",
        "name": name,
        "enabled": bool(policy.get("repair_classes", {}).get(name, enabled)),
        "stored_prose": 0,
    }
