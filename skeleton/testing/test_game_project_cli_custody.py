"""File custody regressions for the installed cross-era game-project CLI."""
from __future__ import annotations

import json
import os
import stat

import pytest

from skeleton.ai.runtime.game_project_cli import (
    GameCapsuleError, MAX_RESULT_BYTES, _read_json, _write_new,
)


def test_round_trip_exclusive_private_new_output(tmp_path):
    destination = tmp_path / "new-game.json"
    assert _write_new(destination, {"value": 7, "active": False}) == str(destination)
    assert _read_json(destination) == {"value": 7, "active": False}
    assert destination.read_bytes() == b'{"active":false,"value":7}\n'
    if os.name == "posix":
        assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    with pytest.raises(GameCapsuleError, match="new file"):
        _write_new(destination, {"value": 8})
    assert _read_json(destination)["value"] == 7


def test_reject_duplicate_properties_and_nonfinite_numbers(tmp_path):
    path = tmp_path / "source.json"
    path.write_text('{"key":1,"key":2}', encoding="utf-8")
    with pytest.raises(GameCapsuleError, match="duplicate"):
        _read_json(path)
    path.write_text('{"key":NaN}', encoding="utf-8")
    with pytest.raises(GameCapsuleError, match="nonfinite"):
        _read_json(path)


def test_read_and_write_budgets_hold_before_publication(tmp_path):
    path = tmp_path / "input.json"
    path.write_text('{"value":"oversized"}', encoding="utf-8")
    with pytest.raises(GameCapsuleError, match="budget"):
        _read_json(path, max_bytes=10)
    with pytest.raises(GameCapsuleError, match="budget"):
        _read_json(path, max_bytes=MAX_RESULT_BYTES + 1)
    destination = tmp_path / "large.json"
    with pytest.raises(GameCapsuleError, match="160-KiB"):
        _write_new(destination, {"blob": "x" * MAX_RESULT_BYTES})
    assert not destination.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX anchored directory handles")
def test_input_symlink_and_parent_symlink_never_followed(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "game.json").write_text('{"original":true}', encoding="utf-8")
    (tmp_path / "linked-file.json").symlink_to(real / "game.json")
    (tmp_path / "linked-parent").symlink_to(real, target_is_directory=True)
    with pytest.raises(GameCapsuleError):
        _read_json(tmp_path / "linked-file.json")
    with pytest.raises(GameCapsuleError, match="unsafe directory"):
        _read_json(tmp_path / "linked-parent" / "game.json")
    with pytest.raises(GameCapsuleError, match="unsafe directory"):
        _write_new(tmp_path / "linked-parent" / "output.json", {"x": 1})
    assert not (real / "output.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX anchored directory handles")
def test_traversal_components_are_not_normalized_away(tmp_path):
    child = tmp_path / "child"
    child.mkdir()
    raw = child / ".." / "new.json"
    with pytest.raises(GameCapsuleError, match="traversal"):
        _write_new(raw, {"x": 1})
    assert not (tmp_path / "new.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX anchored directory handles")
def test_swap_after_file_open_rejects_read_without_trusting_old_inode(tmp_path, monkeypatch):
    path = tmp_path / "original.json"
    path.write_text('{"original":true}', encoding="utf-8")
    moved = tmp_path / "moved.json"
    actual_fdopen = os.fdopen
    changed = False

    def swap_once(fd, mode, *args, **kwargs):
        nonlocal changed
        if mode == "rb" and not changed:
            changed = True
            path.rename(moved)
            path.write_text('{"forged":true}', encoding="utf-8")
        return actual_fdopen(fd, mode, *args, **kwargs)

    monkeypatch.setattr(os, "fdopen", swap_once)
    with pytest.raises(GameCapsuleError, match="input identity changed"):
        _read_json(path)
    assert changed
    assert json.loads(moved.read_text(encoding="utf-8")) == {"original": True}


@pytest.mark.skipif(os.name != "posix", reason="POSIX anchored directory handles")
def test_output_leaf_symlink_not_overwritten(tmp_path):
    target = tmp_path / "original.json"
    target.write_text('{"owned":true}', encoding="utf-8")
    alias = tmp_path / "redirected.json"
    alias.symlink_to(target)
    with pytest.raises(GameCapsuleError, match="new file"):
        _write_new(alias, {"forged": True})
    assert _read_json(target) == {"owned": True}


@pytest.mark.skipif(os.name != "posix", reason="POSIX anchored directory handles")
def test_parent_swap_after_leaf_open_cannot_authorize_read(tmp_path, monkeypatch):
    parent = tmp_path / "original"
    moved = tmp_path / "moved"
    parent.mkdir()
    source = parent / "source.json"
    source.write_text('{"original":true}', encoding="utf-8")
    real_fdopen = os.fdopen
    swapped = False

    def replace_parent(fd, mode, *args, **kwargs):
        nonlocal swapped
        if mode == "rb" and not swapped:
            swapped = True
            parent.rename(moved)
            parent.mkdir()
            (parent / "source.json").write_text('{"new":true}', encoding="utf-8")
        return real_fdopen(fd, mode, *args, **kwargs)

    monkeypatch.setattr(os, "fdopen", replace_parent)
    with pytest.raises(GameCapsuleError, match="parent identity changed"):
        _read_json(source)
    assert swapped
    assert json.loads((moved / "source.json").read_text()) == {"original": True}


@pytest.mark.skipif(os.name != "posix", reason="POSIX anchored directory handles")
def test_parent_swap_during_exclusive_write_does_not_claim_publication(tmp_path, monkeypatch):
    parent = tmp_path / "original"
    moved = tmp_path / "moved"
    parent.mkdir()
    output = parent / "result.json"
    real_fdopen = os.fdopen
    swapped = False

    def replace_parent(fd, mode, *args, **kwargs):
        nonlocal swapped
        if mode == "wb" and not swapped:
            swapped = True
            parent.rename(moved)
            parent.mkdir()
        return real_fdopen(fd, mode, *args, **kwargs)

    monkeypatch.setattr(os, "fdopen", replace_parent)
    with pytest.raises(GameCapsuleError, match="parent identity changed"):
        _write_new(output, {"earned": False})
    assert swapped
    assert not output.exists()
    assert (moved / "result.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX named pipes")
def test_fifo_input_refuses_without_waiting_for_writer(tmp_path):
    fifo = tmp_path / "blocked-input"
    os.mkfifo(fifo, 0o600)
    with pytest.raises(GameCapsuleError, match="budget"):
        _read_json(fifo)
