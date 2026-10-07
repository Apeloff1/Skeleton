"""Plane health must expose degradation without destabilizing healthy cache reuse."""

from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.plane_health import PlaneCircuitOpen, PlaneHealthTracker
from skeleton.retrieval.quad import QuadRetriever


class _Clock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def test_success_telemetry_does_not_change_cache_topology_token() -> None:
    clock = _Clock()
    health = PlaneHealthTracker(clock=clock)
    before = health.cache_token(("rag",))

    health.before_call("rag")
    health.record_success("rag", 10.0)

    assert health.cache_token(("rag",)) == before
    assert health.snapshot()["rag"]["successes"] == 1
    assert health.snapshot()["rag"]["ewma_latency_ms"] == 10.0


def test_repeated_failures_open_and_cooldown_closes_circuit() -> None:
    clock = _Clock()
    health = PlaneHealthTracker(
        failure_threshold=2,
        cooldown_s=5.0,
        clock=clock,
    )
    closed = health.cache_token(("rag",))

    health.before_call("rag")
    health.record_failure("rag", 1.0, RuntimeError("one"))
    assert health.cache_token(("rag",)) == closed

    health.before_call("rag")
    health.record_failure("rag", 1.0, RuntimeError("two"))
    opened = health.cache_token(("rag",))
    assert opened != closed
    assert health.snapshot()["rag"]["circuit_open"] is True

    try:
        health.before_call("rag")
    except PlaneCircuitOpen:
        pass
    else:
        raise AssertionError("open circuit allowed a call")

    clock.value = 5.0
    assert health.cache_token(("rag",)) == closed
    health.before_call("rag")
    assert health.snapshot()["rag"]["circuit_open"] is False


def test_success_after_cooldown_resets_consecutive_failure_count() -> None:
    clock = _Clock()
    health = PlaneHealthTracker(
        failure_threshold=1,
        cooldown_s=2.0,
        clock=clock,
    )
    health.record_failure("rag", 2.0, ValueError("boom"))
    clock.value = 2.0
    health.before_call("rag")
    health.record_success("rag", 4.0)

    state = health.snapshot()["rag"]
    assert state["consecutive_failures"] == 0
    assert state["successes"] == 1
    assert state["failures"] == 1
    assert state["last_error"] == ""


def test_quad_stops_calling_open_plane_and_recovers_after_cooldown() -> None:
    clock = _Clock()
    health = PlaneHealthTracker(
        failure_threshold=2,
        cooldown_s=5.0,
        clock=clock,
    )
    calls = []

    class Flaky:
        def query(self, query: str, top_k: int):
            calls.append(query)
            if len(calls) <= 2:
                raise RuntimeError("down")
            return [ScoredResult("ok", query, 1.0, plane="rag")]

    quad = QuadRetriever(health=health)
    quad.register_plane("rag", Flaky())

    assert quad.retrieve("q1", use_cache=False) == []
    assert quad.retrieve("q2", use_cache=False) == []
    assert quad.retrieve("q3", use_cache=False) == []
    assert calls == ["q1", "q2"]

    clock.value = 5.0
    recovered = quad.retrieve("q4", use_cache=False)
    assert [row.fragment_id for row in recovered] == ["ok"]
    assert calls == ["q1", "q2", "q4"]
    assert quad.stats()["plane_health"]["rag"]["successes"] == 1


def test_ewma_latency_is_stable_and_bounded() -> None:
    health = PlaneHealthTracker(ewma_alpha=0.5)
    health.record_success("rag", 10.0)
    health.record_success("rag", 30.0)
    assert health.snapshot()["rag"]["ewma_latency_ms"] == 20.0


def test_replacing_plane_clears_old_circuit_state() -> None:
    clock = _Clock()
    health = PlaneHealthTracker(
        failure_threshold=1,
        cooldown_s=60.0,
        clock=clock,
    )

    class Broken:
        def query(self, query: str, top_k: int):
            raise RuntimeError("old backend down")

    class Healthy:
        def query(self, query: str, top_k: int):
            return [ScoredResult("fresh", query, 1.0, plane="rag")]

    quad = QuadRetriever(health=health)
    quad.register_plane("rag", Broken())
    assert quad.retrieve("first", use_cache=False) == []
    assert health.snapshot()["rag"]["circuit_open"] is True

    quad.register_plane("rag", Healthy())
    results = quad.retrieve("second", use_cache=False)

    assert [row.fragment_id for row in results] == ["fresh"]
    assert health.snapshot()["rag"]["circuit_open"] is False
