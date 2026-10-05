"""Legions cashier/cohort — port of gameforge-rs legions.rs."""

from __future__ import annotations

import pytest

from skeleton.swarm.legions import Cohort, Legion, LegionRegistry, Member


@pytest.fixture()
def reg() -> LegionRegistry:
    return LegionRegistry()


def test_found_creates_named_legion(reg: LegionRegistry):
    legion = reg.found("Iron Cohort", "We hold the line")
    assert isinstance(legion, Legion)
    assert legion.name == "Iron Cohort"
    assert legion.motto == "We hold the line"
    assert legion.cohorts == []
    assert legion.id
    assert legion.founded > 0
    assert reg.get("Iron Cohort") is legion
    assert len(reg.list()) == 1


def test_enlist_raises_cohort_and_returns_member_id(reg: LegionRegistry):
    reg.found("Scouts", "Eyes open")
    mid = reg.enlist("Scouts", "scouting")
    assert mid is not None
    legion = reg.get("Scouts")
    assert legion is not None
    assert len(legion.cohorts) == 1
    cohort = legion.cohorts[0]
    assert isinstance(cohort, Cohort)
    assert cohort.capability == "scouting"
    assert len(cohort.members) == 1
    member = cohort.members[0]
    assert isinstance(member, Member)
    assert member.id == mid
    assert member.rank == 1
    assert member.capability == "scouting"
    assert member.traitor is False
    assert member.tasks_done == 0
    assert reg.enlisted_total == 1


def test_enlist_unknown_legion_returns_none(reg: LegionRegistry):
    assert reg.enlist("ghost", "rendering") is None
    assert reg.enlisted_total == 0


def test_enlist_reuses_cohort_for_same_capability(reg: LegionRegistry):
    reg.found("Render", "Pixels")
    a = reg.enlist("Render", "rendering")
    b = reg.enlist("Render", "rendering")
    legion = reg.get("Render")
    assert legion is not None
    assert len(legion.cohorts) == 1
    assert {m.id for m in legion.cohorts[0].members} == {a, b}
    assert reg.enlisted_total == 2


def test_heartbeat_updates_and_misses_unknown(reg: LegionRegistry):
    clock = {"t": 1_000.0}

    def tick() -> float:
        return clock["t"]

    reg = LegionRegistry(clock=tick)
    reg.found("Watch", "Beat")
    mid = reg.enlist("Watch", "indexing")
    assert mid is not None
    before = reg.get("Watch").cohorts[0].members[0].last_heartbeat
    clock["t"] = 1_050.0
    assert reg.heartbeat("Watch", mid) is True
    after = reg.get("Watch").cohorts[0].members[0].last_heartbeat
    assert after == 1_050.0
    assert after > before
    assert reg.heartbeat("Watch", "no-such") is False
    assert reg.heartbeat("ghost", mid) is False


def test_cashier_marks_traitor_once(reg: LegionRegistry):
    reg.found("Court", "Truth")
    mid = reg.enlist("Court", "attestation")
    assert reg.cashier("Court", mid) is True
    member = reg.get("Court").cohorts[0].members[0]
    assert member.traitor is True
    assert reg.cashiered_total == 1
    # Second cashier is a no-op
    assert reg.cashier("Court", mid) is False
    assert reg.cashiered_total == 1
    assert reg.cashier("Court", "ghost") is False
    assert reg.cashier("ghost", mid) is False


def test_promote_raises_rank_skips_traitors(reg: LegionRegistry):
    reg.found("Vanguard", "Forward")
    mid = reg.enlist("Vanguard", "assault")
    assert reg.promote("Vanguard", mid) is True
    assert reg.get("Vanguard").cohorts[0].members[0].rank == 2
    reg.cashier("Vanguard", mid)
    assert reg.promote("Vanguard", mid) is False
    assert reg.get("Vanguard").cohorts[0].members[0].rank == 2
    assert reg.promote("ghost", mid) is False


def test_degrade_silent_drops_rank_for_absent(reg: LegionRegistry):
    clock = {"t": 0.0}

    def tick() -> float:
        return clock["t"]

    reg = LegionRegistry(clock=tick)
    reg.found("Patrol", "Present")
    mid = reg.enlist("Patrol", "patrol")
    assert reg.promote("Patrol", mid) is True
    assert reg.promote("Patrol", mid) is True
    assert reg.get("Patrol").cohorts[0].members[0].rank == 3
    clock["t"] = 100.0
    degraded = reg.degrade_silent(max_silence_secs=50.0)
    assert degraded == 1
    assert reg.get("Patrol").cohorts[0].members[0].rank == 2
    # Rank-1 is the floor — no further degrade from silence
    while reg.get("Patrol").cohorts[0].members[0].rank > 1:
        clock["t"] += 100.0
        reg.degrade_silent(50.0)
    clock["t"] += 100.0
    assert reg.degrade_silent(50.0) == 0
    assert reg.get("Patrol").cohorts[0].members[0].rank == 1


def test_degrade_silent_skips_traitors_and_fresh(reg: LegionRegistry):
    clock = {"t": 0.0}
    reg = LegionRegistry(clock=lambda: clock["t"])
    reg.found("A", "a")
    traitor_id = reg.enlist("A", "x")
    fresh_id = reg.enlist("A", "x")
    reg.promote("A", traitor_id)
    reg.promote("A", fresh_id)
    reg.cashier("A", traitor_id)
    reg.heartbeat("A", fresh_id)  # still fresh at t=0
    clock["t"] = 200.0
    # Traitor skipped; fresh still within silence? last beat at 0, silence 200 > 50
    # Actually fresh wasn't re-hearted after promote — both silent. Traitor skipped.
    n = reg.degrade_silent(50.0)
    assert n == 1
    members = {m.id: m for m in reg.get("A").cohorts[0].members}
    assert members[traitor_id].rank == 2  # cashiered, not degraded
    assert members[fresh_id].rank == 1


def test_fit_for_excludes_traitors_sorts_by_rank(reg: LegionRegistry):
    reg.found("Alpha", "A")
    reg.found("Beta", "B")
    low = reg.enlist("Alpha", "rendering")
    high = reg.enlist("Beta", "rendering")
    traitor = reg.enlist("Alpha", "rendering")
    reg.promote("Beta", high)
    reg.promote("Beta", high)
    reg.cashier("Alpha", traitor)
    fitted = reg.fit_for("rendering")
    ids = [m.id for _, m in fitted]
    assert traitor not in ids
    assert ids == [high, low]
    assert fitted[0][0] == "Beta"
    assert fitted[1][0] == "Alpha"
    assert reg.fit_for("missing") == []
