"""Regression tests for bounded Git-index secret-hygiene discovery."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_secret_hygiene.py"
SPEC = importlib.util.spec_from_file_location("check_secret_hygiene_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_candidate_files_uses_git_index_not_workspace_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(tmp_path, "init", "-q")
    tracked = tmp_path / "tracked.py"
    tracked.write_text("print('tracked')\n", encoding="utf-8")
    tracked_markdown = tmp_path / "docs" / "notes.md"
    tracked_markdown.parent.mkdir()
    tracked_markdown.write_text("tracked docs\n", encoding="utf-8")
    tracked_binary = tmp_path / "asset.bin"
    tracked_binary.write_bytes(b"binary")
    untracked = tmp_path / "generated.py"
    untracked.write_text("API_KEY='generated-only'\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.py", "docs/notes.md", "asset.bin")

    monkeypatch.setattr(checker, "REPO_ROOT", tmp_path)

    paths = [path.relative_to(tmp_path).as_posix() for path in checker.candidate_files()]

    assert paths == ["docs/notes.md", "tracked.py"]
    assert "generated.py" not in paths
    assert "asset.bin" not in paths


def test_candidate_files_fails_closed_without_git_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tracked.py").write_text("print('not indexed')\n", encoding="utf-8")
    monkeypatch.setattr(checker, "REPO_ROOT", tmp_path)

    with pytest.raises(OSError, match="tracked-file enumeration failed"):
        list(checker.candidate_files())
