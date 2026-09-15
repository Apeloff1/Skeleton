from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SCANNER = REPO_ROOT / "backend" / "scripts" / "check_process_safety.py"
REPOSITORY_SCANNER = REPO_ROOT / "scripts" / "check_repository_process_safety.py"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backend_scanner_redacts_parse_exception_payload(tmp_path: Path) -> None:
    scanner = _load(BACKEND_SCANNER, "_test_backend_process_safety_redaction")
    source = tmp_path / "invalid.py"
    source.write_text("def broken(:\n    pass\n", encoding="utf-8")

    findings = scanner.violations(source)

    assert findings == [f"{source}: parse failure: SyntaxError"]
    assert "invalid syntax" not in findings[0]


def test_repository_scanner_redacts_parse_exception_payload(tmp_path: Path) -> None:
    scanner = _load(REPOSITORY_SCANNER, "_test_repository_process_safety_redaction")
    source = tmp_path / "invalid.py"
    source.write_text("def broken(:\n    pass\n", encoding="utf-8")

    findings = scanner.argv_violations(source)

    assert findings == [f"{source}: parse failure: SyntaxError"]
    assert "invalid syntax" not in findings[0]


def test_backend_scanner_nested_walk_error_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scanner = _load(BACKEND_SCANNER, "_test_backend_process_safety_nested_walk")
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(scanner, "ROOT", tmp_path)

    def broken_walk(*args: object, **kwargs: object):
        onerror = kwargs["onerror"]
        onerror(OSError("nested enumeration failed"))
        return iter(())

    monkeypatch.setattr(scanner.os, "walk", broken_walk)

    with pytest.raises(scanner.ScanCoverageError, match="nested enumeration failed"):
        list(scanner.python_files())


def test_repository_scanner_nested_walk_error_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scanner = _load(REPOSITORY_SCANNER, "_test_repository_process_safety_nested_walk")
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(scanner, "SCAN_ROOTS", (root,))

    def broken_walk(*args: object, **kwargs: object):
        onerror = kwargs["onerror"]
        onerror(OSError("nested enumeration failed"))
        return iter(())

    monkeypatch.setattr(scanner.os, "walk", broken_walk)

    with pytest.raises(scanner.ScanCoverageError, match="nested enumeration failed"):
        list(scanner.python_files())
