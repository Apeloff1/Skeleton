"""Bounded forge repair scaffold.

Takes the latest failed forge quality record and produces a repair plan.
This pass also includes a single bounded repair attempt that rewrites an
in-memory file map for one common failure class, then re-verifies it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping

from skeleton.intelligence.forge_verifier import ForgeVerifier
from skeleton.organism.quality_state import append_repair, latest_failure, repair_candidates


def latest_repair_plan(*, root=None) -> Dict[str, Any]:
    failure = latest_failure(root=root, surface="forge")
    if not failure:
        return {
            "kind": "forge-repair-plan",
            "ok": 0,
            "reason": "no-failure",
            "targets": [],
            "stored_prose": 0,
        }
    return {
        "kind": "forge-repair-plan",
        "ok": 1,
        "reason": str(failure.get("reason") or "unknown"),
        "surface": "forge",
        "weakest_path": failure.get("weakest_path") or "",
        "targets": _targets(failure),
        "stored_prose": 0,
    }


def candidate_failures(*, root=None, limit: int = 5) -> Dict[str, Any]:
    rows = repair_candidates(root=root, surface="forge")[:max(1, limit)]
    return {
        "kind": "forge-repair-candidates",
        "n": len(rows),
        "items": rows,
        "stored_prose": 0,
    }


def attempt_repair(files: Mapping[str, str], *, request: str = "", root=None) -> Dict[str, Any]:
    """One bounded repair pass over an emitted file map, then re-verify."""
    before = ForgeVerifier().verify(files, request=request)
    fixed = dict(files)
    actions: List[Dict[str, Any]] = []

    if not before.accepted:
        weakest = before.weakest_path or ""
        if weakest.endswith(".gd") and weakest in fixed:
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
                actions.append({"path": weakest, "action": "patched weakest script once"})

        if before.reason == "project_closure":
            project = fixed.get("project.godot", "")
            if project and 'run/main_scene=' not in project:
                fixed["project.godot"] = project + 'run/main_scene="res://scenes/levels/run_level.tscn"\n'
                actions.append({"path": "project.godot", "action": "restored main scene entry"})

    after = ForgeVerifier().verify(fixed, request=request)
    result = {
        "kind": "forge-repair-attempt",
        "ok": int(after.accepted),
        "surface": "forge",
        "reason": str(after.reason),
        "weakest_path": str(after.weakest_path or before.weakest_path or ""),
        "before": before.to_dict(),
        "after": after.to_dict(),
        "actions": actions,
        "changed": int(bool(actions)),
        "stored_prose": 0,
        "files": fixed,
    }
    append_repair(result, root=root)
    return result


def _targets(failure: Dict[str, Any]) -> List[Dict[str, Any]]:
    reason = str(failure.get("reason") or "unknown")
    weakest = str(failure.get("weakest_path") or "")
    summary = dict(failure.get("summary") or {})
    targets: List[Dict[str, Any]] = []
    if reason == "project_closure":
        targets.append({"target": "project graph", "action": "restore missing required files or references"})
    if reason in {"unsafe_code", "low_score"}:
        targets.append({"target": weakest or "generated script", "action": "repair weakest emitted file first"})
    if int(summary.get("blocking_issues") or 0) > 0:
        targets.append({"target": "blocking issues", "action": "clear hard verification failures before soft tuning"})
    if not targets:
        targets.append({"target": weakest or "forge output", "action": "re-emit and re-verify once"})
    return targets
