"""Bounded forge repair scaffold.

Takes the latest failed forge quality record and produces a repair plan.
This first pass is diagnostic and non-destructive: it does not mutate files,
it only names the next candidate targets for a future revise/re-emit loop.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from skeleton.organism.quality_state import latest_failure, repair_candidates


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
