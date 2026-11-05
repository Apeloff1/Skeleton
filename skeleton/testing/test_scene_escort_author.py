"""Source-fenced convoy authoring and deterministic playable preview."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_escort import demo_actions, import_escort, original_escort
from skeleton.game.gameplay.scene_escort_author import (
    apply_author, cli, new_author, preview_author, verify_author,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def edit(document, change):
    return apply_author(
        document, change, expected_digest=document["source_digest"],
        expected_revision=document["revision"],
    )


def test_transactional_edit_replays_and_preview_exports_real_gameplay():
    doc = new_author(original_escort())
    doc = edit(doc, {"kind": "set_integrity", "value": 3})
    doc = edit(doc, {"kind": "set_hazard", "scene_id": "sanctuary", "damage": 1})
    assert verify_author(json.loads(json.dumps(doc))) == doc
    preview = preview_author(doc, demo_actions())
    assert preview["phase"] == "delivered"
    assert preview["integrity"] == 1
    assert import_escort(preview["bundle"])["state"]["reward"] == 20


def test_replay_rejects_tampered_author_state_and_edit_history():
    doc = edit(new_author(original_escort()), {"kind": "set_reward", "value": 5})
    for mutate in (
        lambda x: x["source"].update(delivery_reward=999),
        lambda x: x["edits"][0].update(value=999),
        lambda x: x.update(revision=5),
        lambda x: x.update(source_digest="0" * 64),
    ):
        changed = copy.deepcopy(doc)
        mutate(changed)
        with pytest.raises(SceneTravelError):
            verify_author(changed)


def test_expected_sha_style_revision_and_source_digest_are_required():
    doc = new_author(original_escort())
    with pytest.raises(SceneTravelError, match="stale"):
        apply_author(doc, {"kind": "set_integrity", "value": 4},
                     expected_digest="0" * 64, expected_revision=0)
    with pytest.raises(SceneTravelError, match="stale"):
        apply_author(doc, {"kind": "set_integrity", "value": 4},
                     expected_digest=doc["source_digest"], expected_revision=1)


def test_hazard_and_supply_editor_reject_invalid_or_unearned_content():
    doc = new_author(original_escort())
    with pytest.raises(SceneTravelError, match="missing"):
        edit(doc, {"kind": "set_hazard", "scene_id": "void", "damage": 1})
    with pytest.raises(SceneTravelError, match="already"):
        edit(doc, {"kind": "add_supply", "pickup": "quay:find_key"})
    doc = edit(doc, {"kind": "remove_supply", "pickup": "quay:find_key"})
    with pytest.raises(SceneTravelError, match="not authored"):
        edit(doc, {"kind": "remove_supply", "pickup": "quay:find_key"})
    with pytest.raises(SceneTravelError, match="earned"):
        preview_author(doc, demo_actions())


def test_editor_cli_demo_is_playable(capsys):
    assert cli(["demo"]) == 0
    assert json.loads(capsys.readouterr().out)["phase"] == "delivered"
    assert cli(["verify", "--document-json", "{}"]) == 2
    assert "error" in capsys.readouterr().err
