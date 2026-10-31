"""Bounded source-leased original narrative revision lineage with replay fencing."""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping, Sequence

from .studio_ecosystem_author_revision import RECEIPT_SCHEMA, _canonical, _digest
from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_revision_impact import compare_revision_sources
from .studio_ecosystem_story_html import render_story_html

LINEAGE_SCHEMA = "skeleton.game_builder.studio_author_lineage.v1"
MAX_LINEAGE_STEPS = 8
MAX_LINEAGE_BYTES = 4 * 1024 * 1024


def trace_canon_lineage(
    base: Mapping[str, Any],
    revisions: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    *,
    authorized: bool,
) -> dict[str, object]:
    """Revalidate every revision receipt against its actual predecessor.

    The digest chain is a consistency receipt, not an identity signature.
    Every revision is required to have been explicitly authored and exported;
    skipped or reordered revisions cannot be silently accepted.
    """
    if authorized is not True:
        raise PermissionError("authored lineage requires operator authorization")
    if (not isinstance(base, Mapping) or type(revisions) not in (tuple, list)
            or not 1 <= len(revisions) <= MAX_LINEAGE_STEPS):
        raise StudioQuestError("invalid authored lineage source or step count")
    first = audit_canon_source(base, authorized=True)
    if not first["canon_consistent"]:
        raise StudioQuestError("authored lineage starts from contradictory canon")
    previous: Mapping[str, Any] = base
    previous_proof = first
    seen: set[str] = {first["source_digest"]}
    steps: list[dict[str, object]] = []
    total_bytes = len(_canonical(base))
    for index, pair in enumerate(revisions):
        if (type(pair) not in (tuple, list) or len(pair) != 2
                or not isinstance(pair[0], Mapping) or type(pair[1]) is not dict):
            raise StudioQuestError("invalid authored lineage revision pair")
        source, receipt = pair
        total_bytes += len(_canonical(source)) + len(_canonical(receipt))
        if total_bytes > MAX_LINEAGE_BYTES:
            raise StudioQuestError("authored lineage exceeds source byte budget")
        proof = audit_canon_source(source, authorized=True)
        unsigned = dict(receipt)
        signed_digest = unsigned.pop("receipt_digest", None)
        if (receipt.get("schema") != RECEIPT_SCHEMA
                or type(signed_digest) is not str or len(signed_digest) != 64
                or signed_digest != _digest(unsigned)
                or not proof["canon_consistent"]
                or proof["project_id"] != first["project_id"]
                or receipt.get("project_id") != first["project_id"]
                or receipt.get("base_source_digest") != previous_proof["source_digest"]
                or receipt.get("base_proof_digest") != previous_proof["proof_digest"]
                or receipt.get("revised_source_digest") != proof["source_digest"]
                or receipt.get("revised_proof_digest") != proof["proof_digest"]
                or receipt.get("playable_html_sha256")
                   != sha256(render_story_html(source)).hexdigest()
                or receipt.get("release_certified") is not False
                or receipt.get("originality_rights_verified") is not False
                or proof["source_digest"] in seen):
            raise StudioQuestError("authored lineage source/receipt lease mismatch")
        impact = compare_revision_sources(previous, source, authorized=True)
        if impact["changed_path_count"] == 0:
            raise StudioQuestError("authored lineage rejects empty revision")
        steps.append({
            "index": index,
            "parent_source_digest": previous_proof["source_digest"],
            "source_digest": proof["source_digest"],
            "receipt_digest": signed_digest,
            "impact_digest": impact["impact_digest"],
            "changed_path_count": impact["changed_path_count"],
            "new_save_required": impact["new_save_required"],
            "rendered_playable_html_changed": impact["rendered_playable_html_changed"],
        })
        seen.add(proof["source_digest"])
        previous, previous_proof = source, proof
    payload: dict[str, object] = {
        "schema": LINEAGE_SCHEMA,
        "project_id": first["project_id"],
        "root_source_digest": first["source_digest"],
        "head_source_digest": previous_proof["source_digest"],
        "steps": steps,
        "step_count": len(steps),
        "existing_root_save_lease_valid": False,
        "external_authorship_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["lineage_digest"] = _digest(payload)
    return payload
