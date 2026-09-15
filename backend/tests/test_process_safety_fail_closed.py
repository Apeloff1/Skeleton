from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SCANNER_PATH = REPO_ROOT / "backend" / "scripts" / "check_process_safety.py"
REPOSITORY_SCANNER_PATH = REPO_ROOT / "scripts" / "check_repository_process_safety.py"


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def backend_scanner() -> ModuleType:
    return _load_module("_test_backend_process_safety", BACKEND_SCANNER_PATH)


@pytest.fixture
def repository_scanner() -> ModuleType:
    return _load_module("_test_repository_process_safety", REPOSITORY_SCANNER_PATH)


def test_backend_nested_enumeration_failure_is_fail_closed(
    backend_scanner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "backend"
    blocked = root / "blocked"
    blocked.mkdir(parents=True)
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(backend_scanner, "ROOT", root)

    real_scandir = backend_scanner.os.scandir

    def guarded_scandir(path):
        if Path(path) == blocked:
            raise PermissionError("SECRET_BACKEND_PATH")
        return real_scandir(path)

    monkeypatch.setattr(backend_scanner.os, "scandir", guarded_scandir)

    assert backend_scanner.main() == 1
    captured = capsys.readouterr()
    assert "scanner coverage failure: source traversal failed" in captured.err
    assert "SECRET_BACKEND_PATH" not in captured.err


def test_backend_missing_root_is_fail_closed(
    backend_scanner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(backend_scanner, "ROOT", tmp_path / "missing")

    assert backend_scanner.main() == 1
    captured = capsys.readouterr()
    assert "scanner coverage failure: source traversal failed" in captured.err


def test_backend_zero_coverage_cannot_pass(
    backend_scanner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(backend_scanner, "ROOT", tmp_path)

    assert backend_scanner.main() == 1
    captured = capsys.readouterr()
    assert "no backend Python files were scanned" in captured.err


def test_backend_parse_failure_reports_class_not_payload(
    backend_scanner: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "broken.py"
    bad.write_text("def broken(:  # SECRET_PARSE_PAYLOAD\n    pass\n", encoding="utf-8")

    findings = backend_scanner.violations(bad)

    assert findings == [f"{bad}: parse failure: SyntaxError"]
    assert "SECRET_PARSE_PAYLOAD" not in findings[0]
    assert "invalid syntax" not in findings[0]


def test_repository_nested_enumeration_failure_is_fail_closed(
    repository_scanner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "runtime"
    blocked = root / "blocked"
    blocked.mkdir(parents=True)
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(repository_scanner, "SCAN_ROOTS", (root,))

    real_scandir = repository_scanner.BACKEND_GATE.os.scandir

    def guarded_scandir(path):
        if Path(path) == blocked:
            raise PermissionError("SECRET_REPOSITORY_PATH")
        return real_scandir(path)

    monkeypatch.setattr(repository_scanner.BACKEND_GATE.os, "scandir", guarded_scandir)

    assert repository_scanner.main() == 1
    captured = capsys.readouterr()
    assert "scanner coverage failure: source traversal failed" in captured.err
    assert "SECRET_REPOSITORY_PATH" not in captured.err


def test_repository_missing_required_root_is_fail_closed(
    repository_scanner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(repository_scanner, "SCAN_ROOTS", (tmp_path / "missing",))

    assert repository_scanner.main() == 1
    captured = capsys.readouterr()
    assert "scanner coverage failure: source traversal failed" in captured.err


def test_repository_zero_coverage_cannot_pass(
    repository_scanner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    roots = (tmp_path / "backend", tmp_path / "skeleton", tmp_path / "scripts")
    for root in roots:
        root.mkdir()
    monkeypatch.setattr(repository_scanner, "SCAN_ROOTS", roots)

    assert repository_scanner.main() == 1
    captured = capsys.readouterr()
    assert "no repository Python files were scanned" in captured.err


def test_repository_parse_failure_reports_class_not_payload(
    repository_scanner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bad = tmp_path / "broken.py"
    bad.write_text(
        "def broken(:  # REPOSITORY_SECRET_PAYLOAD\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(repository_scanner, "REPO_ROOT", tmp_path)

    findings = repository_scanner.argv_violations(bad)

    assert findings == ["broken.py: parse failure: SyntaxError"]
    assert "REPOSITORY_SECRET_PAYLOAD" not in findings[0]
    assert "invalid syntax" not in findings[0]


def test_backend_alias_and_shell_analysis_is_preserved(
    backend_scanner: ModuleType, tmp_path: Path
) -> None:
    unsafe = tmp_path / "unsafe.py"
    unsafe.write_text(
        "from subprocess import run as execute\n"
        "execute(['echo', 'hello'], shell=True)\n",
        encoding="utf-8",
    )

    findings = backend_scanner.violations(unsafe)

    assert any(
        "subprocess.run(..., shell=...) is forbidden unless shell=False is literal" in finding
        for finding in findings
    )
