"""Fail-closed authored story, scene, quest and release-hold continuity checks.

A valid design document does not imply a playable engine or a verified ending.
This static analysis connects canonical source owners without materializing
assets or granting evidence; it only qualifies internal *source consistency*.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program,
)
from .studio_ecosystem_catalog import (
    StudioEcosystemError, read_blueprint, ROOT,
)


def _sha(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")
    return sha256(data).hexdigest()


def inspect_continuity(documents: Mapping[str, Any]) -> dict[str, object]:
    """Analyze one validated eight-section studio source; no external IO."""
    if not isinstance(documents, Mapping) or len(documents) != 8:
        raise StudioQuestError("expected eight typed studio sections")
    program = compile_quest_program(documents)
    scene = documents.get("scene")
    cast = documents.get("cast")
    verification = documents.get("verification")
    visual = documents.get("visual")
    audio = documents.get("audio")
    if any(not isinstance(x, dict) for x in (scene, cast, verification, visual, audio)):
        raise StudioQuestError("missing required story sections")
    pid = program.project_id
    for name, part in documents.items():
        if (not isinstance(part, dict) or part.get("project_id") != pid
                or name != "intent" and part.get("release_certified") is not False):
            raise StudioQuestError("source identity or release hold violation")
    episodes = scene.get("episode_plan")
    if not isinstance(episodes, list) or not episodes or len(episodes) > 100:
        raise StudioQuestError("invalid scene plan")
    scenes = []
    errors: list[str] = []
    seen_scene_keys: set[str] = set()
    for episode in episodes:
        if not isinstance(episode, dict):
            raise StudioQuestError("invalid scene")
        key = episode.get("id")
        stage = episode.get("quest_stage")
        if not isinstance(key, str) or not key or key in seen_scene_keys:
            errors.append("duplicate_or_missing_scene_id")
        else:
            seen_scene_keys.add(key)
        if not isinstance(stage, str) or stage not in program.stage_ids:
            errors.append("scene_references_unknown_quest_stage")
        scenes.append(stage)
        objects = episode.get("interactive_objects")
        if not isinstance(objects, list) or len(objects) < 1 or any(
            not isinstance(item, str) or not item for item in objects
        ):
            errors.append("scene_without_interactions")
    if len(scenes) != len(program.stages) or tuple(scenes) != program.stage_ids:
        errors.append("scene_quest_order_or_cardinality_mismatch")
    if len(set(scenes)) != len(scenes):
        errors.append("quest_stage_has_ambiguous_scene")
    # Dialogue hooks are only in the newer source family; normalize role IDs.
    if any("dialogue_hook" in e for e in episodes):
        support = cast.get("support")
        if not isinstance(support, list):
            errors.append("dialogue_has_no_cast")
        else:
            known = {c.get("id") for c in support if isinstance(c, dict)}
            known.add("protagonist")
            for episode in episodes:
                hook = episode.get("dialogue_hook")
                if hook is not None and hook not in known:
                    errors.append("dialogue_hook_unowned")
    gates = verification.get("quality_gates")
    blockers = verification.get("release_blockers")
    if (not isinstance(gates, list) or not gates
            or not isinstance(blockers, list) or not blockers):
        errors.append("missing_release_hold_or_qa_gates")
    elif any(not isinstance(g, dict) or g.get("status") != "not_tested"
             for g in gates):
        errors.append("unearned_qa_gate_status")
    # The authoring file may request asset jobs but cannot assert delivery.
    has_art_plan = bool(visual.get("jobs") or visual.get("asset_recipes"))
    has_audio_plan = bool(audio.get("cue_sheet") or audio.get("sound_layers"))
    if not has_art_plan or not has_audio_plan:
        errors.append("unbound_art_or_audio_plan")
    possible_internal = set(program.stage_ids) | {s.reward for s in program.stages}
    unbound_endings = {
        key: sorted(set(required) - possible_internal)
        for key, required in program.endings
        if not set(required).issubset(possible_internal)
    }
    # An internally eligible ending is only a *sandbox branch*. No physical
    # source, eyewitness, device or art evidence is inferred from this list.
    return {
        "schema": "skeleton.game_builder.studio_continuity_audit.v1",
        "project_id": pid,
        "source_digest": _sha({k: documents[k] for k in sorted(documents)}),
        "quest_stage_count": len(program.stages),
        "scene_count": len(scenes),
        "authored_ending_count": len(program.endings),
        "unbound_ending_predicates": unbound_endings,
        "source_consistent": not errors,
        "status": "source_consistent_with_release_holds" if not errors else "source_rejected",
        "errors": sorted(set(errors)),
        "asset_generation_verified": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }


def audit_catalog_continuity(project_id: str, *, root=ROOT) -> dict[str, object]:
    """Only registered, fully validated catalog sources are auditable."""
    docs = read_blueprint(project_id, root=root)
    return inspect_continuity(docs)
