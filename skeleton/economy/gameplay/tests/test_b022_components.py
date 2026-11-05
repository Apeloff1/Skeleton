"""B022: ECS upkeep (sink) and income (faucet) systems."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.components import (
    Delinquent,
    EconomyWorld,
    Income,
    IncomeSystem,
    Owned,
    Upkeep,
    UpkeepSystem,
)
from skeleton.economy.gameplay.tests.conftest import build_econ
from skeleton.simulation.economy.sim import EconomySimError


def test_upkeep_charges_on_schedule_and_catches_up():
    econ = build_econ()
    econ.grant("daily", "ana", tick=0)
    world = EconomyWorld()
    world.spawn("house", Owned("ana"), Upkeep("upkeep", every_ticks=10))
    system = UpkeepSystem()
    assert system.run(world, econ, 9)["paid"] == []
    assert system.run(world, econ, 10)["paid"] == ["house"]
    assert system.run(world, econ, 35)["paid"] == ["house", "house"]  # ticks 20 and 30
    assert econ.balance("ana", "gold") == 1_000 - 3 * 50
    assert econ.flow_report("gold")["by_sink"] == {"upkeep": 150}


def test_missed_upkeep_marks_delinquent_then_repossesses():
    econ = build_econ()
    world = EconomyWorld()
    world.spawn("mount", Owned("bo"), Upkeep("upkeep", every_ticks=5, grace=2), Income("bounty", every_ticks=5))
    up, inc = UpkeepSystem(), IncomeSystem()
    assert up.run(world, econ, 5)["missed"] == ["mount"]
    assert world.get("mount", Delinquent).misses == 1
    assert inc.run(world, econ, 5)["paid"] == ["mount"]
    assert up.run(world, econ, 10)["paid"] == ["mount"]  # 100 bounty covers 50 upkeep
    assert world.get("mount", Delinquent).misses == 0
    assert up.run(world, econ, 15)["paid"] == ["mount"]
    assert up.run(world, econ, 20)["missed"] == ["mount"]
    assert up.run(world, econ, 25)["repossessed"] == ["mount"]
    assert not world.is_active("mount")
    assert up.run(world, econ, 100) == {"paid": [], "missed": [], "repossessed": []}
    assert inc.run(world, econ, 100)["paid"] == []
    assert econ.audit()["ok"]


def test_income_never_back_pays_and_reports_faucet_refusals():
    econ = build_econ(bounty_cd=50)
    world = EconomyWorld()
    world.spawn("farm", Owned("ana"), Income("bounty", every_ticks=10))
    inc = IncomeSystem()
    assert inc.run(world, econ, 40)["paid"] == ["farm"]  # one claim for 4 elapsed periods
    assert econ.balance("ana", "gold") == 100
    assert inc.run(world, econ, 50)["refused"] == ["farm"]  # faucet cooldown still rules
    assert inc.run(world, econ, 90)["paid"] == ["farm"]


def test_world_queries_are_sorted_and_validated():
    world = EconomyWorld()
    world.spawn("b", Owned("bo"))
    world.spawn("a", Owned("ana"), Income("bounty", every_ticks=1))
    assert [e for e, _ in world.query(Owned)] == ["a", "b"]
    assert [e for e, _ in world.query(Owned, Income)] == ["a"]
    with pytest.raises(EconomySimError, match="exists"):
        world.spawn("a")
    with pytest.raises(EconomySimError, match="unknown component"):
        world.add("a", object())
    world.despawn("a")
    with pytest.raises(EconomySimError, match="no such entity"):
        world.get("a", Owned)
    with pytest.raises(EconomySimError):
        Upkeep("upkeep", every_ticks=0)
