"""Contract tests: Jeeves is the ONLY local primary text inference authority.

These exercise real provider registry admission and model identity checks.
Never construct a hosted adapter, invoke a network provider, or treat an
untrained/synthetic model as a live user-facing assistant.
"""
from __future__ import annotations

import pytest

from skeleton.ai.jeeves_local_policy import (
    JeevesLocalPolicyError, is_local_only, primary_model_id,
    require_local_configuration, require_local_inventory,
    require_primary_selection,
)
from skeleton.provider_runtime import ProviderRegistry, ProviderUnavailableError


def local_config(**overrides):
    config = {
        "JEEVES_LOCAL_ONLY": "1",
        "JEEVES_PRIMARY_MODEL_ID": "jeeves",
        "AI_PROVIDER": "local",
        "AI_LOCAL_DEPLOYMENT_PATH": "/app/configured-local-ai/jeeves.json",
        "AI_LOCAL_MODEL_PATH": "",
        "AI_LOCAL_MODEL_CATALOG_PATH": "",
        "AI_LOCAL_GUARD_REQUIRED": "1",
        "AI_SECONDARY_API_KEY": "",
        "AI_SECONDARY_BASE_URL": "",
        "AI_SECONDARY_MODEL": "",
        "AI_VERIFICATION_MODEL": "",
        "OPENAI_API_KEY": "",
    }
    config.update(overrides)
    return config


@pytest.mark.parametrize("value,expected", [
    ("1", True), ("true", True), ("0", False),
    ("false", False), ("", False),
])
def test_policy_boolean_is_explicit_and_bounded(value, expected):
    assert is_local_only({"JEEVES_LOCAL_ONLY": value}) is expected


@pytest.mark.parametrize("value", ["enabled", "yes", "2", "auto", "-1", "TRUE AND FALSE"])
def test_ambiguous_policy_never_admits_a_provider(value):
    with pytest.raises(JeevesLocalPolicyError, match="invalid boolean"):
        is_local_only({"JEEVES_LOCAL_ONLY": value})


def test_jeeves_requires_one_real_pinned_local_source():
    assert require_local_configuration(local_config()) == "AI_LOCAL_DEPLOYMENT_PATH"
    assert require_local_configuration(local_config(AI_LOCAL_DEPLOYMENT_PATH=""), require_source=False) is None


@pytest.mark.parametrize("overrides,phrase", [
    ({"JEEVES_LOCAL_ONLY": "0"}, "must be explicitly active"),
    ({"AI_PROVIDER": "openai"}, "AI_PROVIDER=local"),
    ({"AI_PROVIDER": "secondary"}, "AI_PROVIDER=local"),
    ({"JEEVES_PRIMARY_MODEL_ID": "gpt-5.5"}, "exactly jeeves"),
    ({"JEEVES_PRIMARY_MODEL_ID": "Jeeves"}, "exactly jeeves"),
    ({"AI_LOCAL_DEPLOYMENT_PATH": ""}, "exactly one"),
    ({"AI_LOCAL_DEPLOYMENT_PATH": "", "AI_LOCAL_MODEL_PATH": "", "AI_LOCAL_MODEL_CATALOG_PATH": ""}, "exactly one"),
    ({"AI_LOCAL_MODEL_PATH": "/app/another.json"}, "exactly one"),
    ({"AI_SECONDARY_API_KEY": "example"}, "external fallback"),
    ({"AI_SECONDARY_BASE_URL": "https://provider.example.org"}, "external fallback"),
    ({"AI_SECONDARY_MODEL": "multimodal-other"}, "external fallback"),
    ({"AI_VERIFICATION_MODEL": "remote-reviewer"}, "external fallback"),
])
def test_nonlocal_or_multi_primary_config_rejected(overrides, phrase):
    with pytest.raises(JeevesLocalPolicyError, match=phrase):
        require_local_configuration(local_config(**overrides))


@pytest.mark.parametrize("provider,model", [
    ("openai", "gpt-5.5"), ("secondary", "jeeves"),
    ("local", "qwen3"), ("local", "Jeeves"),
    ("local", None), (None, "jeeves"),
])
def test_any_client_selected_foreign_or_advisory_primary_is_denied(provider, model):
    with pytest.raises(JeevesLocalPolicyError, match="only permits"):
        require_primary_selection(provider, model, local_config())


def test_omitted_pair_is_local_automatic_only_if_engine_is_local():
    require_primary_selection(None, None, local_config())
    require_primary_selection("local", "jeeves", local_config())


@pytest.mark.parametrize("models", [
    [{"provider_id": "openai", "model_id": "jeeves"}],
    [{"provider_id": "local", "model_id": "other"}],
    [{"provider_id": "local", "model_id": "jeeves"}, {"provider_id": "openai", "model_id": "gpt"}],
])
def test_local_model_catalog_cannot_advertise_hosted_multimodal_primary(models):
    with pytest.raises(JeevesLocalPolicyError, match="nonlocal or nonprimary"):
        require_local_inventory(models, local_config())


def test_engine_rejects_hosted_provider_before_constructing_remote_adapter(monkeypatch):
    for name, value in local_config(AI_PROVIDER="openai").items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ProviderUnavailableError, match="local-only provider configuration"):
        ProviderRegistry.from_env()


def test_engine_rejects_unguarded_development_bypass_when_jeeves_only(monkeypatch):
    for name, value in local_config(
        AI_LOCAL_GUARD_REQUIRED="0",
        AI_DEPLOYMENT_ENV="development",
        AI_LOCAL_LEGACY_DEV_ACK="unsafe-local-dev-only",
    ).items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ProviderUnavailableError, match="cannot disable"):
        ProviderRegistry.from_env(require_guarded_local=False)


def test_no_local_trust_bootstrap_yields_unavailable_not_hosted(monkeypatch):
    for name, value in local_config(OPENAI_API_KEY="sk-" + "X" * 50).items():
        monkeypatch.setenv(name, value)
    registry = ProviderRegistry.from_env(retain_unavailable=True)
    assert registry.active_id == "local"
    assert registry.active is not None
    assert registry.active.available is False
    assert getattr(registry.active, "model", None) in (None, "unavailable")
    assert "openai" not in registry._adapters
