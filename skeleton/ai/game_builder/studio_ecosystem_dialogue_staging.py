"""Canonical scene/NPC dialogue staging from authored source and replayed quests.

These are source quotations and editor cues, not synthetic spoken dialogue,
earned NPC testimony, or certified interactive engine conversation.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest, verify_quest_session,
)

DIALOGUE_SCHEMA = "skeleton.game_builder.studio_dialogue_staging.v1"
MAX_SCENES = 64
MAX_CUES = 5


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical dialogue staging source") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _text(value: object, label: str) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 512
            or value != value.strip() or any(ord(ch) < 32 for ch in value)):
        raise StudioQuestError("invalid authored dialogue " + label)
    return value


def compile_dialogue_staging(
    documents: Mapping[str, Any], actions: list[list[str]], *,
    authorized: bool, expected_source_digest: str | None = None,
    scene_id: str | None = None,
) -> dict[str, object]:
    """Bind authored NPC cues to a verified quest replay and scene chronology.

    A locked scene remains visible as a source-bound editor card, but cannot
    claim an NPC interaction has happened. A completed scene exposes the exact
    authored choice from the replay, never a generated witness statement.
    """
    if authorized is not True:
        raise PermissionError("dialogue staging requires operator authorization")
    if type(actions) is not list or len(actions) > MAX_SCENES:
        raise StudioQuestError("invalid dialogue replay action list")
    if scene_id is not None:
        _text(scene_id, "scene identifier")
    if not isinstance(documents, Mapping) or len(_canonical(documents)) > 512 * 1024:
        raise StudioQuestError("dialogue source missing or exceeds byte budget")
    proof = audit_canon_source(documents, authorized=True)
    if not proof["canon_consistent"]:
        raise StudioQuestError("contradictory authored dialogue canon")
    if (expected_source_digest is not None
            and (type(expected_source_digest) is not str
                 or expected_source_digest != proof["source_digest"])):
        raise StudioQuestError("stale dialogue source digest")
    program = compile_quest_program(documents)
    session = replay_quest(documents, actions, authorized=True)
    verify_quest_session(session, documents, program=program)
    scenes = documents.get("scene", {}).get("episode_plan")
    beats = documents.get("narrative", {}).get("plot_beats")
    support = documents.get("cast", {}).get("support")
    if (type(scenes) is not list or not 1 <= len(scenes) <= MAX_SCENES
            or type(beats) is not list or len(beats) != len(scenes)
            or type(support) is not list or len(support) > MAX_SCENES):
        raise StudioQuestError("invalid authored scene, beat or cast inventory")
    order = documents["scene"].get("continuity", {}).get("canonical_order")
    if type(order) is not list or len(order) != len(scenes):
        raise StudioQuestError("invalid dialogue scene chronology")
    people: dict[str, dict[str, Any]] = {}
    for member in support:
        if type(member) is not dict:
            raise StudioQuestError("invalid authored dialogue cast")
        ident = _text(member.get("id"), "NPC identifier")
        if ident in people:
            raise StudioQuestError("repeated authored dialogue NPC")
        people[ident] = member
    stages = {stage.key: stage for stage in program.stages}
    chosen = dict(session.choices)
    completed = set(session.completed)
    cards: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, scene in enumerate(scenes):
        if type(scene) is not dict or type(beats[index]) is not dict:
            raise StudioQuestError("invalid authored dialogue scene or beat")
        sid = _text(scene.get("id"), "scene ID")
        if sid in seen or sid != order[index] or sid != beats[index].get("id"):
            raise StudioQuestError("scene dialogue chronology mismatch")
        seen.add(sid)
        stage_id = _text(scene.get("quest_stage"), "quest stage")
        npc_id = _text(scene.get("dialogue_hook"), "NPC hook")
        if stage_id not in stages or npc_id not in people:
            raise StudioQuestError("scene dialogue references unknown quest or NPC")
        npc = people[npc_id]
        beat = beats[index]
        # Some original NPCs have a documented goal rather than an authored
        # knowledge claim. Preserve that distinction instead of manufacturing
        # a witness statement or rejecting an otherwise valid original cast.
        cue_field = ("knows" if npc.get("knows") is not None else
                     "goal" if npc.get("goal") is not None else "role")
        cue_kind = {"knows": "npc_knowledge", "goal": "npc_goal",
                    "role": "npc_role"}[cue_field]
        cues = [
            (cue_kind, npc.get(cue_field), f"cast.support.{npc_id}.{cue_field}"),
            ("npc_relationship", npc.get("relationship"),
             f"cast.support.{npc_id}.relationship"),
            ("scene_goal", beat.get("goal"), f"narrative.plot_beats.{sid}.goal"),
            ("scene_decision", beat.get("decision"),
             f"narrative.plot_beats.{sid}.decision"),
            ("scene_consequence", beat.get("consequence"),
             f"narrative.plot_beats.{sid}.consequence"),
        ]
        authored = [
            {"kind": kind, "text": _text(value, kind), "source_ref": source_ref}
            for kind, value, source_ref in cues
        ]
        if len(authored) != MAX_CUES:
            raise StudioQuestError("dialogue staging cue count mismatch")
        stage = stages[stage_id]
        status = ("completed" if stage_id in completed else
                  "available" if set(stage.prerequisites).issubset(completed)
                  else "locked")
        card = {
            "scene_id": sid,
            "quest_stage": stage_id,
            "npc_id": npc_id,
            "npc_name": _text(npc.get("name"), "NPC name"),
            "npc_role": _text(npc.get("role"), "NPC role"),
            "site": _text(scene.get("site"), "scene site"),
            "status": status,
            "prerequisites": list(stage.prerequisites),
            "authored_alternatives": list(stage.alternatives),
            "selected_alternative": chosen.get(stage_id),
            "authored_cues": authored,
            "dialogue_spoken_verified": False,
        }
        card["card_digest"] = _digest(card)
        if scene_id is None or scene_id == sid:
            cards.append(card)
    if scene_id is not None and scene_id not in seen:
        raise StudioQuestError("unknown authored dialogue scene")
    payload: dict[str, object] = {
        "schema": DIALOGUE_SCHEMA,
        "project_id": proof["project_id"],
        "source_digest": proof["source_digest"],
        "quest_source_digest": program.source_digest,
        "session_digest": session.digest,
        "scene_filter": scene_id,
        "scene_count": len(cards),
        "cards": cards,
        "replay_verified": True,
        "source_unchanged": True,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["staging_digest"] = _digest(payload)
    return payload
