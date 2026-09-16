import json
from unittest.mock import patch

from core.shift_supervisor.model_gateway import ModelGateway, ModelRequestError


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, *_args):
        return json.dumps(self.payload).encode("utf-8")


def test_gateway_reads_credentials_at_call_time_and_uses_responses_api(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SHIFT_MODEL_API_URL", raising=False)
    monkeypatch.delenv("SHIFT_MODEL_WEB_SEARCH", raising=False)
    gateway = ModelGateway(max_attempts=1)
    monkeypatch.setenv("OPENAI_API_KEY", "runtime-key")
    monkeypatch.setenv("SHIFT_MODEL_NAME", "test-model")

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": '{"ok": true}'}
                        ],
                    }
                ]
            }
        )

    with patch("urllib.request.urlopen", fake_urlopen):
        result = gateway.call_json(
            system_prompt="system",
            user_prompt="user",
            correlation_id="corr-1",
        )

    assert result == {"ok": True}
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["authorization"] == "Bearer runtime-key"
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["input"][0]["role"] == "system"
    assert captured["body"]["max_output_tokens"] == 8000
    assert "tools" not in captured["body"]


def test_gateway_can_enable_bounded_responses_web_search(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "runtime-key")
    monkeypatch.delenv("SHIFT_MODEL_API_URL", raising=False)
    monkeypatch.setenv("SHIFT_MODEL_WEB_SEARCH", "true")
    gateway = ModelGateway(max_attempts=1, max_tool_calls=4)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse(
            {"output_text": '{"summary":"researched","tasks":[]}' }
        )

    with patch("urllib.request.urlopen", fake_urlopen):
        result = gateway.call_json(
            system_prompt="system",
            user_prompt="user",
            correlation_id="corr-web",
        )

    assert result == {"summary": "researched", "tasks": []}
    assert captured["body"]["tools"] == [{"type": "web_search"}]
    assert captured["body"]["tool_choice"] == "auto"
    assert captured["body"]["max_tool_calls"] == 4
    assert captured["body"]["include"] == ["web_search_call.action.sources"]


def test_gateway_does_not_attach_openai_tools_to_chat_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "runtime-key")
    monkeypatch.setenv("SHIFT_MODEL_API_URL", "https://provider.example/v1/chat/completions")
    monkeypatch.setenv("SHIFT_MODEL_WEB_SEARCH", "1")
    gateway = ModelGateway(max_attempts=1)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse(
            {"choices": [{"message": {"content": '{"mode": "chat"}'}}]}
        )

    with patch("urllib.request.urlopen", fake_urlopen):
        result = gateway.call_json(
            system_prompt="system",
            user_prompt="user",
            correlation_id="corr-chat",
        )

    assert result == {"mode": "chat"}
    assert "messages" in captured["body"]
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert "tools" not in captured["body"]


def test_gateway_fails_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gateway = ModelGateway(max_attempts=1)
    try:
        gateway.call_json(system_prompt="s", user_prompt="u", correlation_id="c")
    except ModelRequestError as exc:
        assert "OPENAI_API_KEY" in str(exc)
    else:
        raise AssertionError("expected ModelRequestError")
