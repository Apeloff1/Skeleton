from __future__ import annotations

import pytest

from skeleton.ai.integrations.xai_oss import (
    XAIProviderConfig,
    XAIProviderEdge,
    require_sensitive_telemetry_disabled,
)


class _ChatClient:
    def __init__(self):
        self.calls = []

    def create(self, model, **kwargs):
        payload = {"model": model, **kwargs}
        self.calls.append(payload)
        return payload


class _FakeClient:
    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.chat = _ChatClient()


class _FakeSDK:
    Client = _FakeClient


def _importer(name: str):
    assert name == "xai_sdk"
    return _FakeSDK


def test_provider_credentials_are_ephemeral_client_inputs() -> None:
    config = XAIProviderConfig(model="grok-test")
    assert "api_key" not in config.__dataclass_fields__

    edge = XAIProviderEdge(config, importer=_importer)
    client = edge.create_client(api_key="ephemeral-secret")
    assert client.init_kwargs["api_key"] == "ephemeral-secret"
    assert client.init_kwargs["api_host"] == "api.x.ai"
    assert client.init_kwargs["use_insecure_channel"] is False


def test_server_side_tools_are_denied_by_default() -> None:
    edge = XAIProviderEdge(XAIProviderConfig(model="grok-test"), importer=_importer)
    client = edge.create_client(api_key="secret")
    with pytest.raises(PermissionError, match="server-side tools are disabled"):
        edge.create_chat(client, tools=(object(),))


def test_provider_chat_defaults_are_bounded_and_non_persistent() -> None:
    config = XAIProviderConfig(
        model="grok-test",
        reasoning_effort="high",
        max_turns=4,
        allow_server_side_tools=True,
    )
    edge = XAIProviderEdge(config, importer=_importer)
    client = edge.create_client(api_key="secret")
    result = edge.create_chat(client, messages=("m1",), tools=("tool",), user="u")
    assert result["model"] == "grok-test"
    assert result["store_messages"] is False
    assert result["use_encrypted_content"] is False
    assert result["max_turns"] == 4
    assert result["reasoning_effort"] == "high"
    assert result["parallel_tool_calls"] is True
    assert result["tools"] == ["tool"]


def test_insecure_provider_transport_is_localhost_only() -> None:
    with pytest.raises(ValueError, match="localhost"):
        XAIProviderConfig(
            model="grok-test",
            api_host="api.x.ai",
            allow_insecure_local_channel=True,
        )

    config = XAIProviderConfig(
        model="grok-test",
        api_host="localhost:50051",
        allow_insecure_local_channel=True,
    )
    assert config.allow_insecure_local_channel is True


def test_sensitive_telemetry_is_fail_closed() -> None:
    with pytest.raises(RuntimeError, match="not disabled"):
        require_sensitive_telemetry_disabled({})
    require_sensitive_telemetry_disabled(
        {"XAI_SDK_DISABLE_SENSITIVE_TELEMETRY_ATTRIBUTES": "true"}
    )
    config = XAIProviderConfig(model="grok-test")
    assert config.telemetry_environment() == {
        "XAI_SDK_DISABLE_SENSITIVE_TELEMETRY_ATTRIBUTES": "1"
    }
