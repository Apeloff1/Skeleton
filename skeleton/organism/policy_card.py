"""Policy card for operator steering."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.organism.policy_state import load_policy


def policy_card(*, root=None) -> Dict[str, Any]:
    policy = load_policy(root=root)
    return {
        "kind": "policy-card",
        "thresholds": dict(policy.get("quality_thresholds") or {}),
        "repair_enabled": dict(policy.get("repair_enabled") or {}),
        "repair_classes": dict(policy.get("repair_classes") or {}),
        "stored_prose": 0,
    }
