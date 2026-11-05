"""Public Skeleton command routing and bounded CLI error behavior."""
from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main


@pytest.mark.parametrize(("command", "subcommand", "field"), [
    ("scene-evacuation", "demo", "state"),
    ("scene-evacuation-board", "demo", "legal_actions"),
    ("scene-evacuation-author", "demo", "source"),
    ("scene-evacuation-accept", "demo", "checkpoints_verified"),
    ("scene-evacuation-solve", "demo", "status"),
    ("scene-evacuation-play", "demo", "checkpoint"),
])
def test_public_cli_vertical_is_reachable_and_json_bounded(capsys, command, subcommand, field):
    assert main([command, subcommand]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert field in payload
    assert payload["schema_version"].startswith("skeleton.")


@pytest.mark.parametrize("command", [
    "scene-evacuation", "scene-evacuation-board",
    "scene-evacuation-author", "scene-evacuation-accept",
    "scene-evacuation-solve", "scene-evacuation-play",
])
def test_public_cli_help_mentions_new_playable_vertical(capsys, command):
    assert main(["help"]) == 0
    assert command in capsys.readouterr().out


def test_malformed_user_source_rejected_without_traceback(capsys):
    assert main(["scene-evacuation", "simulate",
                 "--source-json", "{}", "--actions-json", "[]"]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False
    assert "error" in error
