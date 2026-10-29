"""Production local provider startup may not silently bypass context verification.

Regression gates target the canonical ProviderRegistry application factory.
No model artifact or hosted credentials are needed to prove early denial.
"""

from __future__ import annotations

import pytest

from skeleton.provider_runtime import ProviderRegistry, ProviderUnavailableError


@pytest.fixture
def local_configuration(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", "/unprovisioned/local-model.json")
    monkeypatch.delenv("AI_LOCAL_DEPLOYMENT_PATH", raising=False)
    monkeypatch.delenv("AI_LOCAL_MODEL_CATALOG_PATH", raising=False)
    for key in (
        "AI_LOCAL_GUARD_REQUIRED", "AI_LOCAL_LEGACY_DEV_ACK", "AI_DEPLOYMENT_ENV",
        "AI_SECONDARY_API_KEY", "AI_SECONDARY_BASE_URL", "AI_SECONDARY_MODEL",
        "AI_VERIFICATION_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_local_provider_defaults_to_guard_required_before_artifact_access(local_configuration):
    with pytest.raises(ProviderUnavailableError, match="trusted dependencies"):
        ProviderRegistry.from_env()


def test_retained_local_provider_never_becomes_unprotected_fallback(local_configuration):
    registry = ProviderRegistry.from_env(retain_unavailable=True)
    with pytest.raises(ProviderUnavailableError):
        registry.require_active()


@pytest.mark.parametrize("guard", ("0", "false"))
def test_environment_opt_out_alone_is_denied(local_configuration, monkeypatch, guard):
    monkeypatch.setenv("AI_LOCAL_GUARD_REQUIRED", guard)
    with pytest.raises(ProviderUnavailableError, match="development-only"):
        ProviderRegistry.from_env()


def test_untrusted_legacy_ack_is_denied_without_independent_caller_authorization(
    local_configuration, monkeypatch,
):
    monkeypatch.setenv("AI_LOCAL_GUARD_REQUIRED", "0")
    monkeypatch.setenv("AI_DEPLOYMENT_ENV", "development")
    monkeypatch.setenv("AI_LOCAL_LEGACY_DEV_ACK", "unsafe-local-dev-only")
    with pytest.raises(ProviderUnavailableError, match="development-only"):
        ProviderRegistry.from_env()


def test_explicit_false_cannot_disable_production_guard(local_configuration, monkeypatch):
    monkeypatch.setenv("AI_LOCAL_GUARD_REQUIRED", "0")
    monkeypatch.setenv("AI_DEPLOYMENT_ENV", "production")
    monkeypatch.setenv("AI_LOCAL_LEGACY_DEV_ACK", "unsafe-local-dev-only")
    with pytest.raises(ProviderUnavailableError, match="development-only"):
        ProviderRegistry.from_env(require_guarded_local=False)


def test_local_guard_required_must_have_actual_components(local_configuration, monkeypatch):
    monkeypatch.setenv("AI_LOCAL_GUARD_REQUIRED", "1")
    with pytest.raises(ProviderUnavailableError, match="trusted dependencies"):
        ProviderRegistry.from_env(require_guarded_local=True)
    with pytest.raises(ProviderUnavailableError, match="trusted dependencies"):
        ProviderRegistry.from_env(require_guarded_local=True, guarded_components=object())


def test_explicit_reference_dev_mode_reaches_artifact_admission(local_configuration, monkeypatch):
    monkeypatch.setenv("AI_LOCAL_GUARD_REQUIRED", "0")
    monkeypatch.setenv("AI_DEPLOYMENT_ENV", "development")
    monkeypatch.setenv("AI_LOCAL_LEGACY_DEV_ACK", "unsafe-local-dev-only")
    # Legacy mode can only be opted into through trusted application code AND
    # the three operator-side development-only policy values. The missing
    # model then fails independently rather than triggering a phantom success.
    with pytest.raises(ProviderUnavailableError, match="artifact"):
        ProviderRegistry.from_env(require_guarded_local=False)


def test_invalid_guard_policy_is_fail_closed(local_configuration, monkeypatch):
    monkeypatch.setenv("AI_LOCAL_GUARD_REQUIRED", "maybe")
    with pytest.raises(ProviderUnavailableError, match="invalid AI_LOCAL_GUARD_REQUIRED"):
        ProviderRegistry.from_env()


@pytest.mark.asyncio
async def test_explicit_legacy_reference_artifact_runs_without_hosted_provider(
    tmp_path, monkeypatch, local_configuration,
):
    from skeleton.ai.runtime.inference.local import ReferenceNGramModel
    from skeleton.ai.runtime.inference.artifact import write_local_model_artifact
    from skeleton.provider_runtime import ProviderRequest

    path = tmp_path / "operator-reference-model.json"
    trained = ReferenceNGramModel.train(
        ("local engine answer complete",), order=2, model_id="development-reference",
    )
    write_local_model_artifact(trained, path)
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", str(path))
    monkeypatch.setenv("AI_LOCAL_GUARD_REQUIRED", "0")
    monkeypatch.setenv("AI_LOCAL_LEGACY_DEV_ACK", "unsafe-local-dev-only")
    monkeypatch.setenv("AI_DEPLOYMENT_ENV", "development")
    registry = ProviderRegistry.from_env(require_guarded_local=False)
    adapter = registry.require_active()
    result = await adapter.generate(
        ProviderRequest(
            prompt="local engine", instructions="Respond locally.",
            max_output_tokens=8,
        )
    )
    assert result.provider == "local"
    assert result.model == trained.model_id
    assert result.text == "answer complete"
    assert result.usage.billed_cost == "0"
    assert adapter.require_guarded_inference is False
    # Generic transfer-policy admission does not claim sealed-context review.
    assert result.governance_decision_id is not None
    assert result.context_id is None
    assert result.context_digest is None
    assert result.execution_receipt_digest is None
    assert result.admission_decision_id is not None
