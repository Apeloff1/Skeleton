"""Bounded deterministic prompt-to-typed original scene audio cue proposal.

This is a source-derived planning fallback, not an LLM inference or audio
synthesis service. The operator can edit the returned typed proposal before
source-verified compilation and private publication.
"""
from __future__ import annotations

from hashlib import sha256
import re
from typing import Any, Mapping

from .studio_ecosystem_audio_cues import (
    REQUEST_SCHEMA, _layers, _text, compile_audio_cues,
)
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, compile_scene_schedule,
)

SCHEMA = "skeleton.game_builder.studio_audio_prompt_plan.v1"
MAX_PROMPT_BYTES = 2048
_WORDS = re.compile(r"[a-z0-9]{3,}")


def _terms(text: str) -> frozenset[str]:
    return frozenset(_WORDS.findall(text.casefold()))


def propose_audio_from_prompt(
    documents: Mapping[str, Any], actions: list[list[str]], schedule: object,
    prompt: str, *, authorized: bool, expected_source_digest: str,
    expected_session_digest: str | None = None,
) -> dict[str, Any]:
    """Choose original source layers with stable tie-breaking and replay proof."""
    if authorized is not True:
        raise PermissionError("audio prompt planning requires operator authorization")
    _text(prompt, "prompt", maximum=512)
    if len(prompt.encode("utf-8", "strict")) > MAX_PROMPT_BYTES:
        raise StudioQuestError("audio prompt exceeds byte budget")
    timing = compile_scene_schedule(
        documents, actions, schedule, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)
    audio_digest, layers = _layers(documents)
    original = documents["scene"]["episode_plan"]
    by_scene = {scene["id"]: scene for scene in original}
    if len(by_scene) != len(original):
        raise StudioQuestError("ambiguous authored audio prompt scenes")
    prompt_terms = _terms(prompt)
    request: dict[str, Any] = {
        "schema": REQUEST_SCHEMA, "scene_cues": {},
    }
    rationale: list[dict[str, Any]] = []
    for row in timing["timeline"]:
        scene_id = row["scene_id"]
        source_scene = by_scene.get(scene_id)
        if type(source_scene) is not dict:
            raise StudioQuestError("audio prompt references absent scene")
        context = " ".join(str(source_scene.get(key, "")) for key in (
            "weather_state", "site", "dialogue_hook", "quest_stage"))
        context_terms = _terms(context)
        candidates = []
        for index, (layer_id, layer) in enumerate(layers.items()):
            trigger_terms = _terms(layer["trigger"])
            source_terms = _terms(layer["source"])
            # Scene evidence outranks general user preference, preventing the
            # prompt from silently assigning an unrelated source layer.
            scene_score = len(trigger_terms & context_terms) * 4 + len(source_terms & context_terms)
            prompt_score = len(trigger_terms & prompt_terms) * 2 + len(source_terms & prompt_terms)
            candidates.append((-scene_score, -prompt_score, index, layer_id))
        candidates.sort()
        duration = row["duration_ticks"]
        chosen = [candidates[0][-1]]
        if duration >= 4 and len(candidates) > 1:
            chosen.append(candidates[1][-1])
        authored: list[dict[str, Any]] = []
        for index, layer_id in enumerate(chosen):
            offset = 0 if index == 0 else duration // 2
            length = max(1, min(4, duration - offset))
            caption = ("Original " + layer_id + " cue: " +
                       layers[layer_id]["source"])[:280].strip()
            authored.append({
                "layer_id": layer_id, "start_offset": offset,
                "duration_ticks": length, "caption": caption,
            })
        request["scene_cues"][scene_id] = authored
        rationale.append({
            "scene_id": scene_id, "selected_source_layers": chosen,
            "source_context_digest": _digest(context),
            "selection_method": "bounded_source_token_overlap",
        })
    plan = compile_audio_cues(
        documents, actions, schedule, request, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=timing["session_digest"])
    if (plan["audio_source_digest"] != audio_digest
            or plan["schedule_digest"] != timing["schedule_digest"]):
        raise StudioQuestError("audio prompt proposal source replay diverged")
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": plan["project_id"],
        "prompt_digest": sha256(prompt.encode("utf-8", "strict")).hexdigest(),
        "source_digest": plan["source_digest"],
        "session_digest": plan["session_digest"],
        "audio_source_digest": audio_digest,
        "authoring": request, "selection_rationale": rationale,
        "compiled_plan": plan, "source_replay_verified": True,
        "model_inference_performed": False, "audio_generated": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(result)) > 256 * 1024:
        raise StudioQuestError("audio prompt result exceeds budget")
    result["proposal_digest"] = _digest(result)
    return result
