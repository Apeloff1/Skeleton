from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.developer.bootstrap import (
    BootstrapError,
    REQUIRED_PYTHON,
    build_plan,
    execute_plan,
)


def _project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='skeleton-test'\nversion='0.0.0'\n",
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    return tmp_path


def test_bootstrap_plan_is_deterministic_and_locked(tmp_path: Path) -> None:
    root = _project(tmp_path)
    first = build_plan(root)
    second = build_plan(root)

    assert first == second
    assert first.python_version == REQUIRED_PYTHON
    assert first.commands == (
        ("uv", "python", "install", REQUIRED_PYTHON),
        ("uv", "sync", "--locked", "--python", REQUIRED_PYTHON, "--extra", "dev"),
    )
    assert len(first.project_digest) == 64
    assert len(first.lock_digest) == 64
    assert len(first.digest) == 64


def test_bootstrap_refuses_unlocked_dependency_resolution(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='skeleton-test'\nversion='0.0.0'\n",
        encoding="utf-8",
    )

    with pytest.raises(BootstrapError, match="missing uv.lock"):
        build_plan(tmp_path)


def test_bootstrap_receipt_changes_when_lock_changes(tmp_path: Path) -> None:
    root = _project(tmp_path)
    before = build_plan(root)
    (root / "uv.lock").write_text("version = 2\n", encoding="utf-8")
    after = build_plan(root)

    assert before.lock_digest != after.lock_digest
    assert before.digest != after.digest


def test_execute_plan_runs_only_declared_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = build_plan(_project(tmp_path))
    calls: list[tuple[tuple[str, ...], Path, bool]] = []

    monkeypatch.setattr("skeleton.developer.bootstrap.shutil.which", lambda name: "/usr/bin/uv")
    execute_plan(
        plan,
        runner=lambda command, *, cwd, check: calls.append(
            (tuple(command), Path(cwd), check)
        ),
    )

    assert [item[0] for item in calls] == list(plan.commands)
    assert all(item[1] == Path(plan.root) for item in calls)
    assert all(item[2] is True for item in calls)


def test_execute_plan_fails_closed_without_uv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = build_plan(_project(tmp_path))
    monkeypatch.setattr("skeleton.developer.bootstrap.shutil.which", lambda name: None)

    with pytest.raises(BootstrapError, match="uv is required"):
        execute_plan(plan)
