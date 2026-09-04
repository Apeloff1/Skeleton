"""Bounded pipeline repair scaffold.

Starts with dialogue trees and NPC specs. One conservative repair pass,
then re-verify and persist the repair as its own record.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

from skeleton.intelligence.dialogue_verifier import DialogueVerifier
from skeleton.intelligence.npc_verifier import NpcVerifier
from skeleton.organism.policy_state import load_policy
from skeleton.organism.quality_state import append_repair


def attempt_npc_repair(spec: Mapping[str, Any], *, description: str = "", root=None) -> Dict[str, Any]:
    policy = load_policy(root=root)
    if not bool((policy.get("repair_enabled") or {}).get("npc", True)):
        return {"kind": "pipeline-repair-attempt", "surface": "npc", "ok": 0, "reason": "repair-disabled", "actions": [], "changed": 0, "stored_prose": 0, "spec": dict(spec)}
    threshold = float((policy.get("quality_thresholds") or {}).get("npc", 0.7))
    verifier = NpcVerifier(accept_at=threshold)
    before = verifier.verify(spec, description=description)
    fixed = dict(spec)
    actions = []
    persona = dict(fixed.get("persona") or {})
    allow_seed = bool((policy.get("repair_classes") or {}).get("pipeline_seed", True))
    if not before.accepted and allow_seed:
        if not fixed.get("name"):
            fixed["name"] = "npc_repaired"
            actions.append({"field": "name", "action": "filled default npc name"})
        if not fixed.get("archetype") and not persona.get("archetype"):
            fixed["archetype"] = "guardian"
            persona.setdefault("archetype", "guardian")
            actions.append({"field": "archetype", "action": "filled default archetype"})
        if not persona.get("traits"):
            persona["traits"] = ["stoic", "loyal"]
            actions.append({"field": "persona.traits", "action": "filled default traits"})
        if len(fixed.get("dialogue_tree") or []) < 2:
            fixed["dialogue_tree"] = [{"node_id": "root", "line": "Hello.", "choices": ["farewell"]}, {"node_id": "farewell", "line": "Goodbye.", "choices": []}]
            actions.append({"field": "dialogue_tree", "action": "seeded minimal dialogue tree"})
        if len(fixed.get("behaviour_graph") or []) < 2:
            fixed["behaviour_graph"] = [{"name": "idle", "enter": "idle", "exit": "idle", "transitions": [["player_near", "greet"]]}, {"name": "greet", "enter": "greet", "exit": "idle", "transitions": [["dialogue_end", "idle"]]}]
            actions.append({"field": "behaviour_graph", "action": "seeded minimal behavior graph"})
    if persona:
        fixed["persona"] = persona
    after = verifier.verify(fixed, description=description)
    result = {"kind": "pipeline-repair-attempt", "surface": "npc", "ok": int(after.accepted), "reason": str(after.reason), "weakest_path": str(after.weakest_path or before.weakest_path or ""), "before": before.to_dict(), "after": after.to_dict(), "actions": actions, "changed": int(bool(actions)), "targeted_path": str(before.weakest_path or "npc"), "stored_prose": 0, "spec": fixed}
    append_repair(result, root=root)
    return result


def attempt_dialogue_repair(tree: Mapping[str, Any], *, description: str = "", root=None) -> Dict[str, Any]:
    policy = load_policy(root=root)
    if not bool((policy.get("repair_enabled") or {}).get("dialogue", True)):
        return {"kind": "pipeline-repair-attempt", "surface": "dialogue", "ok": 0, "reason": "repair-disabled", "actions": [], "changed": 0, "stored_prose": 0, "tree": dict(tree)}
    threshold = float((policy.get("quality_thresholds") or {}).get("dialogue", 0.7))
    verifier = DialogueVerifier(accept_at=threshold)
    before = verifier.verify(tree, description=description)
    fixed = dict(tree)
    actions = []
    nodes = dict(fixed.get("nodes") or {})
    allow_seed = bool((policy.get("repair_classes") or {}).get("pipeline_seed", True))
    if not before.accepted and allow_seed:
        if not fixed.get("entry"):
            fixed["entry"] = "root"
            actions.append({"field": "entry", "action": "filled default entry"})
        if not nodes:
            nodes = {"root": {"speaker": "npc", "line": "Hello.", "terminal": False, "on_enter": {}, "edges": [{"text": "Go", "target": "end", "effects": {}}]}, "end": {"speaker": "npc", "line": "Done.", "terminal": True, "on_enter": {}, "edges": []}}
            actions.append({"field": "nodes", "action": "seeded minimal dialogue tree"})
        elif fixed.get("entry") in nodes and not nodes[fixed["entry"]].get("edges") and not nodes[fixed["entry"]].get("terminal"):
            nodes[fixed["entry"]]["edges"] = [{"text": "Continue", "target": "end", "effects": {}}]
            nodes.setdefault("end", {"speaker": "npc", "line": "Done.", "terminal": True, "on_enter": {}, "edges": []})
            actions.append({"field": "entry.edges", "action": "restored minimal outgoing edge"})
    fixed["nodes"] = nodes
    after = verifier.verify(fixed, description=description)
    result = {"kind": "pipeline-repair-attempt", "surface": "dialogue", "ok": int(after.accepted), "reason": str(after.reason), "weakest_path": str(after.weakest_path or before.weakest_path or ""), "before": before.to_dict(), "after": after.to_dict(), "actions": actions, "changed": int(bool(actions)), "targeted_path": str(before.weakest_path or "dialogue"), "stored_prose": 0, "tree": fixed}
    append_repair(result, root=root)
    return result
