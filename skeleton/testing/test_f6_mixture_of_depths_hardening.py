"""Hardening coverage for F-6 Mixture-of-Depths."""
from __future__ import annotations

import random

from skeleton.cortex.mod import DEEP, SHALLOW, SKIP, DepthRouter, MixtureOfDepths, allocate_depths
from skeleton.cortex.transformer import TinyTransformer, TransformerBlock


def _sample_hidden():
    return [
        [0.5, -0.2, 0.1, 0.0, -0.4, 0.3, 0.2, -0.1],
        [0.1, 0.4, -0.3, 0.2, 0.0, -0.5, 0.6, 0.1],
        [-0.2, 0.3, 0.5, -0.1, 0.4, 0.0, -0.3, 0.2],
        [0.7, -0.1, 0.0, -0.4, 0.2, 0.3, -0.2, 0.1],
    ]


def test_capacity_clamps_and_short_sequences_get_positive_budget():
    assert allocate_depths([1.0], deep_capacity=-5.0, shallow_capacity=-1.0) == [SKIP]
    assert allocate_depths([1.0], deep_capacity=0.25, shallow_capacity=0.0) == [DEEP]
    depths = allocate_depths([0.1, 0.9], deep_capacity=4.0, shallow_capacity=4.0)
    assert depths == [DEEP, DEEP]


def test_zero_capacity_survives_router_snapshot_roundtrip():
    router = DepthRouter(8, deep_capacity=0.0, shallow_capacity=0.0)
    restored = DepthRouter.from_snapshot(router.snapshot())
    assert restored.deep_capacity == 0.0
    assert restored.shallow_capacity == 0.0
    assert restored.decide(_sample_hidden()) == [SKIP] * 4


def test_selective_ffn_matches_full_block_on_deep_token():
    block = TransformerBlock(8, 16, random.Random(7), 0.08)
    X = _sample_hidden()
    full, full_cache = block.forward(X, 1)
    mod = MixtureOfDepths(8, decide_fn=lambda _x: [SKIP, SHALLOW, DEEP, SKIP])
    routed, cache = mod.forward_block(block, X, 1)

    assert routed[0] == X[0]
    assert routed[1] == full_cache["U"][1]
    assert routed[2] == full[2]
    assert cache["depths"] == [SKIP, SHALLOW, DEEP, SKIP]
    stats = mod.stats()
    assert stats["ffn_token_evals"] == 1
    assert stats["attention_token_evals"] == len(X)


def test_all_skip_backward_is_identity_and_does_not_require_attention_cache():
    block = TransformerBlock(8, 16, random.Random(8), 0.08)
    X = _sample_hidden()
    mod = MixtureOfDepths(8, decide_fn=lambda xs: [SKIP] * len(xs))
    Y, cache = mod.forward_block(block, X, 1)
    grad = [[0.1 * (i + 1)] * 8 for i in range(len(X))]
    back = block.backward([list(g) for g in grad], cache, 0.01)
    assert Y == X
    assert back == grad
    assert mod.stats()["attention_token_evals"] == 0
    assert mod.stats()["ffn_token_evals"] == 0


def test_mixed_backward_routes_without_shape_loss():
    block = TransformerBlock(8, 16, random.Random(9), 0.08)
    X = _sample_hidden()
    mod = MixtureOfDepths(8, decide_fn=lambda _x: [SKIP, SHALLOW, DEEP, SKIP])
    _Y, cache = mod.forward_block(block, X, 1)
    grad = [[0.05] * 8 for _ in X]
    back = block.backward(grad, cache, 0.001)
    assert len(back) == len(X)
    assert all(len(row) == 8 for row in back)
    assert all(all(value == value for value in row) for row in back)  # no NaNs


def test_tiny_transformer_can_train_with_all_skip_mod_route():
    lm = TinyTransformer(
        ["a", "b", "c"],
        dim=8,
        ctx=4,
        seed=10,
        n_layers=2,
        d_ff=16,
        use_mod=True,
        mod_deep=0.0,
        mod_shallow=0.0,
    )
    assert lm.mod is not None
    lm.mod.decide_fn = lambda xs: [SKIP] * len(xs)
    updates = lm.fit(["a b c"], lr=0.001)
    assert updates == 2
    assert lm.steps == 2
    assert lm.mod.tokens_skip > 0


def test_mod_snapshot_preserves_compute_counters_and_zero_capacities():
    mod = MixtureOfDepths(8, deep_capacity=0.0, shallow_capacity=0.0)
    mod.forward_block(
        TransformerBlock(8, 16, random.Random(11), 0.08),
        _sample_hidden(),
        1,
    )
    restored = MixtureOfDepths.from_snapshot(mod.snapshot())
    assert restored.router.deep_capacity == 0.0
    assert restored.router.shallow_capacity == 0.0
    assert restored.tokens_seen == mod.tokens_seen
    assert restored.attention_token_evals == 0
    assert restored.ffn_token_evals == 0
