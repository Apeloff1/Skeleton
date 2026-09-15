"""Reliability regressions for API-gateway rate-limit state."""
from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor

from skeleton.api.gateway import APIGateway, GatewayRequest


def test_high_cardinality_rate_limit_buckets_are_reclaimed(monkeypatch) -> None:
    now = [100.0]
    monkeypatch.setattr("skeleton.api.gateway.time.monotonic", lambda: now[0])
    gateway = APIGateway()
    gateway.route("/limited", lambda payload: {"ok": True}, rate_limit_per_s=2)
    gateway.route("/unlimited", lambda payload: {"ok": True})
    for index in range(1_000):
        assert gateway.handle(GatewayRequest("/limited", actor=f"actor-{index}")).status == 200
    assert len(gateway._buckets) == 1_000
    now[0] += 1.01
    assert gateway.handle(GatewayRequest("/unlimited", actor="cleanup-trigger")).status == 200
    assert gateway._buckets == {}


def test_rate_limit_semantics_survive_bucket_sweeping(monkeypatch) -> None:
    now = [200.0]
    monkeypatch.setattr("skeleton.api.gateway.time.monotonic", lambda: now[0])
    gateway = APIGateway()
    gateway.route("/limited", lambda payload: payload, rate_limit_per_s=2)
    request = GatewayRequest("/limited", actor="same-actor", payload={"value": 1})
    assert gateway.handle(request).status == 200
    assert gateway.handle(request).status == 200
    assert gateway.handle(request).status == 429
    assert len(gateway._buckets["same-actor:/limited"]) == 2
    now[0] += 1.01
    assert gateway.handle(request).status == 200
    assert len(gateway._buckets["same-actor:/limited"]) == 1


def test_bucket_sweep_is_throttled_between_windows(monkeypatch) -> None:
    now = [300.0]
    monkeypatch.setattr("skeleton.api.gateway.time.monotonic", lambda: now[0])
    gateway = APIGateway()
    gateway.route("/limited", lambda payload: None, rate_limit_per_s=10)
    gateway.handle(GatewayRequest("/limited", actor="a"))
    first_sweep = gateway._last_bucket_sweep
    now[0] += 0.5
    gateway.handle(GatewayRequest("/limited", actor="b"))
    assert gateway._last_bucket_sweep == first_sweep
    assert set(gateway._buckets) == {"a:/limited", "b:/limited"}


def test_rate_limit_budget_is_exact_under_concurrent_callers(monkeypatch) -> None:
    monkeypatch.setattr("skeleton.api.gateway.time.monotonic", lambda: 400.0)
    gateway = APIGateway()
    gateway.route("/limited", lambda payload: payload, rate_limit_per_s=8)
    request = GatewayRequest("/limited", actor="shared-actor", payload={"value": 1})
    with ThreadPoolExecutor(max_workers=32) as pool:
        statuses = list(pool.map(lambda _: gateway.handle(request).status, range(32)))
    assert statuses.count(200) == 8
    assert statuses.count(429) == 24
    assert len(gateway._buckets["shared-actor:/limited"]) == 8
    assert gateway.card()["routes"]["/limited"]["calls"] == 8


def test_rate_limit_window_is_pruned_in_place(monkeypatch) -> None:
    now = [500.0]
    monkeypatch.setattr("skeleton.api.gateway.time.monotonic", lambda: now[0])
    gateway = APIGateway()
    gateway.route("/limited", lambda payload: payload, rate_limit_per_s=4)
    request = GatewayRequest("/limited", actor="steady", payload={"value": 1})

    assert gateway.handle(request).status == 200
    bucket = gateway._buckets["steady:/limited"]
    assert isinstance(bucket, deque)

    now[0] += 0.25
    assert gateway.handle(request).status == 200
    assert gateway._buckets["steady:/limited"] is bucket

    now[0] += 0.80
    assert gateway.handle(request).status == 200
    assert gateway._buckets["steady:/limited"] is bucket
    assert list(bucket) == [500.25, now[0]]


def test_unlimited_route_skips_clock_without_limiter_state(monkeypatch) -> None:
    def unexpected_clock_read() -> float:
        raise AssertionError("unlimited hot path must not read the limiter clock")

    monkeypatch.setattr("skeleton.api.gateway.time.monotonic", unexpected_clock_read)
    gateway = APIGateway()
    gateway.route("/unlimited", lambda payload: payload)

    response = gateway.handle(GatewayRequest("/unlimited", payload={"ok": True}))
    assert response.status == 200
    assert response.body == {"ok": True}
    assert gateway._buckets == {}
