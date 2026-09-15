from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SCANNER = REPO_ROOT / "backend" / "scripts" / "check_process_safety.py"
REPOSITORY_SCANNER = REPO_ROOT / "scripts" / "check_repository_process_safety.py"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=["backend", "repository"])
def scanner(request: pytest.FixtureRequest) -> ModuleType:
    if request.param == "backend":
        return _load_module(BACKEND_SCANNER, "_test_backend_process_safety")
    return _load_module(REPOSITORY_SCANNER, "_test_repository_process_safety")


def _configure_scan_root(scanner: ModuleType, root: Path) -> None:
    if hasattr(scanner, "SCAN_ROOTS"):
        scanner.REPO_ROOT = root
        scanner.SCAN_ROOTS = (root,)
    else:
        scanner.ROOT = root


def _traversal_gate(scanner: ModuleType) -> ModuleType:
    return getattr(scanner, "BACKEND_GATE", scanner)


def test_nested_enumeration_failure_fails_closed(
    scanner: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "visible.py").write_text("value = 1\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "hidden.py").write_text("value = 2\n", encoding="utf-8")
    _configure_scan_root(scanner, tmp_path)

    gate = _traversal_gate(scanner)
    real_scandir = gate.os.scandir

    def fail_nested(path: object):
        if Path(path) == nested:
            raise PermissionError("SECRET_ENUMERATION_PAYLOAD")
        return real_scandir(path)

    monkeypatch.setattr(gate.os, "scandir", fail_nested)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "failed closed" in captured.err
    assert "source discovery failed" in captured.err
    assert "PermissionError" in captured.err
    assert "SECRET_ENUMERATION_PAYLOAD" not in captured.err
    assert "passed" not in captured.out.lower()


def test_zero_python_coverage_fails_closed(
    scanner: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _configure_scan_root(scanner, tmp_path)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "failed closed" in captured.err
    assert "zero Python files discovered" in captured.err
    assert "passed" not in captured.out.lower()


def test_missing_required_root_fails_closed(
    scanner: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "required-but-missing"
    _configure_scan_root(scanner, missing)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "failed closed" in captured.err
    assert "FileNotFoundError" in captured.err
    assert str(missing) not in captured.err


def test_backend_parse_failure_redacts_exception_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _load_module(BACKEND_SCANNER, "_test_backend_parse_redaction")
    target = tmp_path / "broken.py"
    target.write_text("value = 1\n", encoding="utf-8")
    real_read_text = Path.read_text

    def fail_parse(path: Path, *args: object, **kwargs: object) -> str:
        if path == target:
            raise SyntaxError("SECRET_PARSE_PAYLOAD")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_parse)
    findings = scanner.violations(target)

    assert len(findings) == 1
    assert "parse failure: SyntaxError" in findings[0]
    assert "SECRET_PARSE_PAYLOAD" not in findings[0]


def test_repository_argv_parse_failure_redacts_exception_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _load_module(REPOSITORY_SCANNER, "_test_repository_parse_redaction")
    target = tmp_path / "broken.py"
    target.write_text("value = 1\n", encoding="utf-8")
    real_read_text = Path.read_text

    def fail_parse(path: Path, *args: object, **kwargs: object) -> str:
        if path == target:
            raise SyntaxError("SECRET_ARGV_PARSE_PAYLOAD")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_parse)
    findings = scanner.argv_violations(target)

    assert len(findings) == 1
    assert "parse failure: SyntaxError" in findings[0]
    assert "SECRET_ARGV_PARSE_PAYLOAD" not in findings[0]


def test_explicit_traversal_does_not_follow_directory_symlinks(
    scanner: ModuleType,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "inside.py").write_text("value = 1\n", encoding="utf-8")
    (outside / "outside.py").write_text("value = 2\n", encoding="utf-8")
    link = root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("directory symlinks are unavailable on this platform")

    _configure_scan_root(scanner, root)
    discovered = {path.name for path in scanner.python_files()}

    assert discovered == {"inside.py"}
