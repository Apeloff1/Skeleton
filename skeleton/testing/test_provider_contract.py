from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError

import pytest

from skeleton.automation.free_model import FreeModelClient, ModelError, redact_secrets
from skeleton.jeeves.providers import AnthropicProvider, OpenAIProvider
from skeleton.provider_contract import (
    FinishReason,
    ProviderProtocolError,
    ProviderToolCall,
    ProviderToolDefinition,
    ProviderUsage,
    load_provider_architecture,
)
from skeleton.provider_runtime import (
    OpenAISyncProviderAdapter,
    ProviderAdapter,
    ProviderInvocationError,
    ProviderRequest,
    ProviderResponse,
    provider_response_deltas,
)


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



def _tool_definition(name: str = "repo.read") -> ProviderToolDefinition:
    return ProviderToolDefinition(
        tool_id=name,
        description="Read a repository file",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )


def test_provider_tool_call_digest_is_canonical_and_self_validating() -> None:
    left = ProviderToolCall(
        call_id="call-1",
        tool_id="repo.read",
        arguments={"b": 2, "a": 1},
    )
    right = ProviderToolCall(
        call_id="call-2",
        tool_id="repo.read",
        arguments={"a": 1, "b": 2},
    )

    assert left.arguments_digest == right.arguments_digest
    with pytest.raises(ProviderProtocolError, match="does not match"):
        ProviderToolCall(
            call_id="call-3",
            tool_id="repo.read",
            arguments={"a": 1},
            arguments_digest="0" * 64,
        )


def test_provider_usage_keeps_unknown_values_unknown() -> None:
    usage = ProviderUsage(usage_source="unknown")

    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.total_tokens is None
    assert usage.billed_cost is None
    assert usage.as_dict()["usage_source"] == "unknown"


def test_sync_openai_accepts_tool_only_response_and_normalizes_call(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            json.dumps(
                {
                    "id": "resp-tool",
                    "status": "completed",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call-1",
                            "name": "repo.read",
                            "arguments": json.dumps({"path": "README.md"}),
                        }
                    ],
                    "usage": {
                        "input_tokens": 12,
                        "output_tokens": 4,
                        "total_tokens": 16,
                    },
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
            instructions="use tools when needed",
            prompt="read README",
            operation_id="tool-only-test",
            tools=(_tool_definition(),),
            tool_choice="required",
        )
    )

    assert response.text is None
    assert response.finish_reason is FinishReason.TOOL_CALLS
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].tool_id == "repo.read"
    assert response.tool_calls[0].arguments == {"path": "README.md"}
    assert response.usage.input_tokens == 12
    assert response.usage.total_tokens == 16
    assert captured["body"]["tools"][0]["name"] == "repo.read"
    assert captured["body"]["tool_choice"] == "required"


def test_sync_openai_rejects_unoffered_tool_call(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return _Response(
            json.dumps(
                {
                    "id": "resp-tool",
                    "status": "completed",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call-1",
                            "name": "repo.delete",
                            "arguments": "{}",
                        }
                    ],
                }
            ).encode("utf-8")
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = OpenAISyncProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        max_retries=0,
    )

    with pytest.raises(ProviderInvocationError, match="unoffered tool"):
        adapter.generate_sync(
            ProviderRequest(
                instructions="read only",
                prompt="inspect",
                operation_id="unoffered-tool-test",
                tools=(_tool_definition("repo.read"),),
            )
        )


