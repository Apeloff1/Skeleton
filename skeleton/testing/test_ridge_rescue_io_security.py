"""Descriptor-pinned file IO: symlinks, traversal, overwrite and atomic publication."""
from __future__ import annotations

import json
import os
import stat
import pytest

from skeleton.game.gameplay.ridge_rescue.io import IOErrorBounded, read_bounded, write_new


def test_source_read_and_atomic_export(tmp_path):
    source = tmp_path / "source.json"
    source.write_bytes(b'{"a":1}')
    assert read_bounded(source) == b'{"a":1}'
    target = tmp_path / "result.json"
    write_new(target, {"a": 1})
    assert json.loads(read_bounded(target)) == {"a": 1}
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".ridge-*.tmp"))


def test_no_overwrite_and_no_partial_publication(tmp_path):
    path = tmp_path / "existing.json"
    path.write_bytes(b"original")
    with pytest.raises(IOErrorBounded, match="overwrite"):
        write_new(path, {"new": True})
    assert path.read_bytes() == b"original"
    assert not list(tmp_path.glob(".ridge-*.tmp"))


def test_symlink_final_and_parent_rejected(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    (target / "input").write_bytes(b"safe")
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(IOErrorBounded):
        read_bounded(alias / "input")
    with pytest.raises(IOErrorBounded):
        write_new(alias / "output", {"x": 1})
    file_alias = tmp_path / "file_alias"
    file_alias.symlink_to(target / "input")
    with pytest.raises(IOErrorBounded):
        read_bounded(file_alias)
    with pytest.raises(IOErrorBounded):
        write_new(file_alias, {"x": 1})
    assert (target / "input").read_bytes() == b"safe"


@pytest.mark.parametrize("path", ["../escape", "./entry", "dir/../escape", "dir//entry", ""])
def test_traversal_and_noncanonical_components_rejected(path):
    with pytest.raises(IOErrorBounded):
        read_bounded(path)
    with pytest.raises(IOErrorBounded):
        write_new(path, {})


def test_oversized_and_nonregular_input_rejected(tmp_path):
    file = tmp_path / "large"
    file.write_bytes(b"x" * 33)
    with pytest.raises(IOErrorBounded):
        read_bounded(file, 32)
    with pytest.raises(IOErrorBounded):
        read_bounded(tmp_path)
    with pytest.raises(IOErrorBounded):
        write_new(tmp_path / "out", {"payload": "x" * 40}, 10)


def test_failed_link_does_not_publish_destination(tmp_path, monkeypatch):
    target = tmp_path / "blocked.json"
    def refuse_link(*args, **kwargs):
        raise PermissionError("simulated filesystem publication failure")
    monkeypatch.setattr(os, "link", refuse_link)
    with pytest.raises(IOErrorBounded):
        write_new(target, {"a": 1})
    assert not target.exists()
    assert not list(tmp_path.glob(".ridge-*.tmp"))


def test_fifos_rejected_without_blocking(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO unavailable")
    pipe = tmp_path / "pipe"
    os.mkfifo(pipe)
    with pytest.raises(IOErrorBounded):
        read_bounded(pipe)


def test_reject_bad_limits(tmp_path):
    path = tmp_path / "data"
    path.write_bytes(b"x")
    for limit in (True, -1, 1_000_001):
        with pytest.raises(IOErrorBounded):
            read_bounded(path, limit)
        with pytest.raises(IOErrorBounded):
            write_new(tmp_path / "out", {"a": 1}, limit)
