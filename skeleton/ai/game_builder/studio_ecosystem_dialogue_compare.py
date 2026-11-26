"""Source-bound comparison of two original NPC/quest dialogue playthroughs.

Only authoritative authored alternatives and replayed decisions are compared.
A branch difference never creates new NPC speech or proves external outcomes.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_quest import StudioQuestError, quest_progress, replay_quest

COMPARE_SCHEMA = "skeleton.game_builder.studio_dialogue_compare.v1"


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical dialogue comparison") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def compare_dialogue_histories(
    documents: Mapping[str, Any], actions: list[list[str]],
    compare_actions: list[list[str]], *, authorized: bool,
    expected_source_digest: str | None = None, scene_id: str | None = None,
) -> dict[str, object]:
    """Compare verified NPC scene decisions and sandbox ending obligations."""
    if authorized is not True:
        raise PermissionError("dialogue comparison requires operator authorization")
    left = compile_dialogue_staging(
        documents, actions, authorized=True, scene_id=scene_id,
        expected_source_digest=expected_source_digest)
    right = compile_dialogue_staging(
        documents, compare_actions, authorized=True, scene_id=scene_id,
        expected_source_digest=expected_source_digest)
    if (left["source_digest"] != right["source_digest"]
            or left["quest_source_digest"] != right["quest_source_digest"]):
        raise StudioQuestError("dialogue comparison source mismatch")
    left_session = replay_quest(documents, actions, authorized=True)
    right_session = replay_quest(documents, compare_actions, authorized=True)
    if (left_session.digest != left["session_digest"]
            or right_session.digest != right["session_digest"]):
        raise StudioQuestError("dialogue comparison replay mismatch")
    left_choices = list(left_session.choices)
    right_choices = list(right_session.choices)
    common = 0
    while (common < min(len(left_choices), len(right_choices))
           and left_choices[common] == right_choices[common]):
        common += 1
    left_cards = {card["scene_id"]: card for card in left["cards"]}
    right_cards = {card["scene_id"]: card for card in right["cards"]}
    if set(left_cards) != set(right_cards):
        raise StudioQuestError("dialogue comparison scene inventory changed")
    scene_changes = []
    for scene in sorted(left_cards):
        before, after = left_cards[scene], right_cards[scene]
        if before["status"] != after["status"] or (
                before["selected_alternative"] != after["selected_alternative"]):
            scene_changes.append({
                "scene_id": scene, "npc_id": before["npc_id"],
                "quest_stage": before["quest_stage"],
                "left_status": before["status"],
                "right_status": after["status"],
                "left_choice": before["selected_alternative"],
                "right_choice": after["selected_alternative"],
                "authored_card_digest": before["card_digest"],
                "dialogue_spoken_verified": False,
            })
    left_progress = quest_progress(left_session, documents)
    right_progress = quest_progress(right_session, documents)
    payload: dict[str, object] = {
        "schema": COMPARE_SCHEMA,
        "project_id": left["project_id"],
        "source_digest": left["source_digest"],
        "quest_source_digest": left["quest_source_digest"],
        "left_session_digest": left_session.digest,
        "right_session_digest": right_session.digest,
        "common_choice_prefix": common,
        "first_divergence_index": common if (
            common < max(len(left_choices), len(right_choices))) else None,
        "left_suffix": [list(pair) for pair in left_choices[common:]],
        "right_suffix": [list(pair) for pair in right_choices[common:]],
        "scene_changes": scene_changes,
        "left_progress": left_progress,
        "right_progress": right_progress,
        "identical_history": left_choices == right_choices,
        "file_write_performed": False,
        "dialogue_spoken_verified": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["comparison_digest"] = _digest(payload)
    return payload
