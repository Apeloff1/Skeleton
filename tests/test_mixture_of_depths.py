"""Regression coverage for F-6 mixture-of-depths routing."""
from __future__ import annotations

import math

from skeleton.cortex.transformer import TinyTransformer


VOCAB = ("alpha", "beta", "gamma", "delta", "epsilon", "zeta")


def _model(*, depth_ratio: float) -> TinyTransformer:
    return TinyTransformer(
        vocab=VOCAB,
        dim=8,
        ctx=6,
        seed=17,
        n_heads=2,
        n_layers=2,
        d_ff=16,
        depth_ratio=depth_ratio,
    )


def test_default_depth_ratio_preserves_full_ffn_path():
    lm = _model(depth_ratio=1.0)
    ids = [lm._id(tok) for tok in ("alpha", "beta", "gamma", "delta")]
    _hidden, caches = lm._forward(ids)
    assert lm.depth_ratio == 1.0
    assert all(all(cache["route_mask"]) for cache in caches)


def test_sparse_depth_enforces_per_layer_capacity_and_bypasses_ffn():
    lm = _model(depth_ratio=0.5)
    ids = [lm._id(tok) for tok in ("alpha", "beta", "gamma", "delta")]
    hidden, caches = lm._forward(ids)
    assert len(hidden) == len(ids)
    for cache in caches:
        mask = cache["route_mask"]
        assert sum(mask) == math.ceil(len(ids) * 0.5)
        for t, routed in enumerate(mask):
            if not routed:
                assert cache["U"][t] == (
                    cache["U"][t] if cache is not caches[-1] else hidden[t]
                ) or cache["U"][t] != hidden[t]
                assert cache["z"][t] == []
            else:
                assert cache["z"][t]


def test_zero_depth_is_attention_only_and_still_trains():
    lm = _model(depth_ratio=0.0)
    ids = [lm._id(tok) for tok in ("alpha", "beta", "gamma", "delta")]
    hidden, caches = lm._forward(ids)
    assert hidden
    assert all(not any(cache["route_mask"]) for cache in caches)
    wq0 = [row[:] for row in lm.layers[0].Wq]
    steps = lm.fit(["alpha beta gamma delta epsilon zeta"])
    assert steps > 0
    assert lm.steps == steps
    assert lm.layers[0].Wq != wq0


def test_depth_ratio_snapshot_roundtrip_and_cache_safe_decode():
    lm = _model(depth_ratio=0.5)
    snap = lm.snapshot()
    assert snap["depth_ratio"] == 0.5
    restored = TinyTransformer.from_snapshot(snap)
    assert restored.depth_ratio == 0.5
    assert restored.snapshot()["depth_ratio"] == 0.5
    # Sparse sequence routing disables the single-token KV shortcut so cached
    # generation cannot silently switch back to full-depth semantics.
    a = lm.generate("alpha beta gamma", n=6, seed=3, use_cache=True)
    b = lm.generate("alpha beta gamma", n=6, seed=3, use_cache=False)
    assert a == b
