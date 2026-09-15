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


def test_backend_scanner_rejects_missing_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scanner = _load(BACKEND_SCANNER, "_test_backend_process_safety_missing")
    monkeypatch.setattr(scanner, "ROOT", tmp_path / "missing")

    with pytest.raises(scanner.ScanCoverageError, match="does not exist"):
        list(scanner.python_files())


def test_backend_scanner_rejects_zero_file_coverage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scanner = _load(BACKEND_SCANNER, "_test_backend_process_safety_empty")
    monkeypatch.setattr(scanner, "ROOT", tmp_path)

    with pytest.raises(scanner.ScanCoverageError, match="zero Python files"):
        list(scanner.python_files())


def test_backend_scanner_discovery_is_deterministic_and_skips_excluded_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scanner = _load(BACKEND_SCANNER, "_test_backend_process_safety_order")
    (tmp_path / "z.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    excluded = tmp_path / "__pycache__"
    excluded.mkdir()
    (excluded / "ignored.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(scanner, "ROOT", tmp_path)

    assert [path.name for path in scanner.python_files()] == ["a.py", "z.py"]


def test_backend_scanner_converts_traversal_error_to_coverage_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scanner = _load(BACKEND_SCANNER, "_test_backend_process_safety_walk_error")
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(scanner, "ROOT", tmp_path)

    def broken_walk(*args: object, **kwargs: object):
        raise OSError("simulated traversal failure")

    monkeypatch.setattr(scanner.os, "walk", broken_walk)

    with pytest.raises(scanner.ScanCoverageError, match="simulated traversal failure"):
        list(scanner.python_files())


def test_backend_scanner_main_returns_distinct_incomplete_scan_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _load(BACKEND_SCANNER, "_test_backend_process_safety_main")

    def incomplete_scan():
        raise scanner.ScanCoverageError("coverage lost")
        yield  # pragma: no cover

    monkeypatch.setattr(scanner, "python_files", incomplete_scan)

    assert scanner.main() == 2


def test_repository_scanner_rejects_missing_required_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scanner = _load(REPOSITORY_SCANNER, "_test_repository_process_safety_missing")
    existing = tmp_path / "existing"
    existing.mkdir()
    monkeypatch.setattr(scanner, "SCAN_ROOTS", (existing, tmp_path / "missing"))

    with pytest.raises(scanner.ScanCoverageError, match="does not exist"):
        list(scanner.python_files())


def test_repository_scanner_rejects_zero_file_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scanner = _load(REPOSITORY_SCANNER, "_test_repository_process_safety_empty")
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.setattr(scanner, "SCAN_ROOTS", (first, second))

    with pytest.raises(scanner.ScanCoverageError, match="zero Python files"):
        list(scanner.python_files())


def test_repository_scanner_converts_traversal_error_to_coverage_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scanner = _load(REPOSITORY_SCANNER, "_test_repository_process_safety_walk_error")
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(scanner, "SCAN_ROOTS", (root,))

    def broken_walk(*args: object, **kwargs: object):
        raise OSError("simulated traversal failure")

    monkeypatch.setattr(scanner.os, "walk", broken_walk)

    with pytest.raises(scanner.ScanCoverageError, match="simulated traversal failure"):
        list(scanner.python_files())


def test_repository_scanner_main_returns_distinct_incomplete_scan_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _load(REPOSITORY_SCANNER, "_test_repository_process_safety_main")

    def incomplete_scan():
        raise scanner.ScanCoverageError("coverage lost")
        yield  # pragma: no cover

    monkeypatch.setattr(scanner, "python_files", incomplete_scan)

    assert scanner.main() == 2
