"""Reliability and security regressions for API-gateway payload handling."""
from __future__ import annotations

from typing import Any

from skeleton.api.gateway import APIGateway, GatewayRequest


class _MemoryCache:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], Any] = {}
        self.set_calls = 0

    def get(self, namespace: str, key: str) -> Any:
        return self.values.get((namespace, key))

    def set(self, namespace: str, key: str, value: Any, *, ttl_s: float) -> None:
        self.set_calls += 1
        self.values[(namespace, key)] = value


def test_nested_payload_works_when_cache_is_disabled() -> None:
    gateway = APIGateway()
    gateway.route("/echo", lambda payload: payload)
    payload = {"messages": [{"role": "user", "content": "hello"}], "options": {"n": 2}}

    response = gateway.handle(GatewayRequest("/echo", payload=payload))

    assert response.status == 200
    assert response.body == payload
    assert response.cached is False


def test_nested_json_payload_cache_key_is_stable_across_dict_order() -> None:
    cache = _MemoryCache()
    handler_calls = [0]

    def handler(payload: dict[str, Any]) -> dict[str, Any]:
        handler_calls[0] += 1
        return {"call": handler_calls[0], "payload": payload}

    gateway = APIGateway(cache=cache)
    gateway.route("/cached", handler, cache_ttl_s=30)

    first = GatewayRequest(
        "/cached",
        payload={"outer": {"b": 2, "a": [3, 1]}, "enabled": True},
    )
    equivalent = GatewayRequest(
        "/cached",
        payload={"enabled": True, "outer": {"a": [3, 1], "b": 2}},
    )

    first_response = gateway.handle(first)
    second_response = gateway.handle(equivalent)

    assert first_response.status == 200
    assert first_response.cached is False
    assert second_response.status == 200
    assert second_response.cached is True
    assert second_response.body == first_response.body
    assert handler_calls[0] == 1
    assert cache.set_calls == 1


def test_non_json_payload_skips_cache_without_breaking_route() -> None:
    cache = _MemoryCache()
    marker = object()
    gateway = APIGateway(cache=cache)
    gateway.route("/raw", lambda payload: {"ok": payload["value"] is marker}, cache_ttl_s=30)

    first = gateway.handle(GatewayRequest("/raw", payload={"value": marker}))
    second = gateway.handle(GatewayRequest("/raw", payload={"value": marker}))

    assert first.status == 200
    assert first.body == {"ok": True}
    assert second.status == 200
    assert second.cached is False
    assert cache.values == {}
    assert cache.set_calls == 0


def test_handler_exception_does_not_leak_internal_error_text() -> None:
    secret = "provider-token=super-secret"

    def fail(_payload: dict[str, Any]) -> None:
        raise RuntimeError(secret)

    gateway = APIGateway()
    route = gateway.route("/fail", fail)

    response = gateway.handle(GatewayRequest("/fail"))

    assert response.status == 500
    assert response.body == {"error": "internal server error"}
    assert secret not in str(response.body)
    assert route.calls == 1
    assert route.errors == 1
