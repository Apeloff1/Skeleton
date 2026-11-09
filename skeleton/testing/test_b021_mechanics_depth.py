"""B021 deepen tests — determinism + mechanics depth."""

from __future__ import annotations

import pytest

from skeleton.game.mechanics_depth import (
    BehaviorFSM,
    CombatEngine,
    EconomySim,
    ProgressionLadder,
    SeededEntropy,
    TickClock,
)
from skeleton.game.replay_depth import BatchReplayer, EvidenceBundle, compare_digests


def test_tick_clock_monotonic():
    c = TickClock()
    assert c.advance() == 1
    assert c.advance(3) == 4


def test_seeded_entropy_stable():
    a = list(SeededEntropy(42).stream(20))
    b = list(SeededEntropy(42).stream(20))
    assert a == b
    assert list(SeededEntropy(43).stream(20)) != a


def test_combat_duel_deterministic():
    def run():
        e = CombatEngine(99)
        e.spawn("x", hp=90, atk=14, defense=2, crit=0.1)
        e.spawn("y", hp=90, atk=13, defense=3, crit=0.05)
        return e.duel("x", "y")
    r1, r2 = run(), run()
    assert r1.digest == r2.digest
    assert len(r1.frames) == len(r2.frames)


def test_economy_transfer_and_digest():
    eco = EconomySim(7)
    eco.open("a", 500)
    eco.open("b", 0)
    eco.transfer("a", "b", 50)
    d1 = eco.replay_digest()
    eco2 = EconomySim(7)
    eco2.open("a", 500)
    eco2.open("b", 0)
    eco2.transfer("a", "b", 50)
    assert eco2.replay_digest() == d1
    snap = eco.snapshot()
    assert ("b", 50) in snap.balances


def test_progression_level_up():
    p = ProgressionLadder(3)
    p.enroll("hero")
    ev = p.award("hero", 500)
    assert ev.level_after >= ev.level_before
    q = ProgressionLadder(3)
    q.enroll("hero")
    q.award("hero", 500)
    assert p.digest() == q.digest()


def test_fsm_transitions_deterministic():
    def run():
        f = BehaviorFSM(11)
        f.add_state("idle", 0.2, 0.8)
        f.add_state("hunt", 0.9, 0.1)
        f.link("idle", "hunt")
        f.link("hunt", "idle")
        for s in (0.2, 0.7, 0.4, 0.95):
            f.step(s)
        return f.digest()
    assert run() == run()


def test_batch_replayer_combat_stable():
    r1 = BatchReplayer(123).run_combat_batch(12)
    r2 = BatchReplayer(123).run_combat_batch(12)
    assert r1.bundle_digest == r2.bundle_digest
    assert r1.ok and len(r1.digests) == 12


def test_batch_replayer_mixed():
    r = BatchReplayer(5).run_mixed(6)
    assert r.ok and len(r.digests) == 6


def test_evidence_bundle_compare():
    b1 = EvidenceBundle("b021", 1, ("a" * 64,), {"n": 1})
    # force valid hex digests
    d = b1.digest()
    b2 = EvidenceBundle("b021", 1, ("a" * 64,), {"n": 1})
    assert b1.verify_pair(b2)["ok"] is True
    assert compare_digests(d, d)["ok"] is True


def test_combat_rejects_self_strike():
    e = CombatEngine(1)
    e.spawn("a")
    with pytest.raises(ValueError):
        e.strike("a", "a")


def test_economy_rejects_overdraft():
    eco = EconomySim(1)
    eco.open("a", 10)
    with pytest.raises(ValueError):
        eco.transact("a", -20)
