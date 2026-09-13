from skeleton.agents.swarm_circuit import CircuitBreaker
from skeleton.agents.swarm_resilient_scheduler import ResilientSwarmScheduler
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask


def test_open_circuit_quarantines_worker() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("a", capabilities=["gpu"])
    runtime.register_worker("b", capabilities=["gpu"])
    breaker = CircuitBreaker(failure_threshold=1)
    scheduler = ResilientSwarmScheduler(breaker)
    scheduler.record_failure("a")
    task = SwarmTask("t", {}, required_capabilities=frozenset({"gpu"}))
    ranking = scheduler.rank(runtime, task)
    assert ranking.quarantined == ("a",)
    assert [item.worker_id for item in ranking.eligible] == ["b"]


def test_success_closes_worker_circuit() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("a")
    breaker = CircuitBreaker(failure_threshold=1)
    scheduler = ResilientSwarmScheduler(breaker)
    scheduler.record_failure("a")
    scheduler.record_success("a")
    assert scheduler.best_worker(runtime, SwarmTask("t", {})).id == "a"


def test_half_open_probe_reenters_ranking_after_timeout() -> None:
    now = [0.0]
    runtime = SwarmRuntime()
    runtime.register_worker("a")
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=10, clock=lambda: now[0])
    scheduler = ResilientSwarmScheduler(breaker)
    scheduler.record_failure("a")
    assert scheduler.best_worker(runtime, SwarmTask("t", {})) is None
    now[0] = 11.0
    assert scheduler.best_worker(runtime, SwarmTask("t", {})).id == "a"
