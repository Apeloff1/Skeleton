from __future__ import annotations

import json

import pytest

from skeleton.automation.chatgpt_adapter import ChatGPTReasoner, ReasoningRequest


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.payload


def test_reasoner_is_disabled_without_api_key() -> None:
    result = ChatGPTReasoner(api_key="").reason(
        ReasoningRequest("diagnose", ("safe evidence",))
    )

    assert result.ok is False
    assert result.error_kind == "missing_api_key"


def test_redaction_removes_credentials_without_destroying_digests() -> None:
    text = (
        "Authorization: Bearer super-secret-token\n"
        "api_key=abc123\n"
        "ghp_abcdefghijklmnopqrstuvwxyz123456\n"
        "sha256:0123456789abcdef"
    )

    redacted = ChatGPTReasoner.redact(text)

    assert "super-secret-token" not in redacted
    assert "abc123" not in redacted
    assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in redacted
    assert "0123456789abcdef" in redacted


def test_raw_responses_api_output_is_extracted_from_message_content() -> None:
    payload = {
        "output": [
            {"type": "reasoning", "summary": []},
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "first"},
                    {"type": "output_text", "text": "second"},
                ],
            },
        ]
    }

    assert ChatGPTReasoner._extract_output_text(payload) == "first\nsecond"


def test_direct_output_text_is_supported_as_tolerant_fallback() -> None:
    assert ChatGPTReasoner._extract_output_text({"output_text": "answer"}) == "answer"


def test_reason_redacts_bounded_input_and_structured_output(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(api_request, timeout):
        captured["timeout"] = timeout
        captured["payload"] = json.loads(api_request.data.decode("utf-8"))
        body = json.dumps(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "result token=server-secret",
                            }
                        ],
                    }
                ]
            }
        ).encode("utf-8")
        return _Response(body)

    monkeypatch.setattr(
        "skeleton.automation.chatgpt_adapter.request.urlopen",
        fake_urlopen,
    )
    reasoner = ChatGPTReasoner(api_key="test-key", timeout=5)
    result = reasoner.reason(
        ReasoningRequest(
            "diagnose token=task-secret",
            tuple(["api_key=evidence-secret"] * 20),
            max_output_chars=200,
        )
    )

    assert result.ok is True
    assert "server-secret" not in result.text
    assert "[REDACTED]" in result.text
    assert captured["timeout"] == 5.0

    payload = captured["payload"]
    assert isinstance(payload, dict)
    user_content = payload["input"][1]["content"]
    assert "task-secret" not in user_content
    assert "evidence-secret" not in user_content
    assert user_content.count("[REDACTED]") == 21


def test_oversized_inputs_fail_before_redaction_or_network(monkeypatch) -> None:
    called = False

    def fail_urlopen(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("network should not be called")

    monkeypatch.setattr(
        "skeleton.automation.chatgpt_adapter.request.urlopen",
        fail_urlopen,
    )
    reasoner = ChatGPTReasoner(api_key="test-key")

    cases = (
        (
            ReasoningRequest("x" * 20_001, ()),
            "task_too_large",
        ),
        (
            ReasoningRequest("diagnose", tuple("x" for _ in range(21))),
            "too_many_evidence_items",
        ),
        (
            ReasoningRequest("diagnose", ("x" * 20_001,)),
            "evidence_too_large",
        ),
    )

    for request_data, expected_error in cases:
        result = reasoner.reason(request_data)
        assert result.ok is False
        assert result.error_kind == expected_error

    assert called is False


def test_reasoning_request_rejects_invalid_output_limit_without_network(monkeypatch) -> None:
    called = False

    def fail_urlopen(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("network should not be called")

    monkeypatch.setattr(
        "skeleton.automation.chatgpt_adapter.request.urlopen",
        fail_urlopen,
    )

    for limit in (0, -1, True, 20_001):
        result = ChatGPTReasoner(api_key="test-key").reason(
            ReasoningRequest("diagnose", (), max_output_chars=limit)  # type: ignore[arg-type]
        )
        assert result.ok is False
        assert result.error_kind == "invalid_output_limit"

    assert called is False


def test_reasoner_rejects_invalid_request_shapes_without_network(monkeypatch) -> None:
    called = False

    def fail_urlopen(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("network should not be called")

    monkeypatch.setattr(
        "skeleton.automation.chatgpt_adapter.request.urlopen",
        fail_urlopen,
    )
    reasoner = ChatGPTReasoner(api_key="test-key")

    assert reasoner.reason("not-a-request").error_kind == "invalid_request"  # type: ignore[arg-type]
    assert reasoner.reason(ReasoningRequest("diagnose", ["bad"])) .error_kind == "invalid_request"  # type: ignore[arg-type]
    assert reasoner.reason(ReasoningRequest("diagnose", (1,))).error_kind == "invalid_request"  # type: ignore[arg-type]
    assert called is False


def test_reasoner_rejects_non_finite_timeout_and_oversized_key() -> None:
    with pytest.raises(ValueError, match="finite"):
        ChatGPTReasoner(api_key="test-key", timeout=float("inf"))
    with pytest.raises(TypeError, match="timeout"):
        ChatGPTReasoner(api_key="test-key", timeout=True)
    with pytest.raises(ValueError, match="api_key"):
        ChatGPTReasoner(api_key="x" * 4_097)


def test_timeout_is_clamped_to_safe_range() -> None:
    assert ChatGPTReasoner(api_key="test-key", timeout=0.01).timeout == 1.0
    assert ChatGPTReasoner(api_key="test-key", timeout=600).timeout == 60.0


def test_oversized_response_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        "skeleton.automation.chatgpt_adapter.request.urlopen",
        lambda *_args, **_kwargs: _Response(b"x" * 512_001),
    )

    result = ChatGPTReasoner(api_key="test-key").reason(
        ReasoningRequest("diagnose", ())
    )

    assert result.ok is False
    assert result.error_kind == "response_too_large"


def test_invalid_or_missing_output_fails_closed(monkeypatch) -> None:
    reasoner = ChatGPTReasoner(api_key="test-key")

    monkeypatch.setattr(
        "skeleton.automation.chatgpt_adapter.request.urlopen",
        lambda *_args, **_kwargs: _Response(b"not-json"),
    )
    invalid = reasoner.reason(ReasoningRequest("diagnose", ()))
    assert invalid.ok is False
    assert invalid.error_kind == "invalid_response"

    monkeypatch.setattr(
        "skeleton.automation.chatgpt_adapter.request.urlopen",
        lambda *_args, **_kwargs: _Response(b'{"output":[]}'),
    )
    missing = reasoner.reason(ReasoningRequest("diagnose", ()))
    assert missing.ok is False
    assert missing.error_kind == "missing_output"

def test_reasoner_with_key_loads_mandatory_automation_architecture() -> None:
    reasoner = ChatGPTReasoner(api_key="test-key")

    assert reasoner.architecture_receipt is not None
    assert reasoner.architecture_receipt.provider_id == "repository-automation"
    assert reasoner.architecture_receipt.provider_family == "automation_model"
