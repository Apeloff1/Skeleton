"""Explicit study-local tabular Q-policy learning from actual native game traces.

Uses the existing Jeeves GamePolicyLearner rather than an invented learning
model. Ten independent game domains produce ten separate isolated policy
snapshots; no attempts to merge incompatible emulator state spaces or update
production LLM weights. Caller must independently authorize source rights.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

MAX_STUDY_SNAPSHOT_BYTES = 2 * 1024 * 1024


class ComparativeShadowLearningError(ValueError):
    """Local policy training was not independently authorized or evidenced."""


def train_study_local_policy(
    *,
    spec: Any,
    trace: Mapping[str, Any],
    game_id: str,
    rights_evidence_digest: str,
    authorize: Callable[[], None],
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Actually update and checkpoint one Q-policy after a real native episode."""
    from .game_learning import GameLearningConfig, GamePolicyLearner
    from .game_learning_ingestion import _validate_trace

    if not callable(authorize):
        raise ComparativeShadowLearningError("Explicit authenticated study-local training authorization is required")
    authorize()
    source = _validate_trace(dict(trace))
    lineage = source["source_lineage"]
    if (lineage.get("runtime_kind") != "installed_libretro_emulator"
        or lineage.get("rights_evidence_digest") != rights_evidence_digest
        or not isinstance(rights_evidence_digest, str)
        or len(rights_evidence_digest) != 64):
        raise ComparativeShadowLearningError("Training trace lacks its exact declared source-rights receipt")
    if lineage.get("production_training_admitted") is not False:
        raise ComparativeShadowLearningError("Source cannot claim canonical production training approval")
    if not isinstance(game_id, str) or not game_id or len(game_id) > 64:
        raise ComparativeShadowLearningError("Study game identity is invalid")
    count = source["steps"]
    learner = GamePolicyLearner(
        spec,
        GameLearningConfig(
            seed=source["seed"],
            max_updates=max(1, count),
            max_episodes=1,
            max_states=min(512, max(32, count * 8)),
            trace_byte_limit=MAX_STUDY_SNAPSHOT_BYTES,
        ),
        policy_id="comparative-study:" + game_id,
        source_lineage=lineage,
    )
    before = learner.snapshot_digest
    completed = learner.train_offline(
        [source],
        authorize=authorize,
        cancel=cancelled,
    )
    snapshot = completed.snapshot
    payload = {
        "schema_version": "skeleton.game.comparative_local_tabular_training.v1",
        "algorithm": "existing_jeeves_episode_atomic_tabular_q_learning",
        "game_id": game_id,
        "training_episode_count": len(completed.episode_summaries),
        "real_verified_trace_sha256": source["trace_digest"],
        "updates_applied": completed.updates,
        "pretraining_policy_sha256": before,
        "trained_policy_sha256": snapshot["snapshot_digest"],
        "policy_snapshot": snapshot,
        "model_type": "isolated_per_game_tabular_q_policy",
        "human_rights_assertion_digest": rights_evidence_digest,
        "independent_license_review_completed": False,
        "validity_scope": "This game's exact approved native emulator/content/firmware/environment only",
        "cross_game_weights_combined": False,
        "large_language_model_parameters_changed": False,
        "shadow_weight_pipeline_promoted": False,
        "reusable_for_production_without_independent_review": False,
    }
    if len(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()) > MAX_STUDY_SNAPSHOT_BYTES:
        raise ComparativeShadowLearningError("Bounded local learning snapshot exceeds two MiB")
    return payload
