"""Regression coverage for fail-closed Jeeves mirror custody."""
from __future__ import annotations

from pathlib import Path

from scripts.check_jeeves_agent_mirror import CANONICAL, MIRROR, REQUIRED, check_parity


def _fixture(root: Path) -> None:
    for relative in (CANONICAL, MIRROR):
        folder = root / relative
        folder.mkdir(parents=True)
        for name in REQUIRED:
            (folder / name).write_text("identical source bytes\n", encoding="utf-8")


def test_matching_regular_files_are_accepted(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = check_parity(tmp_path)
    assert result["status"] == "passed"
    assert result["checked"] == len(REQUIRED)


def test_missing_file_fails_closed(tmp_path: Path) -> None:
    _fixture(tmp_path)
    (tmp_path / MIRROR / REQUIRED[0]).unlink()
    result = check_parity(tmp_path)
    assert result["status"] == "blocked"
    assert result["files"][0]["status"] == "missing"


def test_divergent_file_fails_closed(tmp_path: Path) -> None:
    _fixture(tmp_path)
    (tmp_path / MIRROR / REQUIRED[0]).write_text("unexpected bytes\n", encoding="utf-8")
    result = check_parity(tmp_path)
    assert result["status"] == "blocked"
    assert result["files"][0]["status"] == "drifted"


def test_mirror_symlink_to_canonical_fails_closed(tmp_path: Path) -> None:
    _fixture(tmp_path)
    mirror = tmp_path / MIRROR / REQUIRED[0]
    canonical = tmp_path / CANONICAL / REQUIRED[0]
    mirror.unlink()
    mirror.symlink_to(canonical)
    result = check_parity(tmp_path)
    assert result["status"] == "blocked"
    assert result["files"][0]["status"] == "symlink"


def test_canonical_symlink_to_mirror_fails_closed(tmp_path: Path) -> None:
    _fixture(tmp_path)
    canonical = tmp_path / CANONICAL / REQUIRED[0]
    mirror = tmp_path / MIRROR / REQUIRED[0]
    canonical.unlink()
    canonical.symlink_to(mirror)
    result = check_parity(tmp_path)
    assert result["status"] == "blocked"
    assert result["files"][0]["status"] == "symlink"


def test_mirror_parent_directory_symlink_fails_closed(tmp_path: Path) -> None:
    _fixture(tmp_path)
    mirror_dir = tmp_path / MIRROR
    redirected = tmp_path / "redirected-agent"
    mirror_dir.rename(redirected)
    mirror_dir.symlink_to(redirected, target_is_directory=True)
    result = check_parity(tmp_path)
    assert result["status"] == "blocked"
    assert all(item["status"] == "symlink" for item in result["files"])


def test_canonical_parent_directory_symlink_fails_closed(tmp_path: Path) -> None:
    _fixture(tmp_path)
    canonical_dir = tmp_path / CANONICAL
    redirected = tmp_path / "redirected-canonical"
    canonical_dir.rename(redirected)
    canonical_dir.symlink_to(redirected, target_is_directory=True)
    result = check_parity(tmp_path)
    assert result["status"] == "blocked"
    assert all(item["status"] == "symlink" for item in result["files"])


def test_file_swap_to_symlink_at_open_boundary_is_rejected(tmp_path: Path, monkeypatch) -> None:
    """A path swapped immediately before open cannot redirect the read."""
    import os
    import scripts.check_jeeves_agent_mirror as parity

    _fixture(tmp_path)
    original = tmp_path / CANONICAL / REQUIRED[0]
    mirror = tmp_path / MIRROR / REQUIRED[0]
    real_open = os.open
    swapped = False

    def swap_at_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if not swapped and path == REQUIRED[0] and kwargs.get("dir_fd") is not None:
            swapped = True
            original.unlink()
            original.symlink_to(mirror)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(parity.os, "open", swap_at_open)
    result = check_parity(tmp_path)
    assert swapped
    assert result["status"] == "blocked"
    assert result["files"][0]["status"] == "symlink"


def test_nonregular_fifo_is_rejected_without_blocking(tmp_path: Path) -> None:
    import os

    _fixture(tmp_path)
    target = tmp_path / CANONICAL / REQUIRED[0]
    target.unlink()
    os.mkfifo(target)
    result = check_parity(tmp_path)
    assert result["status"] == "blocked"
    assert result["files"][0]["status"] == "unsafe"


def test_oversized_source_fails_closed(tmp_path: Path, monkeypatch) -> None:
    import scripts.check_jeeves_agent_mirror as parity

    _fixture(tmp_path)
    monkeypatch.setattr(parity, "MAX_SOURCE_BYTES", 8)
    result = check_parity(tmp_path)
    assert result["status"] == "blocked"
    assert result["files"][0]["status"] == "unsafe"


def test_symlinked_root_is_rejected(tmp_path: Path) -> None:
    _fixture(tmp_path)
    alias = tmp_path.parent / (tmp_path.name + "-alias")
    alias.symlink_to(tmp_path, target_is_directory=True)
    result = check_parity(alias)
    assert result["status"] == "blocked"
    assert all(item["status"] == "symlink" for item in result["files"])
