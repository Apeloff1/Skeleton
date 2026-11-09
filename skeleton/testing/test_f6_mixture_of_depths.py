"""F-6: Mixture-of-depths for the neo transformer (skip / shallow / deep).

MoD is a sibling of MoE — these tests also pin that moe.py still imports
cleanly and ExpertBank still routes experts, not depths.
"""
from __future__ import annotations

from skeleton.cortex.mod import (
    DEEP,
    SHALLOW,
    SKIP,
    DepthRouter,
    MixtureOfDepths,
    allocate_depths,
)
from skeleton.cortex.moe import ExpertBank
from skeleton.cortex.transformer import TinyTransformer, TransformerBlock
import random


def test_allocate_depths_respects_capacity_bands():
    # 8 tokens, 25% deep + 25% shallow → 2 deep, 2 shallow, 4 skip
    scores = [0.1, 0.9, 0.2, 0.8, 0.3, 0.7, 0.4, 0.6]
    depths = allocate_depths(scores, deep_capacity=0.25, shallow_capacity=0.25)
    assert depths.count(DEEP) == 2
    assert depths.count(SHALLOW) == 2
    assert depths.count(SKIP) == 4
    # Highest scores take deep
    assert depths[1] == DEEP and depths[3] == DEEP
    # Next band shallow
    assert depths[5] == SHALLOW and depths[7] == SHALLOW


def test_allocate_depths_deterministic_tie_break():
    scores = [1.0, 1.0, 1.0, 1.0]
    a = allocate_depths(scores, deep_capacity=0.25, shallow_capacity=0.25)
    b = allocate_depths(scores, deep_capacity=0.25, shallow_capacity=0.25)
    assert a == b == [DEEP, SHALLOW, SKIP, SKIP]


def test_depth_router_seeded_scores_stable():
    X = [[0.1 * (i + 1)] * 8 for i in range(4)]
    r1 = DepthRouter(8, seed=23, deep_capacity=0.5, shallow_capacity=0.25)
    r2 = DepthRouter(8, seed=23, deep_capacity=0.5, shallow_capacity=0.25)
    assert r1.score(X) == r2.score(X)
    assert r1.decide(X) == r2.decide(X)


def test_injectable_decide_fn_forces_all_three_depths():
    block = TransformerBlock(8, 16, random.Random(0), 0.08)
    # Non-constant hiddens — LayerNorm zeros a flat vector.
    X = [
        [0.5, -0.2, 0.1, 0.0, -0.4, 0.3, 0.2, -0.1],
        [0.1, 0.4, -0.3, 0.2, 0.0, -0.5, 0.6, 0.1],
        [-0.2, 0.3, 0.5, -0.1, 0.4, 0.0, -0.3, 0.2],
    ]

    def forced(_X):
        return [SKIP, SHALLOW, DEEP]

    mod = MixtureOfDepths(8, seed=1, decide_fn=forced)
    Y, cache = mod.forward_block(block, X, n_heads=1)
    assert cache["depths"] == [SKIP, SHALLOW, DEEP]
    assert Y[0] == X[0]  # skip = identity
    assert Y[1] != X[1]  # shallow moved the residual
    assert Y[2] != X[2]  # deep moved the residual
    # Shallow != deep for the same token when FFN is live
    Y_only_shallow, _ = MixtureOfDepths(8, decide_fn=lambda _X: [SHALLOW] * 3).forward_block(block, X, 1)
    Y_only_deep, _ = MixtureOfDepths(8, decide_fn=lambda _X: [DEEP] * 3).forward_block(block, X, 1)
    assert Y_only_shallow[1] != Y_only_deep[1]
    assert mod.tokens_skip == 1 and mod.tokens_shallow == 1 and mod.tokens_deep == 1


def test_all_skip_is_identity():
    block = TransformerBlock(8, 16, random.Random(1), 0.08)
    X = [[0.2, -0.1, 0.0, 0.3, 0.1, -0.2, 0.4, 0.0]]
    mod = MixtureOfDepths(8, decide_fn=lambda _X: [SKIP] * len(_X))
    Y, cache = mod.forward_block(block, X, n_heads=1)
    assert Y == X
    assert cache["depths"] == [SKIP]


def test_forward_shallow_skips_ffn():
    rng = random.Random(2)
    block = TransformerBlock(8, 16, rng, 0.08)
    X = [[0.1] * 8, [0.2] * 8]
    Y_s, cache_s = block.forward_shallow(X, n_heads=1)
    assert cache_s.get("shallow") is True
    assert cache_s.get("z") == []
    assert len(Y_s) == 2
    Y_d, cache_d = block.forward(X, n_heads=1)
    assert cache_d.get("z")  # deep path ran FFN
    # Shallow output equals attn residual U from deep cache
    assert Y_s == cache_d["U"]


def test_tiny_transformer_use_mod_flag():
    vocab = ["a", "b", "c", "d"]
    lm = TinyTransformer(vocab, dim=8, ctx=4, seed=3, n_layers=2, d_ff=16, use_mod=True,
                         mod_deep=0.5, mod_shallow=0.25)
    assert lm.use_mod and lm.mod is not None
    H = lm.hidden_seq("a b c")
    assert len(H) >= 1 and len(H[-1]) == 8
    st = lm.mod.stats()
    assert st["tokens_seen"] > 0
    assert st["tokens_skip"] + st["tokens_shallow"] + st["tokens_deep"] == st["tokens_seen"]


def test_tiny_transformer_without_mod_unchanged_path():
    vocab = ["a", "b", "c"]
    lm = TinyTransformer(vocab, dim=8, ctx=4, seed=4, n_layers=1, d_ff=8)
    assert lm.use_mod is False and lm.mod is None
    # still runs
    assert len(lm.hidden("a b")) == 8


def test_mod_snapshot_roundtrip():
    mod = MixtureOfDepths(8, seed=9, deep_capacity=0.5, shallow_capacity=0.25)
    mod.forwards = 2
    mod.tokens_deep = 3
    restored = MixtureOfDepths.from_snapshot(mod.snapshot())
    assert restored.router.deep_capacity == 0.5
    assert restored.forwards == 2 and restored.tokens_deep == 3
    assert restored.router.w == mod.router.w


def test_moe_still_imports_and_routes_experts():
    """Regression: MoD must not break or alias MoE."""
    bank = ExpertBank(dim=8, seed=19)
    mixed, gates = bank.forward([0.1] * 8)
    assert abs(sum(gates) - 1.0) < 1e-6
    assert len(mixed) == 8
    # MoE has experts, not depths
    assert set(bank.experts) >= {"left", "right", "pfc", "midbrain"}
