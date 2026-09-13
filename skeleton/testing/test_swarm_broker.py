from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState


def test_broker_leases_exact_submitted_task_not_older_queue_item() -> None:
    runtime=SwarmRuntime(); runtime.register_worker("w", capacity=2)
    runtime.submit(SwarmTask("older", {}, priority=0))
    result=SwarmBroker(runtime).submit_and_dispatch(SwarmTask("new", {}, priority=100))
    assert result.leased is True and result.task_id == "new"
    assert runtime.task("new").state is TaskState.LEASED
    assert runtime.task("older").state is TaskState.QUEUED


def test_broker_idempotent_duplicate_does_not_reexecute_terminal_task() -> None:
    runtime=SwarmRuntime(); runtime.register_worker("w")
    broker=SwarmBroker(runtime)
    first=broker.submit_and_dispatch(SwarmTask("t", {"x":1}), idempotency_key="k")
    broker.record_success("w", "t")
    second=broker.submit_and_dispatch(SwarmTask("t", {"x":1}), idempotency_key="k")
    assert first.leased is True
    assert second.duplicate is True and second.leased is False
    assert runtime.task("t").state is TaskState.SUCCEEDED
