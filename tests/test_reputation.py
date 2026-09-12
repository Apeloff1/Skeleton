"""Reputation deed ledger — port of gameforge-rs reputation.rs."""

from __future__ import annotations

import math

import pytest

from skeleton.agents.reputation import (
    DEED_CAP,
    Deed,
    DeedKind,
    Reputation,
    ReputationError,
    ReputationScore,
    ReputationTable,
)


@pytest.fixture()
def rep() -> Reputation:
    return Reputation()


def test_deed_kind_base_deltas():
    assert DeedKind.SERVICE.base_delta() == 0.15
    assert DeedKind.DISTINCTION.base_delta() == 0.45
    assert DeedKind.LAPSE.base_delta() == -0.35
    assert DeedKind.TREASON.base_delta() == -1.6


def test_record_service_raises_standing(rep: Reputation):
    deed = rep.record("alice", DeedKind.SERVICE, 1.0)
    assert isinstance(deed, Deed)
    assert deed.actor == "alice"
    assert deed.kind is DeedKind.SERVICE
    assert deed.weight == 1.0
    standing = rep.standing("alice")
    assert standing == pytest.approx(math.tanh(0.15 / 4.0))
    assert 0.0 < standing < 1.0


def test_distinction_stronger_than_service(rep: Reputation):
    rep.record("bob", DeedKind.SERVICE, 1.0)
    rep.record("cara", DeedKind.DISTINCTION, 1.0)
    assert rep.standing("cara") > rep.standing("bob")


def test_lapse_and_treason_lower_standing(rep: Reputation):
    rep.record("dan", DeedKind.SERVICE, 1.0)
    before = rep.standing("dan")
    rep.record("dan", DeedKind.LAPSE, 1.0)
    after_lapse = rep.standing("dan")
    assert after_lapse < before
    rep.record("dan", DeedKind.TREASON, 1.0)
    after_treason = rep.standing("dan")
    assert after_treason < after_lapse
    assert after_treason < 0.0


def test_weight_clamped_to_unit_interval(rep: Reputation):
    over = rep.record("eve", DeedKind.SERVICE, 2.5)
    under = rep.record("eve", DeedKind.LAPSE, -0.5)
    assert over.weight == 1.0
    assert under.weight == 0.0
    # zero-weight lapse is a no-op on standing contribution
    only_service = Reputation()
    only_service.record("eve", DeedKind.SERVICE, 1.0)
    assert rep.standing("eve") == pytest.approx(only_service.standing("eve"))


def test_standing_unknown_actor_is_neutral(rep: Reputation):
    assert rep.standing("ghost") == 0.0


def test_ledger_of_newest_first(rep: Reputation):
    clock = {"t": 1_000.0}

    def tick() -> float:
        clock["t"] += 1.0
        return clock["t"]

    ledger = Reputation(clock=tick)
    ledger.record("frank", DeedKind.SERVICE, 0.5)
    ledger.record("frank", DeedKind.DISTINCTION, 0.8)
    ledger.record("frank", DeedKind.LAPSE, 0.2)
    rows = ledger.ledger_of("frank", limit=2)
    assert len(rows) == 2
    assert rows[0].kind is DeedKind.LAPSE
    assert rows[1].kind is DeedKind.DISTINCTION
    assert ledger.ledger_of("nobody") == []


def test_roll_good_and_bad_counts(rep: Reputation):
    rep.record("gina", DeedKind.SERVICE, 1.0)
    rep.record("gina", DeedKind.DISTINCTION, 1.0)
    rep.record("gina", DeedKind.LAPSE, 1.0)
    rep.record("hank", DeedKind.TREASON, 1.0)
    roll = rep.roll()
    assert roll["gina"] == {"good": 2, "bad": 1}
    assert roll["hank"] == {"good": 0, "bad": 1}


def test_deed_cap_drains_oldest_quarter(rep: Reputation):
    # Fill to cap then one more triggers drain of DEED_CAP // 4
    for i in range(DEED_CAP):
        rep.record("crowd", DeedKind.SERVICE, 0.01)
    assert len(rep.ledger_of("crowd", limit=DEED_CAP + 10)) == DEED_CAP
    rep.record("crowd", DeedKind.DISTINCTION, 1.0)
    remaining = len(rep.ledger_of("crowd", limit=DEED_CAP + 10))
    expected = DEED_CAP - (DEED_CAP // 4) + 1
    assert remaining == expected


def test_standing_decays_with_age():
    # Fresh deed vs ancient deed — ancient contributes near-zero
    fresh = Reputation(clock=lambda: 0.0)
    fresh.record("ivy", DeedKind.DISTINCTION, 1.0)
    fresh_standing = fresh.standing("ivy")

    ancient = Reputation(clock=lambda: 0.0)
    ancient.record("ivy", DeedKind.DISTINCTION, 1.0)
    # Re-bind clock to ~two half-lives later (~180 days)
    ancient._now = lambda: 180.0 * 86400.0
    aged = ancient.standing("ivy")
    assert aged < fresh_standing
    assert aged == pytest.approx(
        math.tanh((0.45 * (0.5 ** (180.0 / 90.0))) / 4.0)
    )


# ---------------------------------------------------------------------------
# Legacy ReputationTable — extend-only, callers must keep working
# ---------------------------------------------------------------------------


def test_legacy_table_score_unchanged():
    table = ReputationTable()
    table.record("router-agent", success=True)
    table.record("router-agent", success=True)
    table.record("router-agent", success=False)
    assert table.score("router-agent") == pytest.approx(2 / 3)
    snap = table.snapshot()
    assert snap["router-agent"] == pytest.approx(2 / 3)
    with pytest.raises(ReputationError, match="unknown agent"):
        table.score("missing")


def test_legacy_reputation_score_dataclass():
    rec = ReputationScore(successes=1, attempts=2)
    assert rec.score() == 0.5
    empty = ReputationScore()
    assert empty.score() == 0.0
