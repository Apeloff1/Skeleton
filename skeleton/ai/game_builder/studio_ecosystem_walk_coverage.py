"""Bounded, authoritative coverage of authored walk choices from a verified save.

This audits each alternative on one deterministic reference path. It never
claims exhaustive cross-product branching or native-game certification.
"""
from __future__ import annotations

from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_walkable import playable_world_source
from .studio_ecosystem_walk_replay import (
    MAX_WALK_EVENTS, WalkSession, _sha, replay_walk, verify_walk,
    walk_action, walk_narrative_continuity, walk_route_hint,
)

MAX_COVERAGE_STAGES = 24
MAX_COVERAGE_CHOICES = 96
MAX_COVERAGE_REPLAY_EVENTS = 16_384


def audit_walk_choice_coverage(
    session: WalkSession, documents: Mapping[str, Any], *, authorized: bool,
) -> dict[str, object]:
    """Prove each tested choice is executable at its authored scene marker.

    Each stage is approached using the real shortest collision-checked route.
    Every alternative is independently replayed from the same verified
    pre-choice state; the first alternative alone advances the reference path.
    Bounds cause explicit partial coverage, never a fabricated full proof.
    """
    if not authorized:
        raise PermissionError("walk choice audit requires operator authorization")
    verify_walk(session, documents)
    continuity = walk_narrative_continuity(session, documents, authorized=True)
    world = playable_world_source(documents)
    if (world["project_id"] != session.project_id
            or world["source_digest"] != session.source_digest
            or len(world["stages"]) != continuity["authored_stage_count"]
            or session.scene_index > len(world["stages"])):
        raise StudioQuestError("walk choice audit source identity mismatch")

    remaining = world["stages"][session.scene_index:]
    expected = sum(len(stage["alternatives"]) for stage in remaining)
    if expected > 4096:
        raise StudioQuestError("walk choice audit source exceeds stage budget")
    world_digest = _sha(world)
    cursor = session
    records: list[dict[str, object]] = []
    stage_count = 0
    # Count source replay work conservatively: authorization/continuity and
    # final verification are bounded separately; each walk_action verifies the
    # previous state and recomputes the successor from genesis.
    replay_work = 0
    stop_reason = "complete"

    for stage in remaining:
        if stage_count >= MAX_COVERAGE_STAGES:
            stop_reason = "stage_budget_exhausted"
            break
        alternatives = stage["alternatives"]
        if (not isinstance(alternatives, list) or not alternatives
                or any(not isinstance(value, str) or not value
                       for value in alternatives)
                or len(set(alternatives)) != len(alternatives)):
            raise StudioQuestError("invalid authored choice alternatives")
        if len(records) + len(alternatives) > MAX_COVERAGE_CHOICES:
            stop_reason = "choice_budget_exhausted"
            break
        hint = walk_route_hint(cursor, documents, authorized=True)
        if hint["scene_id"] != stage["id"]:
            raise StudioQuestError("walk choice audit scene drift")
        if hint["status"] not in ("ready", "already_near"):
            stop_reason = str(hint["status"])
            break
        moves = hint["moves"]
        if (not isinstance(moves, list)
                or any(move not in ("up", "down", "left", "right")
                       for move in moves)):
            raise StudioQuestError("walk choice audit invalid route")
        route_events = tuple(("move", move) for move in moves)
        proposed = cursor.events + route_events
        if len(proposed) + 1 > MAX_WALK_EVENTS:
            stop_reason = "event_budget_exhausted"
            break
        cost = (len(cursor.events) + len(proposed)
                + len(alternatives) * (2 * len(proposed) + 1))
        if replay_work + cost > MAX_COVERAGE_REPLAY_EVENTS:
            stop_reason = "replay_budget_exhausted"
            break
        approached = replay_walk(documents, proposed, authorized=True)
        if (approached.source_digest != session.source_digest
                or approached.scene_index != cursor.scene_index
                or approached.chosen != cursor.chosen):
            raise StudioQuestError("walk choice audit route/source drift")
        replay_work += len(cursor.events) + len(proposed)
        first_successor = None
        for alternative in alternatives:
            successor = walk_action(
                approached, documents, action="choose",
                value=alternative, authorized=True,
            )
            replay_work += 2 * len(approached.events) + 1
            if (successor.scene_index != cursor.scene_index + 1
                    or successor.source_digest != session.source_digest
                    or successor.chosen[-1] != (stage["id"], alternative)):
                raise StudioQuestError("walk choice audit successor mismatch")
            records.append({
                "stage_id": stage["id"],
                "scene_id": stage["scene_id"],
                "alternative": alternative,
                "route_digest": hint["route_digest"],
                "route_distance": len(moves),
                "before_choice_digest": approached.digest,
                "after_choice_digest": successor.digest,
            })
            if first_successor is None:
                first_successor = successor
        assert first_successor is not None
        cursor = first_successor
        stage_count += 1

    verify_walk(session, documents)
    if (_sha(playable_world_source(documents)) != world_digest
            or walk_narrative_continuity(
                session, documents, authorized=True)["continuity_digest"]
            != continuity["continuity_digest"]):
        raise StudioQuestError("walk choice audit source changed during replay")
    if cursor.source_digest != session.source_digest:
        raise StudioQuestError("walk choice audit changed authoritative source")
    complete = stop_reason == "complete" and cursor.scene_index == len(world["stages"])
    payload: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_walk_choice_coverage.v1",
        "project_id": session.project_id,
        "source_digest": session.source_digest,
        "input_session_digest": session.digest,
        "reference_path_session_digest": cursor.digest,
        "authored_stage_count": len(world["stages"]),
        "stages_audited": stage_count,
        "alternatives_expected_from_input": expected,
        "alternatives_verified": len(records),
        "alternatives_unverified": expected - len(records),
        "replay_work_events": replay_work,
        "stop_reason": stop_reason,
        "complete_reference_path_coverage": complete,
        "all_branch_combinations_verified": False,
        "original_save_unchanged": True,
        "choices": records,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["coverage_digest"] = _sha(payload)
    return payload
