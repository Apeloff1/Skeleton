"""Client input never creates a stateful GameForge runner before validation."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi import HTTPException  # noqa: E402

from skeleton.ai.runtime.api.routes import run_gameforge_adapter  # noqa: E402


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("vision", []),
        ("era", 42),
        ("archetype", True),
        ("repair_mode", "unreviewed-mode"),
        ("playtest", "unreviewed-playtest"),
        ("target", "unregistered-export"),
        ("answers", []),
        ("answers", "not-a-mapping"),
        ("include_files", 1),
    ],
)
def test_invalid_fields_never_create_runner_or_start_builder(field, value) -> None:
    state = SimpleNamespace()
    with (
        patch("skeleton.ai.runtime.api.routes._gameforge_runner") as runner,
        patch("skeleton.forge.game_builder.build_playable_game") as builder,
    ):
        with pytest.raises(HTTPException) as denied:
            run_gameforge_adapter({"vision": "Small game", field: value}, state)
    assert denied.value.status_code == 422
    runner.assert_not_called()
    builder.assert_not_called()
    assert not hasattr(state, "gameforge_run")


def test_valid_preflight_keeps_all_canonical_builder_parameters() -> None:
    state = SimpleNamespace()
    with (
        patch("skeleton.ai.runtime.api.routes._gameforge_runner", return_value="runner") as runner,
        patch("skeleton.forge.game_builder.build_playable_game", return_value=object()) as builder,
        patch("skeleton.forge.game_builder.project_operator_http", return_value={"ok": True}) as project,
    ):
        response = run_gameforge_adapter(
            {"vision": "Test world", "era": "retro", "include_files": True,
             "answers": {"theme": "snow"}},
            state,
        )
    assert response == {"ok": True}
    runner.assert_called_once_with(state)
    builder.assert_called_once()
    assert builder.call_args.args == ("Test world",)
    assert builder.call_args.kwargs["era"] == "retro"
    assert builder.call_args.kwargs["answers"] == {"theme": "snow"}
    assert builder.call_args.kwargs["runner"] == "runner"
    project.assert_called_once()
    assert project.call_args.kwargs["include_files"] is True
