"""Enriched original consumer preview: consequence-shaped story and optional wins.

Adds completed, independently replayed narrative ending witnesses to the
validated source package. Product signatures cover new artifacts; the
existing mirror is not misrepresented as a hardware/copyright audit.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from .contracts import canonical_digest, canonical_json
from .quest_scene_engine import DirectorWorld, DirectorError
from .quest_director_studio import DirectorStudioProduct, build_director_studio
from .quest_director_solver import solve_quest
from .quest_director_endings import evaluate_story_ending


def _pack(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def build_earned_story_product(
    world: DirectorWorld, *, authorized: bool,
    mirror_attempts: int = 128,
) -> DirectorStudioProduct:
    if not authorized:
        raise PermissionError("consumer game source enrichment needs operator approval")
    base = build_director_studio(
        world, authorized=True, mirror_attempts=mirror_attempts,
    )
    main = next(q for q in world.quests if q.scope == "main")
    candidate_replays = {
        name: solve_quest(world, main.key, strategy=name, authorized=True)
        for name in ("ordinary", "balanced", "creative")
    }
    optional = solve_quest(
        world, main.key, strategy="creative", optional=True, authorized=True,
    )
    results = {
        name: evaluate_story_ending(
            world, proof.replay, authorized=True,
        ).payload() for name, proof in candidate_replays.items()
    }
    perfected = evaluate_story_ending(world, optional.replay, authorized=True)
    if len({v["earned_ending"] for v in results.values()}) < 2:
        raise DirectorError("main storyline endings did not vary with actually performed choices")
    if len({v["invariant_original_goal"] for v in results.values()}) != 1:
        raise DirectorError("player methods illegally rewrote the canonical main goal")
    new_files = dict(base.files)
    new_files.pop("release.json")
    new_files["game/earned_story_endings.json"] = _pack({
        "schema": "skeleton.game_builder.original_earned_endings.v1",
        "world_digest": world.digest,
        "player_method_endings": results,
        "optional_complete": perfected.payload(),
        "optional_solution_replay_digest": optional.replay.digest,
        "original_goal_preserved": True,
        "unsupported_endings_are_not_automatically_unlocked": True,
        "human_narrative_quality_approved": False,
    })
    new_manifest = {
        **{k: v for k, v in base.manifest.items() if k != "manifest_digest"},
        "has_earned_ending_receipts": True,
        "files": {
            name: sha256(data).hexdigest()
            for name, data in sorted(new_files.items())
        },
    }
    new_manifest["manifest_digest"] = canonical_digest(new_manifest)
    new_files["release.json"] = _pack(new_manifest)
    return replace(base, files=new_files, manifest=new_manifest)


__all__ = ["build_earned_story_product"]
