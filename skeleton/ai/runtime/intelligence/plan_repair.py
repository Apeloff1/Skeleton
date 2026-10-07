"""Bounded plan repair scaffold.

A repair may name a missing field. It does not fill an era, a damage
number, or a room bias and then call the plan accepted.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

from skeleton.intelligence.plan_verifier import PlanVerifier
from skeleton.organism.policy_enforcement import repair_class_enabled, repair_enabled_for, threshold_for
from skeleton.organism.quality_state import append_repair


def attempt_plan_repair(plan: Mapping[str, Any], *, vision: str = "", root=None) -> Dict[str, Any]:
    if not repair_enabled_for("plan", root=root):
        return {"kind": "plan-repair-attempt", "surface": "plan", "ok": 0, "reason": "repair-disabled", "actions": [], "changed": 0, "stored_prose": 0, "plan": dict(plan)}
    verifier = PlanVerifier(accept_at=threshold_for("plan", root=root, fallback=0.7), root=root)
    before = verifier.verify(plan, vision=vision)
    proposals = []
    if not before.accepted and repair_class_enabled("plan_fill", root=root):
        if not plan.get("era"):
            proposals.append({"field": "era", "action": "needs an era", "applied": 0})
        if plan.get("primary_dps") in {None, ""}:
            proposals.append({"field": "primary_dps", "action": "needs a primary dps", "applied": 0})
        if not plan.get("room_bias"):
            proposals.append({"field": "room_bias", "action": "needs a room bias", "applied": 0})
        if not vision.strip():
            proposals.append({"field": "vision", "action": "needs a vision", "applied": 0})
    report = before.to_dict()
    result = {
        "kind": "plan-repair-attempt",
        "surface": "plan",
        "ok": int(before.accepted),
        "reason": str(before.reason),
        "weakest_path": str(before.weakest_path or ""),
        "before": report,
        "after": report,
        "actions": proposals,
        "changed": 0,
        "targeted_path": str(before.weakest_path or "plan"),
        "stored_prose": 0,
        "plan": dict(plan),
    }
    append_repair(result, root=root)
    return result
