from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER_PATH = REPO_ROOT / "scripts" / "check_repository_process_safety.py"


def load_scanner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_repository_process_safety_test_target", SCANNER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_fails_closed_when_no_python_files_are_scanned(monkeypatch, capsys) -> None:
    scanner = load_scanner()
    monkeypatch.setattr(scanner, "python_files", lambda: iter(()))

    assert scanner.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "zero Python files scanned" in captured.err


def test_main_fails_closed_when_traversal_raises_oserror(monkeypatch, capsys) -> None:
    scanner = load_scanner()

    def broken_python_files():
        raise OSError("simulated traversal failure")
        yield Path("unreachable.py")  # pragma: no cover

    monkeypatch.setattr(scanner, "python_files", broken_python_files)

    assert scanner.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Repository process-safety scan failed: OSError" in captured.err


def test_main_passes_after_scanning_one_clean_python_file(monkeypatch, capsys, tmp_path) -> None:
    scanner = load_scanner()
    clean_file = tmp_path / "clean.py"
    clean_file.write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(scanner, "python_files", lambda: iter((clean_file,)))

    assert scanner.main() == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "passed across 1 Python files" in captured.out
