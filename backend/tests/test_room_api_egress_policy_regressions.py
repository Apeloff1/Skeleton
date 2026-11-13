"""Focused hostile-admission regressions for bounded external room egress.

No live network: verifies denial before DNS, HTTPX, or user-defined hooks.
"""
from __future__ import annotations

import socket

import pytest

from gameforge.rooms import room_api_gateway as gateway


@pytest.mark.parametrize("name", [
    "Authorization", "Cookie", "Set-Cookie", "X-API-Key", "X-Auth-Token",
    "Proxy-Authorization", "Forwarded", "X-Forwarded-For", "X-Real-IP",
    "Host", "Connection", "Upgrade",
])
def test_private_identity_headers_cannot_cross_room_egress(name):
    with pytest.raises(ValueError, match="forbidden"):
        gateway._safe_headers({name: "private-value"})


@pytest.mark.parametrize("headers", [
    {"X_Test": "x"}, {"X-Test": "café"},
    {"X-Test": "x" * 1025}, {"X-Test": "hello\nHost: evil"},
    {f"X-Test-{i}": "v" for i in range(25)},
])
def test_header_shape_and_budget_are_strict(headers):
    with pytest.raises(ValueError):
        gateway._safe_headers(headers)


def test_untrusted_method_and_timeout_objects_never_run_hooks():
    class Hostile:
        def __str__(self):
            raise AssertionError("untrusted __str__ must not run")
        def __float__(self):
            raise AssertionError("untrusted __float__ must not run")
    with pytest.raises(ValueError):
        gateway._safe_method(Hostile())
    with pytest.raises(ValueError):
        gateway._safe_timeout(Hostile())
    with pytest.raises(ValueError):
        gateway._safe_timeout("9" * 200)
    assert gateway._safe_method("get") == "GET"
    assert gateway._safe_timeout("8") == 8.0


def test_dns_response_count_is_bounded(monkeypatch):
    answer = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
    monkeypatch.setattr(gateway.socket, "getaddrinfo", lambda *a, **k: [answer] * 33)
    with pytest.raises(ValueError, match="too many DNS"):
        gateway._resolve_public_host("api.example.com")


@pytest.mark.asyncio
async def test_untrusted_target_name_never_echoes_credentials(monkeypatch):
    monkeypatch.setattr(gateway, "_EXTERNAL_ENABLED", False)
    for name in ("Bearer SECRET", "https://secret.example", "token=private", object()):
        row = await gateway._api_query({"name": name, "url": "https://api.example.com"})
        assert row["target"] == "external_api"
        assert "SECRET" not in str(row)
    good = await gateway._api_query({"name": "trusted_api"})
    assert good["target"] == "trusted_api"


@pytest.mark.asyncio
async def test_aggregate_fanout_budget_and_hostile_mapping_fail_closed():
    with pytest.raises(ValueError, match="admission budget"):
        await gateway.query_concurrent(
            "room", mcp_queries=["q"] * 32, api_targets=[{}] * 17
        )
    class HostileDict(dict):
        def get(self, *args, **kwargs):
            raise AssertionError("untrusted mapping hooks must not run")
    with pytest.raises(ValueError, match="admission budget"):
        await gateway.query_concurrent("room", api_targets=[HostileDict()])
