"""Public first-install status may expose only observed, fixed guard codes."""

import asyncio

import pytest

from routes import ai


def _status(*, code="local_guard_unavailable", available=False, active=True,
            acknowledged=True, active_provider="local"):
    return {
        "active": active_provider,
        "available": available,
        "providers": [{
            "id": "local", "model": None, "available": available, "active": active,
            "architecture_acknowledged": acknowledged, "readiness_code": code,
        }],
    }


def _project(monkeypatch, runtime):
    class Client:
        async def provider_status(self):
            return runtime
    monkeypatch.setattr(ai.EngineClient, "from_env", lambda: Client())
    return asyncio.run(ai.get_ai_providers())


@pytest.mark.parametrize("code", ["local_guard_unavailable", "local_guard_configuration_invalid"])
def test_guard_issue_is_projected_from_the_exact_active_local_provider(monkeypatch, code):
    result = _project(monkeypatch, _status(code=code))
    assert result["active_readiness_code"] == code
    assert result["llm_available"] is False


@pytest.mark.parametrize("runtime", [
    _status(code="exception contains a secret"),
    _status(code=["invalid"]),
    _status(available=True),
    _status(active=False),
    _status(acknowledged=False),
    _status(active_provider="openai"),
])
def test_untrusted_or_contradictory_codes_are_not_projected(monkeypatch, runtime):
    result = _project(monkeypatch, runtime)
    assert "active_readiness_code" not in result
    assert "secret" not in str(result)


def test_two_active_rows_do_not_claim_a_specific_guard_reason(monkeypatch):
    runtime = _status()
    runtime["providers"].append({**runtime["providers"][0], "model": "another"})
    assert "active_readiness_code" not in _project(monkeypatch, runtime)


def test_real_retained_local_registry_projects_its_guard_failure(monkeypatch):
    from skeleton.provider_runtime import ProviderRegistry

    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", "/not-opened/model.json")
    for name in ("AI_LOCAL_GUARD_REQUIRED", "AI_LOCAL_LEGACY_DEV_ACK", "AI_DEPLOYMENT_ENV",
                 "AI_LOCAL_DEPLOYMENT_PATH", "AI_LOCAL_MODEL_CATALOG_PATH", "AI_SECONDARY_API_KEY",
                 "AI_SECONDARY_BASE_URL", "AI_SECONDARY_MODEL", "AI_VERIFICATION_MODEL"):
        monkeypatch.delenv(name, raising=False)
    registry = ProviderRegistry.from_env(retain_unavailable=True)
    result = _project(monkeypatch, {
        "active": "local", "available": False, "providers": registry.statuses(),
    })
    assert result["active_readiness_code"] == "local_guard_unavailable"
    assert result["llm_available"] is False
