"""Training rows cannot see the future, and a background agent cannot exceed its bounds."""

import time

import pytest

from skeleton.intelligence.background_agent import AgentStep, BackgroundAgent
from skeleton.intelligence.feature_store import FeatureStore, FeatureStoreError


def test_training_row_drops_a_feature_that_did_not_exist_yet() -> None:
    store = FeatureStore()
    store.register("score", "user")
    store.register("later", "user")
    store.write("score", "u1", 10, timestamp_ns=100)
    store.write("later", "u1", 99, timestamp_ns=200)
    assert store.point_in_time("score", "u1", 150) == 10
    assert store.point_in_time("later", "u1", 150) is None
    assert store.training_set(["score", "later"], ["u1"], as_of_ns=150) == []
    rows = store.training_set(["score", "later"], ["u1"], as_of_ns=250)
    assert rows == [{"entity_id": "u1", "score": 10, "later": 99}]
    with pytest.raises(FeatureStoreError):
        store.write("score", "u1", float("nan"), timestamp_ns=300)
    with pytest.raises(KeyError):
        store.point_in_time("ghost", "u1", 150)


def test_existing_feature_store_contracts() -> None:
    store = FeatureStore()
    store.register("clicks", "user", ttl_s=3600)
    store.write("clicks", "u1", 42)
    assert store.online("clicks", "u1") == 42
    store.register("player:score", "player", ttl_s=10.0)
    store.write("player:score", "ada", 3, timestamp_ns=time.time_ns())
    assert store.freshness()["player:score:ada"]["stale"] is False
    store.register("f", "user")
    assert store.register("f", "user").version == 2
    stale = FeatureStore()
    stale.register("f", "user", ttl_s=0.01)
    stale.write("f", "u1", 7, timestamp_ns=1)
    assert stale.online("f", "u1") is None


def test_background_agent_blocks_a_write_and_a_wide_fanout_before_execution() -> None:
    called: list[str] = []

    def executor(step: AgentStep) -> str:
        called.append(step.tool)
        return "ok"

    def illegal(goal: str, calls: tuple[str, ...]) -> AgentStep:
        return AgentStep("artifact.package", {"build_id": "build-1"})

    blocked = BackgroundAgent().run("package the build", illegal, executor)
    assert blocked.status == "blocked"
    assert called == []

    def wide(goal: str, calls: tuple[str, ...]) -> AgentStep:
        child = AgentStep("network.search", {"query": "docs"})
        return AgentStep("repository.query", {"collection": "notes"}, children=(child, child, child))

    wide_result = BackgroundAgent(max_children=2).run("look up notes", wide, executor)
    assert wide_result.status == "blocked"
    assert called == []

    def planned(goal: str, calls: tuple[str, ...]) -> AgentStep | None:
        if calls:
            return None
        return AgentStep("network.search", {"query": goal})

    done = BackgroundAgent(max_steps=2).run("docs", planned, executor)
    assert done.status == "completed"
    assert done.calls == ("network.search",)
    assert called == ["network.search"]

    def forever(goal: str, calls: tuple[str, ...]) -> AgentStep:
        return AgentStep("network.search", {"query": goal})

    budget = BackgroundAgent(max_steps=1).run("docs", forever, executor)
    assert budget.status == "budget"
    assert budget.calls == ("network.search",)
