from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import TaskState
from skeleton.api.swarm_broker_routes import (
    BrokerFailure,
    BrokerSubmission,
    broker_status,
    complete,
    fail,
    submit_and_dispatch,
)


def test_broker_api_submits_and_dispatches_exact_task() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("gpu-1", capabilities=["gpu"], capacity=2)
    broker = SwarmBroker(runtime)
    result = submit_and_dispatch(
        BrokerSubmission(task_id="job", payload={"x": 1}, required_capabilities=["gpu"]),
        broker=broker,
    )
    assert result["task_id"] == "job"
    assert result["leased"] is True
    assert result["worker_id"] == "gpu-1"
    assert runtime.task("job").state is TaskState.LEASED


def test_broker_api_completion_updates_runtime_and_supervisor() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w")
    broker = SwarmBroker(runtime)
    submit_and_dispatch(BrokerSubmission(task_id="job"), broker=broker)
    result = complete("w", "job", broker=broker)
    assert result["state"] == TaskState.SUCCEEDED.value
    assert runtime.task("job").state is TaskState.SUCCEEDED


def test_broker_api_failure_requeues_with_retry_budget() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w")
    broker = SwarmBroker(runtime)
    submit_and_dispatch(BrokerSubmission(task_id="job", max_attempts=2), broker=broker)
    result = fail("w", "job", BrokerFailure(error="transient"), broker=broker)
    assert result["state"] == TaskState.QUEUED.value
    assert result["attempts"] == 1


def test_broker_status_projects_control_plane_state() -> None:
    runtime = HardenedSwarmRuntime()
    broker = SwarmBroker(runtime)
    result = broker_status(broker=broker)
    assert result["snapshot"]["queued"] == 0
    assert result["idempotency_entries"] == 0
    assert "quarantine" in result["supervisor"]
