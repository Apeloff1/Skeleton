"""Deterministic source-bound canon contradiction and closure proof for authors.

Checks the original authored blueprint before playable handoff. Unproven
ending predicates are surfaced as explicit obligations, not fabricated wins.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError, compile_quest_program
from .studio_ecosystem_story_html import story_source

MAX_CANON_SOURCE_BYTES = 128 * 1024
MAX_CANON_ISSUES = 128


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical canon proof source") from exc


def _text(value: object) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise StudioQuestError("invalid canon source identifier")
    if len(value.encode("utf-8", "strict")) > 512 or any(ord(c) < 32 for c in value):
        raise StudioQuestError("unbounded canon source identifier")
    return value


def audit_canon_source(documents: Mapping[str, Any], *, authorized: bool) -> dict[str, object]:
    """Check era/scene/quest/cast consistency and explicit ending obligations."""
    if authorized is not True:
        raise PermissionError("canon proof requires operator authorization")
    if not isinstance(documents, Mapping):
        raise StudioQuestError("canon proof requires original source documents")
    sections = {name: documents.get(name)
                for name in ("narrative", "cast", "scene", "quest")}
    if any(type(part) is not dict for part in sections.values()):
        raise StudioQuestError("canon proof requires four authored source sections")
    raw = _canonical(sections)
    if len(raw) > MAX_CANON_SOURCE_BYTES:
        raise StudioQuestError("canon proof source exceeds byte budget")
    source_digest = sha256(raw).hexdigest()
    program = compile_quest_program(documents)
    story = story_source(documents)
    narrative, cast, scene = (sections[name] for name in ("narrative", "cast", "scene"))
    episodes = scene.get("episode_plan")
    beats = narrative.get("plot_beats")
    canon = narrative.get("canon")
    continuity = scene.get("continuity")
    if (type(episodes) is not list or type(beats) is not list
            or type(canon) is not dict or type(continuity) is not dict
            or len(episodes) != len(program.stages)
            or len(beats) != len(episodes)):
        raise StudioQuestError("canon proof requires bounded aligned authored acts")
    if len(episodes) > 64 or len(program.endings) > 16:
        raise StudioQuestError("canon proof exceeds authored graph budget")
    issues: list[dict[str, object]] = []

    def issue(kind: str, index: int | None, expected: object, actual: object) -> None:
        if len(issues) >= MAX_CANON_ISSUES:
            raise StudioQuestError("canon contradiction budget exhausted")
        issues.append({"kind": kind, "index": index,
                       "expected": expected, "actual": actual})

    scene_ids = []
    actors = cast.get("support")
    protagonist = cast.get("protagonist")
    if type(actors) is not list or type(protagonist) is not dict:
        raise StudioQuestError("canon proof requires typed cast")
    cast_ids = {_text(protagonist.get("id"))}
    for actor in actors:
        if type(actor) is not dict:
            raise StudioQuestError("invalid authored cast member")
        ident = _text(actor.get("id"))
        if ident in cast_ids:
            issue("duplicate_cast_id", None, "unique", ident)
        cast_ids.add(ident)
    for index, (stage, episode, beat) in enumerate(
        zip(program.stages, episodes, beats, strict=True)
    ):
        if type(episode) is not dict or type(beat) is not dict:
            raise StudioQuestError("invalid authored act record")
        scene_id = _text(episode.get("id"))
        scene_ids.append(scene_id)
        if _text(episode.get("quest_stage")) != stage.key:
            issue("scene_quest_mismatch", index, stage.key, episode["quest_stage"])
        if _text(beat.get("id")) != scene_id:
            issue("plot_beat_mismatch", index, scene_id, beat["id"])
        hook = _text(episode.get("dialogue_hook"))
        if hook not in cast_ids:
            issue("unbound_dialogue_hook", index, "known_cast_id", hook)
        if story["stages"][index]["scene_id"] != scene_id:
            issue("compiled_scene_mismatch", index, scene_id,
                  story["stages"][index]["scene_id"])
    if len(set(scene_ids)) != len(scene_ids):
        issue("duplicate_scene_id", None, "unique", scene_ids)
    for kind, source in (
        ("era_order", canon.get("era_order")),
        ("scene_canonical_order", continuity.get("canonical_order")),
    ):
        if type(source) is not list or any(type(item) is not str for item in source):
            raise StudioQuestError("invalid authored canon order")
        if source != scene_ids:
            issue(kind, None, scene_ids, source)
    critical = canon.get("critical_characters")
    if type(critical) is not list:
        raise StudioQuestError("invalid authored critical cast")
    for ident in critical:
        if _text(ident) not in cast_ids:
            issue("missing_critical_cast", None, "known_cast_id", ident)
    earned = {stage.key for stage in program.stages}
    earned.update(stage.reward for stage in program.stages)
    ending_obligations = [
        {"ending_id": ending_id,
         "authored_predicates": list(requirements),
         "unproven_predicates": [predicate for predicate in requirements
                                 if predicate not in earned],
         "external_evidence_required": any(predicate not in earned
                                            for predicate in requirements)}
        for ending_id, requirements in program.endings
    ]
    if sha256(_canonical({name: documents.get(name) for name in sections})).hexdigest() != source_digest:
        raise StudioQuestError("canon source changed during proof")
    payload: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_canon_proof.v1",
        "project_id": program.project_id,
        "source_digest": source_digest,
        "quest_source_digest": program.source_digest,
        "checked_scene_count": len(episodes),
        "checked_cast_count": len(cast_ids),
        "canon_consistent": not issues,
        "issues": issues,
        "ending_obligations": ending_obligations,
        "all_endings_proven": not issues and all(
            not ending["unproven_predicates"] for ending in ending_obligations
        ),
        "originality_rights_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["proof_digest"] = sha256(_canonical(payload)).hexdigest()
    return payload
