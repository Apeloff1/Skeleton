"""Authoritative state-delta -> typed cinematic/cast/quest presentation events.

This adapter presents existing Director scene cues only after an accepted
canonical action. It never invents quest completion, modifies the action
journal, executes scripts, or claims a rendered animation or recorded voice.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from skeleton.developer.jeeves_game_director_session import _load, _read_doc

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
    if index < 1:
        raise ValueError("cannot present an action that never occurred")
    event = _read_doc(folder / f"{index:08d}.json")
    if (event["receipt_sha256"] != receipt
            or event["prior_sha256"] != before.get("last_receipt_sha256")
            or event["before_sha256"] != before.get("current_state_sha256")
            or event["after_sha256"] != after.get("current_state_sha256")
            or before.get("sequence") != index - 1):
        raise ValueError("cinematic presentation cannot fabricate a prior player action")
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
    living_events = {}
    if world.dynamics is not None:
        previous_state = before.get("world_state")
        next_state = after.get("world_state")
        if not isinstance(previous_state, dict) or not isinstance(next_state, dict):
            raise ValueError("dynamic-world presentation lacks canonical standing evidence")
        old = dict(previous_state.get("standings", []))
        new = dict(next_state.get("standings", []))
        effects = [
            {"faction": faction, "before": old[faction],
             "after": new[faction], "delta": new[faction] - old[faction]}
            for faction in sorted(old)
            if new.get(faction) != old[faction]
        ]
        transport = None
        if event["action"]["kind"] == "transit":
            route = next(
                (p for p in world.dynamics.passages
                 if p.key == event["action"]["key"]), None)
            if route is None:
                raise ValueError("native transport action missing from authored world")
            transport = {
                "key": route.key, "mode": route.mode, "name": route.name,
                "source": before["scene"], "destination": after["scene"],
                "cost_turns": route.cost_turns,
                "author_direction_required": True,
                "cinematic_performance_verified": False,
            }
        living_events = {
            "new_world_flags": sorted(
                set(next_state.get("world_flags", []))
                - set(previous_state.get("world_flags", []))),
            "standing_changes": effects,
            "inventory_spent": sorted(
                set(before.get("acquired", [])) - set(after.get("acquired", []))),
            "transport": transport,
        }
        society_before = previous_state.get("society")
        society_after = next_state.get("society")
        if society_before is not None or society_after is not None:
            if not isinstance(society_before, dict) or not isinstance(society_after, dict):
                raise ValueError("society presentation lost its persistent NPC ledger")
            trust_before = dict(society_before.get("relationships", []))
            trust_after = dict(society_after.get("relationships", []))
            if set(trust_before) != set(trust_after):
                raise ValueError("society actor roster drift in recorded cinematic delta")
            npc_changes = [{
                "resident": npc, "before": trust_before[npc],
                "after": trust_after[npc],
                "delta": trust_after[npc] - trust_before[npc],
            } for npc in sorted(trust_before)
                if trust_before[npc] != trust_after[npc]]
            old_stock = {(shop, item): amount for shop, item, amount
                         in society_before.get("shop_stock", [])}
            changed_stock = [{
                "shop": shop, "good": item,
                "before": old_stock[(shop, item)], "after": amount,
            } for shop, item, amount in society_after.get("shop_stock", [])
                if old_stock[(shop, item)] != amount]
            living_events["society"] = {
                "wallet_before": society_before["balance"],
                "wallet_after": society_after["balance"],
                "wallet_delta": society_after["balance"] - society_before["balance"],
                "NPC_trust_changes": npc_changes,
                "merchant_stock_changes": changed_stock,
                "action": event["action"]["kind"] + ":" + event["action"]["key"],
                "has_original_model_generated_dialogue": False,
                "authoritative_action_journal_verified": True,
            }
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
        **({"living_world_events": living_events} if world.dynamics is not None else {}),
        "native_cinematic_rendering_verified": False,
        "voice_or_music_playback_verified": False,
    }
