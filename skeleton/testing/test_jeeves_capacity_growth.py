"""Prove real Jeeves Torch FFN growth without weakening the serving boundary."""
from __future__ import annotations

from copy import deepcopy
import json
import pytest

from skeleton.ai.training.jeeves_capacity_growth import (
    CapacityGrowthError, PROFILE_FACTORS, growth_plan,
    grow_feedforward, parameter_count,
)


def _torch_checkpoint():
    torch = pytest.importorskip("torch")
    from skeleton.cortex.torch_lm import TorchTransformer
    model = TorchTransformer(
        vocab=["alpha", "beta", "gamma", "delta", "epsilon", "world"],
        dim=8, ctx=8, n_heads=2, n_layers=2, d_ff=16, device="cpu")
    model.fit(["alpha beta gamma delta epsilon world"], lr=0.005)
    return torch, model


def test_five_growth_profiles_have_real_parameter_arithmetic():
    torch, model = _torch_checkpoint()
    before = parameter_count(model)
    for name in PROFILE_FACTORS:
        plan = growth_plan(model, name)
        assert plan["existing_trainable_parameters"] == before
        assert plan["projected_trainable_parameters"] == before + plan["new_trainable_parameters"]
        assert plan["new_trainable_parameters"] == (
            plan["new_neurons_per_layer"] * (2*model.dim+1)*model.n_layers)
    assert growth_plan(model, "xlarge")["new_trainable_parameters"] > (
        growth_plan(model, "balanced")["new_trainable_parameters"] > 0)


def test_growth_preserves_parent_output_and_embeds_real_new_weights():
    torch, parent = _torch_checkpoint()
    state = deepcopy(parent.snapshot())
    before = parameter_count(parent)
    enlarged, receipt = grow_feedforward(
        parent, profile="balanced", max_added_parameters=5000)
    assert parent.snapshot() == state  # serving-derived candidate unmodified
    assert receipt["growth_candidate_only"]
    assert receipt["trainable_parameter_count_verified"]
    assert receipt["logit_equivalence_max_abs_diff"] <= receipt["logit_equivalence_tolerance"]
    assert receipt["weights_trained_by_growth"] is False
    assert enlarged.d_ff > parent.d_ff
    assert enlarged.itos == parent.itos and enlarged.steps == parent.steps
    assert parameter_count(enlarged) == before + receipt["new_trainable_parameters"]
    assert enlarged.snapshot()["state"]["enc.layers.0.linear1.weight"][:parent.d_ff] == (
        state["state"]["enc.layers.0.linear1.weight"])
    original_cols = enlarged.snapshot()["state"]["enc.layers.0.linear2.weight"]
    assert all(all(value == 0 for value in row[parent.d_ff:]) for row in original_cols)


def test_newly_added_neurons_receive_real_sgd_updates():
    torch, parent = _torch_checkpoint()
    candidate, receipt = grow_feedforward(
        parent, profile="large", max_added_parameters=5000)
    added_before = torch.tensor(candidate.snapshot()["state"]["enc.layers.0.linear2.weight"])
    start = candidate.steps
    updates = candidate.fit(["alpha beta gamma delta epsilon world"], lr=0.01)
    assert updates > 0 and candidate.steps == start + updates
    added_after = torch.tensor(candidate.snapshot()["state"]["enc.layers.0.linear2.weight"])
    assert not torch.equal(added_before[:, parent.d_ff:], added_after[:, parent.d_ff:])
    assert receipt["weights_trained_by_growth"] is False  # growth itself is not SGD


def test_growth_rejects_unpinned_checkpoint_and_excess_parameter_count():
    _, parent = _torch_checkpoint()
    with pytest.raises(CapacityGrowthError, match="input hash differs"):
        grow_feedforward(parent, profile="micro", expected_snapshot_sha256="0"*64)
    with pytest.raises(CapacityGrowthError, match="operator budget"):
        grow_feedforward(parent, profile="xlarge", max_added_parameters=1)
    with pytest.raises(CapacityGrowthError, match="unsupported"):
        growth_plan(parent, "hallucinated_capacity")
    with pytest.raises(CapacityGrowthError, match="torch-stack"):
        growth_plan(object(), "balanced")


def test_no_growth_performs_no_sgd_and_does_not_clone_or_expand():
    _, parent = _torch_checkpoint()
    state = json.dumps(parent.snapshot(), sort_keys=True)
    candidate, receipt = grow_feedforward(parent, profile="none")
    assert candidate is parent
    assert json.dumps(parent.snapshot(), sort_keys=True) == state
    assert receipt["new_trainable_parameters"] == 0
    assert receipt["weights_trained_by_growth"] is False
