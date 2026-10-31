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
