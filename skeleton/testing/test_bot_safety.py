from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.automation.bot_safety import (
    parse_test_command,
    safe_target,
    scrubbed_subprocess_env,
    write_plan_files,
)


def test_parse_test_command_accepts_only_fixed_shapes() -> None:
    assert parse_test_command("python tests/run_unit.py") == ["python", "tests/run_unit.py"]
    assert parse_test_command("python -m compileall -q skeleton") == [
        "python", "-m", "compileall", "-q", "skeleton"
    ]
    assert parse_test_command("python -m pytest -q tests/test_example.py") == [
        "python", "-m", "pytest", "-q", "tests/test_example.py"
    ]
    assert parse_test_command("python -m pytest -q skeleton/testing") == [
        "python", "-m", "pytest", "-q", "skeleton/testing"
    ]


@pytest.mark.parametrize(
    "command",
    [
        "python -c 'print(1)'",
        "python -m pytest -q -p malicious",
        "python -m pytest -q ../outside.py",
        "bash -lc 'echo unsafe'",
        "git status",
        "pytest -q tests/test_example.py",
    ],
)
def test_parse_test_command_rejects_execution_escape(command: str) -> None:
    with pytest.raises(RuntimeError, match="fixed allowlist"):
        parse_test_command(command)


def test_scrubbed_subprocess_env_removes_credentials_and_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setenv("GH_TOKEN", "secret")
    monkeypatch.setenv("MODEL_API_KEY", "secret")
    monkeypatch.setenv("ACTIONS_RUNTIME_TOKEN", "secret")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/sensitive/workspace")
    monkeypatch.setenv("PATH", "/usr/bin")

    clean = scrubbed_subprocess_env()

    assert "GITHUB_TOKEN" not in clean
    assert "GH_TOKEN" not in clean
    assert "MODEL_API_KEY" not in clean
    assert "ACTIONS_RUNTIME_TOKEN" not in clean
    assert "GITHUB_WORKSPACE" not in clean
    assert clean["PATH"] == "/usr/bin"


def test_safe_target_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "skeleton"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")

    with pytest.raises(RuntimeError, match="escapes workspace"):
        safe_target(root, "skeleton/payload.py")


def test_write_plan_files_does_not_follow_final_symlink(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    target_dir = root / "skeleton"
    target_dir.mkdir(parents=True)
    victim = tmp_path / "victim.txt"
    victim.write_text("sentinel", encoding="utf-8")
    link = target_dir / "module.py"
    try:
        link.symlink_to(victim)
    except OSError:
        pytest.skip("symlink creation unavailable")

    with pytest.raises(RuntimeError, match="symlink"):
        write_plan_files(
            root,
            [{"path": "skeleton/module.py", "content": "print('safe')\n"}],
        )
    assert victim.read_text(encoding="utf-8") == "sentinel"
