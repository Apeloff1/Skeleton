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
