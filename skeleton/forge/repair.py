"""Bounded forge repair scaffold."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping

from skeleton.intelligence.forge_verifier import ForgeVerifier
from skeleton.organism.policy_state import load_policy
from skeleton.organism.quality_state import append_repair, latest_failure, repair_candidates


def latest_repair_plan(*, root=None) -> Dict[str, Any]:
    failure = latest_failure(root=root, surface="forge")
    if not failure:
        return {"kind": "forge-repair-plan", "ok": 0, "reason": "no-failure", "targets": [], "stored_prose": 0}
    return {"kind": "forge-repair-plan", "ok": 1, "reason": str(failure.get("reason") or "unknown"), "surface": "forge", "weakest_path": failure.get("weakest_path") or "", "targets": _targets(failure), "stored_prose": 0}


def candidate_failures(*, root=None, limit: int = 5) -> Dict[str, Any]:
    rows = repair_candidates(root=root, surface="forge")[:max(1, limit)]
    return {"kind": "forge-repair-candidates", "n": len(rows), "items": rows, "stored_prose": 0}


def attempt_repair(files: Mapping[str, str], *, request: str = "", root=None, evidence: Dict[str, Any] | None = None) -> Dict[str, Any]:
    policy = load_policy(root=root)
    if not bool((policy.get("repair_enabled") or {}).get("forge", True)):
        return {"kind": "forge-repair-attempt", "ok": 0, "surface": "forge", "reason": "repair-disabled", "actions": [], "changed": 0, "stored_prose": 0, "files": dict(files)}
    before = ForgeVerifier(accept_at=float((policy.get("quality_thresholds") or {}).get("forge", 0.7)), gd_accept_at=float((policy.get("quality_thresholds") or {}).get("forge", 0.7))).verify(files, request=request)
    fixed = dict(files)
    actions: List[Dict[str, Any]] = []
    target = _select_target(before.to_dict(), evidence or {})
    classes = dict(policy.get("repair_classes") or {})
    if not before.accepted:
        weakest = target or before.weakest_path or ""
        if weakest.endswith(".gd") and weakest in fixed and classes.get("script_patch", True):
            src = fixed[weakest]
            changed = src
            if "extends " not in changed:
                changed = "extends Node\n" + changed
            if "func " not in changed:
                changed += "\nfunc _repair_stub():\n    pass\n"
            if "eval(" in changed:
                changed = changed.replace("eval(", "# eval(")
            if changed != src:
                fixed[weakest] = changed
                actions.append({"path": weakest, "action": "patched targeted script once"})
        if before.reason == "project_closure":
            project = fixed.get("project.godot", "")
            if project and 'run/main_scene=' not in project and classes.get("project_closure", True):
                fixed["project.godot"] = project + 'run/main_scene="res://scenes/levels/run_level.tscn"\n'
                actions.append({"path": "project.godot", "action": "restored main scene entry"})
            if 'EventBus="*res://scripts/autoloads/event_bus.gd"' not in project and project and classes.get("project_closure", True):
                fixed["project.godot"] = fixed["project.godot"] + 'EventBus="*res://scripts/autoloads/event_bus.gd"\n'
                actions.append({"path": "project.godot", "action": "restored EventBus autoload"})
            if "scripts/autoloads/event_bus.gd" not in fixed and classes.get("scene_stub", True):
                fixed["scripts/autoloads/event_bus.gd"] = "extends Node\nsignal repaired()\n"
                actions.append({"path": "scripts/autoloads/event_bus.gd", "action": "stubbed missing EventBus autoload file"})
    after = ForgeVerifier(accept_at=float((policy.get("quality_thresholds") or {}).get("forge", 0.7)), gd_accept_at=float((policy.get("quality_thresholds") or {}).get("forge", 0.7))).verify(fixed, request=request)
    result = {"kind": "forge-repair-attempt", "ok": int(after.accepted), "surface": "forge", "reason": str(after.reason), "weakest_path": str(after.weakest_path or before.weakest_path or ""), "before": before.to_dict(), "after": after.to_dict(), "actions": actions, "changed": int(bool(actions)), "targeted_path": weakest if not before.accepted else "", "stored_prose": 0, "files": fixed}
    append_repair(result, root=root)
    return result


def _select_target(before: Dict[str, Any], evidence: Dict[str, Any]) -> str:
    top = list(evidence.get("top_file_reports") or [])
    for item in top:
        if item.get("hard_issues") and item.get("path"):
            return str(item["path"])
    for item in top:
        if item.get("path"):
            return str(item["path"])
    return str(before.get("weakest_path") or "")


def _targets(failure: Dict[str, Any]) -> List[Dict[str, Any]]:
    reason = str(failure.get("reason") or "unknown")
    weakest = str(failure.get("weakest_path") or "")
    summary = dict(failure.get("summary") or {})
    evidence = dict(failure.get("evidence") or {})
    top = list(evidence.get("top_file_reports") or [])
    hard_first = []
    for item in top:
        if item.get("hard_issues"):
            hard_first.append({"target": item.get("path") or weakest or "generated script", "action": "clear hard verification failures first"})
    targets: List[Dict[str, Any]] = hard_first[:]
    if reason == "project_closure":
        targets.append({"target": "project graph", "action": "restore missing required files or references"})
    if reason in {"unsafe_code", "low_score"}:
        targets.append({"target": weakest or "generated script", "action": "repair weakest emitted file first"})
    if int(summary.get("blocking_issues") or 0) > 0:
        targets.append({"target": "blocking issues", "action": "clear hard verification failures before soft tuning"})
    if not targets:
        targets.append({"target": weakest or "forge output", "action": "re-emit and re-verify once"})
    return targets
