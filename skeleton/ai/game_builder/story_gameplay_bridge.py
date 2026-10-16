"""StoryCanon-to-playable-quest proof, using the actual original Director runtime.

This is a read-only cross-authority verification lens. It does not execute
external game binaries, alter signed story, approve media, or claim completion
of a full consumer game merely because a director stage replay succeeds.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json
import re
from typing import Any

from skeleton.ai.game_builder.story_canon_fabric import verify_story_history
from skeleton.ai.game_builder.quest_playthrough_journal import (
    SegmentedDirectorTrace, replay_director_segments,
)
from skeleton.ai.game_builder.quest_scene_engine import (
    DirectorWorld, DirectorAction, director_play, director_verify,
)

SCHEMA = "skeleton.jeeves.story_gameplay_binding.v1"
_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MAX_LINKS = 9999
MAX_REPLAYS = 64
MAX_ACTIONS_PER_REPLAY = 8192


class StoryGameBridgeError(ValueError):
    """Invalid canonical source, forged replay or unsupported gameplay claim."""


def _digest(data: object) -> str:
    return sha256(json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")).hexdigest()


def _id(value: Any, name: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise StoryGameBridgeError("invalid " + name)
    return value


def review_story_gameplay(
    bible: dict[str, Any], scenes: list[dict[str, Any]], world: DirectorWorld,
    replays: Any, bindings: Any, *, require_distinct_choices: bool = False,
) -> dict[str, Any]:
    """Replay real actions, bind only executed consequences to signed events.

    A binding is a source-to-gameplay QA claim; the author must still
    integrate any approved proposal into the actual game's production source.
    """
    if not isinstance(world, DirectorWorld):
        raise StoryGameBridgeError("typed original DirectorWorld required")
    history = verify_story_history(bible, scenes)
    if world.project_id != bible["project"]:
        raise StoryGameBridgeError("signed novel/game scene and DirectorWorld project identities disagree")
    if not isinstance(replays, list) or not 1 <= len(replays) <= MAX_REPLAYS:
        raise StoryGameBridgeError("require 1..64 named, bounded original action replays")
    if not isinstance(bindings, list) or not 1 <= len(bindings) <= MAX_LINKS:
        raise StoryGameBridgeError("require source-scene to playable quest bindings")
    if type(require_distinct_choices) is not bool:
        raise StoryGameBridgeError("branch divergence gate must be boolean")

    scene_anchors = {}
    for scene in scenes:
        anchors = set()
        for kind in ("events", "interactions", "dialogue", "beats"):
            anchors.update(part["id"] for part in scene[kind])
        scene_anchors[scene["sequence"]] = anchors

    played = {}
    for packet in replays:
        if not isinstance(packet, dict) or set(packet) not in (
            {"name", "actions"}, {"name", "segments"},
        ):
            raise StoryGameBridgeError(
                "replay requires name and real actions or linked segments"
            )
        name = _id(packet["name"], "replay name")
        if name in played:
            raise StoryGameBridgeError("duplicate named original gameplay replay")
        if "segments" in packet:
            replay = replay_director_segments(world, packet["segments"])
        else:
            steps = packet["actions"]
            if not isinstance(steps, list) or len(steps) > MAX_ACTIONS_PER_REPLAY:
                raise StoryGameBridgeError("replay segment exceeds bounded Director action budget")
            actions = []
            for item in steps:
                if not isinstance(item, dict) or set(item) != {"kind", "key", "scene"}:
                    raise StoryGameBridgeError("only original typed DirectorAction inputs are allowed")
                actions.append(DirectorAction(**item))
            replay = director_play(world, actions)
            director_verify(world, replay)
        results = {(x.quest, x.stage): x for x in replay.final.results}
        played[name] = (replay, results)

    quest_map = {q.key: q for q in world.quests}
    linked = []
    seen = set()
    observed_variants = defaultdict(set)
    for row in bindings:
        if not isinstance(row, dict) or set(row) != {
            "scene_sequence", "source_anchor", "replay", "quest", "stage",
            "approach", "consequence",
        }:
            raise StoryGameBridgeError("source-to-gameplay binding missing required evidence")
        sequence = row["scene_sequence"]
        if type(sequence) is not int or sequence not in scene_anchors:
            raise StoryGameBridgeError("gameplay binding references unsigned or absent story scene")
        source = _id(row["source_anchor"], "story event or beat")
        if source not in scene_anchors[sequence]:
            raise StoryGameBridgeError("gameplay binding lacks the exact signed scene anchor")
        replay_name = _id(row["replay"], "original replay")
        quest = _id(row["quest"], "original quest")
        stage = _id(row["stage"], "quest stage")
        approach = _id(row["approach"], "executed victory approach")
        consequence = _id(row["consequence"], "executed world consequence")
        if replay_name not in played:
            raise StoryGameBridgeError("gameplay binding refers to a missing replay")
        if quest not in quest_map or stage not in {s.key for s in quest_map[quest].stages}:
            raise StoryGameBridgeError("story consequence targets a nonexistent playable quest stage")
        result = played[replay_name][1].get((quest, stage))
        if result is None:
            raise StoryGameBridgeError("claimed story consequence has not actually been played")
        if result.approach != approach or result.consequence != consequence:
            raise StoryGameBridgeError("claimed player choice or ending does not match executed gameplay")
        key = (sequence, source, replay_name, quest, stage)
        if key in seen:
            raise StoryGameBridgeError("duplicate gameplay link cannot inflate narrative coverage")
        seen.add(key)
        observed_variants[(quest, stage)].add((result.approach, result.consequence))
        linked.append({
            "scene_sequence": sequence,
            "source_anchor": source,
            "signed_scene_sha256": scenes[sequence - 1]["digest"],
            "replay": replay_name,
            "director_replay_sha256": played[replay_name][0].digest,
            "quest": quest,
            "stage": stage,
            "approach": result.approach,
            "consequence": result.consequence,
            "score": result.score,
            "executed_in_canonical_director": True,
            "semantic_equivalence_to_literary_scene_independently_reviewed": False,
            "native_game_engine_or_complete_playthrough_verified": False,
        })
    if require_distinct_choices and not any(
        len(variants) >= 2 for variants in observed_variants.values()
    ):
        raise StoryGameBridgeError("branching story needs two genuinely distinct replayed consequences")
    source_coverage = {row["scene_sequence"] for row in linked}
    quest_stages = {(q.key, st.key) for q in world.quests for st in q.stages}
    executed_stages = {
        (result.quest, result.stage)
        for replay, _ in played.values() for result in replay.final.results
    }
    linked_stages = {(row["quest"], row["stage"]) for row in linked}
    unbound_source = sorted(set(scene_anchors) - source_coverage)
    unplayed = sorted(quest_stages - executed_stages)
    unused = sorted(executed_stages - linked_stages)
    return {
        "ok": True, "schema": SCHEMA, "action": "direction-gameplay",
        "project": world.project_id,
        "canonical_story_digest": history["digest"],
        "director_world_digest": world.digest,
        "replay_count": len(played),
        "real_actions_executed": sum(
            r.action_count if isinstance(r, SegmentedDirectorTrace) else len(r.actions)
            for r, _ in played.values()
        ),
        "replay_segment_receipts": {
            name: list(replay.segment_receipts)
            for name, (replay, _) in sorted(played.items())
            if isinstance(replay, SegmentedDirectorTrace)
        },
        "source_scenes_reparsed": len(scenes),
        "source_scenes_bound": len(source_coverage),
        "unbound_source_scene_sequences": unbound_source,
        "total_quest_stages": len(quest_stages),
        "quest_stages_executed": len(executed_stages),
        "unexecuted_quest_stages": [{"quest": q, "stage": s} for q, s in unplayed],
        "played_stages_not_bound_to_story": [
            {"quest": q, "stage": s} for q, s in unused
        ],
        "distinct_replayed_consequence_pairs": sum(
            len(x) for x in observed_variants.values()
        ),
        "binding_evidence": linked,
        "story_gameplay_coverage_complete": not unbound_source and not unplayed and not unused,
        "replay_evidence_sha256": _digest({
            "story": history["digest"], "world": world.digest,
            "replays": {name: replay.digest for name, (replay, _) in sorted(played.items())},
            "bindings": linked,
        }),
        "independent_human_story_approval_verified": False,
        "commercial_game_install_or_native_export_verified": False,
        "actual_full_game_playthrough_verified": False,
        "professional_narrative_quality_verified": False,
        "independent_story_to_quest_semantic_review_performed": False,
        "model_training_performed": False,
    }
