"""Industry restore rejects inconsistent identities before resuming a world."""
from copy import deepcopy

import pytest

from skeleton.economy.gameplay.industry.engine import IndustrySystem
from skeleton.economy.gameplay.industry.jobs import BuildQueue
from skeleton.economy.gameplay.industry.tests.conftest import stocked


def test_duplicate_jobs_and_rewound_allocator_are_rejected():
    system = stocked()
    system.queue_build("ana", "smelt_ingot", 1, tick=0)
    valid = system.queue.to_state()
    for bad in (dict(valid, jobs=valid["jobs"] * 2), dict(valid, next_id=1)):
        with pytest.raises(ValueError):
            BuildQueue.from_state(bad)


def test_restore_rejects_missing_dependency_and_foreign_owner():
    system = stocked()
    system.queue_chain("ana", "hull", 1, tick=0)
    valid = system.queue.to_state()
    for owner, deps in (("ana", [999]), ("bo", [1])):
        bad = deepcopy(valid)
        bad["jobs"][1]["owner"] = owner
        bad["jobs"][1]["deps"] = deps
        with pytest.raises(ValueError):
            BuildQueue.from_state(bad)


def test_restore_rejects_duplicate_nodes_and_noncanonical_research():
    system = stocked()
    valid = system.to_state()
    duplicate = deepcopy(valid)
    duplicate["nodes"].append(deepcopy(duplicate["nodes"][0]))
    with pytest.raises(ValueError):
        IndustrySystem.from_state(system.econ, duplicate)
    for research in ({"ana": {"smelt_ingot": {"me": True}}},
                     {"ana": {"smelt_ingot": {"me": 100_000}}},
                     {"ana": {"smelt_ingot": {"unknown": 1}}}):
        bad = deepcopy(valid)
        bad["research"] = research
        with pytest.raises(ValueError):
            IndustrySystem.from_state(system.econ, bad)


def test_restore_rejects_forged_extraction_window():
    system = stocked()
    bad = system.to_state()
    bad["nodes"][0]["window"] = [[10, -1]]
    with pytest.raises(ValueError):
        IndustrySystem.from_state(system.econ, bad)
