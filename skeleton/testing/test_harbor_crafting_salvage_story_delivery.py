"""Story source -> event runtime -> CAS -> package -> CLI -> replay acceptance."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, digest
from skeleton.game.gameplay.harbor_crafting_salvage import build_salvage
from skeleton.game.gameplay.harbor_crafting_salvage_story_authoring import (
    edit_salvage_story, verify_salvage_story_revision,
)
from skeleton.game.gameplay.harbor_crafting_salvage_story_package import (
    build_story_package, play_story_package, verify_story_package_play,
)
from skeleton.game.gameplay.harbor_crafting_salvage_story_cli import main
from skeleton.testing.test_harbor_crafting_salvage import inputs, actions
from skeleton.testing.test_harbor_crafting_salvage_story import story_board


def test_authoring_preview_replay_and_stale_cas():
    source, board = inputs()
    report = build_salvage(source, board, actions())
    story = story_board()
    edits = [{"op": "set-quest", "id": "rescue_signal",
              "field": "reward", "value": 15}]
    revision = edit_salvage_story(report, story, edits,
                                  expected_board_digest=digest(story), preview=True)
    assert verify_salvage_story_revision(revision)["quests"][-1]["reward"] == 15
    assert revision["preview_after"]["reputation"] == 29
    with pytest.raises(HarborError, match="stale"):
        edit_salvage_story(report, story, edits, expected_board_digest="0" * 64)


def test_package_play_requires_earned_quest_chain():
    source, board = inputs()
    package = build_story_package(source, board, story_board(), package_id="original_story")
    play = play_story_package(package, actions(), require_all=True)
    assert verify_story_package_play(play, require_all=True)["ending"] == "harbor_restored"
    with pytest.raises(HarborError):
        play_story_package(package, actions()[:4], require_all=True)
    damaged = deepcopy(play)
    damaged["story"]["events"][0]["story"] = "unearned"
    damaged["play_digest"] = digest({k: v for k, v in damaged.items()
                                      if k != "play_digest"})
    with pytest.raises(HarborError):
        verify_story_package_play(damaged)


def test_cli_source_to_story_and_export(tmp_path, capsys):
    action_path = tmp_path / "actions.json"
    action_path.write_text(json.dumps(actions()))
    assert main(["run", "--actions", str(action_path), "--require-all"]) == 0
    story = json.loads(capsys.readouterr().out)
    story_path = tmp_path / "story.json"
    story_path.write_text(json.dumps(story))
    assert main(["verify", "--story", str(story_path), "--require-all"]) == 0
    assert json.loads(capsys.readouterr().out)["reputation"] == 22
    assert main(["package"]) == 0
    package = json.loads(capsys.readouterr().out)
    package_path = tmp_path / "package.json"
    package_path.write_text(json.dumps(package))
    assert main(["play", "--package", str(package_path),
                 "--actions", str(action_path), "--require-all"]) == 0
    play = json.loads(capsys.readouterr().out)
    play_path = tmp_path / "play.json"
    play_path.write_text(json.dumps(play))
    assert main(["verify-play", "--play", str(play_path), "--require-all"]) == 0
    assert json.loads(capsys.readouterr().out)["ending"] == "harbor_restored"
