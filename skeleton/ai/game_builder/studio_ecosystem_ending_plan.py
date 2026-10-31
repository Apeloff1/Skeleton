"""Deterministic source-bound plans for authored sandbox ending predicates.

A plan proves only that the canonical quest simulation can execute selected
stages. It never fabricates external evidence or certifies a narrative ending.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_canon_proof import audit_canon_source
from .studio_ecosystem_quest import (
    QuestSession, StudioQuestError, compile_quest_program, quest_progress,
    start_quest, step_quest, verify_quest_session,
)

PLAN_SCHEMA = "skeleton.game_builder.studio_ending_plan.v1"
MAX_PLAN_STAGES = 64


def _digest(value: object) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical ending plan") from exc
    return sha256(raw).hexdigest()


def plan_authored_ending(
    documents: Mapping[str, Any], *, ending_id: str,
    session: QuestSession | None = None, authorized: bool,
) -> dict[str, object]:
    """Return a bounded replay-verified quest-stage itinerary for one ending."""
    if authorized is not True:
        raise PermissionError("authored ending plan requires operator authorization")
    if type(ending_id) is not str or not 1 <= len(ending_id) <= 256:
        raise StudioQuestError("invalid authored ending identifier")
    proof = audit_canon_source(documents, authorized=True)
    if not proof["canon_consistent"]:
        raise StudioQuestError("authored ending plan refuses contradictory canon")
    program = compile_quest_program(documents)
    if session is None:
        session = start_quest(documents, authorized=True)
    verify_quest_session(session, documents, program=program)
    ending = next(((key, requirements) for key, requirements in program.endings
                   if key == ending_id), None)
    if ending is None:
        raise StudioQuestError("unknown authored ending")
    stage_by_key = {stage.key: stage for stage in program.stages}
    reward_to_stage: dict[str, str] = {}
    for stage in program.stages:
        reward_to_stage.setdefault(stage.reward, stage.key)
    required = ending[1]
    unbound = sorted(set(required) - set(stage_by_key) - set(reward_to_stage))
    targets = {stage_by_key[key].key if key in stage_by_key
               else reward_to_stage[key] for key in required
               if key in stage_by_key or key in reward_to_stage}
    needed: set[str] = set()
    def visit(key: str) -> None:
        if key in needed:
            return
        stage = stage_by_key[key]
        for dep in stage.prerequisites:
            if dep not in stage_by_key:
                raise StudioQuestError("authored ending has unbound prerequisite")
            visit(dep)
        needed.add(key)
    for key in targets:
        visit(key)
    if len(needed) > MAX_PLAN_STAGES:
        raise StudioQuestError("authored ending plan stage budget exceeded")
    original_digest = session.digest
    simulated = session
    steps: list[dict[str, object]] = []
    completed = set(session.completed)
    for stage in program.stages:
        if stage.key not in needed or stage.key in completed:
            continue
        if not set(stage.prerequisites).issubset(set(simulated.completed)):
            raise StudioQuestError("authored ending stage dependency not executable")
        choice = stage.alternatives[0]
        previous_digest = simulated.digest
        simulated = step_quest(simulated, documents, stage=stage.key,
                               alternative=choice, authorized=True)
        steps.append({
            "stage_id": stage.key, "choice": choice,
            "reward": stage.reward, "before_digest": previous_digest,
            "after_digest": simulated.digest,
        })
    verify_quest_session(simulated, documents, program=program)
    progress = quest_progress(simulated, documents)
    remaining = progress["unmet_ending_predicates"].get(ending_id, [])
    if unbound != remaining:
        raise StudioQuestError("authored ending planning/replay evidence mismatch")
    if session.digest != original_digest:
        raise StudioQuestError("authored ending plan mutated original session")
    payload: dict[str, object] = {
        "schema": PLAN_SCHEMA,
        "project_id": program.project_id,
        "quest_source_digest": program.source_digest,
        "canon_source_digest": proof["source_digest"],
        "ending_id": ending_id,
        "required_predicates": list(required),
        "external_unbound_predicates": unbound,
        "planned_stage_count": len(steps),
        "planned_steps": steps,
        "initial_session_digest": original_digest,
        "simulated_session_digest": simulated.digest,
        "sandbox_eligible_after_plan": not remaining,
        "status": "simulatable" if not remaining else "blocked_external_predicates",
        "original_session_unchanged": True,
        "native_ending_delivery_verified": False,
        "external_evidence_verified": False,
        "release_certified": False,
    }
    payload["plan_digest"] = _digest(payload)
    return payload
