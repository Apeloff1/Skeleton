"""Reliability regressions for API-gateway rate-limit state."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from skeleton.api.gateway import APIGateway, GatewayRequest


def test_high_cardinality_rate_limit_buckets_are_reclaimed(monkeypatch) -> None:
    now = [100.0]
    monkeypatch.setattr("skeleton.api.gateway.time.monotonic", lambda: now[0])

    gateway = APIGateway()
    gateway.route("/limited", lambda payload: {"ok": True}, rate_limit_per_s=2)
    gateway.route("/unlimited", lambda payload: {"ok": True})

    for index in range(1_000):
        response = gateway.handle(GatewayRequest("/limited", actor=f"actor-{index}"))
        assert response.status == 200

    assert len(gateway._buckets) == 1_000

    now[0] += 1.01
    response = gateway.handle(GatewayRequest("/unlimited", actor="cleanup-trigger"))

    assert response.status == 200
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
