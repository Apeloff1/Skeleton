"""Three-way, source-bound reconciliation of independently authored original worlds.

A merge is a new playable revision, never a mutation of the registered catalog.
Only fields accepted by the canonical prose editor can be merged. No semantic
conflict is guessed away and no old gameplay save lease is silently migrated.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_author_revision import (
    MAX_SOURCE_BYTES, RECEIPT_SCHEMA, _allowed_path, _canonical, _digest,
)
from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_revision_impact import compare_revision_sources
from .studio_ecosystem_story_html import render_story_html

MERGE_SCHEMA = "skeleton.game_builder.studio_author_merge.v1"
MAX_MERGE_EDITS = 32


def _read(source: Mapping[str, Any], path: list[str | int]) -> Any:
    value: Any = source
    try:
        for part in path:
            value = value[part]
    except (KeyError, IndexError, TypeError) as exc:
        raise StudioQuestError("authored merge path missing from source") from exc
    return value


def _apply(source: dict[str, Any], path: list[str | int], value: str) -> None:
    parent: Any = source
    for part in path[:-1]:
        parent = parent[part]
    parent[path[-1]] = value


def merge_canon_revisions(
    base: Mapping[str, Any],
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    authorized: bool,
) -> tuple[dict[str, Any], bytes, dict[str, object], dict[str, object]]:
    """Merge nonconflicting original prose with strict base and source leases.

    A conflicting edit raises before returning an exportable source. The caller
    must explicitly resolve the conflict using a new source-leased author edit.
    """
    if authorized is not True:
        raise PermissionError("authored merge requires operator authorization")
    sources = (base, left, right)
    snapshots: list[bytes] = []
    proofs: list[dict[str, object]] = []
    for source in sources:
        if not isinstance(source, Mapping):
            raise StudioQuestError("authored merge requires three source documents")
        raw = _canonical(source)
        if len(raw) > MAX_SOURCE_BYTES:
            raise StudioQuestError("authored merge source exceeds byte budget")
        proof = audit_canon_source(source, authorized=True)
        if not proof["canon_consistent"]:
            raise StudioQuestError("authored merge rejects contradictory canon")
        snapshots.append(raw)
        proofs.append(proof)
    if len({proof["project_id"] for proof in proofs}) != 1:
        raise StudioQuestError("authored merge cross-project source refused")

    left_impact = compare_revision_sources(base, left, authorized=True)
    right_impact = compare_revision_sources(base, right, authorized=True)
    edits: dict[str, tuple[list[str | int], str, str]] = {}
    for side, impact, source in (
        ("left", left_impact, left), ("right", right_impact, right)
    ):
        for changed in impact["changed_paths"]:
            path = changed["path"]
            if (type(path) is not list or len(path) < 2
                    or type(path[0]) is not str
                    or not _allowed_path(path[0], path[1:])):
                raise StudioQuestError("authored merge refuses protected source changes")
            old = _read(base, path)
            new = _read(source, path)
            if (type(old) is not str or type(new) is not str
                    or not new or new.strip() != new
                    or len(new.encode("utf-8", "strict")) > 512
                    or any(ord(char) < 32 for char in new)):
                raise StudioQuestError("authored merge refuses invalid prose")
            key = json.dumps(path, separators=(",", ":"), ensure_ascii=True)
            if key in edits and edits[key][2] != new:
                raise StudioQuestError("authored merge conflict at " + key)
            if key not in edits:
                edits[key] = (path, side, new)
    if len(edits) > MAX_MERGE_EDITS:
        raise StudioQuestError("authored merge exceeds changed-field budget")

    merged: dict[str, Any] = json.loads(snapshots[0])
    changes: list[dict[str, object]] = []
    for key in sorted(edits):
        path, first_side, value = edits[key]
        before = _read(merged, path)
        _apply(merged, path, value)
        changes.append({
            "path": path, "first_side": first_side,
            "before_digest": _digest(before), "after_digest": _digest(value),
        })
    if len(_canonical(merged)) > MAX_SOURCE_BYTES:
        raise StudioQuestError("merged original source exceeds byte budget")
    proof = audit_canon_source(merged, authorized=True)
    if not proof["canon_consistent"]:
        raise StudioQuestError("authored merge creates contradictory canon")
    html = render_story_html(merged)
    if len(html) > 1024 * 1024:
        raise StudioQuestError("authored merge playable export exceeds byte budget")
    if any(_canonical(source) != raw for source, raw in zip(sources, snapshots, strict=True)):
        raise StudioQuestError("authored merge source drift during proof")
    impact = compare_revision_sources(base, merged, authorized=True)
    receipt: dict[str, object] = {
        "schema": RECEIPT_SCHEMA,
        "project_id": proof["project_id"],
        "base_source_digest": proofs[0]["source_digest"],
        "revised_source_digest": proof["source_digest"],
        "base_proof_digest": proofs[0]["proof_digest"],
        "revised_proof_digest": proof["proof_digest"],
        "playable_html_sha256": sha256(html).hexdigest(),
        "edits": changes,
        "canon_consistent": True,
        "ending_obligations": proof["ending_obligations"],
        "original_catalog_unchanged": True,
        "merge_provenance": {
            "schema": MERGE_SCHEMA,
            "base_source_digest": sha256(snapshots[0]).hexdigest(),
            "left_source_digest": sha256(snapshots[1]).hexdigest(),
            "right_source_digest": sha256(snapshots[2]).hexdigest(),
            "merged_source_digest": sha256(_canonical(merged)).hexdigest(),
            "conflict_count": 0,
            "changed_field_count": len(changes),
        },
        "native_genre_runtime_verified": False,
        "originality_rights_verified": False,
        "release_certified": False,
    }
    receipt["receipt_digest"] = _digest(receipt)
    return merged, html, receipt, impact
