"""Conservation and sink accounting across mixed industry activity."""

from __future__ import annotations

import random

import pytest

from skeleton.economy.gameplay.industry.errors import IndustryConservationError
from skeleton.economy.gameplay.industry.tests.conftest import OWNERS, stocked
from skeleton.simulation.economy.sim import EconomySimError


def _churn(system, seed: int, steps: int = 300) -> None:
    rng = random.Random(seed)
    tick = 0
    for _ in range(steps):
        tick += rng.randint(0, 7)
        owner = rng.choice(OWNERS)
        roll = rng.random()
        try:
            if roll < 0.3:
                system.queue_build(
                    owner,
                    rng.choice(["smelt_ingot", "press_plate"]),
                    rng.randint(1, 4),
                    tick,
                )
            elif roll < 0.4:
                system.queue_chain(owner, "hull", 1, tick)
            elif roll < 0.5:
                system.queue_research(
                    owner,
                    rng.choice(["smelt_ingot", "press_plate"]),
                    rng.choice(["me", "te"]),
                    tick,
                )
            elif roll < 0.7:
                system.extract(owner, rng.choice(["vein_a", "seam_b"]), tick)
            elif roll < 0.8:
                queued = [j for j in system.jobs(owner) if j["status"] == "queued"]
                if queued:
                    system.cancel(owner, queued[0]["job_id"], tick)
            else:
                system.advance(tick)
        except EconomySimError:  # refusals are fine; books must still balance
            pass
        assert system.audit()["ok"], system.audit()
    system.advance(tick + 100_000)


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_random_churn_keeps_books_balanced(seed):
    system = stocked()
    _churn(system, seed)
    system.require_conserved()


def test_item_identity_minted_equals_held_plus_burned(system):
    system.queue_chain("ana", "hull", 2, tick=0)
    system.extract("bo", "vein_a", tick=1)
    system.advance(10_000)
    for item in sorted(system.econ.items):
        rep = system.econ.item_report(item)
        held = sum(system.econ.inventory(o).count(item) for o in system.econ.owners())
        assert rep["minted"] == held + rep["burned"], item


def test_material_loss_is_a_real_sink(system):
    job = system.queue_build("ana", "smelt_ingot", 10, tick=0)
    assert job["used"] == {"coal": 10, "ore": 30} and job["lost"] == {
        "coal": 1,
        "ore": 3,
    }
    assert system.econ.inventory("ana").count("ore") == 300 - 33
    rep = system.sink_report()
    assert rep["craft_input_units"] == 40 and rep["craft_loss_units"] == 4
    assert system.econ.item_report("ore")["by_sink"]["craft_loss"] == 3


def test_money_sinks_match_charges(system):
    gold0 = system.econ.flow_report("gold")["circulating"]
    b = system.queue_build("ana", "smelt_ingot", 1, tick=0)
    r = system.queue_research("bo", "smelt_ingot", "me", tick=0)
    rep = system.sink_report()
    assert rep["install_fees"] == b["fee"] and rep["research_spend"] == r["fee"]
    assert system.econ.flow_report("gold")["circulating"] == gold0 - b["fee"] - r["fee"]


def test_cancel_does_not_refund_fees(system):
    system.set_lines("ana", 1)
    system.queue_build("ana", "smelt_ingot", 1, tick=0)
    q = system.queue_build("ana", "smelt_ingot", 1, tick=0)
    fees = system.sink_report()["install_fees"]
    system.cancel("ana", q["job_id"], tick=1)
    assert system.sink_report()["install_fees"] == fees
    assert system.audit()["ok"]


def test_tampering_is_detected(system):
    system.queue_build("ana", "smelt_ingot", 2, tick=0)
    system.econ.consume_items("craft_loss", "ana", "ore", 1)  # off-book burn
    with pytest.raises(IndustryConservationError):
        system.require_conserved()
