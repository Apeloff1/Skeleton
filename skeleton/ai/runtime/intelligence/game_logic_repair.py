"""Bounded game-logic repair scaffold.

Now wired to policy_enforcement for dynamic threshold/repair gating.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

from skeleton.intelligence.pipeline_verifier import PipelineVerifier
from skeleton.organism.policy_enforcement import repair_class_enabled, repair_enabled_for, threshold_for
from skeleton.organism.quality_state import append_repair


def attempt_game_logic_repair(spec: Mapping[str, Any], *, description: str = "", root=None) -> Dict[str, Any]:
    gate = repair_enabled_for("game_logic", root=root)
    if not gate:
        return {"kind": "pipeline-repair-attempt", "surface": "game_logic", "ok": 0, "reason": "repair-disabled", "actions": [], "changed": 0, "stored_prose": 0, "spec": dict(spec)}
    threshold = threshold_for("game_logic", root=root, fallback=0.7)
    verifier = PipelineVerifier(accept_at=threshold, root=root)
    before = verifier.verify_game_logic(spec, description=description)
    proposals = []
    if not before.accepted and repair_class_enabled("pipeline_seed", root=root):
        combat = spec.get("combat") or {}
        economy = spec.get("economy") or {}
        progression = spec.get("progression") or {}
        if not combat.get("damage_formula"):
            proposals.append({"field": "combat.damage_formula", "action": "needs a damage formula", "applied": 0})
        if not economy.get("currency"):
            proposals.append({"field": "economy.currency", "action": "needs a currency", "applied": 0})
        if "starting_balance" not in economy or not isinstance(economy.get("starting_balance"), (int, float)) or isinstance(economy.get("starting_balance"), bool) or economy.get("starting_balance") < 0:
            proposals.append({"field": "economy.starting_balance", "action": "needs a non-negative balance", "applied": 0})
        if not progression.get("curve"):
            proposals.append({"field": "progression.curve", "action": "needs a curve", "applied": 0})
        level = progression.get("max_level")
        if isinstance(level, bool) or not isinstance(level, int) or level < 1:
            proposals.append({"field": "progression.max_level", "action": "needs a max level", "applied": 0})
    result = {
        "kind": "pipeline-repair-attempt",
        "surface": "game_logic",
        "ok": int(before.accepted),
        "reason": str(before.reason),
        "weakest_path": str(before.weakest_path or ""),
        "before": before.to_dict(),
        "after": before.to_dict(),
        "actions": proposals,
        "changed": 0,
        "targeted_path": str(before.weakest_path or "game_logic"),
        "stored_prose": 0,
        "spec": dict(spec),
    }
    append_repair(result, root=root)
    return result
