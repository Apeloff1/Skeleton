"""Verified original-game vertical slice from archived B028/B030/B037."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .constraint_quest_synthesis import ContentPolicy, WorldModel, synthesize_quest
from .genre_template_composition import (
    CompositionError, PackRegistry, compose_slice, verify_slice,
)
from .quest_objective_runtime import QuestDefinition, QuestError, run_quest

SCHEMA = "skeleton.game_builder.verified_original_slice.v1"


class SliceBuildError(ValueError):
    """An invalid or unproven game-creation slice is not publishable."""


def _digest(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def compose_verified_quest_slice(
    registry: PackRegistry,
    pack_ids: Sequence[str],
    *,
    slice_id: str,
    world: WorldModel,
    policy: ContentPolicy,
    seed: int,
    quest_length: int = 3,
    quest_title: str = "An Original Adventure",
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compose and prove the abstract objective sequence, not native Godot play."""
    if not isinstance(slice_id, str) or not slice_id or len(slice_id) > 128:
        raise SliceBuildError("invalid slice ID")
    if not isinstance(pack_ids, Sequence) or isinstance(pack_ids, (str, bytes)):
        raise SliceBuildError("pack_ids must be a bounded sequence")
    if not 1 <= len(pack_ids) <= 64:
        raise SliceBuildError("slice must include one to 64 mechanic packs")
    if not isinstance(world, WorldModel) or not isinstance(policy, ContentPolicy):
        raise SliceBuildError("world and content policy must be validated models")
    if not isinstance(quest_title, str) or not 1 <= len(quest_title) <= 256:
        raise SliceBuildError("invalid quest title")
    if overrides is not None and (not isinstance(overrides, Mapping) or len(overrides) > 64):
        raise SliceBuildError("invalid pack overrides")

    try:
        composition = compose_slice(registry, slice_id, pack_ids, overrides=overrides)
        if "quests" not in composition["capabilities"]:
            raise SliceBuildError("a quest-capable mechanic pack is required")
        if not verify_slice(registry, composition):
            raise SliceBuildError("mechanic-pack integrity verification failed")
        generated = synthesize_quest(
            world, policy, seed=seed, length=quest_length, title=quest_title,
        )
        if not generated.get("accepted"):
            raise SliceBuildError("quest synthesis failed all acceptance constraints")
        raw = generated["quest"]
        definition = QuestDefinition.from_mapping({
            "id": slice_id + ".quest",
            "objectives": [{
                "id": step["id"],
                "requires": list(step.get("requires", ())),
                "target": 1,
                "rewards": list(step.get("rewards", ())),
            } for step in raw["steps"]],
        })
        proof = run_quest(definition, [
            {"advance": step["id"]} for step in raw["steps"]
        ])
        if proof["status"] != "completed":
            raise SliceBuildError("objective progression never reaches completion")
    except (CompositionError, QuestError, KeyError, TypeError, IndexError) as exc:
        raise SliceBuildError("invalid composition, quest, or proof") from exc

    body = {
        "schema": SCHEMA,
        "slice_id": slice_id,
        "mechanics": composition,
        "world_quest": generated,
        "quest_definition": definition.to_mapping(),
        "quest_definition_digest": definition.digest,
        "proof": {
            "status": proof["status"],
            "rewards": proof["rewards"],
            "snapshot": proof["snapshot"],
        },
    }
    return {**body, "digest": _digest(body)}


def verify_original_slice(
    artifact: Mapping[str, Any],
    registry: PackRegistry,
) -> bool:
    """Verify source and mechanic references before using an archived slice."""
    try:
        if not isinstance(artifact, Mapping) or artifact.get("schema") != SCHEMA:
            return False
        if _digest({k: v for k, v in artifact.items() if k != "digest"}) != artifact["digest"]:
            return False
        if not verify_slice(registry, artifact["mechanics"]):
            return False
        definition = QuestDefinition.from_mapping(artifact["quest_definition"])
        if definition.digest != artifact["quest_definition_digest"]:
            return False
        return artifact["proof"]["status"] == "completed"
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


__all__ = ["SCHEMA", "SliceBuildError", "compose_verified_quest_slice", "verify_original_slice"]
