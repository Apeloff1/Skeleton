"""Reviewable, bounded game quality repair cycles without evidence fabrication."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from typing import Any

from .production_quality import QualityGateError, _digest
from .production_deep_gates import audit_deep_candidate

# Repairs must be supplied by a trusted original source/editor owner. No
# unsafe auto-filling signatures, measurements, legal rights or game victories.
_SAFE_EDIT_ROOTS = frozenset({"world", "story", "assets", "design", "campaign",
                              "screens", "profiles", "envelopes", "package"})
_FORBIDDEN_FIELDS = frozenset({
    "sha256", "source_sha256", "receipt", "evidence_ref",
    "reviewed", "observed", "won", "candidate_passed", "release_certified",
    "native_process_executed", "native_gameplay_consistent", "verified",
    "completed", "playthroughs", "proofs", "frames", "session", "builds",
    "sources",
})


def suggest_quality_repairs(report: Mapping[str, Any]) -> dict:
    """Produce individual, actionable work tickets from real gate findings."""
    if (not isinstance(report, Mapping) or
            report.get("schema") != "game.candidate.deep_quality.v1" or
            not isinstance(report.get("findings"), list)):
        raise QualityGateError("deep quality report required for deterministic repair plan")
    actions = []
    seen = set()
    for finding in report["findings"][:1000]:
        if type(finding) is not dict:
            raise QualityGateError("malformed source quality finding")
        key = (finding.get("gate"), finding.get("code"), finding.get("subject"))
        if any(type(x) is not str or len(x) > 256 for x in key):
            raise QualityGateError("invalid quality finding identity")
        if key in seen:
            continue
        seen.add(key)
        gate, code, subject = key
        owner = {
            "world": "world_editor", "canon": "narrative_director",
            "assets": "asset_forge", "replay": "build_pipeline",
            "performance": "render_optimizer", "rights": "human_rights_reviewer",
            "traceability": "gdd_author", "quests": "quest_director",
            "accessibility": "ui_director", "controls": "controller_editor",
            "resources": "resource_optimizer", "session": "canonical_replay_owner",
            "package": "build_linker",
        }.get(gate, "quality_owner")
        actions.append({"gate": gate, "code": code, "subject": subject,
                        "responsible_owner": owner, "requires_source_edit": True,
                        "automatically_authorized": False})
    plan = {
        "schema": "game.quality_repair_plan.v1",
        "source_sha256": report.get("source_digest"),
        "initial_evidence_sha256": report.get("evidence_digest"),
        "actions": actions, "work_items": len(actions),
        "automatic_edits": 0, "rights_override_allowed": False,
    }
    return {**plan, "receipt_digest": _digest(plan)}


def _apply_edit(target: dict, edit: Mapping[str, Any]) -> None:
    """Restricted exact-old-value replacement; no arbitrary pointer eval."""
    if type(edit) is not dict or set(edit) != {"path", "old", "new"}:
        raise QualityGateError("repair must be an exact three-field patch")
    parts = edit["path"]
    if (type(parts) not in (list, tuple) or not 2 <= len(parts) <= 12 or
            parts[0] not in _SAFE_EDIT_ROOTS or
            any(type(p) not in (str, int) or isinstance(p, bool) for p in parts) or
            any(type(p) is str and p in _FORBIDDEN_FIELDS for p in parts)):
        raise QualityGateError("repair targets an authoritative/provenance field")
    cursor: Any = target
    for part in parts[:-1]:
        if type(part) is int and (type(cursor) is not list or not 0 <= part < len(cursor)):
            raise QualityGateError("repair array index escaped source")
        if type(part) is str and (type(cursor) is not dict or part not in cursor):
            raise QualityGateError("repair key absent from source")
        cursor = cursor[part]
    leaf = parts[-1]
    if type(cursor) is not dict and type(cursor) is not list:
        raise QualityGateError("repair did not select container")
    if (type(cursor) is list and (type(leaf) is not int or not 0 <= leaf < len(cursor))
            or type(cursor) is dict and (type(leaf) is not str or leaf not in cursor)):
        raise QualityGateError("repair destination does not exist")
    if cursor[leaf] != edit["old"]:
        raise QualityGateError("stale edit; original value changed")
    cursor[leaf] = deepcopy(edit["new"])


def execute_reviewed_repairs(
    candidate: Mapping[str, Any], repairs: Sequence[Mapping[str, Any]], *,
    authorize: Callable[[Mapping[str, Any]], bool],
    verify_source: Callable[[Mapping[str, Any]], bool],
    max_attempts: int = 16,
) -> dict:
    """Apply host-authorized patches only to an isolated candidate copy.

    Every repair is independently rechecked by a host-provided verifier.
    Only measurable strictly decreasing defect counts can advance a cycle.
    Nothing persists, signs release or changes authoritative game state.
    """
    if (not isinstance(candidate, Mapping) or
            type(repairs) not in (list, tuple) or len(repairs) > 64 or
            type(max_attempts) is not int or not 1 <= max_attempts <= 64 or
            not callable(authorize) or not callable(verify_source)):
        raise QualityGateError("finite source-bound repair batch and host callbacks required")
    working = deepcopy(dict(candidate))
    before = audit_deep_candidate(working)
    history = []
    for index, repair in enumerate(repairs[:max_attempts]):
        if authorize(repair) is not True:
            history.append({"attempt": index, "status": "denied"})
            continue
        changed = deepcopy(working)
        try:
            _apply_edit(changed, repair)
            if verify_source(changed) is not True:
                raise QualityGateError("independent source checker rejected candidate")
            after = audit_deep_candidate(changed)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            history.append({"attempt": index, "status": "rejected", "reason": type(exc).__name__})
            continue
        if len(after["findings"]) >= len(before["findings"]):
            history.append({"attempt": index, "status": "non_improving"})
            continue
        history.append({"attempt": index, "status": "improved",
                        "new_findings": len(after["findings"])})
        working, before = changed, after
    report = {
        "schema": "game.quality_repair_cycle.v1",
        "source_sha256": candidate.get("source_sha256"),
        "attempted": len(history), "accepted": sum(r["status"] == "improved" for r in history),
        "actions": history, "candidate": working,
        "candidate_report": before, "persisted": False,
        "production_release_certified": False,
    }
    return {**report, "receipt_digest": _digest(report)}
