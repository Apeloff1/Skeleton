"""Source-leased decision atlas for every authored sandbox ending.

This reports possible quest-stage routes and unresolved external predicates.
Authored choice alternatives are NOT evidence that an ending was played.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_ending_plan import plan_authored_ending
from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)

ENDING_ATLAS_SCHEMA = "skeleton.game_builder.studio_ending_atlas.v1"
MAX_ATLAS_ENDINGS = 16
MAX_ATLAS_BYTES = 128 * 1024


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical ending atlas") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _lease(value: object, kind: str) -> str:
    if (type(value) is not str or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise StudioQuestError("invalid " + kind + " lease")
    return value


def build_ending_atlas(
    documents: Mapping[str, Any], actions: list[list[str]], *,
    authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, object]:
    """Replay all ending routes, preserve external holds and prove shared stages.

    All evidence is bound to the canonical source and original quest session.
    A stage with multiple alternatives is only a *choice opportunity*; there
    is no invented causal mapping from that choice to an authored ending.
    """
    if authorized is not True:
        raise PermissionError("ending atlas requires operator authorization")
    _lease(expected_source_digest, "ending atlas source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "ending atlas session")
    proof = audit_canon_source(documents, authorized=True)
    if not proof["canon_consistent"]:
        raise StudioQuestError("ending atlas refuses contradictory authored canon")
    if proof["source_digest"] != expected_source_digest:
        raise StudioQuestError("stale ending atlas source lease")
    program = compile_quest_program(documents)
    if not 1 <= len(program.endings) <= MAX_ATLAS_ENDINGS:
        raise StudioQuestError("ending atlas exceeds authored ending budget")
    session = replay_quest(documents, actions, authorized=True)
    if expected_session_digest is not None and session.digest != expected_session_digest:
        raise StudioQuestError("stale ending atlas session lease")
    stage_by_id = {stage.key: stage for stage in program.stages}
    cards: list[dict[str, object]] = []
    routes: dict[str, set[str]] = {}
    for ending_id, requirements in program.endings:
        plan = plan_authored_ending(
            documents, ending_id=ending_id, session=session, authorized=True)
        steps = plan["planned_steps"]
        route = [step["stage_id"] for step in steps]
        if len(route) != len(set(route)):
            raise StudioQuestError("ending atlas detected repeated stage")
        routes[ending_id] = set(route)
        opportunities = [
            {"stage_id": key, "alternative_count": len(stage_by_id[key].alternatives)}
            for key in route if len(stage_by_id[key].alternatives) > 1
        ]
        cards.append({
            "ending_id": ending_id,
            "required_predicates": list(requirements),
            "status": plan["status"],
            "sandbox_eligible_after_plan": plan["sandbox_eligible_after_plan"],
            "unresolved_external_predicates": list(plan["external_unbound_predicates"]),
            "remaining_stage_count": len(route),
            "stage_route": route,
            "choice_opportunities": opportunities,
            "simulated_session_digest": plan["simulated_session_digest"],
            "ending_plan_digest": plan["plan_digest"],
            "choice_to_ending_causality_verified": any(
                predicate.startswith("choice:") for predicate in requirements
            ),
            "external_evidence_verified": False,
        })
    pairwise: list[dict[str, object]] = []
    for left_index, left in enumerate(cards):
        for right in cards[left_index + 1:]:
            left_id, right_id = left["ending_id"], right["ending_id"]
            lset, rset = routes[left_id], routes[right_id]
            pairwise.append({
                "left_ending_id": left_id,
                "right_ending_id": right_id,
                "shared_required_stages": [
                    stage.key for stage in program.stages
                    if stage.key in lset and stage.key in rset
                ],
                "left_only_stages": [
                    stage.key for stage in program.stages
                    if stage.key in lset and stage.key not in rset
                ],
                "right_only_stages": [
                    stage.key for stage in program.stages
                    if stage.key in rset and stage.key not in lset
                ],
                "choice_alternative_causality_verified": False,
            })
    payload: dict[str, object] = {
        "schema": ENDING_ATLAS_SCHEMA,
        "project_id": program.project_id,
        "source_digest": proof["source_digest"],
        "quest_source_digest": program.source_digest,
        "session_digest": session.digest,
        "ending_count": len(cards),
        "simulatable_count": sum(c["status"] == "simulatable" for c in cards),
        "external_hold_count": sum(c["status"] != "simulatable" for c in cards),
        "endings": cards,
        "route_overlap": pairwise,
        "original_session_unchanged": True,
        "file_write_performed": False,
        "native_ending_delivery_verified": False,
        "external_evidence_verified": False,
        "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_ATLAS_BYTES:
        raise StudioQuestError("ending atlas receipt exceeds byte budget")
    payload["atlas_digest"] = _digest(payload)
    return payload
