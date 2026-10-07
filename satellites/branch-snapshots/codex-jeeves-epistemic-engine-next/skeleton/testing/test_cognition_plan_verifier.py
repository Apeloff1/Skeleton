"""Cognition log-odds / schisms + PlanVerifier feed."""
from __future__ import annotations

import math

from skeleton.intelligence.cognition import CONVICTION, WITNESS_STEP, Cognition
from skeleton.intelligence.plan_verifier import PlanVerifier


def _clock_at(t: float):
    return lambda: t


def _convict(cog: Cognition, predicate: str, polarity: bool, *, prefix: str = "w") -> str:
    """Drive a belief past conviction with two independent witnesses (weight=1)."""
    bid = cog.hold(predicate, polarity)
    # one perfect witness → lodds=1.2 → conf≈0.769 < 0.8
    cog.testify(bid, f"{prefix}0", True, 1.0)
    # second independent witness → lodds=2.4 → conf≈0.917 ≥ 0.8
    cog.testify(bid, f"{prefix}1", True, 1.0)
    b = cog.belief(bid)
    assert b is not None
    assert b.confidence() >= 0.5 + CONVICTION
    return bid


def test_testify_moves_confidence_in_log_odds_single_witness_bounded():
    cog = Cognition(clock=_clock_at(1_700_000_000.0))
    bid = cog.hold("terrain.north.passable", True)
    conf = cog.testify(bid, "scout", True, 1.0)
    assert conf is not None
    b = cog.belief(bid)
    assert b is not None
    assert abs(b.lodds - WITNESS_STEP) < 1e-9
    expected = 1.0 / (1.0 + math.exp(-WITNESS_STEP))
    assert abs(conf - expected) < 1e-9
    # same witness again — diminishing voice; still far from extreme clamp (±8)
    cog.testify(bid, "scout", True, 1.0)
    b2 = cog.belief(bid)
    assert b2 is not None
    # step2 = 1.2 * (1/2) = 0.6 → lodds = 1.8
    assert abs(b2.lodds - (WITNESS_STEP + WITNESS_STEP / 2.0)) < 1e-9
    assert abs(b2.lodds) < 8.0
    # one witness cannot alone pin lodds at the clamp
    assert b2.confidence() < 0.95


def test_scan_schism_detects_both_polarities_at_conviction():
    cog = Cognition(clock=_clock_at(1_700_000_000.0))
    _convict(cog, "era.extraction", True, prefix="pro")
    assert cog.schisms() == []
    _convict(cog, "era.extraction", False, prefix="con")
    schisms = cog.schisms()
    assert len(schisms) == 1
    assert schisms[0].predicate == "era.extraction"
    assert schisms[0].supporting
    assert schisms[0].refuting


def test_resolve_schism_clears_losing_polarity():
    cog = Cognition(clock=_clock_at(1_700_000_000.0))
    win_id = _convict(cog, "room.arena", True, prefix="a")
    lose_id = _convict(cog, "room.arena", False, prefix="b")
    assert len(cog.schisms()) == 1
    assert cog.resolve_schism("room.arena", True) is True
    assert cog.schisms() == []
    loser = cog.belief(lose_id)
    winner = cog.belief(win_id)
    assert loser is not None and loser.lodds == 0.0
    assert winner is not None and winner.lodds != 0.0
    assert cog.resolve_schism("room.arena", True) is False


def test_plan_verifier_with_cognition_rejects_schism_plan():
    cog = Cognition(clock=_clock_at(1_700_000_000.0))
    # Pre-seed opposing convictions so plan claim opens/surfaces a schism.
    _convict(cog, "era.extraction", True, prefix="seed_t")
    _convict(cog, "era.extraction", False, prefix="seed_f")
    assert len(cog.schisms()) == 1

    verifier = PlanVerifier(accept_at=0.5, cognition=cog)
    report = verifier.verify(
        {
            "era": "extraction",
            "title": "Extraction Ops",
            "room_bias": "pressure",
            "primary_dps": 120.0,
            "claims": [
                {"predicate": "era.extraction", "polarity": True},
            ],
        },
        vision="extraction pressure",
    )
    assert not report.accepted
    assert any(i.startswith("hard: schism on predicate era.extraction") for i in report.issues)
    assert report.summary["hard_issues"] >= 1


def test_plan_verifier_without_cognition_unchanged_on_minimal_plan():
    plan = {
        "era": "soulslike",
        "title": "Elden Ring",
        "room_bias": "pressure labyrinth",
        "primary_dps": 144.0,
    }
    vision = "like Elden Ring pressure labyrinth"
    baseline = PlanVerifier(accept_at=0.7).verify(plan, vision=vision)
    with_none = PlanVerifier(accept_at=0.7, cognition=None).verify(plan, vision=vision)
    assert baseline.accepted == with_none.accepted
    assert baseline.reason == with_none.reason
    assert baseline.score == with_none.score
    assert baseline.issues == with_none.issues
    assert baseline.accepted is True


def test_ingest_claim_returns_open_schisms_for_predicate():
    cog = Cognition(clock=_clock_at(1_700_000_000.0))
    verifier = PlanVerifier(cognition=cog)
    _convict(cog, "npc.hostile", True, prefix="yes")
    opened = []
    # Drive opposing polarity via ingest_claim (two witnesses).
    opened = verifier.ingest_claim("npc.hostile", False, "spy0", True, 1.0)
    assert opened == []  # not yet at conviction
    opened = verifier.ingest_claim("npc.hostile", False, "spy1", True, 1.0)
    assert len(opened) == 1
    assert opened[0].predicate == "npc.hostile"
