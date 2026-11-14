"""Public Jeeves game-quality catalog must never execute a model."""
from __future__ import annotations

from backend.routes.skeleton_gameforge import jeeves_game_quality_catalog
from skeleton.eval.game_builder_quality import TASKS, TASKSET_ID, taskset_digest


def test_public_quality_catalog_is_source_bound_and_never_runs_inference():
    result = jeeves_game_quality_catalog()
    assert result["schema"] == "skeleton.jeeves.game_quality.catalog.v1"
    assert result["task_count"] == len(TASKS) == 24
    assert result["taskset_id"] == TASKSET_ID
    assert result["taskset_sha256"] == taskset_digest()
    assert result["model_quality_certified"] is False
    assert result["inference_started"] is False
    assert result["local_gguf_required_for_run"] is True
    assert set(result["dimensions"]) == {"structure", "requirements", "correctness"}
