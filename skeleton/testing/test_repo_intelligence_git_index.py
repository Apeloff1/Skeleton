from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

from skeleton.repo_intelligence.git_index import GitIndex, GitIndexError, TrackedFile


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "repo-intel@example.invalid")
    _git(repo, "config", "user.name", "Repo Intel Test")
    return repo


def _commit_all(repo: Path, message: str = "test") -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def test_snapshot_detects_content_and_mode_changes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    tracked = repo / "alpha.txt"
    tracked.write_text("alpha\n", encoding="utf-8")
    _commit_all(repo)

    clean = GitIndex(repo).snapshot()
    assert clean.tracked_files == 1
    assert clean.files[0].working_tree is False

    tracked.write_text("beta\n", encoding="utf-8")
    dirty = GitIndex(repo).snapshot()
    assert dirty.files[0].working_tree is True
    assert dirty.files[0].effective_blob != dirty.files[0].index_blob
    assert dirty.source_digest != clean.source_digest

    tracked.write_text("alpha\n", encoding="utf-8")
    restored = GitIndex(repo).snapshot()
    assert restored.files[0].working_tree is False
    assert restored.source_digest == clean.source_digest

    if os.name != "nt":
        tracked.chmod(0o755)
        mode_dirty = GitIndex(repo).snapshot()
        assert mode_dirty.files[0].working_tree is True
        assert mode_dirty.files[0].working_mode == "100755"
        assert mode_dirty.source_digest != clean.source_digest


def test_source_digest_includes_effective_working_mode() -> None:
    base = dict(
        path="tool.py",
        mode="100644",
        index_blob="a" * 40,
        effective_blob="a" * 40,
        size=4,
        working_tree=True,
        deleted=False,
    )
    non_exec = TrackedFile(**base, working_mode="100644")
    executable = TrackedFile(**base, working_mode="100755")

    assert GitIndex._source_digest((non_exec,)) != GitIndex._source_digest((executable,))


def test_inherited_git_repository_overrides_are_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    (repo / "tracked.txt").write_text("safe\n", encoding="utf-8")
    _commit_all(repo)

    decoy = tmp_path / "decoy"
    decoy.mkdir()
    _git(decoy, "init", "-q", "-b", "main")

    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(decoy))
    monkeypatch.setenv("GIT_INDEX_FILE", str(decoy / ".git" / "index"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "definitely-not-a-safe-command")

    snapshot = GitIndex(repo).snapshot()
    assert snapshot.tracked_files == 1
    assert snapshot.files[0].path == "tracked.txt"


@pytest.mark.skipif(os.name == "nt", reason="filter probe uses POSIX command quoting")
def test_snapshot_does_not_execute_repository_clean_filter(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    tracked = repo / "alpha.txt"
    tracked.write_text("alpha\n", encoding="utf-8")
    _commit_all(repo, "base")

    sentinel = tmp_path / "filter-ran.txt"
    helper = tmp_path / "filter_probe.py"
    helper.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path(sys.argv[1]).write_text('called', encoding='utf-8')\n"
        "sys.stdout.buffer.write(sys.stdin.buffer.read())\n",
        encoding="utf-8",
    )
    command = " ".join(
        [
            shlex.quote(sys.executable),
            shlex.quote(str(helper)),
            shlex.quote(str(sentinel)),
        ]
    )
    _git(repo, "config", "filter.probe.clean", command)
    _git(repo, "config", "filter.probe.smudge", "cat")
    (repo / ".gitattributes").write_text("alpha.txt filter=probe\n", encoding="utf-8")
    _commit_all(repo, "attributes")
    sentinel.unlink(missing_ok=True)

    snapshot = GitIndex(repo).snapshot()

    assert snapshot.tracked_files == 2
    assert sentinel.exists() is False


@pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
def test_tracked_symlink_is_hashed_without_following_target(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("first secret\n", encoding="utf-8")
    link = repo / "outside-link"
    link.symlink_to(outside)
    _commit_all(repo)

    first = GitIndex(repo).snapshot()
    row = first.files[0]
    assert row.path == "outside-link"
    assert row.mode == "120000"
    assert row.working_tree is False

    outside.write_text("completely different secret\n", encoding="utf-8")
    second = GitIndex(repo).snapshot()
    assert second.source_digest == first.source_digest
    assert second.files[0].effective_blob == row.effective_blob


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX no-follow directory walk")
def test_intermediate_symlink_cannot_escape_repository(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    nested = repo / "nested"
    nested.mkdir()
    (nested / "payload.txt").write_text("inside\n", encoding="utf-8")
    _commit_all(repo)

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "payload.txt").write_text("outside secret\n", encoding="utf-8")
    shutil.rmtree(nested)
    nested.symlink_to(outside, target_is_directory=True)

    with pytest.raises(GitIndexError, match="unsafe tracked parent path"):
        GitIndex(repo).snapshot()


def test_byte_limit_fails_closed_before_large_file_is_accepted(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "large.bin").write_bytes(b"x" * 64)
    _commit_all(repo)

    with pytest.raises(GitIndexError, match="byte count"):
        GitIndex(repo, max_total_bytes=32).snapshot()


def test_unmerged_index_fails_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = repo / "conflict.txt"
    target.write_text("base\n", encoding="utf-8")
    _commit_all(repo, "base")

    _git(repo, "checkout", "-q", "-b", "other")
    target.write_text("other\n", encoding="utf-8")
    _commit_all(repo, "other")

    _git(repo, "checkout", "-q", "main")
    target.write_text("main\n", encoding="utf-8")
    _commit_all(repo, "main")

    merge = _git(repo, "merge", "other", check=False)
    assert merge.returncode != 0

    with pytest.raises(GitIndexError, match="unmerged index"):
        GitIndex(repo).snapshot()
