"""Source-bound NPC chronology and causal continuity for original authored scenes.

This editor proof uses the canonical quest replay and dialogue staging owners.
It does not create NPC speech, grant interaction authority, or certify gameplay.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)

NPC_CONTINUITY_SCHEMA = "skeleton.game_builder.studio_npc_continuity.v1"
MAX_CONTINUITY_SCENES = 64
MAX_CONTINUITY_BYTES = 512 * 1024


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical NPC continuity record") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _identifier(value: object, label: str) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 512
            or value != value.strip() or any(ord(ch) < 32 for ch in value)):
        raise StudioQuestError("invalid NPC continuity " + label)
    return value


def audit_npc_continuity(
    documents: Mapping[str, Any],
    actions: list[list[str]],
    *,
    authorized: bool,
    expected_source_digest: str,
    expected_session_digest: str | None = None,
    npc_id: str | None = None,
    require_chronological_prerequisites: bool = False,
) -> dict[str, object]:
    """Audit authored scene order against canonical quest prerequisites.

    Scene order is an authored chronology, not real-world time or evidence of
    speech. The exact source and replayed session are required to avoid mixing
    timelines from different edits or saved playthroughs. An optional NPC
    filter changes only presentation, never the global causality verdict.
    """
    if authorized is not True:
        raise PermissionError("NPC continuity requires operator authorization")
    if type(require_chronological_prerequisites) is not bool:
        raise StudioQuestError("invalid NPC continuity strictness")
    if npc_id is not None:
        _identifier(npc_id, "cast filter")
    if (type(expected_source_digest) is not str
            or len(expected_source_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in expected_source_digest)):
        raise StudioQuestError("invalid NPC continuity source lease")
    if expected_session_digest is not None and (
            type(expected_session_digest) is not str
            or len(expected_session_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in expected_session_digest)):
        raise StudioQuestError("invalid NPC continuity session lease")
    if (type(actions) is not list or len(actions) > MAX_CONTINUITY_SCENES
            or len(_canonical(actions)) > 16384):
        raise StudioQuestError("invalid NPC continuity action history")

    staging = compile_dialogue_staging(
        documents, actions, authorized=True,
        expected_source_digest=expected_source_digest,
    )
    session = replay_quest(documents, actions, authorized=True)
    program = compile_quest_program(documents)
    if (session.digest != staging["session_digest"]
            or session.source_digest != staging["quest_source_digest"]
            or staging["source_digest"] != expected_source_digest):
        raise StudioQuestError("NPC continuity replay or source drift")
    if (expected_session_digest is not None
            and session.digest != expected_session_digest):
        raise StudioQuestError("stale NPC continuity session lease")

    cards = staging["cards"]
    if not 1 <= len(cards) <= MAX_CONTINUITY_SCENES:
        raise StudioQuestError("NPC continuity scene budget exceeded")
    by_stage = {stage.key: stage for stage in program.stages}
    scene_index: dict[str, int] = {}
    for index, card in enumerate(cards):
        stage_id = _identifier(card["quest_stage"], "quest stage")
        if stage_id in scene_index:
            raise StudioQuestError("ambiguous NPC continuity stage-to-scene mapping")
        scene_index[stage_id] = index
    cast_ids = {card["npc_id"] for card in cards}
    if npc_id is not None and npc_id not in cast_ids:
        raise StudioQuestError("NPC continuity references unknown cast member")

    violations: list[dict[str, object]] = []
    timeline: list[dict[str, object]] = []
    cast: dict[str, dict[str, object]] = {}
    for index, card in enumerate(cards):
        stage_id = card["quest_stage"]
        stage = by_stage.get(stage_id)
        if stage is None:
            raise StudioQuestError("NPC continuity references unknown quest stage")
        predecessors = []
        for parent in stage.prerequisites:
            parent_index = scene_index.get(parent)
            if parent_index is None:
                raise StudioQuestError("NPC continuity prerequisite has no authored scene")
            if parent_index >= index:
                violations.append({
                    "scene_id": card["scene_id"],
                    "quest_stage": stage_id,
                    "prerequisite": parent,
                    "prerequisite_scene_id": cards[parent_index]["scene_id"],
                    "reason": "prerequisite_not_earlier_in_authored_chronology",
                })
            predecessors.append({
                "quest_stage": parent,
                "scene_id": cards[parent_index]["scene_id"],
                "scene_index": parent_index,
                "completed_in_replay": parent in session.completed,
            })
        cues = [{
            "kind": cue["kind"],
            "source_ref": cue["source_ref"],
            "source_text_digest": _digest(cue["text"]),
        } for cue in card["authored_cues"]]
        record = {
            "scene_index": index,
            "scene_id": card["scene_id"],
            "site": card["site"],
            "npc_id": card["npc_id"],
            "npc_name": card["npc_name"],
            "npc_role": card["npc_role"],
            "quest_stage": stage_id,
            "status": card["status"],
            "selected_alternative": card["selected_alternative"],
            "authored_alternatives": list(card["authored_alternatives"]),
            "prerequisite_scenes": predecessors,
            "authored_cue_sources": cues,
            "authored_card_digest": card["card_digest"],
            "interaction_verified": False,
        }
        record["scene_proof_digest"] = _digest(record)
        timeline.append(record)
        member = cast.setdefault(card["npc_id"], {
            "npc_id": card["npc_id"],
            "npc_name": card["npc_name"],
            "npc_role": card["npc_role"],
            "first_scene_index": index,
            "last_scene_index": index,
            "scene_ids": [],
            "sites": [],
            "completed_count": 0,
            "available_count": 0,
            "locked_count": 0,
        })
        member["last_scene_index"] = index
        member["scene_ids"].append(card["scene_id"])
        if card["site"] not in member["sites"]:
            member["sites"].append(card["site"])
        member[card["status"] + "_count"] += 1
    if require_chronological_prerequisites and violations:
        raise StudioQuestError("NPC continuity has forward chronological prerequisites")

    visible = [item for item in timeline if npc_id is None or item["npc_id"] == npc_id]
    people = [person for person in cast.values()
              if npc_id is None or person["npc_id"] == npc_id]
    ready = [item["scene_id"] for item in visible if item["status"] == "available"]
    payload: dict[str, object] = {
        "schema": NPC_CONTINUITY_SCHEMA,
        "project_id": staging["project_id"],
        "source_digest": staging["source_digest"],
        "quest_source_digest": staging["quest_source_digest"],
        "session_digest": session.digest,
        "npc_filter": npc_id,
        "authored_scene_count": len(cards),
        "visible_scene_count": len(visible),
        "cast_count": len(people),
        "cast": people,
        "timeline": visible,
        "next_available_scene_ids": ready,
        "causality_violations": violations,
        "chronological_prerequisites_consistent": not violations,
        "replay_verified": True,
        "source_unchanged": True,
        "file_write_performed": False,
        "interaction_verified": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_CONTINUITY_BYTES:
        raise StudioQuestError("NPC continuity result exceeds byte budget")
    payload["continuity_digest"] = _digest(payload)
    return payload
