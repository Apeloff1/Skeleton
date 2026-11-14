"""Hermetic CLI surface continuity after first-install source reconciliation."""
from __future__ import annotations

import sys
from types import ModuleType

import pytest

from skeleton.app.cli import _parser, run_app_cli


def test_cold_installer_verification_defaults_remain_60_attempts_and_two_seconds():
    args = _parser().parse_args(["up"])
    assert args.verify_attempts == 60
    assert args.verify_delay == 2.0


@pytest.mark.parametrize(("command", "module"), [
    ("play-dialogue", "skeleton.app.dialogue_cli"),
    ("play-combat", "skeleton.app.combat_cli"),
    ("game-project", "skeleton.ai.runtime.game_project_cli"),
])
def test_source_bound_game_commands_delegate_without_swallowing_argv(
    monkeypatch, command, module,
):
    called = []
    fake = ModuleType(module)

    def run(arguments):
        called.append(list(arguments))
        return 27

    fake.main = run
    monkeypatch.setitem(sys.modules, module, fake)
    assert run_app_cli([command, "--help", "--source", "original"]) == 27
    assert called == [["--help", "--source", "original"]]


@pytest.mark.parametrize("command", ["play-dialogue", "play-combat"])
def test_source_bound_game_commands_remain_in_help(command):
    help_text = _parser().format_help()
    assert command in help_text
