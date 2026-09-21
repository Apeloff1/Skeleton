from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import subprocess

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SECURITY_PATH = REPO_ROOT / "skeleton" / "security" / "activation_security.py"
_SECURITY_SPEC = importlib.util.spec_from_file_location(
    "bot_activation_security_under_test",
    _SECURITY_PATH,
)
assert _SECURITY_SPEC is not None and _SECURITY_SPEC.loader is not None
security = importlib.util.module_from_spec(_SECURITY_SPEC)
_SECURITY_SPEC.loader.exec_module(security)


@pytest.fixture(autouse=True)
def _clear_activation_cache():
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


def _method(path: str, class_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse((REPO_ROOT / path).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    return child
    raise AssertionError(f"missing {class_name}.{method_name} in {path}")


def _is_activation_call(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == "enforce_bot_activation_security"
    )


def test_model_entrypoints_gate_before_configuration_or_network() -> None:
    reasoner_init = _method(
        "skeleton/automation/chatgpt_adapter.py",
        "ChatGPTReasoner",
        "__init__",
    )
    supervisor_call = _method(
        "core/shift_supervisor/model_gateway.py",
        "ModelGateway",
        "call_json",
    )

    assert reasoner_init.body and _is_activation_call(reasoner_init.body[0])
    assert supervisor_call.body and _is_activation_call(supervisor_call.body[0])


def test_model_entrypoints_import_dependency_free_gate() -> None:
    for relative in (
        "skeleton/automation/chatgpt_adapter.py",
        "core/shift_supervisor/model_gateway.py",
    ):
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert (
            "from skeleton.security.activation_security "
            "import enforce_bot_activation_security"
        ) in source
        assert "from core.activation_security import enforce_bot_activation_security" not in source


def test_repair_intake_issue_body_stays_inside_yaml_shell_block() -> None:
    workflow = (REPO_ROOT / ".github/workflows/repair-intake.yml").read_text(
        encoding="utf-8"
    )

    assert "printf -v body '%s\\n'" in workflow
    assert "\n${marker}\n" not in workflow
    assert "\n- Workflow: ${RUN_NAME}\n" not in workflow
    assert "\nCorrelate this observation against existing findings" not in workflow

def test_legacy_core_activation_module_is_a_thin_canonical_shim() -> None:
    source = (REPO_ROOT / "core" / "activation_security.py").read_text(encoding="utf-8")

    assert "from skeleton.security.activation_security import (" in source
    assert "run_bot_activation_security_baseline" in source
    assert 'if __name__ == "__main__":' in source
    assert "raise SystemExit(main())" in source
