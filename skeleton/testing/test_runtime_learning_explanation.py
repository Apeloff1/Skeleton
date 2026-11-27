"""Operational predictor explanations remain bounded, advisory and scope-bound."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math

import pytest

from skeleton.contracts import runtime_learning_core as learning
from skeleton.contracts.ai_execution import AIExecutionRequest, AIExecutionResult, ExecutionState
from skeleton.persistence.execution_repository import SQLiteExecutionRepository


def _request(index: int, instant: datetime) -> AIExecutionRequest:
    return AIExecutionRequest(
        operation_id=f"explanation-op-{index}", execution_id=f"explanation-exec-{index}",
        objective="Inspect the authored gameplay evidence.",
        context_policy={"tenant_id": "explanation-tenant", "capability": "assistant.chat",
                        "provider_selection": "resident-explicit-model",
                        "source_snapshot": [{"source_id": "project:reference", "digest": "a" * 64}]},
        tool_policy={}, resource_budget={"max_model_turns": 2, "max_tool_calls": 0},
        stop_policy={"max_turns": 2}, created_at=instant - timedelta(seconds=1),
    )


@pytest.fixture
def learned_repository():
    """Use real committed terminal outcomes, not fabricated persisted optimizer rows."""
    repo = SQLiteExecutionRepository()
    instant = datetime.now(timezone.utc)
    repo.set_runtime_learning_policy(
        tenant_id="explanation-tenant", expected_version=1,
        policy={"min_samples": 4, "uncertainty_ceiling": 0.75, "replay_steps": 0},
        now=instant,
    )
    outcomes = set()
    for index in range(24):
        request = _request(index, instant)
        current = repo.create(request, now=request.created_at)
        for state in (ExecutionState.LOADING, ExecutionState.ASSEMBLING_CONTEXT,
                      ExecutionState.ROUTING, ExecutionState.PROVIDER_PENDING,
                      ExecutionState.PROVIDER_COMPLETED, ExecutionState.VERIFYING):
            current = repo.transition(request.execution_id, state,
                                      expected_version=current.version, now=instant)
        result = AIExecutionResult(
            operation_id=request.operation_id, execution_id=request.execution_id,
            status="completed", final_output="artifact:explicit-test-fixture",
            usage={}, completed_at=instant,
        )
        repo.finalize(result, expected_execution_version=current.version, now=instant)
        outcomes.add(learning.terminal_observation(request, result)["outcome_id"])
    try:
        yield repo, _request(99, instant), outcomes
    finally:
        repo.close()


def test_local_derivatives_match_numeric_predictor_without_mutating_state():
    state = learning.new_state("finite-difference-explanation")
    before = deepcopy(state)
    features = [0.2 + index * 0.03 for index in range(12)]
    policy = learning.normalize_policy()
    projection = learning._prediction_explanation(
        state, policy, features, basis="current_request", source_snapshot_digest="b" * 64,
    )
    assert state == before
    assert projection["advisory_only"] is True
    assert projection["method"] == "analytic_local_partial_derivative"
    assert len(learning.canonical(projection).encode()) <= learning.MAX_EXPLANATION_BYTES
    assert projection["explanation_digest"] == learning.digest(
        {key: value for key, value in projection.items() if key != "explanation_digest"}
    )
    epsilon = 1e-6
    for output_index, output in enumerate(projection["outputs"]):
        assert len(output["top_features"]) == 4
        for feature in output["top_features"]:
            column = feature["feature_index"]
            lower, upper = list(features), list(features)
            lower[column] -= epsilon
            upper[column] += epsilon
            numeric = (learning._forward(state["weights"], upper)[-1][output_index]
                       - learning._forward(state["weights"], lower)[-1][output_index]) / (2 * epsilon)
            assert math.isfinite(feature["local_sensitivity"])
            assert feature["local_sensitivity"] == pytest.approx(numeric, rel=1e-5, abs=1e-8)


def test_nonempty_sqlite_snapshot_binds_retained_explanation_to_committed_state(learned_repository):
    repo, request, outcomes = learned_repository
    snapshot = repo.runtime_learning_snapshot(tenant_id="explanation-tenant")
    assert len(snapshot["partitions"]) == 1
    partition = snapshot["partitions"][0]
    assert partition["readiness"] == "ready"
    projection = partition["reference_explanation"]
    assert projection["basis"] == "retained_numeric_replay"
    assert projection["sample_outcome_id"] in outcomes
    assert projection["requested_source_snapshot_digest"] is None
    binding = projection["binding"]
    assert binding["tenant_id"] == "explanation-tenant"
    assert binding["state_version"] == partition["state_version"] == 24
    assert binding["partition_id"] == partition["partition_id"]
    assert binding["model_selection_digest"] == learning.runtime_learning_identity(request)["model_selection_digest"]
    assert binding["learning_policy_version"] == 2
    assert binding["learning_policy_digest"] == projection["policy_digest"]
    assert len(learning.canonical(projection).encode()) <= learning.MAX_EXPLANATION_BYTES
    assert projection["explanation_digest"] == learning.digest(
        {key: value for key, value in projection.items() if key != "explanation_digest"}
    )
    assert repo.runtime_learning_snapshot(tenant_id="another-tenant")["partitions"] == []


def test_current_request_projection_cannot_widen_execution_authority(learned_repository):
    repo, request, _outcomes = learned_repository
    advice = repo.runtime_learning_recommendation(
        tenant_id="explanation-tenant", request=request, allowed_rounds=1, requested_rounds=3,
    )
    assert advice["readiness"] == "ready"
    assert advice["recommended_rounds"] <= 1
    assert advice["authority"] == {
        "model_selection": "unchanged", "resource_grants": "unchanged", "verification": "unchanged",
    }
    projection = advice["explanation"]
    assert projection["basis"] == "current_request"
    assert projection["sample_outcome_id"] is None and projection["sample_digest"] is None
    assert projection["requested_source_snapshot_digest"] == advice["source_snapshot_digest"]
    assert projection["input_digest"] == learning.digest({
        "feature_schema": learning.FEATURE_SCHEMA,
        "features": learning.request_features(request, requested_rounds=3),
    })


def test_failed_optional_projection_leaves_recommendation_and_readiness_unchanged(learned_repository, monkeypatch):
    repo, request, _outcomes = learned_repository
    def advice():
        return repo.runtime_learning_recommendation(
            tenant_id="explanation-tenant", request=request, allowed_rounds=2, requested_rounds=2,
        )
    baseline = advice()
    def failed_projection(*_args, **_kwargs):
        raise learning.RuntimeLearningError("projection intentionally unavailable")
    monkeypatch.setattr(learning, "_prediction_explanation", failed_projection)
    unavailable = advice()
    # Evidence age advances between reads; all operational decisions remain equal.
    assert unavailable["freshness"]["observed_age_seconds"] >= baseline["freshness"]["observed_age_seconds"]
    baseline["freshness"].pop("observed_age_seconds")
    unavailable["freshness"].pop("observed_age_seconds")
    assert unavailable == {**baseline, "explanation": None}
    snapshot = repo.runtime_learning_snapshot(tenant_id="explanation-tenant")
    assert snapshot["partitions"][0]["readiness"] == "ready"
    assert snapshot["partitions"][0]["reference_explanation"] is None


def test_cold_optimizer_does_not_gain_readiness_from_explanation_request():
    policy = learning.normalize_policy()
    state = learning.new_state("cold-explanation")
    ordinary = learning.state_readiness(state, policy, observed_age_seconds=0)
    projected = learning.state_readiness(state, policy, observed_age_seconds=0,
                                         include_reference_explanation=True)
    assert projected == {**ordinary, "reference_explanation": None}
    assert projected["readiness"] == "cold_start"
    with pytest.raises(learning.RuntimeLearningError, match="must be boolean"):
        learning.state_readiness(state, policy, include_reference_explanation=1)
