"""Headless validation for the frozen game's native preview entrypoint."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / "packaging" / "windows" / "game_preview_entry.py"
_spec = importlib.util.spec_from_file_location("skeleton_game_preview_entry", ENTRY)
assert _spec is not None and _spec.loader is not None
game_entry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(game_entry)


@pytest.mark.parametrize("argv", [
    ["--output", "another.json"],
    ["--port-blueprint", "enhancement.json"],
    ["--seed", "7", "--project", "project.json"],
    ["--chip8-demo", "--edit-project", "project.json"],
])
def test_invalid_mode_combinations_fail_without_launching_native_window(argv):
    with patch.object(game_entry, "run_game_preview") as preview:
        with patch.object(game_entry, "open_homebrew_editor") as editor:
            with pytest.raises(SystemExit) as error:
                game_entry.main(argv)
            assert error.value.code == 2
            preview.assert_not_called()
            editor.assert_not_called()


def test_seed_mode_dispatches_only_to_preview():
    with patch.object(game_entry, "run_game_preview", return_value=0) as preview:
        assert game_entry.main(["--seed", "42"]) == 0
        preview.assert_called_once_with(seed=42)


def test_editor_mode_dispatches_explicit_paths():
    with patch.object(game_entry, "open_homebrew_editor", return_value=0) as editor:
        assert game_entry.main(["--edit-project", "project.json", "--output", "fresh.json"]) == 0
        editor.assert_called_once_with("project.json", output="fresh.json")


def test_port_mode_requires_explicit_project_and_blueprint():
    with patch.object(game_entry, "open_native_homebrew_port", return_value=0) as port:
        assert game_entry.main(["--project", "owned.json", "--port-blueprint", "plan.json"]) == 0
        port.assert_called_once_with("owned.json", "plan.json")


def test_chip8_mode_does_not_start_regular_preview():
    with patch.object(game_entry, "run_native_chip8_preview", return_value=0) as chip8:
        with patch.object(game_entry, "run_game_preview") as preview:
            assert game_entry.main(["--chip8-demo"]) == 0
            chip8.assert_called_once_with()
            preview.assert_not_called()
