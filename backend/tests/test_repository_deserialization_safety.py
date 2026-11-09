"""Regression tests for repository-wide deserialization safety coverage."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = REPO_ROOT / "scripts" / "check_repository_deserialization_safety.py"
SPEC = importlib.util.spec_from_file_location("repository_deserialization_safety", GATE_PATH)
assert SPEC is not None and SPEC.loader is not None
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def _scan(tmp_path: Path, source: str) -> list[str]:
    target = tmp_path / "sample.py"
    target.write_text(source, encoding="utf-8")
    return GATE.violations(target)


def test_repository_deserialization_scope_covers_core_and_tooling() -> None:
    files = list(GATE.python_files())
    relative = [path.relative_to(REPO_ROOT) for path in files]

    assert any(path.parts and path.parts[0] == "skeleton" for path in relative)
    assert any(path.parts and path.parts[0] == "scripts" for path in relative)


def test_repository_wrapper_reuses_canonical_violation_engine(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import pickle\nvalue = pickle.loads(payload)\n")

    assert any("pickle.loads() is forbidden" in finding for finding in findings)


def test_repository_wrapper_keeps_safe_json_deserialization_allowed(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import json\nvalue = json.loads(payload)\n")

    assert findings == []


def test_repository_deserialization_fails_closed_when_required_root_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing"
    monkeypatch.setattr(GATE, "SCAN_ROOTS", (missing,))

    assert GATE.main() == 1
    captured = capsys.readouterr()
    assert "source traversal failure" in captured.err
    assert str(missing) not in captured.err


def test_repository_deserialization_requires_every_root_nonempty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    populated = tmp_path / "skeleton"
    empty = tmp_path / "scripts"
    populated.mkdir()
    empty.mkdir()
    (populated / "safe.py").write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(GATE, "SCAN_ROOTS", (populated, empty))

    assert GATE.main() == 1
    error = capsys.readouterr().err
    assert "no Python files scanned under" in error
    assert str(empty) in error


def test_repository_deserialization_accepts_clean_nonempty_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = tmp_path / "skeleton"
    second = tmp_path / "scripts"
    first.mkdir()
    second.mkdir()
    (first / "safe.py").write_text("value = 1\n", encoding="utf-8")
    (second / "safe.py").write_text("other = 2\n", encoding="utf-8")
    monkeypatch.setattr(GATE, "SCAN_ROOTS", (first, second))

    assert GATE.main() == 0
    output = capsys.readouterr().out
    assert "2 Python files" in output
    assert f"{first}=1" in output
    assert f"{second}=1" in output


def test_repository_deserialization_rejects_symlinked_required_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "safe.py").write_text("value = 1\n", encoding="utf-8")
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this platform")
    monkeypatch.setattr(GATE, "SCAN_ROOTS", (linked,))

    assert GATE.main() == 1
    assert "source traversal failure" in capsys.readouterr().err
