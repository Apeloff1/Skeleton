from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError

import pytest

from skeleton.automation.free_model import FreeModelClient, ModelError, redact_secrets
from skeleton.jeeves.providers import AnthropicProvider, OpenAIProvider
from skeleton.provider_contract import load_provider_architecture
from skeleton.provider_runtime import OpenAISyncProviderAdapter, ProviderRequest


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _limit: int) -> bytes:
        return self._payload


def _automation_env(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_API_URL", "https://provider.example/v1/chat/completions")
    monkeypatch.setenv("MODEL_API_KEY", "test-automation-key")
    monkeypatch.setenv("MODEL_NAME", "test-model")


def test_shared_runtime_and_automation_receipts_load_active_contract() -> None:
    runtime = load_provider_architecture("openai", provider_family="runtime_model")
    automation = load_provider_architecture(
        "repository-automation",
        provider_family="automation_model",
    )

    assert runtime.architecture_tag == automation.architecture_tag
    assert runtime.construction_version == automation.construction_version
    assert runtime.provider_family == "runtime_model"
    assert automation.provider_family == "automation_model"
    assert runtime.contract_digest == automation.contract_digest


@pytest.mark.parametrize(
    "url",
    [
        "http://provider.example/v1",
        "https://user:pass@provider.example/v1",
        "https://localhost/v1",
        "https://service.localhost/v1",
        "https://127.0.0.1/v1",
        "https://10.0.0.1/v1",
        "https://169.254.169.254/latest/meta-data",
        "https://metadata.google.internal/computeMetadata/v1",
        "https://provider.example/v1?target=elsewhere",
        "https://provider.example/v1#fragment",
    ],
)
def test_automation_model_rejects_unsafe_endpoints(monkeypatch, url: str) -> None:
    _automation_env(monkeypatch)
    monkeypatch.setenv("MODEL_API_URL", url)

    with pytest.raises(ModelError):
        FreeModelClient()


def test_automation_model_status_exposes_receipt_without_secret(monkeypatch) -> None:
    _automation_env(monkeypatch)

    client = FreeModelClient()
    status = client.status()

    assert status["provider_id"] == "repository-automation"
    assert status["provider_family"] == "automation_model"
    assert status["architecture"]["provider_family"] == "automation_model"
    assert "test-automation-key" not in json.dumps(status)


def test_automation_model_redacts_prompt_secrets_before_network(monkeypatch) -> None:
    _automation_env(monkeypatch)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response(
            json.dumps(
                {"choices": [{"message": {"content": "clean answer"}}]}
            ).encode("utf-8")
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = FreeModelClient()

    result = client.chat("system sk-1234567890abcdefghijkl", "token=supersecretvalue")

    assert result == "clean answer"
    body = captured["request"].data.decode("utf-8")
    assert "sk-1234567890abcdefghijkl" not in body
    assert "supersecretvalue" not in body
    assert "[REDACTED]" in body


def test_automation_model_sanitizes_network_failure(monkeypatch) -> None:
    _automation_env(monkeypatch)

    def fail(*_args, **_kwargs):
        raise URLError("Bearer abcdefghijklmnopqrstuvwxyz")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    client = FreeModelClient()

    with pytest.raises(ModelError) as exc:
        client.chat("rules", "work")

    assert "abcdefghijklmnopqrstuvwxyz" not in str(exc.value)


def test_jeeves_openai_requires_shared_receipt(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = OpenAIProvider()

    assert provider.available() is True
    assert provider._architecture_receipt is not None
    assert provider._architecture_receipt.provider_family == "runtime_model"


def test_jeeves_anthropic_is_denied_until_declared(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = AnthropicProvider()

    assert provider.available() is False
    with pytest.raises(RuntimeError, match="not declared"):
        provider.complete("hello")


def test_secret_redactor_covers_repository_provider_tokens() -> None:
    assert "sk-secret" not in redact_secrets(
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz and sk-abcdefghijklmnop"
    )


def test_sync_openai_transport_uses_canonical_receipts(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response(
            json.dumps(
                {
                    "id": "resp-sync",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": "sync answer"}
                            ],
                        }
                    ],
                }
            ).encode("utf-8")
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = OpenAISyncProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        timeout_seconds=5,
        max_retries=0,
    )

    response = adapter.generate_sync(
        ProviderRequest(
            instructions="answer safely",
            prompt="hello",
            max_output_tokens=128,
            operation_id="sync-provider-test",
        )
    )

    assert response.text == "sync answer"
    assert response.provider == "openai"
    assert response.model == "test-model"
    assert response.request_id == "resp-sync"
    assert response.governance_decision_id.startswith("gov-")
    assert response.admission_decision_id.startswith("adm-")
    assert captured["timeout"] == 5
    assert captured["request"].full_url == "https://api.openai.com/v1/responses"
    assert captured["request"].get_header("Authorization") == "Bearer test-runtime-key"


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.openai.com/v1",
        "https://localhost/v1",
        "https://127.0.0.1/v1",
        "https://169.254.169.254/v1",
        "https://user:pass@api.openai.com/v1",
    ],
)
def test_sync_openai_transport_rejects_unsafe_endpoint(
    base_url: str,
) -> None:
    adapter = OpenAISyncProviderAdapter(
        api_key="test-runtime-key",
        base_url=base_url,
    )

    assert adapter.available is False


def test_jeeves_provider_module_contains_no_runtime_credentials_or_transport() -> None:
    source = Path("skeleton/jeeves/providers.py").read_text(encoding="utf-8")

    for forbidden in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "SKELETON_OPENAI_API_KEY",
        "SKELETON_ANTHROPIC_API_KEY",
        "urllib.request",
        "api.openai.com",
        "api.anthropic.com",
    ):
        assert forbidden not in source

    assert "OpenAISyncProviderAdapter" in source
    assert "ProviderRequest" in source
