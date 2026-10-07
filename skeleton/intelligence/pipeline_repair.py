"""Bounded pipeline repair scaffold.

A repair may name what is missing. It does not invent the missing NPC or
dialogue and then score that invention as accepted.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

from skeleton.intelligence.dialogue_verifier import DialogueVerifier
from skeleton.intelligence.npc_verifier import NpcVerifier
from skeleton.organism.policy_enforcement import repair_class_enabled, repair_enabled_for, threshold_for
from skeleton.organism.quality_state import append_repair


def _proposal(field: str, action: str) -> Dict[str, Any]:
    return {"field": field, "action": action, "applied": 0}


def _result(surface: str, before, proposals, payload_key: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    report = before.to_dict()
    return {
        "kind": "pipeline-repair-attempt",
        "surface": surface,
        "ok": int(before.accepted),
        "reason": str(before.reason),
        "weakest_path": str(before.weakest_path or ""),
        "before": report,
        "after": report,
        "actions": proposals,
        "changed": 0,
        "targeted_path": str(before.weakest_path or surface),
        "stored_prose": 0,
        payload_key: dict(payload),
    }


def attempt_npc_repair(spec: Mapping[str, Any], *, description: str = "", root=None) -> Dict[str, Any]:
    if not repair_enabled_for("npc", root=root):
        return {"kind": "pipeline-repair-attempt", "surface": "npc", "ok": 0, "reason": "repair-disabled", "actions": [], "changed": 0, "stored_prose": 0, "spec": dict(spec)}
    verifier = NpcVerifier(accept_at=threshold_for("npc", root=root, fallback=0.7), root=root)
    before = verifier.verify(spec, description=description)
    proposals = []
    if not before.accepted and repair_class_enabled("pipeline_seed", root=root):
        persona = spec.get("persona") or {}
        if not spec.get("name"):
            proposals.append(_proposal("name", "needs a name"))
        if not spec.get("archetype") and not persona.get("archetype"):
            proposals.append(_proposal("archetype", "needs an archetype"))
        if not persona.get("traits"):
            proposals.append(_proposal("persona.traits", "needs traits"))
        dialogue = spec.get("dialogue_tree")
        if not isinstance(dialogue, list) or len(dialogue) < 2:
            proposals.append(_proposal("dialogue_tree", "needs a dialogue tree"))
        behavior = spec.get("behaviour_graph")
        if not isinstance(behavior, list) or len(behavior) < 2:
            proposals.append(_proposal("behaviour_graph", "needs a behavior graph"))
    result = _result("npc", before, proposals, "spec", spec)
    append_repair(result, root=root)
    return result


def attempt_dialogue_repair(tree: Mapping[str, Any], *, description: str = "", root=None) -> Dict[str, Any]:
    if not repair_enabled_for("dialogue", root=root):
        return {"kind": "pipeline-repair-attempt", "surface": "dialogue", "ok": 0, "reason": "repair-disabled", "actions": [], "changed": 0, "stored_prose": 0, "tree": dict(tree)}
    verifier = DialogueVerifier(accept_at=threshold_for("dialogue", root=root, fallback=0.7), root=root)
    before = verifier.verify(tree, description=description)
    proposals = []
    if not before.accepted and repair_class_enabled("pipeline_seed", root=root):
        nodes = tree.get("nodes") or {}
        if not tree.get("entry"):
            proposals.append(_proposal("entry", "needs an entry"))
        if not nodes:
            proposals.append(_proposal("nodes", "needs nodes"))
    result = _result("dialogue", before, proposals, "tree", tree)
    append_repair(result, root=root)
    return result
