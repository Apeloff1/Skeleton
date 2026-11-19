"""Hermetic tests for skeleton.main_guard.bisect (temp git repos, no network)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from skeleton.main_guard.bisect import BisectError, bisect, classify_returncode, render_bisect_markdown
from skeleton.testing.main_guard_test_support import commit, git, init_repo

CHECK = [sys.executable, "-c", "import pathlib,sys; sys.exit(1 if 'BROKEN' in pathlib.Path('app.txt').read_text() else 0)"]


def _history(tmp_path: Path, bad_index: int, total: int = 8) -> tuple[Path, list[str]]:
    repo = init_repo(tmp_path / "repo")
    shas = [commit(repo, {"app.txt": "ok\n"}, "base")]
    for i in range(1, total):
        body = "BROKEN\n" if i >= bad_index else f"ok {i}\n"
        shas.append(commit(repo, {"app.txt": body}, f"push {i}", author=f"Dev{i}", email=f"dev{i}@example.invalid"))
    return repo, shas


@pytest.mark.parametrize("strategy", ["direct", "git"])
@pytest.mark.parametrize("bad_index", [1, 4, 7])
def test_finds_first_bad_commit_and_restores_head(tmp_path: Path, strategy: str, bad_index: int) -> None:
    repo, shas = _history(tmp_path, bad_index)
    head_before = git(repo, "rev-parse", "HEAD")
    result = bisect(repo, shas[0], shas[-1], CHECK, strategy=strategy)
    assert result.found
    assert result.first_bad is not None and result.first_bad.sha == shas[bad_index]
    assert result.first_bad.author_name == f"Dev{bad_index}"
    assert git(repo, "rev-parse", "HEAD") == head_before
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert not (Path(git(repo, "rev-parse", "--absolute-git-dir")) / "BISECT_LOG").exists()


def test_rejects_good_that_is_not_ancestor(tmp_path: Path) -> None:
    repo, shas = _history(tmp_path, 3)
    with pytest.raises(BisectError):
        bisect(repo, shas[-1], shas[0], CHECK)


def test_rejects_non_repo(tmp_path: Path) -> None:
    (tmp_path / "plain").mkdir()
    with pytest.raises(BisectError):
        bisect(tmp_path / "plain", "a" * 40, "b" * 40, CHECK)


def test_endpoint_verification_flags_good_that_fails(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    a = commit(repo, {"app.txt": "BROKEN\n"}, "already broken")
    b = commit(repo, {"app.txt": "BROKEN again\n"}, "still broken")
    with pytest.raises(BisectError):
        bisect(repo, a, b, CHECK, strategy="direct", verify_endpoints=True)


def test_markdown_names_commit_and_author(tmp_path: Path) -> None:
    repo, shas = _history(tmp_path, 5)
    md = render_bisect_markdown(bisect(repo, shas[0], shas[-1], CHECK))
    assert shas[5][:7] in md
    assert "Dev5" in md


def test_classify_returncode() -> None:
    assert classify_returncode(0) == "good"
    assert classify_returncode(1) == "bad"
    assert classify_returncode(125) == "skip"
    assert classify_returncode(None, timed_out=True) == "skip"
