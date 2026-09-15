"""Fail-closed coverage regressions for both process-safety scanner planes."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from scripts import check_process_safety as backend_gate

REPO_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_GATE_PATH = REPO_ROOT / "scripts" / "check_repository_process_safety.py"
SPEC = importlib.util.spec_from_file_location("repository_process_safety_coverage", REPOSITORY_GATE_PATH)
assert SPEC is not None and SPEC.loader is not None
repository_gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repository_gate)

SENTINEL = "SENSITIVE_TRAVERSAL_OR_PARSE_DETAIL"


def _nested_failure_scandir(blocked: Path):
    real_scandir = os.scandir

    def scan(path):
        if Path(path) == blocked:
            raise PermissionError(SENTINEL)
        return real_scandir(path)

    return scan


def test_backend_gate_fails_closed_on_nested_traversal_error(tmp_path, monkeypatch, capsys) -> None:
    root = tmp_path / "backend"
    blocked = root / "blocked"
    blocked.mkdir(parents=True)
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(backend_gate, "ROOT", root)
    monkeypatch.setattr(backend_gate, "_scandir", _nested_failure_scandir(blocked), raising=False)

    assert backend_gate.main() == 1
    stderr = capsys.readouterr().err
    assert "PermissionError" in stderr
    assert SENTINEL not in stderr


def test_repository_gate_fails_closed_on_nested_traversal_error(tmp_path, monkeypatch, capsys) -> None:
    root = tmp_path / "runtime"
    blocked = root / "blocked"
    blocked.mkdir(parents=True)
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(repository_gate, "SCAN_ROOTS", (root,))
    monkeypatch.setattr(repository_gate, "_scandir", _nested_failure_scandir(blocked), raising=False)

    assert repository_gate.main() == 1
    stderr = capsys.readouterr().err
    assert "PermissionError" in stderr
    assert SENTINEL not in stderr


def test_backend_gate_redacts_read_failure_details(tmp_path, monkeypatch) -> None:
    target = tmp_path / "sample.py"
    target.write_text("value = 1\n", encoding="utf-8")
    real_read_text = Path.read_text

    def fail_read(self, *args, **kwargs):
        if self == target:
            raise PermissionError(SENTINEL)
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read)
    findings = backend_gate.violations(target)
    assert any("parse failure (PermissionError)" in finding for finding in findings)
    assert all(SENTINEL not in finding for finding in findings)


def test_repository_gate_redacts_read_failure_details(tmp_path, monkeypatch) -> None:
    target = tmp_path / "sample.py"
    target.write_text("value = 1\n", encoding="utf-8")
    real_read_text = Path.read_text

    def fail_read(self, *args, **kwargs):
        if self == target:
            raise PermissionError(SENTINEL)
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read)
    findings = repository_gate.violations(target)
    assert findings
    assert any("parse failure (PermissionError)" in finding for finding in findings)
    assert all(SENTINEL not in finding for finding in findings)


def test_repository_gate_fails_closed_when_required_root_is_missing(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(repository_gate, "SCAN_ROOTS", (tmp_path / "missing",))

    assert repository_gate.main() == 1
    stderr = capsys.readouterr().err
    assert "FileNotFoundError" in stderr


def test_repository_gate_fails_closed_on_zero_python_coverage(tmp_path, monkeypatch, capsys) -> None:
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    monkeypatch.setattr(repository_gate, "SCAN_ROOTS", (empty_root,))

    assert repository_gate.main() == 1
    assert "no repository Python files were scanned" in capsys.readouterr().err
