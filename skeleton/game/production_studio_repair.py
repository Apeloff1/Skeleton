"""Governed 27-plane source-edit proposals with measurable repair previews.

Only a trusted host may authorize a patch and independently verify resulting
authored candidate source. This plane DOES NOT persist, release, approve rights,
or invent native evidence. Candidate previews can be rejected or compared.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from typing import Any

from .production_quality import QualityGateError, _digest
from .production_studio_gates import audit_complete_studio, verify_complete_studio

_EDITOR_FAMILIES = frozenset((
    "cinematics", "dialogue", "npcs", "streaming", "saves",
    "environment", "latency",
))
_PROTECTED = frozenset((
    "source_sha256", "sha256", "receipt", "receipt_digest",
    "evidence_digest", "original_source", "reviewer_id",
    "independently_replayed", "observed", "has_voice",
    "verified", "approved", "native_process_executed",
    "production_approved", "release_certified",
))


def _apply_patch(original: dict, patch: Mapping[str, Any]) -> None:
    if type(patch) is not dict or set(patch) != {"path", "old", "new"}:
        raise QualityGateError("studio repair requires exact path/old/new patch")
    path = patch["path"]
    if (type(path) not in (list, tuple) or not 3 <= len(path) <= 16 or
            path[0] != "studio" or path[1] not in _EDITOR_FAMILIES or
            any(type(part) not in (str, int) for part in path) or
            any(type(part) is str and (part in _PROTECTED or
                    part.startswith("_") or len(part) > 128) for part in path) or
            any(type(part) is int and not 0 <= part < 100000 for part in path)):
        raise QualityGateError("patch escapes authorized original studio editor surface")
    node: Any = original
    for part in path[:-1]:
        if type(node) is dict:
            if type(part) is not str or part not in node:
                raise QualityGateError("source edit references absent field")
            node = node[part]
        elif type(node) is list:
            if type(part) is not int or not 0 <= part < len(node):
                raise QualityGateError("source edit references absent item")
            node = node[part]
        else:
            raise QualityGateError("source edit traverses non-editor data")
    leaf = path[-1]
    if (type(node) is dict and (type(leaf) is not str or leaf not in node)
            or type(node) is list and (type(leaf) is not int or not 0 <= leaf < len(node))
            or type(node) not in (list, dict)):
        raise QualityGateError("repair cannot add undeclared editor fields")
    if node[leaf] != patch["old"]:
        raise QualityGateError("stale repair: exact original value changed")
    if isinstance(patch["new"], (dict, list)):
        raise QualityGateError("editor repair only permits one scalar edit at a time")
    if type(patch["new"]) not in (str, float, int, bool, type(None)):
        raise QualityGateError("editor repair scalar must be canonical JSON")
    node[leaf] = deepcopy(patch["new"])


def preview_reviewed_studio_repairs(
    bundle: Mapping[str, Any],
    patches: Sequence[Mapping[str, Any]], *,
    authorize: Callable[[Mapping[str, Any]], bool],
    independently_verify: Callable[[Mapping[str, Any]], bool],
    max_attempts: int = 16,
) -> dict:
    """Host-gated, non-persistent improvements; reject neutral or regressing edits."""
    if (not isinstance(bundle, Mapping) or type(patches) not in (list, tuple)
            or len(patches) > 64 or not callable(authorize)
            or not callable(independently_verify)
            or type(max_attempts) is not int or not 1 <= max_attempts <= 64):
        raise QualityGateError("bounded repair plan and trusted host verifiers required")
    working = deepcopy(dict(bundle))
    before = audit_complete_studio(working)
    starting_source = before["source_digest"]
    actions = []
    for index, patch in enumerate(patches[:max_attempts]):
        if authorize(patch) is not True:
            actions.append({"index": index, "outcome": "host_denied"})
            continue
        changed = deepcopy(working)
        try:
            _apply_patch(changed, patch)
            # The host must independently recompile/revalidate original source.
            if independently_verify(changed) is not True:
                raise QualityGateError("trusted source reviewer refused candidate")
            observed = audit_complete_studio(changed)
            if observed["source_digest"] != starting_source:
                raise QualityGateError("repair changed protected original source")
            verify_complete_studio(changed, observed)
        except (ValueError, KeyError, IndexError, TypeError, RecursionError) as exc:
            actions.append({"index": index, "outcome": "invalid_or_unreviewed",
                            "reason": type(exc).__name__})
            continue
        if len(observed["findings"]) >= len(before["findings"]):
            actions.append({"index": index, "outcome": "not_objectively_better"})
            continue
        actions.append({"index": index, "outcome": "measured_improvement",
                        "previous_findings": len(before["findings"]),
                        "remaining_findings": len(observed["findings"]),
                        "result_sha256": observed["evidence_digest"]})
        before, working = observed, changed
    result = {
        "schema": "game.studio.nonpersistent_repair_preview.v1",
        "source_sha256": starting_source,
        "attempt_count": len(actions),
        "accepted_count": sum(x["outcome"] == "measured_improvement" for x in actions),
        "attempts": actions,
        "proposed_source": working,
        "post_quality": before,
        "persisted": False,
        "release_approved": False,
        "rights_review_bypassed": False,
        "native_engine_executed": False,
    }
    return {**result, "receipt_digest": _digest(result)}
