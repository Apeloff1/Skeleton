"""Bounded forge repair scaffold.

Now wired to policy_enforcement for dynamic threshold/repair gating.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping

from skeleton.intelligence.forge_verifier import ForgeVerifier
from skeleton.organism.policy_enforcement import repair_class_enabled, repair_enabled_for, threshold_for
from skeleton.organism.quality_state import append_repair, latest_failure, repair_candidates


def latest_repair_plan(*, root=None) -> Dict[str, Any]:
    failure = latest_failure(root=root, surface="forge")
    if not failure:
        return {"kind": "forge-repair-plan", "ok": 0, "reason": "no-failure", "targets": [], "stored_prose": 0}
    reason = failure.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return {"kind": "forge-repair-plan", "ok": 0, "reason": "missing-reason", "targets": [], "stored_prose": 0}
    return {"kind": "forge-repair-plan", "ok": 1, "reason": reason, "surface": "forge", "weakest_path": failure.get("weakest_path") or "", "targets": _targets(failure), "stored_prose": 0}


def candidate_failures(*, root=None, limit: int = 5) -> Dict[str, Any]:
    rows = repair_candidates(root=root, surface="forge")[:max(1, limit)]
    return {"kind": "forge-repair-candidates", "n": len(rows), "items": rows, "stored_prose": 0}


def attempt_repair(files: Mapping[str, str], *, request: str = "", root=None, evidence: Dict[str, Any] | None = None) -> Dict[str, Any]:
    gate = repair_enabled_for("forge", root=root)
    if not gate:
        return {"kind": "forge-repair-attempt", "ok": 0, "surface": "forge", "reason": "repair-disabled", "actions": [], "changed": 0, "stored_prose": 0, "files": dict(files)}
    threshold = threshold_for("forge", root=root, fallback=0.7)
    before = ForgeVerifier(accept_at=threshold, gd_accept_at=threshold, root=root).verify(files, request=request)
    proposals: List[Dict[str, Any]] = []
    if not before.accepted:
        target = _select_target(before.to_dict(), evidence or {})
        weakest = target or before.weakest_path or ""
        if weakest.endswith(".gd") and repair_class_enabled("script_patch", root=root):
            proposals.append({"path": weakest, "action": "needs a real script", "applied": 0})
        if before.reason == "project_closure" and repair_class_enabled("project_closure", root=root):
            proposals.append({"path": "project.godot", "action": "needs a closed project graph", "applied": 0})
    else:
        weakest = ""
    report = before.to_dict()
    result = {
        "kind": "forge-repair-attempt",
        "ok": int(before.accepted),
        "surface": "forge",
        "reason": str(before.reason),
        "weakest_path": str(before.weakest_path or ""),
        "before": report,
        "after": report,
        "actions": proposals,
        "changed": 0,
        "targeted_path": weakest if not before.accepted else "",
        "stored_prose": 0,
        "files": dict(files),
    }
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
    reason = failure.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return []
    weakest = failure.get("weakest_path") if isinstance(failure.get("weakest_path"), str) else ""
    summary = dict(failure.get("summary") or {})
    evidence = dict(failure.get("evidence") or {})
    top = list(evidence.get("top_file_reports") or [])
    targets: List[Dict[str, Any]] = []
    for item in top:
        if item.get("hard_issues") and isinstance(item.get("path"), str) and item["path"]:
            targets.append({"target": item["path"], "action": "clear hard verification failures first"})
    if reason == "project_closure":
        targets.append({"target": "project graph", "action": "restore missing required files or references"})
    if reason in {"unsafe_code", "low_score"} and weakest:
        targets.append({"target": weakest, "action": "repair weakest emitted file first"})
    blocking = summary.get("blocking_issues")
    if isinstance(blocking, int) and not isinstance(blocking, bool) and blocking > 0:
        targets.append({"target": "blocking issues", "action": "clear hard verification failures before soft tuning"})
    return targets


def polish_artefact(
    item: Mapping[str, Any],
    *,
    root=None,
    max_rounds: int = 3,
    stage_index: int = 0,
    stage_floor_grade: int = 0,
    gdd_stages=(),
    regions=(),
    era: str | None = None,
    artefact_id: str = "",
    use_file_repair: bool = True,
) -> Dict[str, Any]:
    """Bounded forge quality polish loop (Prood forge_quality / polish surface).

    Composes ``forge_quality.polish_loop`` with optional ``attempt_repair`` on
    embedded file maps. Does not rewrite VerificationLoop.
    """
    from skeleton.forge.forge_quality import polish_loop

    repair_fn = attempt_repair if use_file_repair else None
    return polish_loop(
        item,
        stage_index=stage_index,
        stage_floor_grade=stage_floor_grade,
        gdd_stages=gdd_stages,
        regions=regions,
        era=era,
        max_rounds=max_rounds,
        persist=True,
        artefact_id=artefact_id,
        root=root,
        repair_files=repair_fn,
    )
