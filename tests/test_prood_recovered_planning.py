"""Contract coverage for the recovered isolated Prood planning surface."""
import sys

import pytest

from skeleton.prood import forge_registry, swarm_planner


def test_planner_is_deterministic_unique_and_never_executes():
    args = ("build", ["world", "assets", "asset_variant"], 7, 4)
    first = swarm_planner.plan_build(*args, game_ctx={"genre": "rpg"})
    assert first == swarm_planner.plan_build(*args, game_ctx={"genre": "rpg"})
    assert first["plan_hash"] != swarm_planner.plan_build(*args, game_ctx={"genre": "maze"})["plan_hash"]
    workers = [worker for node in first["nodes"] for worker in node["workers"]]
    assert len({worker["code"] for worker in workers}) == first["worker_count"] == 12
    assert first["status"] == "planned_only"
    assert not first["execution_verified"]
    assert all(not worker["admitted"] for worker in workers)


@pytest.mark.parametrize("kwargs", [
    {"phases": ["a", "a"]}, {"phases": ["a"] * 129},
    {"platoon_size": True}, {"platoon_size": 13},
    {"seed": True}, {"game_ctx": []}, {"unknown": True},
])
def test_invalid_planning_requests_are_denied(kwargs):
    with pytest.raises(ValueError):
        swarm_planner.plan_build("build", **kwargs)


def test_catalog_counts_and_statuses_are_historical_not_execution_evidence():
    catalog = forge_registry.catalog()
    assert catalog["total"] == catalog["active_count"] + catalog["deferred_count"]
    assert all(row["status"] == "deferred" for row in catalog["deferred"])
    assert len({row["key"] for row in catalog["deferred"]}) == catalog["deferred_count"]


def test_prood_no_longer_installs_fake_global_modules():
    import skeleton.prood

    assert not hasattr(skeleton.prood, "_install_core_shim")
    module = sys.modules.get("core.databases")
    assert module is None or module.__name__ != "skeleton.prood._memory_db"
