"""Deterministic coverage for residual-norm mixture-of-depths routing."""
from __future__ import annotations

import math

import pytest

from skeleton.cortex.mixture_depth import MixtureOfDepths
from skeleton.cortex.transformer import TinyTransformer


def _model(*, layers: int = 4) -> TinyTransformer:
    return TinyTransformer(
        vocab=("alpha", "beta", "gamma", "delta"),
        dim=8,
        ctx=6,
        seed=17,
        n_heads=2,
        n_layers=layers,
        d_ff=12,
    )


def _ids(model: TinyTransformer):
    return [model._id(token) for token in ("alpha", "beta", "gamma", "delta")]


def test_disabled_router_is_exact_full_depth_path() -> None:
    model = _model()
    ids = _ids(model)
    expected, _ = model._forward(ids)

    router = MixtureOfDepths(model, enabled=False)
    actual = router.forward_ids(ids)

    assert actual == expected
    assert router.metrics()["token_depths"] == [4, 4, 4, 4]
    assert router.metrics()["estimated_block_savings"] == 0.0


def test_all_easy_tokens_exit_at_minimum_depth_with_fixed_shape() -> None:
    model = _model()
    ids = _ids(model)
    router = MixtureOfDepths(model, threshold=float("inf"), min_depth=2)

    hidden = router.forward_ids(ids)
    metrics = router.metrics()
    logits = router.logits_ids(ids)

    assert len(hidden) == len(ids)
    assert all(len(row) == model.dim for row in hidden)
    assert len(logits) == model.V
    assert all(math.isfinite(value) for row in hidden for value in row)
    assert all(math.isfinite(value) for value in logits)
    assert metrics["token_depths"] == [2, 2, 2, 2]
    assert metrics["mean_depth"] == 2.0
    assert metrics["layer_token_fraction"] == pytest.approx(0.5)
    assert metrics["estimated_block_savings"] == pytest.approx(0.5)


def test_all_hard_tokens_reach_full_depth() -> None:
    model = _model()
    ids = _ids(model)
    router = MixtureOfDepths(model, threshold=-1.0, min_depth=1)

    actual = router.forward_ids(ids)
    expected, _ = model._forward(ids)
    metrics = router.metrics()

    assert actual == expected
    assert metrics["token_depths"] == [4, 4, 4, 4]
    assert metrics["active_token_updates"] == metrics["full_token_updates"]
    assert metrics["estimated_block_savings"] == 0.0


def test_selective_layer_freezes_exited_tokens_without_changing_active_queries() -> None:
    model = _model(layers=2)
    ids = _ids(model)
    hidden = model._encode(ids)
    layer = model.layers[0]
    full, _ = layer.forward([list(row) for row in hidden], model.n_heads)
    router = MixtureOfDepths(model, threshold=0.0)

    selective = router._selective_layer(layer, hidden, active=(2, 3))

    # Exited positions stay byte-for-byte frozen.
    assert selective[0] == hidden[0]
    assert selective[1] == hidden[1]
    # Active queries still see the same causal K/V bank and therefore produce
    # exactly the same update as the original full-sequence block.
    assert selective[2] == full[2]
    assert selective[3] == full[3]


def test_threshold_schedule_and_metrics_are_deterministic() -> None:
    model = _model(layers=3)
    ids = _ids(model)
    router = MixtureOfDepths(model, threshold=(-1.0, float("inf"), float("inf")))

    first = router.forward_ids(ids)
    first_metrics = router.metrics()
    second = router.forward_ids(ids)
    second_metrics = router.metrics()

    assert first == second
    assert first_metrics == second_metrics
    assert first_metrics["token_depths"] == [2, 2, 2, 2]
    assert first_metrics["p50_depth"] == 2.0
    assert first_metrics["p90_depth"] == 2.0
    assert first_metrics["p95_depth"] == 2.0


def test_short_schedule_holds_its_last_threshold() -> None:
    model = _model(layers=4)
    ids = _ids(model)
    router = MixtureOfDepths(model, threshold=(-1.0, float("inf")), min_depth=3)

    router.forward_ids(ids)

    assert router.metrics()["token_depths"] == [3, 3, 3, 3]


def test_metrics_are_copy_safe() -> None:
    model = _model()
    router = MixtureOfDepths(model, threshold=float("inf"), min_depth=2)
    router.forward_ids(_ids(model))

    first = router.metrics()
    first["token_depths"].append(999)

    assert router.metrics()["token_depths"] == [2, 2, 2, 2]


def test_invalid_configuration_fails_fast() -> None:
    model = _model()

    with pytest.raises(ValueError, match="cannot be empty"):
        MixtureOfDepths(model, threshold=())
    with pytest.raises(ValueError, match="cannot contain NaN"):
        MixtureOfDepths(model, threshold=(0.1, float("nan")))
    with pytest.raises(ValueError, match="min_depth"):
        MixtureOfDepths(model, min_depth=0)
    with pytest.raises(ValueError, match="min_depth"):
        MixtureOfDepths(model, min_depth=model.n_layers + 1)


def test_configuration_rejects_lossy_or_ambiguous_coercions() -> None:
    model = _model()

    with pytest.raises(TypeError, match="enabled"):
        MixtureOfDepths(model, enabled="false")
    with pytest.raises(TypeError, match="min_depth"):
        MixtureOfDepths(model, min_depth=1.9)
    with pytest.raises(TypeError, match="min_depth"):
        MixtureOfDepths(model, min_depth=True)
    with pytest.raises(TypeError, match="threshold"):
        MixtureOfDepths(model, threshold=True)
    with pytest.raises(TypeError, match="threshold"):
        MixtureOfDepths(model, threshold="0.1")
    with pytest.raises(TypeError, match="only real numbers"):
        MixtureOfDepths(model, threshold=(0.1, "0.2"))
