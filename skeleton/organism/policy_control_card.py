"""Policy control card aggregating threshold and repair toggles."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.organism.policy_card import policy_card


def policy_control_card(*, root=None) -> Dict[str, Any]:
    base = policy_card(root=root)
    return {
        "kind": "policy-control-card",
        "thresholds": base.get("thresholds") or {},
        "repair_enabled": base.get("repair_enabled") or {},
        "repair_classes": base.get("repair_classes") or {},
        "stored_prose": 0,
    }
