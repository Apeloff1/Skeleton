"""GameForge remote projection flags must be validated before invoking the builder."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi import HTTPException  # noqa: E402

from skeleton.ai.runtime.api.routes import run_gameforge_adapter  # noqa: E402


def _state():
    # An existing execution-capable runner keeps the test independent of UI boot.
    return SimpleNamespace(gameforge=SimpleNamespace(execute=lambda *a, **kw: None))


@pytest.mark.parametrize("invalid", ["false", "true", 0, 1, None, [], {}])
def test_malformed_include_files_never_invokes_game_builder(invalid) -> None:
    with patch("skeleton.forge.game_builder.build_playable_game") as builder:
        with pytest.raises(HTTPException) as raised:
            run_gameforge_adapter({"vision": "Test scene", "include_files": invalid}, _state())
    assert raised.value.status_code == 422
    builder.assert_not_called()


@pytest.mark.parametrize("accepted", [False, True])
def test_valid_projection_flag_forwarded_after_builder(accepted: bool) -> None:
    sentinel = object()
    with (
        patch("skeleton.forge.game_builder.build_playable_game", return_value=sentinel) as builder,
        patch("skeleton.forge.game_builder.project_operator_http", return_value={"ok": True}) as projector,
    ):
        result = run_gameforge_adapter(
            {"vision": "Test scene", "include_files": accepted}, _state()
        )
    assert result == {"ok": True}
    builder.assert_called_once()
    projector.assert_called_once_with(sentinel, include_files=accepted)


def test_remote_project_write_guard_remains_pre_build() -> None:
    with patch("skeleton.forge.game_builder.build_playable_game") as builder:
        with pytest.raises(HTTPException) as raised:
            run_gameforge_adapter(
                {"vision": "Test scene", "project_root": "/tmp/untrusted", "include_files": True},
                _state(),
            )
    assert raised.value.status_code == 422
    builder.assert_not_called()
