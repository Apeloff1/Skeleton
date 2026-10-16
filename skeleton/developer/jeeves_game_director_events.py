"""Authoritative state-delta -> typed cinematic/cast/quest presentation events.

This adapter presents existing Director scene cues only after an accepted
canonical action. It never invents quest completion, modifies the action
journal, executes scripts, or claims a rendered animation or recorded voice.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from skeleton.developer.jeeves_game_director_session import _load

SCHEMA = "skeleton.jeeves.director_presentation_delta.v1"
MAX_TIMELINES = 64


def delta(root: Path, *, session: str, before: dict[str, Any],
          after: dict[str, Any]) -> dict[str, Any]:
    if (not isinstance(before, dict) or not isinstance(after, dict)
            or after.get("sequence") != before.get("sequence", -1) + 1):
        raise ValueError("presentation requires adjacent canonical action states")
    folder, world, state, manifest, receipt, index = _load(root, name=session)
    if (after.get("current_state_sha256") != state.digest
            or after.get("last_receipt_sha256") != receipt
            or after.get("world_sha256") != world.digest
            or after.get("sequence") != index):
        raise ValueError("presentation would render noncanonical or stale gameplay")
    incoming = {(r["quest"], r["stage"]) for r in before.get("quest_stage_results", [])}
    new_results = [r for r in after.get("quest_stage_results", [])
                   if (r["quest"], r["stage"]) not in incoming]
    was_complete = {q["id"] for q in before.get("quests", []) if q["completed"]}
    newly_completed = {q["id"] for q in after.get("quests", []) if q["completed"]} - was_complete
    scenes = {s.key: s for s in world.scenes}
    quests = {q.key: q for q in world.quests}
    triggered: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(scene_key: str, cut_key: str, reason: str) -> None:
        if scene_key not in scenes:
            return
        scene = scenes[scene_key]
        for cut in scene.cutscenes:
            if cut.key == cut_key:
                receipt_key = (scene_key, cut.key, reason)
                if receipt_key in seen:
                    return
                seen.add(receipt_key)
                triggered.append({
                    "scene": scene_key,
                    "timeline": cut.key,
                    "trigger": cut.trigger,
                    "trigger_reason": reason,
                    "title": cut.title,
                    "skippable": cut.skippable,
                    "cues": [cue.payload() for cue in cut.cues],
                    "authored_timeline_ms": max(
                        cue.at + cue.duration for cue in cut.cues),
                    "runtime_animation_executed": False,
                })
                if len(triggered) > MAX_TIMELINES:
                    raise ValueError("single gameplay action triggered too many cinematic timelines")
                return

    prior_scene = before.get("scene")
    next_scene = after.get("scene")
    if prior_scene != next_scene:
        if prior_scene in scenes:
            for cut in scenes[prior_scene].cutscenes:
                if cut.trigger == "on_exit":
                    add(prior_scene, cut.key, "left_scene")
        if next_scene in scenes:
            for cut in scenes[next_scene].cutscenes:
                if cut.trigger == "on_enter":
                    add(next_scene, cut.key, "entered_scene")
    for result in new_results:
        quest = quests.get(result["quest"])
        if quest is None:
            raise ValueError("new Director stage belongs to an unknown quest")
        stage = next((st for st in quest.stages if st.key == result["stage"]), None)
        if stage is None:
            raise ValueError("new Director result has no authored stage")
        if stage.cutscene_on_complete:
            for scene_id in stage.scene_ids:
                add(scene_id, stage.cutscene_on_complete,
                    "completed_stage:" + quest.key + ":" + stage.key)
    for quest_key in sorted(newly_completed):
        for scene in world.scenes:
            for cut in scene.cutscenes:
                if cut.trigger == "on_quest_complete":
                    add(scene.key, cut.key, "completed_quest:" + quest_key)
    if not before.get("complete") and after.get("complete"):
        for scene in world.scenes:
            for cut in scene.cutscenes:
                if cut.trigger == "on_ending":
                    add(scene.key, cut.key, "reached_campaign_ending")
    flags_before = set(before.get("narrative_flags", []))
    new_flags = sorted(set(after.get("narrative_flags", [])) - flags_before)
    return {
        "schema": SCHEMA, "source_sha256": manifest["source_sha256"],
        "director_world_sha256": world.digest,
        "action_sequence": index,
        "state_sha256": state.digest,
        "new_story_results": new_results,
        "new_narrative_flags": new_flags,
        "newly_completed_quests": sorted(newly_completed),
        "presentation_timelines": triggered,
        "triggered_timelines": len(triggered),
        "native_cinematic_rendering_verified": False,
        "voice_or_music_playback_verified": False,
    }
