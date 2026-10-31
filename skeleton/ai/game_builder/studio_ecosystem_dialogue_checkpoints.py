"""Digest-leased pagination of canonical NPC dialogue quest checkpoints.

Every checkpoint is reconstructed from the authored source and prefix replay;
no save, NPC speech, or external evidence is inferred from a timeline card.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_quest import StudioQuestError, quest_progress, replay_quest

CHECKPOINTS_SCHEMA = "skeleton.game_builder.studio_dialogue_checkpoints.v1"
MAX_CHECKPOINT_PAGE = 8
MAX_CHECKPOINT_EVENTS = 64


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical dialogue checkpoint") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def page_dialogue_checkpoints(
    documents: Mapping[str, Any], actions: list[list[str]], *,
    authorized: bool, expected_source_digest: str | None = None,
    expected_session_digest: str | None = None,
    offset: int = 0, limit: int = MAX_CHECKPOINT_PAGE,
) -> dict[str, object]:
    """Expose exact prefix replay receipts for deterministic checkpoint forks."""
    if authorized is not True:
        raise PermissionError("dialogue checkpoints require operator authorization")
    if (type(actions) is not list or len(actions) > MAX_CHECKPOINT_EVENTS
            or type(offset) is not int or not 0 <= offset <= MAX_CHECKPOINT_EVENTS
            or type(limit) is not int or not 1 <= limit <= MAX_CHECKPOINT_PAGE):
        raise StudioQuestError("invalid dialogue checkpoint page budget")
    final = replay_quest(documents, actions, authorized=True)
    staged = compile_dialogue_staging(
        documents, actions, authorized=True,
        expected_source_digest=expected_source_digest)
    if final.digest != staged["session_digest"]:
        raise StudioQuestError("dialogue checkpoint source/replay drift")
    if (expected_session_digest is not None
            and (type(expected_session_digest) is not str
                 or expected_session_digest != final.digest)):
        raise StudioQuestError("stale dialogue checkpoint continuation")
    total = len(final.choices) + 1
    if offset >= total:
        raise StudioQuestError("dialogue checkpoint offset beyond history")
    cards = {card["quest_stage"]: card for card in staged["cards"]}
    entries: list[dict[str, object]] = []
    for index in range(offset, min(total, offset + limit)):
        prefix = [list(pair) for pair in final.choices[:index]]
        state = replay_quest(documents, prefix, authorized=True)
        progress = quest_progress(state, documents)
        if state.source_digest != final.source_digest:
            raise StudioQuestError("dialogue checkpoint source changed")
        previous = final.choices[index - 1] if index else None
        card = cards.get(previous[0]) if previous else None
        if previous is not None and (
                card is None or card["selected_alternative"] != previous[1]):
            raise StudioQuestError("dialogue checkpoint scene reference drift")
        item: dict[str, object] = {
            "checkpoint_index": index,
            "previous_scene_id": card["scene_id"] if card else None,
            "previous_npc_id": card["npc_id"] if card else None,
            "previous_stage": previous[0] if previous else None,
            "previous_alternative": previous[1] if previous else None,
            "completed": list(state.completed),
            "available": progress["available"],
            "sandbox_endings_eligible": progress["sandbox_endings_eligible"],
            "unmet_ending_predicates": progress["unmet_ending_predicates"],
            "quest_receipt": state.receipt(),
            "source_bound": True,
            "dialogue_spoken_verified": False,
        }
        item["checkpoint_digest"] = _digest(item)
        entries.append(item)
    next_offset = offset + len(entries) if offset + len(entries) < total else None
    payload: dict[str, object] = {
        "schema": CHECKPOINTS_SCHEMA,
        "project_id": final.project_id,
        "source_digest": staged["source_digest"],
        "quest_source_digest": final.source_digest,
        "session_digest": final.digest,
        "staging_digest": staged["staging_digest"],
        "offset": offset,
        "limit": limit,
        "total_checkpoints": total,
        "next_offset": next_offset,
        "entries": entries,
        "file_write_performed": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["page_digest"] = _digest(payload)
    return payload
