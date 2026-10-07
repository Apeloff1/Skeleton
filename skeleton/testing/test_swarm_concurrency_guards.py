from concurrent.futures import ThreadPoolExecutor

from skeleton.agents.swarm_circuit import CircuitBreaker, CircuitState
from skeleton.agents.swarm_idempotency import IdempotencyRegistry


def test_idempotency_registry_is_stable_under_concurrent_resolution() -> None:
    registry = IdempotencyRegistry()

    def resolve():
        return registry.resolve("same", "task", {"x": 1})

    with ThreadPoolExecutor(max_workers=16) as pool:
        records = list(pool.map(lambda _: resolve(), range(128)))

    assert len(registry) == 1
    assert {record.fingerprint for record in records} == {records[0].fingerprint}
    assert {record.task_id for record in records} == {"task"}


def test_half_open_circuit_allows_only_one_probe() -> None:
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=10, clock=lambda: now[0])
    breaker.failure("w")
    assert breaker.snapshot()["w"]["state"] == CircuitState.OPEN.value
    now[0] = 11.0
    assert breaker.allow("w") is True
    assert breaker.allow("w") is False
    snap = breaker.snapshot()["w"]
    assert snap["state"] == CircuitState.HALF_OPEN.value
    assert snap["probe_in_flight"] is True
    assert snap["probes"] == 1


def test_success_releases_half_open_probe() -> None:
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=1, clock=lambda: now[0])
    breaker.failure("w")
    now[0] = 2.0
    assert breaker.allow("w") is True
    breaker.success("w")
    assert breaker.allow("w") is True
    assert breaker.snapshot()["w"]["state"] == CircuitState.CLOSED.value
