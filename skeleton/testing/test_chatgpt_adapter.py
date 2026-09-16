from skeleton.automation.chatgpt_adapter import ChatGPTReasoner, ReasoningRequest


def test_reasoner_is_disabled_without_api_key():
    result = ChatGPTReasoner(api_key="").reason(ReasoningRequest("diagnose", ("safe evidence",)))
    assert result.ok is False
    assert result.error_kind == "missing_api_key"


def test_redaction_removes_credentials_without_destroying_digests():
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


def test_reasoning_request_rejects_invalid_output_limit_without_network():
    result = ChatGPTReasoner(api_key="test-key").reason(
        ReasoningRequest("diagnose", (), max_output_chars=0)
    )
    assert result.ok is False
    assert result.error_kind == "invalid_output_limit"
