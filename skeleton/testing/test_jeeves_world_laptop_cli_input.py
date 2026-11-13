"""Fail-closed laptop CLI input handling for operator-owned JSON."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.jeeves.worlds.laptop_cli import MAX_INPUT, _file
from skeleton.jeeves.worlds.world_canon import CanonError


def test_cli_json_accepts_bounded_regular_file(tmp_path):
    path = tmp_path / "brief.json"
    value = {"id": "lighthouse", "premise": "An original coastal mystery"}
    path.write_text(json.dumps(value), encoding="utf-8")
    assert _file(str(path)) == value


def test_cli_json_rejects_oversize_without_truncating(tmp_path):
    path = tmp_path / "huge.json"
    path.write_bytes(b" " * (MAX_INPUT + 1))
    with pytest.raises(CanonError) as error:
        _file(str(path))
    assert error.value.code == "input_too_large"


def test_cli_json_rejects_symlink(tmp_path):
    source = tmp_path / "source.json"
    source.write_text('{"id":"lighthouse"}', encoding="utf-8")
    alias = tmp_path / "alias.json"
    alias.symlink_to(source)
    with pytest.raises(OSError):
        _file(str(alias))


def test_cli_json_rejects_directory(tmp_path):
    with pytest.raises((CanonError, OSError)):
        _file(str(tmp_path))


def test_cli_json_rejects_nonfinite_number(tmp_path):
    path = tmp_path / "nonfinite.json"
    path.write_text('{"count":1e9999}', encoding="utf-8")
    with pytest.raises(CanonError):
        _file(str(path))


def test_cli_json_rejects_fifo_without_waiting_for_writer(tmp_path):
    if not hasattr(os, "mkfifo") or not hasattr(os, "O_NONBLOCK"):
        pytest.skip("POSIX FIFO/nonblocking open unavailable")
    pipe = tmp_path / "untrusted.json"
    os.mkfifo(pipe)
    with pytest.raises(CanonError) as error:
        _file(str(pipe))
    assert error.value.code == "input_not_regular"


def test_cli_json_rejects_empty_regular_file(tmp_path):
    path = tmp_path / "empty.json"
    path.touch()
    with pytest.raises(CanonError):
        _file(str(path))


def test_cli_json_rejects_symlinked_parent(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "brief.json").write_text('{"id":"lighthouse"}', encoding="utf-8")
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(OSError):
        _file(str(alias / "brief.json"))


@pytest.mark.parametrize("path", ["", ".", "../brief.json", "a/../brief.json", "a//brief.json"])
def test_cli_json_rejects_ambiguous_path(path):
    with pytest.raises(CanonError) as error:
        _file(path)
    assert error.value.code == "input_invalid_path"


def test_cli_json_accepts_nested_regular_file(tmp_path):
    directory = tmp_path / "nested"
    directory.mkdir()
    (directory / "brief.json").write_text('{"id":"lighthouse"}', encoding="utf-8")
    assert _file(str(directory / "brief.json")) == {"id": "lighthouse"}


def test_cli_json_rejects_parent_fifo_without_blocking(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO unavailable")
    os.mkfifo(tmp_path / "pipe")
    with pytest.raises(OSError):
        _file(str(tmp_path / "pipe" / "brief.json"))


def test_cli_json_rejects_embedded_nul_before_open(tmp_path):
    path = str(tmp_path / "brief.json") + "\x00" + "/ignored"
    with pytest.raises(CanonError) as error:
        _file(path)
    assert error.value.code == "input_invalid_path"


def test_cli_json_rejects_duplicate_object_keys(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"world":"one","world":"two"}', encoding="utf-8")
    with pytest.raises(CanonError):
        _file(str(path))


def test_cli_json_rejects_trailing_payload(tmp_path):
    path = tmp_path / "trailing.json"
    path.write_text('{"world":"one"} {"world":"two"}', encoding="utf-8")
    with pytest.raises(CanonError):
        _file(str(path))


def test_cli_json_rejects_nested_symlinked_parent(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    real = root / "real"
    real.mkdir()
    (real / "brief.json").write_text('{"id":"lighthouse"}', encoding="utf-8")
    (root / "alias").symlink_to(real, target_is_directory=True)
    with pytest.raises(OSError):
        _file(str(root / "alias" / "brief.json"))
