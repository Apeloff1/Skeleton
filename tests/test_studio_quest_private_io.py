"""Descriptor-anchored private Studio A authoring file custody."""
from __future__ import annotations

import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_private_io import read_studio_private_json


def private(path, text):
    path.write_text(text)
    os.chmod(path, 0o600)
    return path


def test_private_json_reads_exact_strict_object(tmp_path):
    path = private(tmp_path / "approved.json", '{"a":[1,2],"b":{"c":true}}')
    assert read_studio_private_json(path, 4096) == {
        "a": [1, 2], "b": {"c": True},
    }


@pytest.mark.parametrize("text", [
    '{"a":1,"a":2}',
    '{"a":NaN}',
    '{"a":Infinity}',
    '{"a":-Infinity}',
    '[]',
    '{"a":',
    '{"a":1}{"b":2}',
    'null',
])
def test_private_json_rejects_duplicate_nonfinite_and_nonobject(tmp_path, text):
    path = private(tmp_path / "approved.json", text)
    with pytest.raises((StudioQuestError, ValueError)):
        read_studio_private_json(path, 4096)


def test_private_json_rejects_oversize_empty_and_invalid_limit(tmp_path):
    path = private(tmp_path / "approved.json", '{"a":"' + "x" * 4096 + '"}')
    with pytest.raises(StudioQuestError):
        read_studio_private_json(path, 4096)
    with pytest.raises(StudioQuestError):
        read_studio_private_json(path, 65537)
    private(path, "")
    with pytest.raises(StudioQuestError):
        read_studio_private_json(path, 4096)


def test_private_json_rejects_hardlinks_and_permissive_modes(tmp_path):
    path = private(tmp_path / "approved.json", '{"a":1}')
    other = tmp_path / "hardlink.json"
    os.link(path, other)
    with pytest.raises(StudioQuestError):
        read_studio_private_json(path, 4096)
    other.unlink()
    os.chmod(path, 0o644)
    with pytest.raises(StudioQuestError):
        read_studio_private_json(path, 4096)


def test_private_json_rejects_symlinked_file_and_ancestor(tmp_path):
    target = private(tmp_path / "target.json", '{"a":1}')
    link = tmp_path / "linked.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported")
    with pytest.raises((OSError, StudioQuestError)):
        read_studio_private_json(link, 4096)
    parent = tmp_path / "parent"
    parent.mkdir()
    private(parent / "approved.json", '{"a":1}')
    alias = tmp_path / "alias"
    alias.symlink_to(parent, target_is_directory=True)
    with pytest.raises((OSError, StudioQuestError)):
        read_studio_private_json(alias / "approved.json", 4096)


def test_private_json_detects_parent_replacement_during_read(tmp_path, monkeypatch):
    from skeleton.ai.game_builder import studio_quest_private_io as module
    parent = tmp_path / "parent"
    parent.mkdir()
    path = private(parent / "approved.json", '{"a":1}')
    old_open = module._open_directory
    calls = 0

    def swapped(directory):
        nonlocal calls
        calls += 1
        if calls == 2:
            parent.rename(tmp_path / "retired")
            parent.mkdir()
            private(parent / "approved.json", '{"a":2}')
        return old_open(directory)

    monkeypatch.setattr(module, "_open_directory", swapped)
    with pytest.raises(StudioQuestError, match="parent directory was replaced"):
        read_studio_private_json(path, 4096)
