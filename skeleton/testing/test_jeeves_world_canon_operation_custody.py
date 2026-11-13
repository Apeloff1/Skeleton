"""Fail-closed descriptor-anchored review input regression fixtures."""
from __future__ import annotations

import os

import pytest

from skeleton.jeeves.worlds.cli import _read_operation_file
from skeleton.jeeves.worlds.world_canon import CanonError


pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"),
    reason="POSIX descriptor-anchored review custody",
)


def test_regular_review_file_is_read_without_modification(tmp_path):
    source = tmp_path / "review.json"
    payload = b'{"action":"batch","value":[]}'
    source.write_bytes(payload)
    assert _read_operation_file(str(source)) == payload
    assert source.read_bytes() == payload


@pytest.mark.parametrize("suffix", ["../review.json", "./review.json", "folder//review.json"])
def test_rejects_noncanonical_components(tmp_path, suffix):
    with pytest.raises(CanonError, match="operation_invalid_path"):
        _read_operation_file(str(tmp_path) + "/" + suffix)


def test_rejects_final_symlink(tmp_path):
    source = tmp_path / "review.json"
    source.write_bytes(b"{}")
    link = tmp_path / "link.json"
    link.symlink_to(source)
    with pytest.raises(OSError):
        _read_operation_file(str(link))


def test_rejects_symlinked_parent(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "review.json").write_bytes(b"{}")
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(OSError):
        _read_operation_file(str(alias / "review.json"))


def test_rejects_fifo_without_blocking(tmp_path):
    fifo = tmp_path / "review.fifo"
    os.mkfifo(fifo)
    with pytest.raises(CanonError, match="operation_not_regular"):
        _read_operation_file(str(fifo))


def test_rejects_oversized_review(tmp_path):
    source = tmp_path / "large.json"
    source.write_bytes(b"x" * 524289)
    with pytest.raises(CanonError, match="operation_too_large"):
        _read_operation_file(str(source))


def test_rejects_embedded_nul_and_empty_path():
    for path in ("", "bad\x00path"):
        with pytest.raises(CanonError, match="operation_invalid_path"):
            _read_operation_file(path)
