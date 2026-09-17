from __future__ import annotations

import io
import json
import urllib.error
from email.message import Message
from unittest.mock import patch

import pytest

from core.shift_supervisor.model_gateway import ModelGateway, ModelRequestError


def _http_error(*, code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://example.invalid", code, "error", headers, None)


def test_429_honors_retry_after_with_upper_bound() -> None:
    gateway = ModelGateway(max_retry_delay_seconds=30)

    assert gateway._retry_delay(_http_error(code=429, retry_after="12"), 1) == 12
    assert gateway._retry_delay(_http_error(code=429, retry_after="120"), 1) == 30


def test_invalid_or_unrelated_retry_after_uses_bounded_backoff() -> None:
    gateway = ModelGateway(max_retry_delay_seconds=30)

    assert gateway._retry_delay(_http_error(code=429, retry_after="later"), 2) == 2
    assert gateway._retry_delay(_http_error(code=503, retry_after="20"), 3) == 4


def test_rate_limit_can_use_extended_bounded_retry_budget(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "runtime-key")
    monkeypatch.delenv("SHIFT_MODEL_API_URL", raising=False)
    gateway = ModelGateway(max_attempts=6, max_non_rate_limit_attempts=3)
    calls = 0

    def fake_urlopen(_request, timeout):
        nonlocal calls
        calls += 1
        assert timeout == gateway.timeout_seconds
        if calls <= 3:
            raise _http_error(code=429, retry_after="0")
        return io.BytesIO(json.dumps({"output_text": '{"ok": true}'}).encode("utf-8"))

    with patch("urllib.request.urlopen", fake_urlopen), patch("time.sleep") as sleep:
        result = gateway.call_json(
            system_prompt="system",
            user_prompt="user",
            correlation_id="corr-rate-limit",
        )

    assert result == {"ok": True}
    assert calls == 4
    assert sleep.call_count == 3


def test_non_rate_limit_failures_keep_standard_retry_budget(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "runtime-key")
    monkeypatch.delenv("SHIFT_MODEL_API_URL", raising=False)
    gateway = ModelGateway(max_attempts=6, max_non_rate_limit_attempts=3)
    calls = 0

    def fake_urlopen(_request, timeout):
        nonlocal calls
        calls += 1
        assert timeout == gateway.timeout_seconds
        raise _http_error(code=503, retry_after="0")

    with patch("urllib.request.urlopen", fake_urlopen), patch("time.sleep") as sleep:
        with pytest.raises(ModelRequestError, match="after 3 attempts"):
            gateway.call_json(
                system_prompt="system",
                user_prompt="user",
                correlation_id="corr-standard-failure",
            )

    assert calls == 3
    assert sleep.call_count == 2
