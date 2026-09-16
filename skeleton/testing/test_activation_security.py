from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_activation_security():
    path = REPO_ROOT / "skeleton" / "automation" / "activation_security.py"
    spec = importlib.util.spec_from_file_location("activation_security_test_target", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


security = _load_activation_security()


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


def test_model_entrypoints_enforce_gate_before_provider_access() -> None:
    chatgpt_source = (
        REPO_ROOT / "skeleton" / "automation" / "chatgpt_adapter.py"
    ).read_text(encoding="utf-8")
    chatgpt_init = chatgpt_source.split("def __init__(", 1)[1].split("    @staticmethod", 1)[0]
    assert chatgpt_init.index("enforce_bot_activation_security()") < chatgpt_init.index(
        "resolved_key ="
    )

    supervisor_source = (
        REPO_ROOT / "core" / "shift_supervisor" / "model_gateway.py"
    ).read_text(encoding="utf-8")
    call_json = supervisor_source.split("def call_json(", 1)[1].split("    @staticmethod", 1)[0]
    assert call_json.index("enforce_bot_activation_security()") < call_json.index(
        "self._config()"
    )


def test_repair_intake_body_stays_inside_yaml_shell_block() -> None:
    workflow = (
        REPO_ROOT / ".github" / "workflows" / "repair-intake.yml"
    ).read_text(encoding="utf-8")

    assert "printf -v body '%s\\n'" in workflow
    assert "\nAutomated repair intake record.\n" not in workflow
    assert "--body \"$body\"" in workflow
