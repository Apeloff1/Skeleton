"""Canonical original NPC scene route planner over authored quest prerequisites.

Plans only source-authorized stage choices.  It never asserts a scene was
played, a witness spoke, or an external narrative predicate was fulfilled.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_dialogue_choice_preview import preview_dialogue_choices
from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_quest import (
    StudioQuestError, available_stages, compile_quest_program,
    quest_progress, replay_quest, step_quest,
)

ROUTE_SCHEMA = "skeleton.game_builder.studio_dialogue_scene_route.v1"
MAX_ROUTE_STEPS = 64


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical NPC scene route") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def plan_dialogue_scene_route(
    documents: Mapping[str, Any], actions: list[list[str]], *,
    target_scene_id: str, authorized: bool,
    preferred_alternatives: Mapping[str, str] | None = None,
    expected_source_digest: str | None = None,
) -> dict[str, object]:
    """Compute the minimal prerequisite closure for one authored NPC scene.

    Replays only missing ancestor stages in canonical topological order.
    Choice preferences must name exactly required uncompleted ancestors;
    every preference must be a valid authored alternative. The final target
    remains unplayed and its actual options are source-previewed.
    """
    if authorized is not True:
        raise PermissionError("dialogue scene route requires operator authorization")
    if (type(target_scene_id) is not str or not 1 <= len(target_scene_id) <= 512
            or target_scene_id != target_scene_id.strip()
            or any(ord(ch) < 32 for ch in target_scene_id)):
        raise StudioQuestError("invalid NPC route target scene")
    preferences = {} if preferred_alternatives is None else preferred_alternatives
    if (type(preferences) is not dict or len(preferences) > MAX_ROUTE_STEPS
            or len(_canonical(preferences)) > 8192):
        raise StudioQuestError("invalid NPC route preference map")
    program = compile_quest_program(documents)
    before = replay_quest(documents, actions, authorized=True)
    staging = compile_dialogue_staging(
        documents, actions, authorized=True,
        expected_source_digest=expected_source_digest)
    cards = {card["scene_id"]: card for card in staging["cards"]}
    target = cards.get(target_scene_id)
    if target is None:
        raise StudioQuestError("NPC route target is not an authored scene")
    stages = {stage.key: stage for stage in program.stages}
    stage_id = target["quest_stage"]
    if stage_id not in stages:
        raise StudioQuestError("NPC route references unknown quest stage")
    required: set[str] = set()
    def visit(key: str) -> None:
        for parent in stages[key].prerequisites:
            if parent not in required:
                required.add(parent)
                visit(parent)
    visit(stage_id)
    remaining = required - set(before.completed)
    if set(preferences) - remaining:
        raise StudioQuestError("NPC route preference targets completed or unrelated stage")
    for key, value in preferences.items():
        if (type(key) is not str or type(value) is not str
                or value not in stages[key].alternatives):
            raise StudioQuestError("NPC route preference is not an authored alternative")
    state = before
    steps: list[dict[str, object]] = []
    by_stage = {card["quest_stage"]: card for card in staging["cards"]}
    for stage in program.stages:
        if stage.key not in remaining:
            continue
        if len(steps) >= MAX_ROUTE_STEPS or stage.key not in available_stages(state, documents):
            raise StudioQuestError("NPC route prerequisite is unreachable")
        option = preferences.get(stage.key, stage.alternatives[0])
        next_state = step_quest(
            state, documents, stage=stage.key, alternative=option, authorized=True)
        card = by_stage.get(stage.key)
        if card is None:
            raise StudioQuestError("NPC route ancestor has no authored NPC scene")
        steps.append({
            "scene_id": card["scene_id"],
            "npc_id": card["npc_id"],
            "quest_stage": stage.key,
            "alternative": option,
            "before_session_digest": state.digest,
            "after_session_digest": next_state.digest,
            "authored_card_digest": card["card_digest"],
            "scene_played_verified": False,
        })
        state = next_state
    if stage_id not in state.completed and stage_id not in available_stages(state, documents):
        raise StudioQuestError("NPC route did not unlock target")
    after_staging = compile_dialogue_staging(
        documents, [list(pair) for pair in state.choices], authorized=True,
        expected_source_digest=staging["source_digest"], scene_id=target_scene_id)
    if after_staging["session_digest"] != state.digest:
        raise StudioQuestError("NPC route staging replay mismatch")
    previews = preview_dialogue_choices(
        documents, [list(pair) for pair in state.choices], authorized=True,
        expected_source_digest=staging["source_digest"], scene_id=target_scene_id)
    progress = quest_progress(state, documents)
    payload: dict[str, object] = {
        "schema": ROUTE_SCHEMA,
        "project_id": before.project_id,
        "source_digest": staging["source_digest"],
        "quest_source_digest": before.source_digest,
        "target_scene_id": target_scene_id,
        "target_npc_id": target["npc_id"],
        "target_quest_stage": stage_id,
        "target_status": after_staging["cards"][0]["status"],
        "original_session_digest": before.digest,
        "planned_session_digest": state.digest,
        "steps": steps,
        "step_count": len(steps),
        "preferred_alternatives": dict(sorted(preferences.items())),
        "planned_quest_receipt": state.receipt(),
        "target_scene_staging": after_staging,
        "target_choice_previews": previews,
        "progress": progress,
        "file_write_performed": False,
        "scene_played_verified": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["route_digest"] = _digest(payload)
    return payload
