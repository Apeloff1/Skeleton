from fastapi import HTTPException
import pytest

from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask
from skeleton.api.swarm_operator_routes import slo, tasks


def test_operator_slo_endpoint_reports_capacity_failure() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("a", {}))
    result = slo(max_dead_ratio=0.01, max_queue_per_slot=50.0, min_available_slots=1, runtime=runtime)
    assert result["met"] is False


def test_operator_tasks_endpoint_filters_and_pages() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("b", {}, priority=2, required_capabilities=frozenset({"gpu"})))
    runtime.submit(SwarmTask("a", {}, priority=1, required_capabilities=frozenset({"gpu"})))
    result = tasks(state="queued", capability="gpu", offset=0, limit=1, runtime=runtime)
    assert result["total"] == 2
    assert result["items"][0]["id"] == "a"


def test_operator_tasks_endpoint_rejects_invalid_state() -> None:
    runtime = SwarmRuntime()
    with pytest.raises(HTTPException) as exc:
        tasks(state="not-a-state", capability=None, offset=0, limit=100, runtime=runtime)
    assert exc.value.status_code == 422
