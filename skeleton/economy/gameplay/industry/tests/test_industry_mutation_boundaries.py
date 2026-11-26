"""Atomic resource preflight and iterative production-graph regression."""
import pytest

from skeleton.economy.gameplay.industry.blueprints import Blueprint, BlueprintBook
from skeleton.economy.gameplay.industry.errors import JobRejected
from skeleton.economy.gameplay.industry.tests.conftest import stocked
from skeleton.simulation.economy.sim import EconomySimError


def test_batch_refusal_preserves_all_item_books():
    system = stocked()
    before = system.econ.snapshot()
    with pytest.raises(EconomySimError):
        system.econ.consume_items_batch("ana", [("craft_input", "coal", 1),
                                                ("craft_input", "ore", 9999)])
    assert system.econ.snapshot() == before


def test_batch_consumes_bound_copies_last_and_books_exact_sinks():
    system = stocked()
    system.econ.bind("ana", "coal", 99)
    assert system.econ.consume_items_batch("ana", [("craft_input", "coal", 1),
                                                 ("craft_loss", "coal", 1)]) == 2
    assert system.econ.bound_count("ana", "coal") == 98
    report = system.econ.item_report("coal")
    assert report["by_sink"]["craft_input"] == 1
    assert report["by_sink"]["craft_loss"] == 1
    assert system.econ.item_audit()["ok"]


def test_chain_capacity_failure_precedes_fee_and_identity_allocation(monkeypatch):
    from skeleton.economy.gameplay.industry import jobs
    system = stocked()
    monkeypatch.setattr(jobs, "MAX_JOBS", 2)
    before = system.digest()
    with pytest.raises(ValueError, match="capacity"):
        system.queue_chain("ana", "hull", 1, tick=0)
    assert system.digest() == before


def test_foreign_cancel_does_not_advance_world_time():
    system = stocked()
    job = system.queue_build("ana", "smelt_ingot", 1, tick=0)
    before = system.digest()
    with pytest.raises(JobRejected):
        system.cancel("bo", job["job_id"], tick=1000)
    assert system.digest() == before


def test_shared_dependency_graph_uses_iterative_depths():
    book = BlueprintBook()
    previous = "raw"
    for index in range(60):
        left, right, joined = f"l{index}", f"r{index}", f"j{index}"
        book.add(Blueprint(f"bl{index}", left, 1, ((previous, 1),), base_ticks=1))
        book.add(Blueprint(f"br{index}", right, 1, ((previous, 1),), base_ticks=1))
        book.add(Blueprint(f"bj{index}", joined, 2, ((left, 1), (right, 1)), base_ticks=1))
        previous = joined
    assert book.depth(previous) == 120
    assert len(book.plan(previous, 1).steps) == 180
