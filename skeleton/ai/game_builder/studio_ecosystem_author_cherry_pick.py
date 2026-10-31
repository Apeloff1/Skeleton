"""Selectively transplant original authored prose across source-leased revisions.

This is a deterministic, operator-authorized cherry-pick, not a merge of game
state. Every source must share the registered project and pass canon proof.
Only existing author-editable fields can move. Conflicts never auto-resolve.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from .studio_ecosystem_author_revision import (
    MAX_SOURCE_BYTES, REVISION_SCHEMA, _allowed_path, _canonical, _digest,
    preview_canon_revision,
)
from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_revision_impact import compare_revision_sources

CHERRY_PICK_SCHEMA = "skeleton.game_builder.studio_author_cherry_pick.v1"
MAX_SELECTED_PATHS = 16


def _at(source: Mapping[str, Any], path: list[str | int]) -> Any:
    value: Any = source
    try:
        for part in path:
            value = value[part]
    except (KeyError, IndexError, TypeError) as exc:
        raise StudioQuestError("authored cherry-pick path missing") from exc
    return value


def cherry_pick_canon_revision(
    base: Mapping[str, Any],
    donor: Mapping[str, Any],
    target: Mapping[str, Any],
    selected_paths: list[list[str | int]],
    *,
    authorized: bool,
) -> tuple[dict[str, Any], bytes, dict[str, object], dict[str, object]]:
    """Apply explicit donor changes to target and compile a new playable bundle.

    The base identifies the common ancestor. The donor and target may each
    have other independent prose edits, but never protected source mutations.
    No input is changed; prior save/replay leases remain invalid for new source.
    """
    if authorized is not True:
        raise PermissionError("authored cherry-pick requires operator authorization")
    if (type(selected_paths) is not list
            or not 1 <= len(selected_paths) <= MAX_SELECTED_PATHS):
        raise StudioQuestError("invalid authored cherry-pick selection count")
    snapshots: list[bytes] = []
    proofs: list[dict[str, Any]] = []
    for source in (base, donor, target):
        if not isinstance(source, Mapping):
            raise StudioQuestError("authored cherry-pick requires three sources")
        raw = _canonical(source)
        if len(raw) > MAX_SOURCE_BYTES:
            raise StudioQuestError("authored cherry-pick source exceeds byte budget")
        proof = audit_canon_source(source, authorized=True)
        if not proof["canon_consistent"]:
            raise StudioQuestError("authored cherry-pick rejects contradictory canon")
        snapshots.append(raw)
        proofs.append(proof)
    if len({p["project_id"] for p in proofs}) != 1:
        raise StudioQuestError("authored cherry-pick cross-project source refused")
    donor_impact = compare_revision_sources(base, donor, authorized=True)
    target_impact = compare_revision_sources(base, target, authorized=True)
    for impact in (donor_impact, target_impact):
        for change in impact["changed_paths"]:
            path = change["path"]
            if (type(path) is not list or len(path) < 2
                    or type(path[0]) is not str
                    or not _allowed_path(path[0], path[1:])):
                raise StudioQuestError("authored cherry-pick rejects protected source change")
    donor_paths = {_canonical(c["path"]): c["path"]
                   for c in donor_impact["changed_paths"]}
    target_paths = {_canonical(c["path"])
                    for c in target_impact["changed_paths"]}
    edits: list[dict[str, Any]] = []
    seen: set[bytes] = set()
    for path in selected_paths:
        if (type(path) is not list or len(path) < 2
                or type(path[0]) is not str
                or not _allowed_path(path[0], path[1:])):
            raise StudioQuestError("invalid or protected authored cherry-pick path")
        key = _canonical(path)
        if key in seen or key not in donor_paths:
            raise StudioQuestError("duplicate or unchanged authored cherry-pick path")
        seen.add(key)
        donor_value = _at(donor, path)
        target_value = _at(target, path)
        if key in target_paths and donor_value != target_value:
            raise StudioQuestError("authored cherry-pick conflict at " + key.decode("ascii"))
        if donor_value == target_value:
            raise StudioQuestError("authored cherry-pick would be a no-op")
        if type(donor_value) is not str:
            raise StudioQuestError("authored cherry-pick requires original prose")
        edits.append({"section": path[0], "path": path[1:], "value": donor_value})
    revised, html, receipt = preview_canon_revision(
        target, {
            "schema": REVISION_SCHEMA,
            "project_id": proofs[0]["project_id"],
            "expected_source_digest": proofs[2]["source_digest"],
            "edits": edits,
        }, authorized=True)
    if any(_canonical(source) != raw
           for source, raw in zip((base, donor, target), snapshots, strict=True)):
        raise StudioQuestError("authored cherry-pick source drift")
    impact = compare_revision_sources(target, revised, authorized=True)
    receipt["cherry_pick_provenance"] = {
        "schema": CHERRY_PICK_SCHEMA,
        "base_source_digest": proofs[0]["source_digest"],
        "donor_source_digest": proofs[1]["source_digest"],
        "target_source_digest": proofs[2]["source_digest"],
        "result_source_digest": receipt["revised_source_digest"],
        "selected_paths": selected_paths,
        "selected_count": len(edits),
        "conflict_count": 0,
        "external_authorship_verified": False,
    }
    receipt.pop("receipt_digest")
    receipt["receipt_digest"] = _digest(receipt)
    return revised, html, receipt, impact
