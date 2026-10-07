"""A silent member is not fit, and a short drain does not claim the graph is finished."""

import pytest

from skeleton.swarm.dag import SwarmDag
from skeleton.swarm.legions import LegionRegistry
from skeleton.swarm.ready_wave_runner import ReadyWaveRunner


def test_a_silent_member_is_not_fit_and_a_name_is_founded_once() -> None:
    clock = {"t": 0.0}
    registry = LegionRegistry(clock=lambda: clock["t"])
    registry.found("Alpha", "A")
    with pytest.raises(ValueError):
        registry.found("Alpha", "again")
    member_id = registry.enlist("Alpha", "rendering")
    clock["t"] = 120.0
    assert registry.fit_for("rendering") == []
    clock["t"] = 10.0
    registry.heartbeat("Alpha", member_id)
    fitted = registry.fit_for("rendering", max_silence_secs=60)
    assert [member.id for _, member in fitted] == [member_id]
    fitted[0][1].traitor = True
    assert registry.get("Alpha").cohorts[0].members[0].traitor is False


def test_drain_stops_on_the_budget_and_records_the_error_type() -> None:
    graph = SwarmDag()
    graph.submit("fetch", "read", {"q": "docs"})
    graph.submit("cite", "write", {"q": "docs"}, deps=["fetch"])
    runner = ReadyWaveRunner(graph)

    def boom(task):
        raise RuntimeError("secret-trace")

    report = runner.drain("ada", {"read": boom}, max_waves=1)
    assert report.failed == ["fetch"]
    assert report.errors == ["RuntimeError"]
    assert "secret-trace" not in str(report.errors)
    assert graph.get("cite").status.value == "blocked"

    graph = SwarmDag()
    graph.submit("fetch", "read", {"q": "docs"})
    graph.submit("cite", "write", {"q": "docs"}, deps=["fetch"])
    runner = ReadyWaveRunner(graph)
    report = runner.drain("ada", {"read": lambda task: "ok", "write": lambda task: "ok"}, max_waves=1)
    assert report.stopped == "budget"
    assert report.completed == ["fetch"]
    assert graph.get("cite").status.value == "pending"
    with pytest.raises(ValueError):
        runner.drain("", {"read": lambda task: "ok"})
