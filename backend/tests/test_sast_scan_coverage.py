from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER_PATH = REPO_ROOT / "backend" / "scripts" / "check_sast_security.py"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCANNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_backend_root_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scanner = _load("_test_sast_missing_backend")
    monkeypatch.setattr(scanner, "BACKEND_ROOT", tmp_path / "missing")

    with pytest.raises(OSError):
        list(scanner.python_files())


def test_missing_frontend_root_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scanner = _load("_test_sast_missing_frontend")
    monkeypatch.setattr(scanner, "FRONTEND_ROOT", tmp_path / "missing")

    with pytest.raises(OSError):
        list(scanner.javascript_files())


def test_nested_traversal_failure_is_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scanner = _load("_test_sast_nested_walk")
    root = tmp_path / "runtime"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (nested / "target.py").write_text("x = 1\n", encoding="utf-8")
    original_scandir = scanner.os.scandir

    def guarded_scandir(path: object):
        if Path(path) == nested:
            raise PermissionError("sensitive traversal detail")
        return original_scandir(path)

    monkeypatch.setattr(scanner.os, "scandir", guarded_scandir)

    with pytest.raises(PermissionError, match="sensitive traversal detail"):
        list(scanner.walk_source_files(root, {".py"}))


def test_main_redacts_traversal_error_payload(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    scanner = _load("_test_sast_main_redaction")

    def broken_python_files():
        raise PermissionError("sensitive traversal detail")
        yield  # pragma: no cover

    monkeypatch.setattr(scanner, "python_files", broken_python_files)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "PermissionError" in captured.err
    assert "sensitive traversal detail" not in captured.err


def test_python_parse_failure_is_redacted(tmp_path: Path) -> None:
    scanner = _load("_test_sast_python_redaction")
    source = tmp_path / "invalid.py"
    source.write_text("def broken(:\n    pass\n", encoding="utf-8")

    findings = scanner.violations(source)

    assert findings == [f"{source}: parse failure: SyntaxError"]
    assert "invalid syntax" not in findings[0]


def test_javascript_read_failure_is_redacted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scanner = _load("_test_sast_js_redaction")
    source = tmp_path / "app.ts"
    source.write_text("export const value = 1;\n", encoding="utf-8")
    original_read_text = Path.read_text

    def broken_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == source:
            raise OSError("sensitive read detail")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", broken_read_text)

    findings = scanner.javascript_violations(source)

    assert findings == [f"{source}: read failure: OSError"]
    assert "sensitive read detail" not in findings[0]


def test_symlink_scan_root_is_rejected(tmp_path: Path) -> None:
    scanner = _load("_test_sast_symlink_root")
    real_root = tmp_path / "real"
    real_root.mkdir()
    link_root = tmp_path / "link"
    link_root.symlink_to(real_root, target_is_directory=True)

    with pytest.raises(OSError, match="must not be a symlink"):
        list(scanner.walk_source_files(link_root, {".py"}))


def test_zero_file_scan_fails_coverage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    scanner = _load("_test_sast_zero_files")
    backend = tmp_path / "backend"
    frontend = tmp_path / "frontend"
    backend.mkdir()
    frontend.mkdir()
    monkeypatch.setattr(scanner, "BACKEND_ROOT", backend)
    monkeypatch.setattr(scanner, "FRONTEND_ROOT", frontend)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "no backend Python files were scanned" in captured.err
    assert "no frontend JavaScript/TypeScript files were scanned" in captured.err
