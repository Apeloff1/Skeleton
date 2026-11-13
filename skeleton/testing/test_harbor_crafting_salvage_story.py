"""Ordered story events, earned consequences, CAS resume and hostile boards."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, digest
from skeleton.game.gameplay.harbor_crafting_salvage import build_salvage
from skeleton.game.gameplay.harbor_crafting_salvage_quest_events import (
    build_salvage_story, resume_salvage_story, verify_salvage_story,
)
from skeleton.testing.test_harbor_crafting_salvage import inputs, actions

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"


def story_board():
    return json.loads((FIXTURES / "harbor_lantern_quay_salvage_story.json").read_text())


def test_original_story_quests_earned_in_order():
    source, board = inputs()
    report = build_salvage(source, board, actions(), require_complete=True)
    story = build_salvage_story(report, story_board(), require_all=True)
    state = verify_salvage_story(story, require_all=True)
    assert len(state["completed"]) == 5
    assert state["reputation"] == 22
    assert state["ending"] == "harbor_restored"
    assert [event["quest_id"] for event in story["events"]] == state["completed"]


def test_story_cas_resume_preserves_previous_events():
    source, board = inputs()
    prefix = build_salvage(source, board, actions()[:4])
    story = build_salvage_story(prefix, story_board())
    completed = resume_salvage_story(story, actions()[4:],
                                      expected_digest=story["story_digest"],
                                      require_all=True)
    assert verify_salvage_story(completed)["reputation"] == 22
    assert completed["events"][0] == story["events"][0]
    with pytest.raises(HarborError, match="stale"):
        resume_salvage_story(story, [], expected_digest="0" * 64)


def test_invalid_prerequisite_and_resealed_story_event_rejected():
    source, board = inputs()
    report = build_salvage(source, board, actions())
    authored = story_board()
    authored["quests"][0]["requires"] = ["rescue_signal"]
    with pytest.raises(HarborError):
        build_salvage_story(report, authored)
    story = build_salvage_story(report, story_board())
    damaged = deepcopy(story)
    damaged["events"][0]["story"] = "unearned_epilogue"
    damaged["story_digest"] = digest({k: v for k, v in damaged.items()
                                       if k != "story_digest"})
    with pytest.raises(HarborError):
        verify_salvage_story(damaged)


def test_story_without_rescue_quest_cannot_mint_ending():
    source, board = inputs()
    report = build_salvage(source, board, actions(), require_complete=True)
    authored = story_board()
    authored["quests"] = authored["quests"][:-1]
    story = build_salvage_story(report, authored, require_all=True)
    assert verify_salvage_story(story)["ending"] is None
