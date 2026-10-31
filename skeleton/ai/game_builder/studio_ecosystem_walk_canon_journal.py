"""Verified authored canon journal over played offline world decisions.

The journal describes authored context, not observed world events or inferred
consequences. It never mints quest evidence or mutates the authoritative save.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_walk_replay import WalkSession, verify_walk
from .studio_ecosystem_walk_story_transcript import walk_story_transcript
from .studio_ecosystem_walkable import playable_world_source

MAX_JOURNAL_PAGE = 8
MAX_JOURNAL_SOURCE_BYTES = 128 * 1024
MAX_JOURNAL_TEXT_BYTES = 512


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical authored journal source") from exc


def _text(value: object) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise StudioQuestError("invalid authored journal text")
    try:
        size = len(value.encode("utf-8", "strict"))
    except UnicodeError as exc:
        raise StudioQuestError("invalid authored journal encoding") from exc
    if size > MAX_JOURNAL_TEXT_BYTES or any(ord(ch) < 32 for ch in value):
        raise StudioQuestError("unbounded or unsafe authored journal text")
    return value


def walk_canon_journal(
    session: WalkSession, documents: Mapping[str, Any], *,
    authorized: bool, offset: int = 0, limit: int = MAX_JOURNAL_PAGE,
    expected_session_digest: str | None = None,
    expected_source_digest: str | None = None,
) -> dict[str, object]:
    """Source-bind narrative/cast/scene context to replayed player decisions."""
    if authorized is not True:
        raise PermissionError("canon journal requires operator authorization")
    if type(limit) is not int or not 1 <= limit <= MAX_JOURNAL_PAGE:
        raise StudioQuestError("canon journal page limit must be 1..8")
    if not isinstance(documents, Mapping):
        raise StudioQuestError("canon journal requires authored documents")
    transcript = walk_story_transcript(
        session, documents, authorized=True, offset=offset, max_scenes=limit,
        expected_session_digest=expected_session_digest,
    )
    source = {key: documents.get(key) for key in ("narrative", "scene", "cast")}
    if any(type(section) is not dict for section in source.values()):
        raise StudioQuestError("missing canon journal source section")
    raw_source = _canonical(source)
    if len(raw_source) > MAX_JOURNAL_SOURCE_BYTES:
        raise StudioQuestError("canon journal source exceeds byte budget")
    source_digest = sha256(raw_source).hexdigest()
    if offset and expected_source_digest is None:
        raise StudioQuestError("canon journal continuation requires source digest")
    if expected_source_digest is not None and (
        type(expected_source_digest) is not str
        or expected_source_digest != source_digest
    ):
        raise StudioQuestError("stale canon journal source")
    narrative, scene, cast = (source[key] for key in ("narrative", "scene", "cast"))
    world = playable_world_source(documents)
    episodes = scene.get("episode_plan")
    beats = narrative.get("plot_beats")
    support = cast.get("support")
    foundation = narrative.get("foundation")
    protagonist = cast.get("protagonist")
    if (type(episodes) is not list or type(beats) is not list
            or len(episodes) != len(world["stages"])
            or len(beats) != len(episodes)
            or type(support) is not list or type(foundation) is not dict
            or type(protagonist) is not dict):
        raise StudioQuestError("canon journal scene/cast/beat cardinality mismatch")
    actor_ids = set()
    for actor in support:
        if type(actor) is not dict:
            raise StudioQuestError("invalid canon journal actor")
        ident = _text(actor.get("id"))
        if ident in actor_ids:
            raise StudioQuestError("duplicate canon journal actor")
        actor_ids.add(ident)
    era = _text(foundation.get("era"))
    protagonist_name = _text(protagonist.get("name"))

    def entry(index: int, chosen: str | None) -> dict[str, object]:
        stage = world["stages"][index]
        episode, beat = episodes[index], beats[index]
        if type(episode) is not dict or type(beat) is not dict:
            raise StudioQuestError("invalid authored journal scene")
        scene_id = _text(stage["scene_id"])
        if (episode.get("id") != scene_id or beat.get("id") != scene_id
                or episode.get("quest_stage") != stage["id"]):
            raise StudioQuestError("canon journal scene/quest/beat drift")
        hook = _text(episode.get("dialogue_hook"))
        if hook not in actor_ids and hook != protagonist.get("id"):
            raise StudioQuestError("canon journal dialogue hook has no cast source")
        return {
            "index": index, "stage_id": _text(stage["id"]),
            "scene_id": scene_id, "act": beat.get("act"),
            "site": _text(episode.get("site")),
            "weather_state": _text(episode.get("weather_state")),
            "dialogue_hook": hook,
            "cause": _text(beat.get("cause")),
            "goal": _text(beat.get("goal")),
            "decision_prompt": _text(beat.get("decision")),
            "authored_possible_consequence": _text(beat.get("consequence")),
            "selected_alternative": chosen,
        }

    if any(type(beat.get("act")) is not int or beat["act"] < 1
           for beat in beats if isinstance(beat, dict)):
        raise StudioQuestError("invalid authored journal act")
    played = [
        entry(item["index"], item["selected_alternative"])
        for item in transcript["completed_scenes"]
    ]
    pending = (entry(session.scene_index, None)
               if session.scene_index < len(episodes) else None)
    verify_walk(session, documents)
    if sha256(_canonical({key: documents.get(key)
                          for key in ("narrative", "scene", "cast")})).hexdigest() != source_digest:
        raise StudioQuestError("canon journal source changed during read")
    payload: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_walk_canon_journal.v1",
        "project_id": session.project_id,
        "source_digest": session.source_digest,
        "journal_source_digest": source_digest,
        "session_digest": session.digest,
        "transcript_digest": transcript["transcript_digest"],
        "era": era, "protagonist": protagonist_name,
        "page_offset": offset, "page_limit": limit,
        "completed_scene_count": session.scene_index,
        "scenes": played, "next_authored_scene": pending,
        "next_offset": transcript["next_offset"],
        "continuation_session_digest": transcript["continuation_session_digest"],
        "continuation_source_digest": (source_digest
                                      if transcript["next_offset"] is not None else None),
        "authored_context_not_observed_consequence": True,
        "original_save_unchanged": True,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["journal_digest"] = sha256(_canonical(payload)).hexdigest()
    return payload
