from concurrent.futures import ThreadPoolExecutor

from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import SwarmTask, TaskState


def _leased_broker() -> tuple[SwarmBroker, HardenedSwarmRuntime]:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w")
    broker = SwarmBroker(runtime)
    result = broker.submit_and_dispatch(SwarmTask("t", {}))
    assert result.leased is True
    return broker, runtime


def test_duplicate_success_token_is_idempotent() -> None:
    broker, runtime = _leased_broker()
    first = broker.record_success("w", "t", completion_token="done-1")
    second = broker.record_success("w", "t", completion_token="done-1")
    assert first.duplicate is False
    assert second.duplicate is True
    assert second.task.state is TaskState.SUCCEEDED
    assert runtime.worker("w").completed == 1


def test_duplicate_failure_token_does_not_consume_retry_twice() -> None:
    broker, runtime = _leased_broker()
    first = broker.record_failure("w", "t", "boom", completion_token="fail-1")
    second = broker.record_failure("w", "t", "boom", completion_token="fail-1")
    assert first.duplicate is False
    assert second.duplicate is True
    assert runtime.task("t").attempts == 1
    assert runtime.worker("w").failed == 1


def test_concurrent_duplicate_completion_token_mutates_once() -> None:
    broker, runtime = _leased_broker()

    def complete(_: int):
        return broker.record_success("w", "t", completion_token="same")

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(complete, range(64)))

    assert sum(not result.duplicate for result in results) == 1
    assert sum(result.duplicate for result in results) == 63
    assert runtime.worker("w").completed == 1
