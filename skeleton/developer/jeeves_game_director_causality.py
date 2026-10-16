"""Causality and continuity receipts over *actual* Director player decisions.

Every event is independently applied to the immutable authored world and
checked against the persisted journal. The lore/quest/NPC matrices distinguish
hard runtime invariants from artistic judgments requiring a human reviewer.
Reading the ledger never changes gameplay, model weights, or reviewed canon.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from skeleton.ai.game_builder.quest_scene_engine import (
    DirectorAction, available_director_actions, director_initial, director_step,
)
from skeleton.developer.jeeves_game_director_session import (
    _hash, _load, _read_doc,
)

SCHEMA = "skeleton.jeeves.director_causality.v1"


def audit(root: Path, *, session: str, page: int = 1,
          page_size: int = 100) -> dict[str, Any]:
    if type(page) is not int or page < 1:
        raise ValueError("causal journal page must be a positive integer")
    if type(page_size) is not int or not 1 <= page_size <= 500:
        raise ValueError("causal evidence page-size must be 1..500")
    folder, world, final, source, head, count = _load(root, name=session)
    quest_lookup = {quest.key: quest for quest in world.quests}
    scenes = {scene.key: scene for scene in world.scenes}
    visible_from = (page - 1) * page_size + 1
    visible_to = visible_from + page_size - 1
    state = director_initial(world)
    evidence = []
    methods = Counter()
    actors = Counter()
    scene_visits = Counter({state.scene: 1})
    completed_at = {}
    flags_created_at = {}
    causal_edges = []
    invariant_warnings = []
    action_totals = Counter()
    for index in range(1, count + 1):
        recorded = _read_doc(folder / f"{index:08d}.json")
        action = DirectorAction(**recorded["action"])
        if action not in available_director_actions(world, state):
            raise ValueError("persisted story contains an action unavailable in its causal past")
        previous = state
        state = director_step(world, state, action)
        if (recorded["before_sha256"] != previous.digest
                or recorded["after_sha256"] != state.digest):
            raise ValueError("causal replay contradicts historical Director state")
        if state.turn <= previous.turn or not set(previous.complete).issubset(state.complete):
            raise ValueError("time reversal or erased completed canonical quest")
        if not set(previous.narrative_flags).issubset(state.narrative_flags):
            raise ValueError("authoritative consequences disappeared from story history")
        if not set(previous.results).issubset(state.results):
            raise ValueError("previous narrative result disappeared")
        before_results = {(r.quest, r.stage) for r in previous.results}
        fresh = [r for r in state.results if (r.quest, r.stage) not in before_results]
        new_flags = sorted(set(state.narrative_flags) - set(previous.narrative_flags))
        new_complete = sorted(set(state.complete) - set(previous.complete))
        if action.kind == "travel":
            scene_visits[state.scene] += 1
        here = scenes[state.scene]
        for actor in here.cast:
            actors[actor] += 1
        action_totals[action.kind] += 1
        for result in fresh:
            quest = quest_lookup[result.quest]
            stage = next((item for item in quest.stages if item.key == result.stage), None)
            if stage is None or result.approach not in {item.key for item in stage.solutions}:
                raise ValueError("recorded narrative method absent from original story canon")
            method = next(item for item in stage.solutions if item.key == result.approach)
            if quest.requires_quests and not set(quest.requires_quests).issubset(previous.complete):
                raise ValueError("story progressed before required predecessor quest")
            expected_flag = quest.key + "_" + method.outcome_flag
            if result.consequence != expected_flag or method.outcome_flag not in state.narrative_flags:
                raise ValueError("canonical ending/consequence was not preserved")
            if result.turns < 1 or result.score < 0:
                raise ValueError("canonical story score or time is invalid")
            label = (result.quest, result.stage)
            if label in completed_at:
                raise ValueError("stage completed more than once in original history")
            completed_at[label] = index
            methods[result.approach] += 1
            for predecessor in quest.requires_quests:
                if predecessor not in completed_at and predecessor not in previous.complete:
                    raise ValueError("unverified prerequisite at narrative transition")
                causal_edges.append({
                    "from_quest": predecessor, "to_quest": quest.key,
                    "at_sequence": index, "reason": "explicit_requires_quests",
                })
        for flag in new_flags:
            flags_created_at.setdefault(flag, index)
        if visible_from <= index <= visible_to:
            evidence.append({
                "sequence": index, "action": action.payload(),
                "scene_before": previous.scene, "scene_after": state.scene,
                "turn_before": previous.turn, "turn_after": state.turn,
                "state_before_sha256": previous.digest, "state_after_sha256": state.digest,
                "action_receipt_sha256": recorded["receipt_sha256"],
                "new_stage_results": [r.payload() for r in fresh],
                "new_consequence_flags": new_flags, "newly_completed_quests": new_complete,
                "inventory_gained": sorted(set(state.acquired) - set(previous.acquired)),
                "inventory_consumed": sorted(set(previous.acquired) - set(state.acquired)),
                "cast_present_after_action": list(here.cast),
            })
    if state != final:
        raise ValueError("causal report end differs from independently verified journal")
    _, current_world, current, current_source, current_head, current_count = _load(root, name=session)
    if (current_world.digest != world.digest or current != final
            or current_source["source_sha256"] != source["source_sha256"]
            or current_head != head or current_count != count):
        raise ValueError("game history changed during continuity scrutiny")
    unfinished = [
        {"quest": q.key, "next_stage": q.stages[dict(state.stage_index)[q.key]].key,
         "blocked_by": sorted(set(q.requires_quests) - set(state.complete))}
        for q in world.quests if dict(state.stage_index)[q.key] < len(q.stages)
    ]
    summary = {
        "project": world.project_id, "source_sha256": source["source_sha256"],
        "world_sha256": world.digest,
        "session": session, "journal_head_sha256": head,
        "actions_replayed": count, "end_state_sha256": state.digest,
        "quest_stage_count": sum(len(q.stages) for q in world.quests),
        "stages_completed": len(completed_at),
        "quest_completion_count": len(state.complete),
        "consequence_flags_created_at": dict(sorted(flags_created_at.items())),
        "action_kinds": dict(sorted(action_totals.items())),
        "approach_counts": dict(sorted(methods.items())),
        "visited_scene_counts": dict(sorted(scene_visits.items())),
        "cast_encounter_counts": dict(sorted(actors.items())),
        "causal_prerequisite_edges": causal_edges,
        "unresolved_quest_stages": unfinished,
        "authored_canonical_facts": list(world.bible.canonical_facts),
        "contradictions_in_typed_canonical_replay": invariant_warnings,
        "complete_campaign_logic": len(state.complete) == len(world.quests),
        "literary_voice_independently_reviewed": False,
        "npc_behavior_and_dialogue_quality_proven": False,
        "real_native_story_playthrough_verified": False,
    }
    return {
        "ok": True, "action": "director-causality", "schema": SCHEMA,
        "summary": summary, "summary_sha256": _hash(summary),
        "page": page, "page_size": page_size,
        "total_events": count, "has_next_page": visible_to < count,
        "events": evidence,
        "recorded_causal_replay_verified": True,
        "model_or_player_preferences_inferred": False,
    }


def contrast(root: Path, *, first: str, second: str) -> dict[str, Any]:
    """Compare two exact-source branches without conflating receipts with story."""
    first_report = audit(root, session=first, page_size=1)
    second_report = audit(root, session=second, page_size=1)
    a, b = first_report["summary"], second_report["summary"]
    if a["world_sha256"] != b["world_sha256"] or a["source_sha256"] != b["source_sha256"]:
        raise ValueError("storyline comparison needs identical approved game source")
    left_folder, _, _, _, _, left_count = _load(root, name=first)
    right_folder, _, _, _, _, right_count = _load(root, name=second)
    first_different = None
    for i in range(1, max(left_count, right_count) + 1):
        if i > left_count or i > right_count:
            first_different = i
            break
        left = _read_doc(left_folder / f"{i:08d}.json")
        right = _read_doc(right_folder / f"{i:08d}.json")
        if left["action"] != right["action"]:
            first_different = i
            break
    # End receipts differ for forked sessions even with identical actions;
    # compare *story causality* and replayed states, not session IDs.
    a_flags = set(a["consequence_flags_created_at"])
    b_flags = set(b["consequence_flags_created_at"])
    a_quests = {(x["quest"], x["next_stage"]) for x in a["unresolved_quest_stages"]}
    b_quests = {(x["quest"], x["next_stage"]) for x in b["unresolved_quest_stages"]}
    return {
        "ok": True, "action": "director-story-contrast", "schema": SCHEMA,
        "first": first, "second": second, "world_sha256": a["world_sha256"],
        "first_head_sha256": a["journal_head_sha256"],
        "second_head_sha256": b["journal_head_sha256"],
        "first_different_action_sequence": first_different,
        "flags_unique_to_first": sorted(a_flags - b_flags),
        "flags_unique_to_second": sorted(b_flags - a_flags),
        "unresolved_stages_unique_to_first": sorted([list(x) for x in a_quests - b_quests]),
        "unresolved_stages_unique_to_second": sorted([list(x) for x in b_quests - a_quests]),
        "causal_evidence_sha256": _hash({
            "first": a["journal_head_sha256"], "second": b["journal_head_sha256"],
            "left_summary": first_report["summary_sha256"],
            "right_summary": second_report["summary_sha256"],
        }),
        "canon_story_differences_observed": bool(a_flags != b_flags or a_quests != b_quests),
        "visual_engine_ending_verified": False,
    }
