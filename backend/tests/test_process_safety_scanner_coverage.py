from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BACKEND_GATE = _load_module(
    "_test_backend_process_safety",
    REPO_ROOT / "backend" / "scripts" / "check_process_safety.py",
)
REPOSITORY_GATE = _load_module(
    "_test_repository_process_safety",
    REPO_ROOT / "scripts" / "check_repository_process_safety.py",
)


def _make_partial_tree(root: Path) -> Path:
    root.mkdir()
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")
    blocked = root / "blocked"
    blocked.mkdir()
    (blocked / "hidden.py").write_text("value = 2\n", encoding="utf-8")
    return blocked


def _fail_on_directory(monkeypatch: pytest.MonkeyPatch, module: ModuleType, blocked: Path) -> str:
    secret = "sensitive traversal detail"
    real_scandir = module.os.scandir

    def failing_scandir(path: str | Path):
        if Path(path) == blocked:
            raise PermissionError(secret)
        return real_scandir(path)

    monkeypatch.setattr(module.os, "scandir", failing_scandir)
    return secret


def test_backend_scan_fails_closed_on_nested_enumeration_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "backend"
    blocked = _make_partial_tree(root)
    monkeypatch.setattr(BACKEND_GATE, "ROOT", root)
    secret = _fail_on_directory(monkeypatch, BACKEND_GATE, blocked)

    assert BACKEND_GATE.main() == 1
    captured = capsys.readouterr()
    assert "Process safety scan failed: PermissionError" in captured.err
    assert secret not in captured.err
    assert "gate passed" not in captured.out


def test_backend_scan_fails_closed_on_zero_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "backend"
    root.mkdir()
    monkeypatch.setattr(BACKEND_GATE, "ROOT", root)

    assert BACKEND_GATE.main() == 1
    captured = capsys.readouterr()
    assert "no backend Python files were scanned" in captured.err
    assert "gate passed" not in captured.out


def test_backend_parse_failure_is_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "backend"
    root.mkdir()
    (root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    monkeypatch.setattr(BACKEND_GATE, "ROOT", root)

    assert BACKEND_GATE.main() == 1
    captured = capsys.readouterr()
    assert "broken.py: parse failure: SyntaxError" in captured.err
    assert "invalid syntax" not in captured.err
    assert "def broken(" not in captured.err


def test_backend_scan_fails_closed_when_root_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing-backend"
    monkeypatch.setattr(BACKEND_GATE, "ROOT", missing)

    assert BACKEND_GATE.main() == 1
    captured = capsys.readouterr()
    assert "Process safety scan failed: FileNotFoundError" in captured.err
    assert str(missing) not in captured.err


def _configure_repository_gate(monkeypatch: pytest.MonkeyPatch, roots: tuple[Path, ...]) -> None:
    common_root = roots[0].parent
    monkeypatch.setattr(REPOSITORY_GATE, "REPO_ROOT", common_root)
    monkeypatch.setattr(REPOSITORY_GATE, "SCAN_ROOTS", roots)
    monkeypatch.setattr(REPOSITORY_GATE.BACKEND_GATE, "ROOT", common_root)


def test_repository_scan_fails_closed_on_nested_enumeration_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "runtime"
    blocked = _make_partial_tree(root)
    _configure_repository_gate(monkeypatch, (root,))
    secret = _fail_on_directory(monkeypatch, REPOSITORY_GATE.BACKEND_GATE, blocked)

    assert REPOSITORY_GATE.main() == 1
    captured = capsys.readouterr()
    assert "Repository process-safety scan failed: PermissionError" in captured.err
    assert secret not in captured.err
    assert "process safety passed" not in captured.out


def test_repository_scan_fails_closed_on_zero_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    _configure_repository_gate(monkeypatch, (root,))

    assert REPOSITORY_GATE.main() == 1
    captured = capsys.readouterr()
    assert "zero Python files scanned" in captured.err
    assert "process safety passed" not in captured.out


def test_repository_parse_failure_is_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    _configure_repository_gate(monkeypatch, (root,))

    assert REPOSITORY_GATE.main() == 1
    captured = capsys.readouterr()
    assert "runtime/broken.py: parse failure: SyntaxError" in captured.err
    assert "invalid syntax" not in captured.err
    assert "def broken(" not in captured.err


def test_repository_scan_requires_every_configured_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")
    missing = tmp_path / "missing-runtime"
    _configure_repository_gate(monkeypatch, (root, missing))

    assert REPOSITORY_GATE.main() == 1
    captured = capsys.readouterr()
    assert "Repository process-safety scan failed: FileNotFoundError" in captured.err
    assert str(missing) not in captured.err
