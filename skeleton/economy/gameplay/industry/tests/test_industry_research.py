"""Research: cost as a money sink, timers, caps and effect on builds."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.industry.errors import JobRejected


def test_research_charges_sink_and_applies_after_timer(system):
    job = system.queue_research("ana", "smelt_ingot", "me", tick=0)
    assert job["fee"] == 100
    assert system.sink_report()["research_spend"] == 100
    assert system.research.levels("ana", "smelt_ingot") == (0, 0)
    system.advance(30)
    assert system.research.levels("ana", "smelt_ingot") == (1, 0)


def test_cost_grows_and_queued_levels_count(system):
    system.set_lines("ana", 4)
    costs = [
        system.queue_research("ana", "smelt_ingot", "te", tick=0)["fee"]
        for _ in range(3)
    ]
    assert costs == [100, 150, 225]
    system.advance(10_000)
    assert system.research.level("ana", "smelt_ingot", "te") == 3


def _rich(system):
    for t in range(1, 6):
        system.econ.grant("daily", "ana", tick=t * 100_000)


def test_research_cap(system):
    _rich(system)
    system.set_lines("ana", 20)
    for _ in range(10):
        system.queue_research("ana", "weld_hull", "me", tick=0)
    with pytest.raises(JobRejected):
        system.queue_research("ana", "weld_hull", "me", tick=0)


def test_research_reduces_loss_and_time(system):
    _rich(system)
    system.set_lines("ana", 10)
    for _ in range(10):
        system.queue_research("ana", "smelt_ingot", "me", tick=0)
    for _ in range(5):
        system.queue_research("ana", "smelt_ingot", "te", tick=0)
    system.advance(100_000)
    job = system.queue_build("ana", "smelt_ingot", 10, tick=100_000)
    assert job["lost"] == {} and job["used"] == {"coal": 10, "ore": 30}
    assert job["end"] - job["start"] == 80
    assert system.queue_build("bo", "smelt_ingot", 10, tick=100_000)["lost"] == {
        "coal": 1,
        "ore": 3,
    }


def test_research_refused_without_funds():
    from skeleton.economy.gameplay.industry.tests.conftest import build_system

    s = build_system()
    with pytest.raises(JobRejected):
        s.queue_research("ana", "smelt_ingot", "me", tick=0)
    with pytest.raises(JobRejected):
        s.queue_research("ana", "smelt_ingot", "xx", tick=0)
