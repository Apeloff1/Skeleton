from skeleton.agents.swarm_load_shed import LoadShedPolicy
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask
from skeleton.agents.swarm_supervisor import SwarmSupervisor


def test_supervisor_selects_healthy_worker() -> None:
    runtime = SwarmRuntime(); runtime.register_worker("w", capabilities=["gpu"])
    task = SwarmTask("t", {}, required_capabilities=frozenset({"gpu"}))
    decision = SwarmSupervisor().dispatch(runtime, task)
    assert decision.accepted is True and decision.worker_id == "w"


def test_supervisor_respects_quarantine() -> None:
    runtime = SwarmRuntime(); runtime.register_worker("w")
    supervisor = SwarmSupervisor(); supervisor.quarantine_worker("w", reason="bad")
    decision = supervisor.dispatch(runtime, SwarmTask("t", {}))
    assert decision.accepted is False


def test_load_shedding_preserves_priority_work() -> None:
    runtime = SwarmRuntime(); runtime.submit(SwarmTask("q", {}))
    policy = LoadShedPolicy(max_queue_pressure=0.5, protect_priority_at_or_below=10)
    supervisor = SwarmSupervisor(shed_policy=policy)
    assert supervisor.dispatch(runtime, SwarmTask("critical", {}, priority=0)).reason != "queue pressure limit exceeded"
    assert supervisor.dispatch(runtime, SwarmTask("bulk", {}, priority=100)).reason == "queue pressure limit exceeded"


def test_circuit_failures_remove_worker_from_dispatch() -> None:
    runtime = SwarmRuntime(); runtime.register_worker("w")
    supervisor = SwarmSupervisor()
    for _ in range(5): supervisor.record_failure("w")
    assert supervisor.dispatch(runtime, SwarmTask("t", {})).accepted is False
