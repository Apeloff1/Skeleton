import pytest

from skeleton.api.v1_edge.envelope import EdgeError
from skeleton.api.v1_edge.quota_store import (DistributedQuotas, InMemoryCounterStore, Limit,
                                              QuotaPlan, QuotaTelemetry)
from skeleton.api.v1_edge.quota_store.telemetry import (M_QUOTA_AUDIT, M_QUOTA_REMAINING,
                                                        M_QUOTA_STORE_ERRORS)
from skeleton.api.v1_edge.quota_store.testing import FlakyCounterStore
from skeleton.api.v1_edge.registry import RouteSpec
from skeleton.gate_plane.telemetry import GateTelemetry

GET = RouteSpec("GET", "/things/{id}")


def test_decisions_flow_into_gate_telemetry():
    gt = GateTelemetry()
    tel = QuotaTelemetry(gt)
    q = DistributedQuotas(QuotaPlan({"default": Limit(0.01, 1)}),
                          store=InMemoryCounterStore(clock=lambda: 0.0), telemetry=tel)
    q.check_request("tenant-secret-id", GET, "GET")
    with pytest.raises(EdgeError):
        q.check_request("tenant-secret-id", GET, "GET")
    assert tel.count("tenant", "default", "allowed", "memory") == 1
    assert tel.count("tenant", "default", "denied", "memory") == 1
    assert gt.counter(M_QUOTA_AUDIT, event="quota.denied") == 1
    snap = gt.snapshot()
    assert "tenant-secret-id" not in repr(snap)
    assert any(M_QUOTA_REMAINING in k for k in snap.get("gauges", {}))
    assert "latency" in repr(snap)


def test_store_errors_counted_and_sinks_receive_copies():
    gt = GateTelemetry()
    tel = QuotaTelemetry(gt)
    seen = []
    tel.add_sink(seen.append)
    flaky = FlakyCounterStore(InMemoryCounterStore(), name="redis")
    flaky.down = True
    q = DistributedQuotas(QuotaPlan({"default": Limit(1, 1)}), store=flaky, telemetry=tel)
    with pytest.raises(EdgeError):
        q.check_request("t", GET, "GET")
    assert gt.counter(M_QUOTA_STORE_ERRORS, store="redis", op="take") == 1
    assert seen and seen[0]["event"] == "quota.store_unavailable"
    seen[0]["event"] = "mutated"
    assert tel.recent()[0]["event"] == "quota.store_unavailable"


def test_broken_sink_and_metrics_never_change_verdict():
    class Boom:
        def increment(self, *a, **k):
            raise RuntimeError("x")
        gauge = histogram = increment

    gt = GateTelemetry()
    gt.metrics = Boom()
    tel = QuotaTelemetry(gt)
    tel.add_sink(lambda rec: 1 / 0)
    q = DistributedQuotas(QuotaPlan({"default": Limit(0.01, 1)}),
                          store=InMemoryCounterStore(clock=lambda: 0.0), telemetry=tel)
    assert q.check_request("t", GET, "GET")["ratelimit-remaining"] == "0"
    with pytest.raises(EdgeError) as e:
        q.check_request("t", GET, "GET")
    assert e.value.status == 429 and tel.dropped > 0


def test_audit_ring_is_bounded():
    tel = QuotaTelemetry(max_audit=3, clock=lambda: 42.0)
    for i in range(10):
        tel.audit("quota.denied", n=i)
    r = tel.recent()
    assert [x["n"] for x in r] == [7, 8, 9] and r[0]["ts"] == 42.0
    assert tel.recent("quota.reset") == []
