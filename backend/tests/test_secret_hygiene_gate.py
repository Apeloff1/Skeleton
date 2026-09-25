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
    skipped = tmp_path / "build" / "generated.py"
    skipped.parent.mkdir()
    skipped.write_text("print('tracked build output')\n", encoding="utf-8")
    untracked = tmp_path / "generated.py"
    untracked.write_text("API_KEY='generated-only'\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.py", "docs/notes.md", "asset.bin", "build/generated.py")

    monkeypatch.setattr(checker, "REPO_ROOT", tmp_path)

    paths = [path.relative_to(tmp_path).as_posix() for path in checker.candidate_files()]

    assert paths == ["docs/notes.md", "tracked.py"]
    assert "generated.py" not in paths
    assert "build/generated.py" not in paths
    assert "asset.bin" not in paths


def test_candidate_files_fails_closed_without_git_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tracked.py").write_text("print('not indexed')\n", encoding="utf-8")
    monkeypatch.setattr(checker, "REPO_ROOT", tmp_path)

    with pytest.raises(OSError, match="tracked-file enumeration failed"):
        list(checker.candidate_files())


def test_explicit_dummy_database_uri_is_allowed_as_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "workflow.yml"
    candidate.write_text(
        "MONGO_URL: mongodb://admin:dummy-mongo-password@mongo:27017/app?authSource=admin\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPO_ROOT", tmp_path)

    assert checker.violations(candidate) == []


def test_credential_bearing_database_uri_fails_without_echoing_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "workflow.yml"
    secret_value = "ci-mongo-password"
    credential_uri = (
        "mongodb://"
        + f"admin:{secret_value}@mongo:27017/app?authSource=admin"
    )
    candidate.write_text(
        f"MONGO_URL: {credential_uri}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "REPO_ROOT", tmp_path)

    findings = checker.violations(candidate)

    assert findings == [
        "workflow.yml:1: possible credential-bearing database URI"
    ]
    assert secret_value not in "\n".join(findings)
