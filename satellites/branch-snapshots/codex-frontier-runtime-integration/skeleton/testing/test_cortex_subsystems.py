"""Smoke tests for the cortex subsystems exercised only via the neo path.

Callosum, sleep consolidation, REINFORCE, and the MoE expert bank are all
reachable through JeevesCortex but had no direct coverage. These tests pin
their core contracts against the real implementations so drift surfaces
in CI instead of in a running organism.
"""

from __future__ import annotations

from skeleton.cortex.callosum import CorpusCallosum, energy
from skeleton.cortex.moe import ExpertBank
from skeleton.cortex.rl import ReinforceState, reinforce_mix
from skeleton.cortex.sleep import SleepCycle
from skeleton.cortex.heads import NumericHead
from skeleton.cortex.port import Thought


# ── Corpus callosum ──────────────────────────────────────────────────────

def test_callosum_fuse_returns_dim_sized_streams():
    cc = CorpusCallosum(dim=8)
    fused, left, right = cc.fuse([0.1] * 8)
    assert len(left) == 8 and len(right) == 8
    assert len(fused) == 8
    assert cc.fires == 1


def test_callosum_hebb_moves_coupling_energy():
    cc = CorpusCallosum(dim=8)
    delta = cc.hebb([0.5] * 8, lr=0.1)
    assert delta != 0.0            # co-firing changed the coupling matrix
    assert cc.hebbs == 1


def test_callosum_snapshot_roundtrip():
    cc = CorpusCallosum(dim=8, seed=7)
    cc.fuse([0.2] * 8)
    cc.hebb([0.3] * 8)
    restored = CorpusCallosum.from_snapshot(cc.snapshot())
    assert restored.fires == cc.fires and restored.hebbs == cc.hebbs
    assert restored.C == cc.C      # the learned coupling survives


def test_callosum_seq_fusion_handles_multi_token():
    cc = CorpusCallosum(dim=8)
    seq = [[0.1 * i] * 8 for i in range(1, 4)]
    fused, fused_l, fused_r = cc.fuse_seq(seq)
    assert len(fused) == 8
    assert cc.seq_fires == 1


# ── MoE expert bank ──────────────────────────────────────────────────────

def test_moe_forward_gates_sum_to_one():
    bank = ExpertBank(dim=8)
    mixed, gates = bank.forward([0.1] * 8)
    assert abs(sum(gates) - 1.0) < 1e-6
    assert len(mixed) == 8
    assert bank.forwards == 1


def test_moe_acquire_stamps_expert():
    bank = ExpertBank(dim=8)
    assert bank.acquire("left") == 1
    assert bank.acquire("left") == 2
    assert bank.acquire("nope") == 0
    assert bank.experts["left"].acquired == 2


def test_moe_predicts_none_until_heads_fitted():
    bank = ExpertBank(dim=8)
    # heads need MIN_FITTED steps before predicting
    assert bank.predict_mix([0.1] * 8) is None
    assert bank.predict_veto([0.1] * 8) is None


def test_moe_fingerprint_stable_and_sensitive():
    a, b = ExpertBank(dim=8, seed=19), ExpertBank(dim=8, seed=19)
    assert a.fingerprint() == b.fingerprint()      # same seed → same guts
    a.acquire("left")
    a.router.credit(0, lr=0.02)
    assert a.fingerprint() != b.fingerprint()      # learning moves the merkle


# ── REINFORCE ────────────────────────────────────────────────────────────

def test_reinforce_positive_advantage_steps_toward_action():
    head = NumericHead(dim=8)
    state = ReinforceState(baseline=0.0)
    info = reinforce_mix(head, [0.1] * 8, (4, 2, 1), reward=1.0, state=state)
    assert info["toward"] == "action"
    assert state.wins == 1 and state.trials == 1
    assert info["adv"] > 0


def test_reinforce_negative_advantage_stays():
    head = NumericHead(dim=8)
    state = ReinforceState(baseline=1.0)
    info = reinforce_mix(head, [0.1] * 8, (4, 2, 1), reward=0.0, state=state)
    assert info["toward"] == "stay"
    assert state.wins == 0


def test_reinforce_baseline_converges_to_reward():
    head = NumericHead(dim=8)
    state = ReinforceState(alpha=0.5, baseline=0.0)
    for _ in range(10):
        reinforce_mix(head, [0.1] * 8, (2, 2, 2), reward=1.0, state=state)
    assert state.baseline > 0.9


def test_reinforce_snapshot_roundtrip():
    state = ReinforceState()
    state.steps = 5
    state.wins = 3
    restored = ReinforceState.from_snapshot(state.snapshot())
    assert restored.steps == 5 and restored.wins == 3


# ── Sleep consolidation ──────────────────────────────────────────────────

def test_sleep_record_tracks_cofire():
    sc = SleepCycle()
    left = Thought(slot="left", kind="x", text="t", confidence=0.8,
                   numbers=(4.0, 2.0, 1.0))
    right = Thought(slot="right", kind="x", text="bias=balanced",
                    confidence=0.7, tags=("balanced",))
    sc.record("stim", [0.1] * 8, left=left, right=right)
    assert sc.hebb["left:right"] == 1.0
    assert len(sc.buffer) == 1


def test_sleep_consolidate_empty_buffer_is_noop():
    sc = SleepCycle()
    out = sc.consolidate(object())   # neo stand-in: no attrs needed
    assert out["replays"] == 0


def test_sleep_prune_drops_low_confidence():
    sc = SleepCycle()
    sc.record("weak", [0.0] * 8)                        # conf = 0.0
    dropped = sc.prune(min_conf=0.35)
    assert dropped == 1 and len(sc.buffer) == 0
    assert sc.pruned == 1


def test_sleep_snapshot_roundtrip():
    sc = SleepCycle()
    sc.record("stim", [0.1] * 8)
    sc.cycles = 2
    restored = SleepCycle()
    n = restored.restore(sc.snapshot())
    assert n == 1 and restored.cycles == 2
