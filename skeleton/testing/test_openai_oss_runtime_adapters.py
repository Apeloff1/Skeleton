from __future__ import annotations

import pytest

from skeleton.ai.integrations.openai_oss import (
    AgentsSdkBridge,
    CodexApprovalMode,
    CodexInteropPolicy,
    CodexSandbox,
    EvalCase,
    ExternalAgentSpec,
    ExternalHandoffSpec,
    GptOssRuntimeConfig,
    WhisperAdapter,
    export_jsonl,
)


class _WhisperModel:
    def transcribe(self, audio, **kwargs):
        assert audio == "clip.wav"
        assert kwargs["task"] == "transcribe"
        return {
            "text": "hello world",
            "language": "en",
            "segments": [{"id": 0, "text": "hello world"}],
        }


def test_whisper_preloaded_model_never_needs_download() -> None:
    adapter = WhisperAdapter(model=_WhisperModel(), model_name="turbo")
    result = adapter.transcribe("clip.wav")
    assert result.text == "hello world"
    assert result.language == "en"
    assert result.model_name == "turbo"


def test_whisper_implicit_model_download_is_blocked() -> None:
    adapter = WhisperAdapter(model_name="turbo", allow_model_download=False)
    with pytest.raises(RuntimeError, match="implicit model download"):
        adapter.load()


class _Agent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _GuardrailOutput:
    def __init__(self, output_info, tripwire_triggered):
        self.output_info = output_info
        self.tripwire_triggered = tripwire_triggered


class _Agents:
    Agent = _Agent
    GuardrailFunctionOutput = _GuardrailOutput

    @staticmethod
    def handoff(agent, **kwargs):
        return {"agent": agent, **kwargs}


def _agents_importer(name: str):
    assert name == "agents"
    return _Agents


def test_agents_bridge_sanitizes_context_and_builds_handoff() -> None:
    bridge = AgentsSdkBridge(importer=_agents_importer)
    assert bridge.sanitize_context(
        {"objective": "x", "secret": "never", "tenant": "t"},
        allowed_keys=("objective", "tenant"),
    ) == {"objective": "x", "tenant": "t"}

    agent = bridge.create_agent(
        ExternalAgentSpec(
            name="reviewer",
            instructions="Review only.",
            handoff_description="Independent review",
        )
    )
    handoff = bridge.create_handoff(
        agent,
        ExternalHandoffSpec(tool_name="review"),
    )
    assert handoff["tool_name_override"] == "review"
    assert agent.kwargs["instructions"] == "Review only."


def test_codex_full_access_requires_three_explicit_gates() -> None:
    default = CodexInteropPolicy()
    assert not default.admit(
        CodexSandbox.FULL_ACCESS,
        CodexApprovalMode.AUTO_REVIEW,
        explicit_user_action=True,
    ).allowed

    enabled = CodexInteropPolicy(allow_full_access=True)
    assert not enabled.admit(
        CodexSandbox.FULL_ACCESS,
        CodexApprovalMode.DENY_ALL,
        explicit_user_action=True,
    ).allowed
    assert not enabled.admit(
        CodexSandbox.FULL_ACCESS,
        CodexApprovalMode.AUTO_REVIEW,
        explicit_user_action=False,
    ).allowed
    assert enabled.admit(
        CodexSandbox.FULL_ACCESS,
        CodexApprovalMode.AUTO_REVIEW,
        explicit_user_action=True,
    ).allowed


def test_evals_jsonl_is_deterministic_and_rejects_duplicate_ids() -> None:
    case = EvalCase(
        sample_id="case-1",
        input=[{"role": "user", "content": "2+2"}],
        ideal="4",
        metadata={"suite": "math"},
    )
    first = export_jsonl((case,))
    second = export_jsonl((case,))
    assert first == second
    assert '"sample_id":"case-1"' in first
    with pytest.raises(ValueError, match="duplicate"):
        export_jsonl((case, case))


def test_gpt_oss_tools_are_explicit_allowlist_only() -> None:
    assert GptOssRuntimeConfig(enabled_tools=frozenset()).enabled_tools == frozenset()
    configured = GptOssRuntimeConfig(enabled_tools=frozenset({"browser", "python"}))
    assert configured.enabled_tools == frozenset({"browser", "python"})
    with pytest.raises(ValueError, match="unsupported"):
        GptOssRuntimeConfig(enabled_tools=frozenset({"shell"}))