def test_sync_openai_normalizes_structured_output(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            json.dumps(
                {
                    "id": "resp-json",
                    "status": "completed",
                    "output_text": json.dumps({"answer": 42}),
                    "output": [],
                }
            ).encode("utf-8")
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = OpenAISyncProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        max_retries=0,
    )

    response = adapter.generate_sync(
        ProviderRequest(
            instructions="return json",
            prompt="answer",
            operation_id="structured-test",
            structured_output_schema={
                "type": "object",
                "properties": {"answer": {"type": "integer"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
        )
    )

    assert response.structured_output == {"answer": 42}
    assert response.finish_reason is FinishReason.COMPLETED
    assert captured["body"]["text"]["format"]["type"] == "json_schema"


def test_sync_openai_deadline_clamps_transport_timeout(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        return _Response(
            json.dumps(
                {
                    "id": "resp-deadline",
                    "status": "completed",
                    "output_text": "ok",
                    "output": [],
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
            instructions="answer",
            prompt="hello",
            operation_id="deadline-test",
            deadline=datetime.now(timezone.utc) + timedelta(seconds=1),
        )
    )

    assert response.text == "ok"
    assert 0 < captured["timeout"] <= 1.0


def test_sync_openai_rejects_expired_deadline_before_network(monkeypatch) -> None:
    called = {"network": 0}

    def fake_urlopen(request, timeout):
        called["network"] += 1
        raise AssertionError("network must not be reached")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = OpenAISyncProviderAdapter(
        api_key="test-runtime-key",
        model="test-model",
        max_retries=0,
    )

    with pytest.raises(ProviderInvocationError, match="deadline exceeded"):
        adapter.generate_sync(
            ProviderRequest(
                instructions="answer",
                prompt="hello",
                operation_id="expired-deadline-test",
                deadline=datetime.now(timezone.utc) - timedelta(seconds=1),
            )
        )

    assert called["network"] == 0



def test_normalized_response_decomposes_into_ordered_neutral_deltas() -> None:
    usage = ProviderUsage(
        input_tokens=10,
        output_tokens=4,
        total_tokens=14,
        usage_source="provider",
    )
    tool_call = ProviderToolCall(
        call_id="call-1",
        tool_id="repo.read",
        arguments={"path": "README.md"},
    )
    response = ProviderResponse(
        text="answer",
        provider="test",
        model="model",
        response_id="resp-1",
        structured_output={"answer": 42},
        tool_calls=(tool_call,),
        finish_reason=FinishReason.TOOL_CALLS,
        usage=usage,
    )

    deltas = provider_response_deltas(
        response,
        emitted_at=datetime(2026, 9, 24, 0, 30, tzinfo=timezone.utc),
    )

    assert [delta.sequence for delta in deltas] == [0, 1, 2, 3, 4]
    assert [delta.kind.value for delta in deltas] == [
        "text",
        "structured",
        "tool_call",
        "usage",
        "final",
    ]
    assert deltas[0].text == "answer"
    assert deltas[1].structured_fragment == {"answer": 42}
    assert deltas[2].tool_call == tool_call
    assert deltas[3].usage == usage
    assert deltas[4].finish_reason is FinishReason.TOOL_CALLS
    assert all(delta.response_id == "resp-1" for delta in deltas)


@pytest.mark.asyncio
async def test_default_provider_stream_uses_neutral_delta_contract() -> None:
    calls = {"generate": 0}

    class FakeAdapter(ProviderAdapter):
        provider_id = "fake"
        model = "fake-model"

        @property
        def available(self) -> bool:
            return True

        async def generate(self, request: ProviderRequest) -> ProviderResponse:
            calls["generate"] += 1
            return ProviderResponse(
                text="hello",
                provider=self.provider_id,
                model=self.model,
                response_id="resp-stream",
                finish_reason=FinishReason.COMPLETED,
                usage=ProviderUsage(
                    input_tokens=1,
                    output_tokens=1,
                    total_tokens=2,
                    usage_source="provider",
                ),
            )

    request = ProviderRequest(
        instructions="answer",
        prompt="hello",
        operation_id="stream-test",
    )
    deltas = [delta async for delta in FakeAdapter().stream(request)]

    assert calls["generate"] == 1
    assert [delta.kind.value for delta in deltas] == ["text", "usage", "final"]
    assert deltas[-1].finish_reason is FinishReason.COMPLETED
    assert deltas[-1].response_id == "resp-stream"
