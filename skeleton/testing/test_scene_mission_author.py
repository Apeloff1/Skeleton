"""Transactional mission editing must preserve source custody and real play."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_mission import demo_actions, original_mission
from skeleton.game.gameplay.scene_mission_author import (
    apply_edits, cli, new_editor, preview_editor, verify_editor,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _apply(editor, edits):
    return apply_edits(editor, edits, expected_revision=editor["revision"],
                       expected_digest=editor["digest"])


def test_original_mission_editor_preview_reaches_earned_ending():
    editor = new_editor(original_mission())
    report = preview_editor(editor, demo_actions())
    assert report["ending"] == "lantern_restored"
    assert report["reputation"] >= 5
    assert report["bundle_checksum"]
    assert verify_editor(json.loads(json.dumps(editor))) == editor


def test_atomic_choice_and_mission_edits_change_real_preview_reputation():
    editor = new_editor(original_mission())
    updated = _apply(editor, [
        {"kind": "choice_reputation", "choice_id": "restore_lantern",
         "option_id": "help", "reputation": 5},
        {"kind": "mission_reputation", "mission_id": "pledge", "reputation": 3},
    ])
    assert updated["revision"] == 2
    assert editor["revision"] == 0
    assert updated["source_digest"] != editor["source_digest"]
    assert preview_editor(updated, demo_actions())["reputation"] == (
        preview_editor(editor, demo_actions())["reputation"] + 5
    )


def test_editing_ending_threshold_affects_actual_earned_outcome():
    editor = new_editor(original_mission())
    updated = _apply(editor, [
        {"kind": "ending_threshold", "ending_id": "lantern_restored",
         "min_reputation": 999},
    ])
    with pytest.raises(SceneTravelError, match="reputation"):
        preview_editor(updated, demo_actions())


def test_world_step_limit_edit_changes_playable_route():
    editor = new_editor(original_mission())
    updated = _apply(editor, [{"kind": "step_limit", "step_limit": 2}])
    with pytest.raises(SceneTravelError):
        preview_editor(updated, demo_actions())


def test_exit_requirement_must_reference_real_authored_item():
    editor = new_editor(original_mission())
    with pytest.raises(SceneTravelError):
        _apply(editor, [{"kind": "exit_requirement", "scene_id": "quay",
                         "exit_id": "north", "requires_item": "unearned"}])
    assert editor == new_editor(original_mission())


def test_pickup_edit_preserves_exit_item_referential_integrity():
    editor = new_editor(original_mission())
    with pytest.raises(SceneTravelError, match="required item"):
        _apply(editor, [{"kind": "pickup_item", "scene_id": "quay",
                         "pickup_id": "find_key", "item_id": "new_key"}])
    assert editor == new_editor(original_mission())


def test_batch_failure_is_atomic_and_stale_lease_fails_closed():
    editor = new_editor(original_mission())
    with pytest.raises(SceneTravelError):
        _apply(editor, [
            {"kind": "choice_reputation", "choice_id": "restore_lantern",
             "option_id": "help", "reputation": 7},
            {"kind": "mission_reputation", "mission_id": "missing", "reputation": 1},
        ])
    assert editor["revision"] == 0
    updated = _apply(editor, [{"kind": "mission_reputation",
                               "mission_id": "pledge", "reputation": 2}])
    with pytest.raises(SceneTravelError, match="stale"):
        apply_edits(updated, [{"kind": "step_limit", "step_limit": 10}],
                    expected_revision=0, expected_digest=editor["digest"])


@pytest.mark.parametrize("field", ["source", "source_digest", "revision", "digest", "journal"])
def test_forged_editor_receipts_are_rejected(field):
    editor = new_editor(original_mission())
    updated = _apply(editor, [{"kind": "mission_reputation",
                               "mission_id": "pledge", "reputation": 2}])
    bad = copy.deepcopy(updated)
    if field == "source":
        bad["source"]["missions"][0]["reputation"] = 900
    elif field in ("source_digest", "digest"):
        bad[field] = "0" * 64
    elif field == "revision":
        bad[field] = 0
    else:
        bad["journal"][0]["edit"]["reputation"] = 500
    with pytest.raises(SceneTravelError):
        verify_editor(bad)


@pytest.mark.parametrize("edits", [
    [], [{"kind": "step_limit", "step_limit": True}],
    [{"kind": "mission_reputation", "mission_id": "pledge", "reputation": -1}],
    [{"kind": "choice_reputation", "choice_id": "restore_lantern",
      "option_id": "missing", "reputation": 2}],
    [{"kind": "unknown"}],
])
def test_invalid_edits_rejected(edits):
    with pytest.raises(SceneTravelError):
        _apply(new_editor(original_mission()), edits)


def test_cli_new_apply_preview_verify_via_main(capsys):
    from skeleton.__main__ import main
    assert main(["scene-mission-author", "demo"]) == 0
    assert json.loads(capsys.readouterr().out)["ending"] == "lantern_restored"
    editor = new_editor(original_mission())
    assert cli(["apply", "--editor-json", json.dumps(editor),
                "--edits-json", json.dumps([{"kind": "mission_reputation",
                                            "mission_id": "pledge", "reputation": 2}]),
                "--expected-revision", "0", "--expected-digest", editor["digest"]]) == 0
    updated = json.loads(capsys.readouterr().out)
    assert updated["revision"] == 1
    assert cli(["verify", "--editor-json", json.dumps(updated)]) == 0
    assert json.loads(capsys.readouterr().out) == updated
