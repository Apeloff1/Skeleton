"""Transactional quest authoring, CAS and replayed preview acceptance."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, digest
from skeleton.game.gameplay.harbor_crafting_patrol_quest_authoring import (
    edit_patrol_quests, verify_patrol_quest_revision,
)
from skeleton.game.gameplay.harbor_crafting_patrol_cli import main
from skeleton.testing.test_harbor_crafting_patrol_quests import inputs_with_quests


def test_quest_editor_replays_reward_consequences():
    patrol, board = inputs_with_quests()
    edits = [{"op": "set-reward", "id": "quiet_extraction", "value": 21}]
    revision = edit_patrol_quests(patrol, board, edits, expected_digest=digest(board))
    assert verify_patrol_quest_revision(revision)["quests"][-1]["reward"] == 21
    assert revision["preview_before"]["reward"] == 30
    assert revision["preview_after"]["reward"] == 41
    assert board["quests"][-1]["reward"] == 10
    with pytest.raises(HarborError, match="stale"):
        edit_patrol_quests(patrol, board, edits, expected_digest="0" * 64)


def test_quest_editor_rejects_cyclic_prerequisite():
    patrol, board = inputs_with_quests()
    edits = [{"op": "set-requires", "id": "recover_registry",
              "value": ["quiet_extraction"]}]
    with pytest.raises(HarborError, match="precede"):
        edit_patrol_quests(patrol, board, edits, expected_digest=digest(board))


def test_quest_revision_forgery_rejected():
    patrol, board = inputs_with_quests()
    edits = [{"op": "set-reward", "id": "quiet_extraction", "value": 21}]
    revision = edit_patrol_quests(patrol, board, edits, expected_digest=digest(board))
    forged = deepcopy(revision)
    forged["preview_after"]["reward"] = 999
    forged["revision_digest"] = digest({k: v for k, v in forged.items()
                                         if k != "revision_digest"})
    with pytest.raises(HarborError):
        verify_patrol_quest_revision(forged)


def test_quest_authoring_cli_roundtrip(tmp_path, capsys):
    patrol, board = inputs_with_quests()
    report_path = tmp_path / "patrol.json"
    report_path.write_text(json.dumps(patrol))
    edits = tmp_path / "edits.json"
    edits.write_text(json.dumps([{"op": "set-reward",
                                  "id": "quiet_extraction", "value": 21}]))
    assert main(["quest-author", "--report", str(report_path),
                 "--quest-edits", str(edits),
                 "--expected-digest", digest(board)]) == 0
    revision = json.loads(capsys.readouterr().out)
    path = tmp_path / "revision.json"
    path.write_text(json.dumps(revision))
    assert main(["quest-verify-author", "--quest-revision", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["quests"][-1]["reward"] == 21
