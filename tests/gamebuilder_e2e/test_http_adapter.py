"""``run_gameforge_adapter`` — the function behind ``POST /api/v1/gameforge/run``.

Driven in-process with a minimal state object so no server, seal, or charter
is required; HTTP gating is covered elsewhere.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from skeleton.api.routes import run_gameforge_adapter


def _state():
    return SimpleNamespace(cockpit=None, gameforge=None)


def test_adapter_returns_ten_stage_body():
    body = run_gameforge_adapter({"vision": "a small platformer about a fox"}, _state())
    assert body["succeeded"] is True
    assert "files" not in body
    assert "project.godot" in body["file_names"]


def test_adapter_include_files():
    body = run_gameforge_adapter({"vision": "a platformer", "include_files": True}, _state())
    assert set(body["files"]) == set(body["file_names"])


def test_adapter_caches_runner_on_state():
    state = _state()
    run_gameforge_adapter({"vision": "a platformer"}, state)
    first = state.gameforge_run
    run_gameforge_adapter({"vision": "a platformer"}, state)
    assert state.gameforge_run is first


@pytest.mark.parametrize("key", ["project_root", "out", "overwrite"])
def test_remote_fs_keys_rejected(key):
    with pytest.raises(HTTPException) as info:
        run_gameforge_adapter({"vision": "a platformer", key: "/tmp/x"}, _state())
    assert info.value.status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [("repair_mode", "nope"), ("playtest", "always"), ("target", "unreal5000")],
)
def test_bad_enum_rejected_before_state_mutation(field, value):
    state = _state()
    with pytest.raises((HTTPException, ValueError)):
        run_gameforge_adapter({"vision": "a platformer", field: value}, state)
    assert not hasattr(state, "gameforge_run")


def test_adapter_honours_era():
    body = run_gameforge_adapter({"vision": "a platformer", "era": "soulslike"}, _state())
    assert body["succeeded"] is True
