"""Fail-closed coverage regressions for both process-safety enforcement planes."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BACKEND_GATE = _load(
    "process_safety_fail_closed_runner",
    REPO_ROOT / "backend" / "scripts" / "run_process_safety_gate.py",
)
REPOSITORY_GATE = _load(
    "repository_process_safety_fail_closed",
    REPO_ROOT / "scripts" / "check_repository_process_safety.py",
)


def test_backend_nested_directory_failure_blocks_without_raw_detail(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "hidden.py").write_text("print('hidden')\n", encoding="utf-8")
    (tmp_path / "visible.py").write_text("print('safe')\n", encoding="utf-8")
    real_scandir = os.scandir

    def guarded_scandir(path):
        if Path(path) == blocked:
            raise PermissionError("sensitive backend traversal detail")
        return real_scandir(path)

    monkeypatch.setattr(BACKEND_GATE, "ROOT", tmp_path)
    monkeypatch.setattr(BACKEND_GATE.os, "scandir", guarded_scandir)

    assert BACKEND_GATE.main() == 1
    captured = capsys.readouterr()
    assert "repository traversal failure: PermissionError" in captured.err
    assert "sensitive backend traversal detail" not in captured.err


def test_backend_zero_coverage_blocks(monkeypatch, capsys) -> None:
    monkeypatch.setattr(BACKEND_GATE, "python_files", lambda: iter(()))

    assert BACKEND_GATE.main() == 1
    assert "scanner coverage failure: no Python files were scanned" in capsys.readouterr().err


def test_backend_parse_failure_is_redacted(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "blocked.py"
    target.write_text("print('safe')\n", encoding="utf-8")
    original_read_text = Path.read_text

    def blocked_read_text(self: Path, *args, **kwargs):
        if self == target:
            raise PermissionError("sensitive backend parse detail")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", blocked_read_text)
    findings = BACKEND_GATE.violations(target)

    assert findings == [f"{target}: parse failure: PermissionError"]
    assert all("sensitive backend parse detail" not in finding for finding in findings)


def test_repository_nested_directory_failure_blocks_without_raw_detail(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    root = tmp_path / "runtime"
    blocked = root / "blocked"
    root.mkdir()
    blocked.mkdir()
    (blocked / "hidden.py").write_text("print('hidden')\n", encoding="utf-8")
    (root / "visible.py").write_text("print('safe')\n", encoding="utf-8")
    real_scandir = os.scandir

    def guarded_scandir(path):
        if Path(path) == blocked:
            raise PermissionError("sensitive repository traversal detail")
        return real_scandir(path)

    monkeypatch.setattr(REPOSITORY_GATE, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(REPOSITORY_GATE, "SCAN_ROOTS", (root,))
    monkeypatch.setattr(REPOSITORY_GATE.os, "scandir", guarded_scandir)

    assert REPOSITORY_GATE.main() == 1
    captured = capsys.readouterr()
    assert "repository traversal failure: PermissionError" in captured.err
    assert "sensitive repository traversal detail" not in captured.err


def test_repository_missing_required_root_blocks(monkeypatch, tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing-runtime-root"
    monkeypatch.setattr(REPOSITORY_GATE, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(REPOSITORY_GATE, "SCAN_ROOTS", (missing,))

    assert REPOSITORY_GATE.main() == 1
    captured = capsys.readouterr()
    assert "repository traversal failure: FileNotFoundError" in captured.err


def test_repository_zero_coverage_blocks(monkeypatch, capsys) -> None:
    monkeypatch.setattr(REPOSITORY_GATE, "python_files", lambda: iter(()))

    assert REPOSITORY_GATE.main() == 1
    assert "scanner coverage failure: no Python files were scanned" in capsys.readouterr().err


def test_repository_parse_failure_is_redacted(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "blocked.py"
    target.write_text("print('safe')\n", encoding="utf-8")
    original_read_text = Path.read_text

    def blocked_read_text(self: Path, *args, **kwargs):
        if self == target:
            raise PermissionError("sensitive repository parse detail")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", blocked_read_text)
    findings = REPOSITORY_GATE.violations(target)

    assert findings == [f"{target}: parse failure: PermissionError"]
    assert all("sensitive repository parse detail" not in finding for finding in findings)
