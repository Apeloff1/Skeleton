"""Boot-safe LLM router admission and cache budget contracts, all offline."""
from __future__ import annotations

import asyncio
import math

import pytest

from routes import llm_router as router


@pytest.mark.parametrize("raw", [
    "nan", "NaN", "inf", "-Infinity", "-1", "0", "301",
    "nope", " ", "99999999999999999999999999999999",
])
def test_timeout_env_bad_values_fall_back_without_breaking_import(monkeypatch, raw):
    monkeypatch.setenv("LLM_ROUTER_TIMEOUT_S", raw)
    monkeypatch.setattr(router, "_CONFIG_ISSUES", [])
    value = router._env_bounded_float(
        "LLM_ROUTER_TIMEOUT_S", 60.0, minimum=0.01, maximum=300.0,
    )
    assert value == 60.0
    assert router._CONFIG_ISSUES == [
        "LLM_ROUTER_TIMEOUT_S is invalid; using safe default"
    ]


@pytest.mark.parametrize("name,maximum,raw", [
    ("LLM_ROUTER_CACHE_MAX", 2048, "999999999999"),
    ("LLM_ROUTER_CACHE_MAX", 2048, "-1"),
    ("LLM_ROUTER_CACHE_MAX", 2048, "NaN"),
    ("LLM_ROUTER_CACHE_TTL_S", 86400, "86401"),
    ("LLM_ROUTER_CACHE_TTL_S", 86400, "-1"),
    ("LLM_ROUTER_CACHE_TTL_S", 86400, "bad"),
])
def test_malformed_cache_env_does_not_disable_router(monkeypatch, name, maximum, raw):
    monkeypatch.setenv(name, raw)
    monkeypatch.setattr(router, "_CONFIG_ISSUES", [])
    safe = 512 if name.endswith("MAX") else 3600
    value = router._env_bounded_int(name, safe, minimum=0, maximum=maximum)
    assert value == safe
    assert router._CONFIG_ISSUES == [name + " is invalid; using safe default"]


@pytest.mark.parametrize("name,maximum", [
    ("LLM_ROUTER_CACHE_MAX", 2048),
    ("LLM_ROUTER_CACHE_TTL_S", 86400),
])
def test_cache_zero_is_a_valid_explicit_disable(monkeypatch, name, maximum):
    monkeypatch.setenv(name, "0")
    monkeypatch.setattr(router, "_CONFIG_ISSUES", [])
    assert router._env_bounded_int(name, 512, minimum=0, maximum=maximum) == 0
    assert router._CONFIG_ISSUES == []


@pytest.mark.parametrize("options", [
    {"task": 5, "prompt": "hello"},
    {"task": {"a": "b"}, "prompt": "hello"},
    {"task": True, "prompt": "hello"},
    {"task": "creative", "prompt": 42},
    {"task": "creative", "prompt": "hello", "timeout_s": float("nan")},
    {"task": "creative", "prompt": "hello", "timeout_s": float("inf")},
    {"task": "creative", "prompt": "hello", "timeout_s": 10 ** 1000},
    {"task": "creative", "prompt": "hello", "timeout_s": True},
    {"task": "creative", "prompt": "hello", "use_cache": "false"},
    {"task": "creative", "prompt": "hello", "use_cache": 1},
    {"task": "creative", "prompt": "hello", "tenant_id": ""},
    {"task": "creative", "prompt": "hello", "tenant_id": {"tenant": "bad"}},
    {"task": "creative", "prompt": "hello", "actor_id": "  "},
    {"task": "creative", "prompt": "hello", "actor_id": True},
    {"task": "creative", "prompt": "hello", "idempotency_key": []},
    {"task": "creative", "prompt": "hello", "idempotency_key": " "},
    {"task": "creative", "prompt": "hello", "idempotency_key": "x" * 1025},
    {"task": "creative", "prompt": "hello", "max_output_tokens": True},
    {"task": "creative", "prompt": "hello", "max_output_tokens": 0},
    {"task": "creative", "prompt": "hello", "max_output_tokens": 131073},
    {"task": "creative", "prompt": "hello", "provider_id": "runtime-provider"},
    {"task": "creative", "prompt": "hello", "model_id": "runtime-model"},
])
def test_direct_completion_rejects_untrusted_types_before_engine_or_cache(monkeypatch, options):
    async def forbidden(*_args, **_kwargs):
        raise AssertionError("entered engine with malformed request")

    monkeypatch.setattr(router, "model_catalog", forbidden)
    monkeypatch.setattr(
        router.EngineClient, "from_env",
        lambda: (_ for _ in ()).throw(AssertionError("engine environment read")),
    )
    reply = asyncio.run(router.route_complete(**options))
    assert reply["error_code"] == "request_invalid"
    assert reply["cached"] is False


def test_valid_config_remains_strictly_bounded(monkeypatch):
    monkeypatch.setenv("LLM_ROUTER_TIMEOUT_S", "299.5")
    monkeypatch.setenv("LLM_ROUTER_CACHE_MAX", "1024")
    monkeypatch.setenv("LLM_ROUTER_CACHE_TTL_S", "86400")
    monkeypatch.setattr(router, "_CONFIG_ISSUES", [])
    assert router._env_bounded_float(
        "LLM_ROUTER_TIMEOUT_S", 60.0, minimum=0.01, maximum=300.0
    ) == 299.5
    assert router._env_bounded_int(
        "LLM_ROUTER_CACHE_MAX", 512, minimum=0, maximum=2048
    ) == 1024
    assert router._env_bounded_int(
        "LLM_ROUTER_CACHE_TTL_S", 3600, minimum=0, maximum=86400
    ) == 86400
    assert router._CONFIG_ISSUES == []


def test_invalid_startup_config_reports_only_variable_names(monkeypatch):
    monkeypatch.setenv("LLM_ROUTER_TIMEOUT_S", "password-like-invalid-value")
    monkeypatch.setattr(router, "_CONFIG_ISSUES", [])
    assert router._env_bounded_float(
        "LLM_ROUTER_TIMEOUT_S", 60, minimum=0.01, maximum=300
    ) == 60
    assert "password-like-invalid-value" not in " ".join(router._CONFIG_ISSUES)
