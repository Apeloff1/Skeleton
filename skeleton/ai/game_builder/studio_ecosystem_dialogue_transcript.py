"""Digest-leased NPC authored dialogue transcript from canonical quest replay.

Quotes exact authored scene/NPC cues; it never fabricates spoken dialogue.
History is ordered by actual verified player choices, not presumed scene order.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_quest import StudioQuestError, replay_quest

TRANSCRIPT_SCHEMA = "skeleton.game_builder.studio_dialogue_transcript.v1"
MAX_TRANSCRIPT_PAGE = 16
MAX_TRANSCRIPT_EVENTS = 64


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical dialogue transcript") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def compile_dialogue_transcript(
    documents: Mapping[str, Any], actions: list[list[str]], *,
    authorized: bool, expected_source_digest: str | None = None,
    expected_session_digest: str | None = None, offset: int = 0,
    limit: int = 16, scene_id: str | None = None,
) -> dict[str, object]:
    """Page exact authored cues for replayed choices with stale-cursor holds."""
    if authorized is not True:
        raise PermissionError("dialogue transcript requires operator authorization")
    if (type(offset) is not int or not 0 <= offset <= MAX_TRANSCRIPT_EVENTS
            or type(limit) is not int or not 1 <= limit <= MAX_TRANSCRIPT_PAGE):
        raise StudioQuestError("invalid dialogue transcript page budget")
    staged = compile_dialogue_staging(
        documents, actions, authorized=True, scene_id=scene_id,
        expected_source_digest=expected_source_digest)
    session = replay_quest(documents, actions, authorized=True)
    if staged["session_digest"] != session.digest:
        raise StudioQuestError("dialogue transcript session drift")
    if (expected_session_digest is not None
            and (type(expected_session_digest) is not str
                 or expected_session_digest != session.digest)):
        raise StudioQuestError("stale dialogue transcript continuation")
    cards = {card["quest_stage"]: card for card in staged["cards"]}
    entries: list[dict[str, object]] = []
    for index, (stage_id, alternative) in enumerate(session.choices):
        card = cards.get(stage_id)
        if card is None:
            if scene_id is not None:
                continue
            raise StudioQuestError("completed quest stage has no authored NPC scene")
        if card["status"] != "completed" or card["selected_alternative"] != alternative:
            raise StudioQuestError("authored NPC dialogue choice does not match replay")
        entries.append({
            "choice_index": index,
            "scene_id": card["scene_id"],
            "npc_id": card["npc_id"],
            "npc_name": card["npc_name"],
            "npc_role": card["npc_role"],
            "site": card["site"],
            "quest_stage": stage_id,
            "selected_alternative": alternative,
            "authored_cues": card["authored_cues"],
            "card_digest": card["card_digest"],
            "dialogue_spoken_verified": False,
        })
    total = len(entries)
    if offset > total:
        raise StudioQuestError("dialogue transcript offset exceeds completed history")
    page = entries[offset:offset + limit]
    next_offset = offset + len(page) if offset + len(page) < total else None
    payload: dict[str, object] = {
        "schema": TRANSCRIPT_SCHEMA,
        "project_id": session.project_id,
        "source_digest": staged["source_digest"],
        "quest_source_digest": session.source_digest,
        "session_digest": session.digest,
        "staging_digest": staged["staging_digest"],
        "scene_filter": scene_id,
        "offset": offset,
        "limit": limit,
        "total_completed_scenes": total,
        "next_offset": next_offset,
        "entries": page,
        "source_bound": True,
        "file_write_performed": False,
        "dialogue_spoken_verified": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["page_digest"] = _digest(payload)
    return payload
