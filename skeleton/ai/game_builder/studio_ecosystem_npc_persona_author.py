"""NPC persona authoring through canonical source-leased revisions and playable HTML.

Only the existing game-builder revision owner mutates prose in a private
derived source. This adapter resolves original NPC identity into safe,
allowlisted edit paths and never changes the registered catalog.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_author_revision import (
    REVISION_SCHEMA, preview_canon_revision,
)
from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import StudioQuestError

NPC_AUTHOR_SCHEMA = "skeleton.game_builder.studio_npc_persona_author.v1"
EDITABLE_NPC_FIELDS = frozenset({"name", "knows", "relationship"})
MAX_NPC_EDIT_BYTES = 2048


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical NPC persona edit") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def preview_npc_persona_revision(
    documents: Mapping[str, Any],
    *,
    npc_id: str,
    changes: Mapping[str, str],
    expected_source_digest: str,
    authorized: bool,
) -> tuple[dict[str, Any], bytes, dict[str, object], dict[str, object]]:
    """Author one existing NPC's prose and compile a verified playable export.

    The NPC's immutable ID, role, quest prerequisites and scene ownership are
    never editable here. Source identity and revision validation remain with
    audit_canon_source and preview_canon_revision. No model output is trusted
    as authorization or proof of original-content rights.
    """
    if authorized is not True:
        raise PermissionError("NPC persona authoring requires operator authorization")
    if (type(npc_id) is not str or not 1 <= len(npc_id) <= 512
            or npc_id != npc_id.strip() or any(ord(ch) < 32 for ch in npc_id)):
        raise StudioQuestError("invalid authored NPC identity")
    if (type(changes) is not dict or not 1 <= len(changes) <= 3
            or set(changes) - EDITABLE_NPC_FIELDS
            or len(_canonical(changes)) > MAX_NPC_EDIT_BYTES):
        raise StudioQuestError("invalid authored NPC edit fields or byte budget")
    for field, value in changes.items():
        if (type(field) is not str or type(value) is not str
                or not value or value != value.strip()
                or any(ord(ch) < 32 for ch in value)
                or len(value.encode("utf-8", "strict")) > 512):
            raise StudioQuestError("invalid authored NPC prose")
    proof = audit_canon_source(documents, authorized=True)
    if (type(expected_source_digest) is not str
            or proof["source_digest"] != expected_source_digest):
        raise StudioQuestError("stale NPC persona source lease")
    cast = documents.get("cast")
    support = cast.get("support") if isinstance(cast, Mapping) else None
    if type(support) is not list or not 1 <= len(support) <= 64:
        raise StudioQuestError("invalid NPC persona cast inventory")
    matching = [
        (index, member) for index, member in enumerate(support)
        if type(member) is dict and member.get("id") == npc_id
    ]
    if len(matching) != 1:
        raise StudioQuestError("NPC persona target is unknown or ambiguous")
    index, member = matching[0]
    for field in changes:
        if type(member.get(field)) is not str:
            raise StudioQuestError("NPC persona field is not editable prose")
    edits = [
        {"section": "cast", "path": ["support", index, field],
         "value": changes[field]}
        for field in sorted(changes)
    ]
    request = {
        "schema": REVISION_SCHEMA,
        "project_id": proof["project_id"],
        "expected_source_digest": expected_source_digest,
        "edits": edits,
    }
    revised, html, receipt = preview_canon_revision(
        documents, request, authorized=True)
    updated = revised["cast"]["support"][index]
    if (updated["id"] != npc_id
            or updated.get("role") != member.get("role")
            or any(updated[field] != value for field, value in changes.items())
            or receipt["base_source_digest"] != expected_source_digest):
        raise StudioQuestError("NPC persona revision identity or output drift")
    detail: dict[str, object] = {
        "schema": NPC_AUTHOR_SCHEMA,
        "project_id": proof["project_id"],
        "npc_id": npc_id,
        "edited_fields": sorted(changes),
        "original_npc_digest": _digest(member),
        "revised_npc_digest": _digest(updated),
        "base_source_digest": expected_source_digest,
        "revised_source_digest": receipt["revised_source_digest"],
        "playable_html_sha256": sha256(html).hexdigest(),
        "revision_receipt": receipt,
        "original_catalog_unchanged": True,
        "playable_html_compiled": True,
        "private_bundle_written": False,
        "native_genre_runtime_verified": False,
        "originality_rights_verified": False,
        "release_certified": False,
    }
    detail["author_digest"] = _digest(detail)
    return revised, html, receipt, detail
