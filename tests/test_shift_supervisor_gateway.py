import json
import os
from unittest.mock import patch

from core.shift_supervisor.model_gateway import ModelGateway, ModelRequestError


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_gateway_reads_credentials_at_call_time(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gateway = ModelGateway(max_attempts=1)
    monkeypatch.setenv("OPENAI_API_KEY", "runtime-key")
    monkeypatch.setenv("SHIFT_MODEL_NAME", "test-model")

    captured = {}

    def fake_urlopen(request, timeout):
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse({"choices": [{"message": {"content": '{"ok": true}'}}]})

    with patch("urllib.request.urlopen", fake_urlopen):
        result = gateway.call_json(
            system_prompt="system",
            user_prompt="user",
            correlation_id="corr-1",
        )

    assert result == {"ok": True}
    assert captured["authorization"] == "Bearer runtime-key"
    assert captured["body"]["model"] == "test-model"


def test_gateway_fails_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    gateway = ModelGateway(max_attempts=1)
    try:
        gateway.call_json(system_prompt="s", user_prompt="u", correlation_id="c")
    except ModelRequestError as exc:
        assert "OPENAI_API_KEY" in str(exc)
    else:
        raise AssertionError("expected ModelRequestError")
