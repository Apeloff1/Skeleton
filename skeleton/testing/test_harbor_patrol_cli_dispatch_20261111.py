"""Regression for patrol CLI command families that already produced a result.

The second command-dispatch chain must not re-enter run/author fallthrough
and reject otherwise successful hint, quest, debrief or choice commands.
"""
from __future__ import annotations

import json

import pytest

from skeleton.game.gameplay import harbor_crafting_patrol_cli as cli


@pytest.mark.parametrize(("command", "handler", "flags"), [
    ("quest-author", "edit_patrol_quests",
     ["--report", "report.json", "--quest-board", "quests.json", "--quest-edits", "edits.json"]),
    ("quest-verify-author", "verify_patrol_quest_revision",
     ["--quest-revision", "revision.json"]),
    ("quest-run", "build_patrol_quests",
     ["--report", "report.json", "--quest-board", "quests.json"]),
    ("quest-verify", "verify_patrol_quests",
     ["--quest-ledger", "ledger.json"]),
    ("hint", "patrol_hints", ["--report", "report.json"]),
    ("verify-debrief", "verify_patrol_debrief",
     ["--debrief", "debrief.json"]),
    ("choices", "compare_patrol_debriefs",
     ["--report", "report.json", "--debrief", "debrief.json"]),
    ("debrief", "build_patrol_debrief",
     ["--report", "report.json", "--debrief", "debrief.json"]),
])
def test_prevalidated_command_does_not_fall_through(
    monkeypatch, capsys, command, handler, flags,
):
    calls = []

    def fake_handler(*args, **kwargs):
        calls.append((args, kwargs))
        return {"completed": command}

    monkeypatch.setattr(cli, "_read", lambda path, maximum: {"fixture": path})
    monkeypatch.setattr(cli, handler, fake_handler)
    monkeypatch.setattr(cli, "canonical", lambda result: json.dumps(result).encode("utf-8"))
    assert cli.main([command, *flags]) == 0
    assert len(calls) == 1
    assert json.loads(capsys.readouterr().out) == {"completed": command}


def test_unknown_command_still_fails_closed():
    with pytest.raises(SystemExit) as caught:
        cli.main(["unsupported"])
    assert caught.value.code == 2
