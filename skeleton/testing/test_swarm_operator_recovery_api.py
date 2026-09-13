from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask
from skeleton.api.swarm_operator_routes import (
    FailoverRequest,
    ReplicaReport,
    checkpoint,
    elect_failover,
    gc,
    recovery_status,
)


def test_operator_checkpoint_records_runtime() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("a", {}))
    recovery = SwarmRecoveryManager()
    result = checkpoint(runtime=runtime, recovery=recovery)
    assert result["sequence"] == 1
    assert result["status"]["checkpoints"] == 1


def test_operator_failover_election() -> None:
    recovery = SwarmRecoveryManager()
    body = FailoverRequest(replicas=[
        ReplicaReport(replica_id="a", epoch=1, sequence=10),
        ReplicaReport(replica_id="b", epoch=2, sequence=1),
    ])
    result = elect_failover(body=body, recovery=recovery)
    assert result["leader"] == "b"
    assert recovery_status(recovery=recovery)["epoch"] == 2


def test_gc_endpoint_reclaims_terminal_history(monkeypatch) -> None:
    runtime = SwarmRuntime(max_tasks=4)
    runtime.register_worker("w")
    for i in range(4):
        runtime.submit(SwarmTask(str(i), {}))
        runtime.lease("w")
        runtime.succeed("w", str(i))

    class State:
        swarm = runtime

    monkeypatch.setattr("skeleton.api.swarm_operator_routes._state", lambda: State)
    result = gc(keep_terminal=1, runtime=runtime)
    assert result["result"]["removed"] == 3
    assert result["capacity"]["available"] == 3
