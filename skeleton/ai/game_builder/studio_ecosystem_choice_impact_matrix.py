"""Deterministic branch-impact matrix for currently executable authored choices.

The canonical quest simulator awards stage rewards independently of the
alternative chosen. This tool makes that limitation explicit instead of
inventing narrative causality or claiming native gameplay consequences.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import (
    StudioQuestError, available_stages, compile_quest_program, quest_progress,
    replay_quest, step_quest,
)

CHOICE_IMPACT_SCHEMA = "skeleton.game_builder.studio_choice_impact_matrix.v1"
MAX_CHOICE_IMPACT_PAGE = 8
MAX_CHOICE_IMPACT_BYTES = 128 * 1024


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical authored choice impact") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _lease(value: object, kind: str) -> str:
    if (type(value) is not str or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise StudioQuestError("invalid " + kind + " lease")
    return value


def page_choice_impacts(
    documents: Mapping[str, Any], actions: list[list[str]], *,
    authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
    offset: int = 0, limit: int = 4,
) -> dict[str, object]:
    """Compare every authored alternative of a bounded page of open stages.

    The original session and source are never changed. Each candidate is
    actually replayed through step_quest and checked with quest_progress.
    A mechanical equivalence finding is *not* evidence that narrative prose
    or an external world simulation treats those alternatives identically.
    """
    if authorized is not True:
        raise PermissionError("choice impact matrix requires operator authorization")
    _lease(expected_source_digest, "choice impact source")
    if expected_session_digest is not None:
        _lease(expected_session_digest, "choice impact session")
    if (type(offset) is not int or offset < 0
            or type(limit) is not int or not 1 <= limit <= MAX_CHOICE_IMPACT_PAGE):
        raise StudioQuestError("invalid choice impact pagination")
    if offset and expected_session_digest is None:
        raise StudioQuestError("choice impact continuation requires session lease")
    proof = audit_canon_source(documents, authorized=True)
    if not proof["canon_consistent"]:
        raise StudioQuestError("choice impact refuses contradictory authored canon")
    if proof["source_digest"] != expected_source_digest:
        raise StudioQuestError("stale choice impact source lease")
    program = compile_quest_program(documents)
    session = replay_quest(documents, actions, authorized=True)
    if expected_session_digest is not None and session.digest != expected_session_digest:
        raise StudioQuestError("stale choice impact session lease")
    baseline = quest_progress(session, documents)
    baseline_eligible = set(baseline["sandbox_endings_eligible"])
    baseline_available = set(baseline["available"])
    open_ids = available_stages(session, documents)
    if offset > len(open_ids):
        raise StudioQuestError("choice impact page exceeds open stage count")
    stage_map = {stage.key: stage for stage in program.stages}
    cards: list[dict[str, object]] = []
    divergence_count = 0
    for key in open_ids[offset:offset + limit]:
        stage = stage_map[key]
        candidates: list[dict[str, object]] = []
        signatures: set[str] = set()
        for alternative in stage.alternatives:
            candidate = step_quest(
                session, documents, stage=key, alternative=alternative,
                authorized=True)
            progress = quest_progress(candidate, documents)
            newly_eligible = sorted(
                set(progress["sandbox_endings_eligible"]) - baseline_eligible)
            newly_available = sorted(set(progress["available"]) - baseline_available)
            outcome = {
                "completed_stage_ids": list(candidate.completed),
                "available_stage_ids": list(progress["available"]),
                "sandbox_endings_eligible": list(progress["sandbox_endings_eligible"]),
                "unmet_ending_predicates": progress["unmet_ending_predicates"],
            }
            signatures.add(_digest(outcome))
            candidates.append({
                "alternative": alternative,
                "candidate_session_digest": candidate.digest,
                "newly_available_stage_ids": newly_available,
                "newly_eligible_sandbox_endings": newly_eligible,
                "unmet_ending_predicates": progress["unmet_ending_predicates"],
                "mechanical_outcome_digest": _digest(outcome),
                "external_consequence_verified": False,
            })
        divergence = len(signatures) > 1
        divergence_count += int(divergence)
        cards.append({
            "stage_id": key,
            "prerequisites": list(stage.prerequisites),
            "reward": stage.reward,
            "alternative_count": len(candidates),
            "alternatives": candidates,
            "mechanical_outcomes_diverge": divergence,
            "alternative_specific_narrative_consequences_verified": False,
        })
    payload: dict[str, object] = {
        "schema": CHOICE_IMPACT_SCHEMA,
        "project_id": program.project_id,
        "source_digest": proof["source_digest"],
        "quest_source_digest": program.source_digest,
        "session_digest": session.digest,
        "offset": offset, "limit": limit,
        "total_available_stages": len(open_ids),
        "next_offset": offset + len(cards) if offset + len(cards) < len(open_ids) else None,
        "mechanically_divergent_stages_on_page": divergence_count,
        "stages": cards,
        "simulation_model": "authored_stage_reward_only",
        "original_session_unchanged": True,
        "file_write_performed": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    if len(_canonical(payload)) > MAX_CHOICE_IMPACT_BYTES:
        raise StudioQuestError("choice impact receipt exceeds byte budget")
    payload["matrix_digest"] = _digest(payload)
    return payload
