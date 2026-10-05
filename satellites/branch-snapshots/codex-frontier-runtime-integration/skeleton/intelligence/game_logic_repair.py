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
    fixed = dict(spec)
    actions = []
    combat = dict(fixed.get("combat") or {})
    economy = dict(fixed.get("economy") or {})
    progression = dict(fixed.get("progression") or {})
    base_values = dict(combat.get("base_values") or {})
    allow_fill = repair_class_enabled("pipeline_seed", root=root)
    if not before.accepted and allow_fill:
        if not combat.get("damage_formula"):
            combat["damage_formula"] = "max(1, atk * 100 / (100 + def))"
            actions.append({"field": "combat.damage_formula", "action": "filled default damage formula"})
        if any(float(v) < 0 for v in base_values.values()):
            for k, v in list(base_values.items()):
                if float(v) < 0:
                    base_values[k] = abs(float(v)) or 1.0
            actions.append({"field": "combat.base_values", "action": "clamped negative base stats"})
        if not economy.get("currency"):
            economy["currency"] = "credits"
            actions.append({"field": "economy.currency", "action": "filled default currency"})
        if float(economy.get("starting_balance") or 0) < 0:
            economy["starting_balance"] = abs(float(economy.get("starting_balance") or 0)) or 10.0
            actions.append({"field": "economy.starting_balance", "action": "clamped negative starting balance"})
        if not progression.get("curve"):
            progression["curve"] = "quadratic"
            actions.append({"field": "progression.curve", "action": "filled default curve"})
        if int(progression.get("max_level") or 0) < 1:
            progression["max_level"] = 20
            actions.append({"field": "progression.max_level", "action": "filled default max level"})
    if base_values:
        combat["base_values"] = base_values
    if combat:
        fixed["combat"] = combat
    if economy:
        fixed["economy"] = economy
    if progression:
        fixed["progression"] = progression
    after = verifier.verify_game_logic(fixed, description=description)
    result = {"kind": "pipeline-repair-attempt", "surface": "game_logic", "ok": int(after.accepted), "reason": str(after.reason), "weakest_path": str(after.weakest_path or before.weakest_path or ""), "before": before.to_dict(), "after": after.to_dict(), "actions": actions, "changed": int(bool(actions)), "targeted_path": str(before.weakest_path or "game_logic"), "stored_prose": 0, "spec": fixed}
    append_repair(result, root=root)
    return result
