"""Read-only source-bound NPC encounter codex from canonical quest staging."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_quest import StudioQuestError

NPC_CODEX_SCHEMA = "skeleton.game_builder.studio_npc_encounter_codex.v1"
MAX_CODEX_PAGE = 16
MAX_CODEX_SCENES = 64


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical NPC encounter codex") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def page_npc_encounters(
    documents: Mapping[str, Any], actions: list[list[str]], *,
    authorized: bool, expected_source_digest: str,
    npc_id: str | None = None, offset: int = 0, limit: int = 8,
    expected_session_digest: str | None = None,
) -> dict[str, object]:
    """Expose original NPC cues, stage status and replayed choice history.

    This is an editor index, not evidence that an NPC spoke. Pages are leased
    to the exact authored source and quest session to prevent mixed histories.
    """
    if authorized is not True:
        raise PermissionError("NPC codex requires operator authorization")
    if (type(offset) is not int or offset < 0 or type(limit) is not int
            or not 1 <= limit <= MAX_CODEX_PAGE):
        raise StudioQuestError("invalid NPC codex pagination")
    if npc_id is not None and (
            type(npc_id) is not str or not 1 <= len(npc_id) <= 512
            or npc_id != npc_id.strip() or any(ord(ch) < 32 for ch in npc_id)):
        raise StudioQuestError("invalid NPC codex filter")
    if (type(expected_source_digest) is not str
            or len(expected_source_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in expected_source_digest)):
        raise StudioQuestError("invalid NPC codex source lease")
    staged = compile_dialogue_staging(
        documents, actions, authorized=True,
        expected_source_digest=expected_source_digest)
    if expected_session_digest is not None and (
            type(expected_session_digest) is not str
            or expected_session_digest != staged["session_digest"]):
        raise StudioQuestError("stale NPC codex session lease")
    if offset and expected_session_digest is None:
        raise StudioQuestError("NPC codex continuation requires session lease")
    cards = staged["cards"]
    if len(cards) > MAX_CODEX_SCENES:
        raise StudioQuestError("NPC codex exceeds authored scene budget")
    available_ids = sorted({card["npc_id"] for card in cards})
    if npc_id is not None and npc_id not in available_ids:
        raise StudioQuestError("NPC codex references unknown original cast member")
    matching = [card for card in cards if npc_id is None or card["npc_id"] == npc_id]
    page = []
    for card in matching[offset:offset + limit]:
        page.append({
            "scene_id": card["scene_id"],
            "npc_id": card["npc_id"],
            "npc_name": card["npc_name"],
            "npc_role": card["npc_role"],
            "site": card["site"],
            "quest_stage": card["quest_stage"],
            "status": card["status"],
            "prerequisites": list(card["prerequisites"]),
            "selected_alternative": card["selected_alternative"],
            "authored_alternatives": list(card["authored_alternatives"]),
            "authored_cues": list(card["authored_cues"]),
            "card_digest": card["card_digest"],
            "dialogue_spoken_verified": False,
        })
    payload: dict[str, object] = {
        "schema": NPC_CODEX_SCHEMA, "project_id": staged["project_id"],
        "source_digest": staged["source_digest"],
        "quest_source_digest": staged["quest_source_digest"],
        "session_digest": staged["session_digest"],
        "npc_filter": npc_id, "npc_ids": available_ids,
        "offset": offset, "limit": limit, "total": len(matching),
        "next_offset": offset + len(page) if offset + len(page) < len(matching) else None,
        "entries": page, "source_unchanged": True,
        "replay_verified": True, "file_write_performed": False,
        "dialogue_spoken_verified": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    payload["codex_digest"] = _digest(payload)
    return payload
