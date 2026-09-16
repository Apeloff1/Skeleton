from __future__ import annotations

import subprocess

import pytest

from core.shift_supervisor.model_gateway import ModelGateway
from skeleton.automation import activation_security as security
from skeleton.automation.chatgpt_adapter import ChatGPTReasoner


@pytest.fixture(autouse=True)
def _clear_activation_cache() -> None:
    security._VERIFIED.clear()
    yield
    security._VERIFIED.clear()


def test_non_bot_workflow_skips_activation_subprocess(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WORKFLOW", "Workflow Input Security")

    def unexpected(*_args, **_kwargs):
        raise AssertionError("security subprocess should not run outside bot workflows")

    monkeypatch.setattr(security.subprocess, "run", unexpected)
    security.enforce_bot_activation_security()


def test_gated_workflow_runs_all_checks_without_credentials(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WORKFLOW", "Idle Studio")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("OPENAI_API_KEY", "model-secret")
    monkeypatch.setenv("GH_TOKEN", "github-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "github-secret-2")
    calls: list[tuple[list[str], dict]] = []

    def fake_run(args, **kwargs):
        calls.append((list(args), kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    monkeypatch.setattr(security.subprocess, "run", fake_run)
    security.enforce_bot_activation_security()

    assert len(calls) == len(security.SECURITY_GATES)
    for _args, kwargs in calls:
        child_env = kwargs["env"]
        assert "OPENAI_API_KEY" not in child_env
        assert "GH_TOKEN" not in child_env
        assert "GITHUB_TOKEN" not in child_env
        assert kwargs["check"] is False
        assert kwargs["stdout"] == subprocess.PIPE
        assert kwargs["stderr"] == subprocess.PIPE


def test_gated_workflow_fails_closed_without_leaking_checker_output(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WORKFLOW", "Autonomous Studio Night Shift")
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)
    leaked = "credential-value-that-must-not-escape"

    def fake_run(args, **_kwargs):
        return subprocess.CompletedProcess(args, 7, stdout=leaked, stderr=leaked)

    monkeypatch.setattr(security.subprocess, "run", fake_run)
    with pytest.raises(security.ActivationSecurityError) as exc_info:
        security.enforce_bot_activation_security()

    assert leaked not in str(exc_info.value)
    assert "failed" in str(exc_info.value)


def test_successful_baseline_is_cached_per_workflow_and_sha(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WORKFLOW", "Shift Supervisor Control")
    monkeypatch.setenv("GITHUB_SHA", "c" * 40)
    calls = 0

    def fake_run(args, **_kwargs):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(security.subprocess, "run", fake_run)
    security.enforce_bot_activation_security()
    security.enforce_bot_activation_security()

    assert calls == len(security.SECURITY_GATES)


def test_chatgpt_reasoner_checks_activation_before_key_or_network(monkeypatch) -> None:
    def blocked() -> None:
        raise security.ActivationSecurityError("blocked-before-model")

    monkeypatch.setattr(
        "skeleton.automation.chatgpt_adapter.enforce_bot_activation_security",
        blocked,
    )
    with pytest.raises(security.ActivationSecurityError, match="blocked-before-model"):
        ChatGPTReasoner(api_key="")


def test_shift_supervisor_checks_activation_before_provider_config(monkeypatch) -> None:
    def blocked() -> None:
        raise security.ActivationSecurityError("blocked-before-supervisor-model")

    monkeypatch.setattr(
        "core.shift_supervisor.model_gateway.enforce_bot_activation_security",
        blocked,
    )
    with pytest.raises(
        security.ActivationSecurityError,
        match="blocked-before-supervisor-model",
    ):
        ModelGateway().call_json(
            system_prompt="system",
            user_prompt="user",
            correlation_id="test",
        )
