"""Bounded plan repair scaffold.

Performs one conservative repair pass over a plan card, then re-verifies it.
This mirrors the forge repair shape without pretending to be a full planner.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

from skeleton.intelligence.plan_verifier import PlanVerifier
from skeleton.organism.policy_state import load_policy
from skeleton.organism.quality_state import append_repair


def attempt_plan_repair(plan: Mapping[str, Any], *, vision: str = "", root=None) -> Dict[str, Any]:
    policy = load_policy(root=root)
    if not bool((policy.get("repair_enabled") or {}).get("plan", True)):
        return {"kind": "plan-repair-attempt", "surface": "plan", "ok": 0, "reason": "repair-disabled", "actions": [], "changed": 0, "stored_prose": 0, "plan": dict(plan)}
    threshold = float((policy.get("quality_thresholds") or {}).get("plan", 0.7))
    verifier = PlanVerifier(accept_at=threshold)
    before = verifier.verify(plan, vision=vision)
    fixed = dict(plan)
    actions = []
    allow_fill = bool((policy.get("repair_classes") or {}).get("plan_fill", True))

    if not before.accepted and allow_fill:
        if not fixed.get("era"):
            fixed["era"] = "extraction_now"
            actions.append({"field": "era", "action": "filled default era"})
        if fixed.get("primary_dps") in {None, ""}:
            fixed["primary_dps"] = 120.0
            actions.append({"field": "primary_dps", "action": "filled default dps"})
        if not fixed.get("room_bias"):
            fixed["room_bias"] = "pressure labyrinth"
            actions.append({"field": "room_bias", "action": "filled default room bias"})

    after = verifier.verify(fixed, vision=vision)
    result = {
        "kind": "plan-repair-attempt",
        "surface": "plan",
        "ok": int(after.accepted),
        "reason": str(after.reason),
        "weakest_path": str(after.weakest_path or before.weakest_path or ""),
        "before": before.to_dict(),
        "after": after.to_dict(),
        "actions": actions,
        "changed": int(bool(actions)),
        "targeted_path": str(before.weakest_path or "plan"),
        "stored_prose": 0,
        "plan": fixed,
    }
    append_repair(result, root=root)
    return result
