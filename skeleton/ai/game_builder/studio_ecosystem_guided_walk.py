"""Operator-selected guided world traversal with authoritative route and choice replay.

The caller supplies every authored choice. This composes the canonical route
solver and walk engine, never guesses narrative consent, and atomically returns
a new receipt only after replaying the entire proposed event history.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_walk_replay import (
    MAX_WALK_EVENTS, WalkSession, follow_walk_route,
    replay_walk, verify_walk, walk_action, walk_choice_previews,
)

GUIDED_WALK_SCHEMA = "skeleton.game_builder.studio_guided_walk.v1"
MAX_GUIDED_SCENES = 3
MAX_GUIDED_INPUT_BYTES = 4096


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical guided world traversal") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def execute_guided_walk(
    documents: Mapping[str, Any],
    events: list[list[str]],
    *,
    authored_choices: list[str],
    expected_source_digest: str,
    expected_session_digest: str,
    authorized: bool,
) -> tuple[WalkSession, dict[str, object]]:
    """Navigate and select 1..3 explicitly chosen original scene alternatives.

    This is an in-memory atomic operation. If any route, choice, source or
    resource validation fails, no new save receipt is returned. Route
    movements and each choice are independently verified against the
    authoritative walk engine, then the entire history is replayed again.
    """
    if authorized is not True:
        raise PermissionError("guided world traversal requires operator authorization")
    if (type(events) is not list or len(events) > MAX_WALK_EVENTS
            or len(_canonical(events)) > 65536):
        raise StudioQuestError("invalid guided walk history")
    if (type(authored_choices) is not list
            or not 1 <= len(authored_choices) <= MAX_GUIDED_SCENES
            or len(_canonical(authored_choices)) > MAX_GUIDED_INPUT_BYTES):
        raise StudioQuestError("invalid guided walk choice budget")
    if any(type(choice) is not str or not 1 <= len(choice) <= 256
           or choice != choice.strip() or any(ord(ch) < 32 for ch in choice)
           for choice in authored_choices):
        raise StudioQuestError("invalid guided authored alternative")
    for digest in (expected_source_digest, expected_session_digest):
        if (type(digest) is not str or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)):
            raise StudioQuestError("invalid guided walk digest lease")

    initial = replay_walk(documents, events, authorized=True)
    verify_walk(initial, documents)
    if (initial.source_digest != expected_source_digest
            or initial.digest != expected_session_digest):
        raise StudioQuestError("stale guided walk source or session lease")
    current = initial
    steps: list[dict[str, object]] = []
    for alternative in authored_choices:
        before = current
        approached, route = follow_walk_route(
            current, documents, authorized=True)
        if (approached.source_digest != expected_source_digest
                or approached.scene_index != before.scene_index
                or approached.chosen != before.chosen):
            raise StudioQuestError("guided route changed source or narrative state")
        preview = walk_choice_previews(
            approached, documents, authorized=True)
        if (preview["status"] != "ready"
                or preview["session_digest"] != approached.digest):
            raise StudioQuestError("guided scene is not ready for an authored choice")
        matching = [
            item for item in preview["alternatives"]
            if item["alternative"] == alternative
        ]
        if len(matching) != 1:
            raise StudioQuestError("guided choice is not an authored alternative")
        successor = walk_action(
            approached, documents, action="choose",
            value=alternative, authorized=True)
        if (successor.digest != matching[0]["result_session_digest"]
                or successor.scene_index != before.scene_index + 1
                or successor.source_digest != expected_source_digest
                or successor.chosen[:-1] != before.chosen
                or len(successor.events) > MAX_WALK_EVENTS):
            raise StudioQuestError("guided walk successor failed authoritative replay")
        steps.append({
            "scene_index": before.scene_index,
            "scene_id": preview["scene_id"],
            "authored_alternative": alternative,
            "before_session_digest": before.digest,
            "approached_session_digest": approached.digest,
            "after_session_digest": successor.digest,
            "route_digest": route["route_digest"],
            "choice_preview_digest": preview["preview_digest"],
            "movement_events": len(approached.events) - len(before.events),
            "choice_events": 1,
            "scene_played_in_sandbox": True,
            "native_genre_runtime_verified": False,
        })
        current = successor
    final = replay_walk(documents, list(current.events), authorized=True)
    if (final != current
            or final.project_id != initial.project_id
            or final.source_digest != initial.source_digest
            or final.chosen[:len(initial.chosen)] != initial.chosen):
        raise StudioQuestError("guided walk final history failed replay")
    payload: dict[str, object] = {
        "schema": GUIDED_WALK_SCHEMA,
        "project_id": initial.project_id,
        "source_digest": initial.source_digest,
        "original_session_digest": initial.digest,
        "final_session_digest": final.digest,
        "scene_count": len(steps),
        "steps": steps,
        "new_events": [list(event) for event in final.events[len(initial.events):]],
        "final_receipt": final.receipt(),
        "replay_verified": True,
        "file_write_performed": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["guided_digest"] = _digest(payload)
    return final, payload
