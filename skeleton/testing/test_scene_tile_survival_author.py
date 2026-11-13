"""Transactional survival authoring with source and replay witnesses."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_tile_survival import (
    import_survival, original_survival,
)
from skeleton.game.gameplay.scene_tile_survival_author import (
    apply_author, cli, new_author, preview_author, solve_author, verify_author,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def apply(document, edit):
    return apply_author(
        document, edit, expected_digest=document["source_digest"],
        expected_revision=document["revision"],
    )


def test_editor_preview_and_solver():
    source, actions = original_survival()
    document = new_author(source)
    assert verify_author(json.loads(json.dumps(document))) == document
    preview = preview_author(document, actions)
    assert preview["phase"] == "won"
    assert import_survival(preview["bundle"])["state_digest"] == (
        preview["state_digest"]
    )
    route = solve_author(document, max_states=4096)
    assert route["route"]["status"] == "found"
    assert route["route"]["source_digest"] == document["source_digest"]


def test_transactional_hazard_and_camp_edits():
    source, actions = original_survival()
    document = new_author(source)
    original = copy.deepcopy(document)
    edited = apply(document, {
        "kind": "set_hazard", "scene_id": "quay",
        "at": [2, 1], "damage": 2,
    })
    assert edited["revision"] == 1
    assert edited["source"]["hazards"][0]["damage"] == 2
    assert document == original
    preview = preview_author(edited, actions)
    assert preview["phase"] == "won"
    assert preview["health"] == 2
    edited = apply(edited, {
        "kind": "remove_hazard", "scene_id": "quay", "at": [2, 1],
    })
    assert edited["source"]["hazards"] == []
    edited = apply(edited, {
        "kind": "add_camp", "scene_id": "quay", "at": [0, 1],
    })
    assert len(edited["source"]["camps"]) == 2
    edited = apply(edited, {
        "kind": "remove_camp", "scene_id": "quay", "at": [0, 1],
    })
    assert len(edited["source"]["camps"]) == 1
    assert verify_author(edited) == edited


def test_food_edit_never_grants_unearned_item():
    source, actions = original_survival()
    document = new_author(source)
    edited = apply(document, {"kind": "remove_food", "pickup": "quay:find_key"})
    assert edited["source"]["food_pickups"] == []
    with pytest.raises(SceneTravelError, match="earned food"):
        preview_author(edited, actions)
    restored = apply(edited, {"kind": "add_food", "pickup": "quay:find_key"})
    assert preview_author(restored, actions)["phase"] == "won"


@pytest.mark.parametrize("edit", [
    {"kind": "set_health", "value": True},
    {"kind": "set_initial_food", "value": 99},
    {"kind": "set_turn_limit", "value": 0},
    {"kind": "add_food", "pickup": "quay:unknown"},
    {"kind": "remove_food", "pickup": "quay:unknown"},
    {"kind": "add_camp", "scene_id": "quay", "at": [1, 0]},
    {"kind": "add_camp", "scene_id": "gate", "at": [0, 1]},
    {"kind": "set_hazard", "scene_id": "gate", "at": [0, 1], "damage": 1},
    {"kind": "remove_hazard", "scene_id": "gate", "at": [0, 1]},
    {"kind": "invalid"},
])
def test_invalid_edits_fail_without_mutation(edit):
    source, _ = original_survival()
    document = new_author(source)
    before = copy.deepcopy(document)
    with pytest.raises(SceneTravelError):
        apply(document, edit)
    assert document == before


def test_stale_revision_and_forged_document_rejected():
    source, _ = original_survival()
    document = new_author(source)
    with pytest.raises(SceneTravelError, match="stale"):
        apply_author(
            document, {"kind": "set_health", "value": 4},
            expected_digest=document["source_digest"], expected_revision=1,
        )
    edited = apply(document, {"kind": "set_health", "value": 4})
    for key in ("source_digest", "digest"):
        forged = copy.deepcopy(edited)
        forged[key] = "0" * 64
        with pytest.raises(SceneTravelError):
            verify_author(forged)
    forged = copy.deepcopy(edited)
    forged["edits"][0]["value"] = 99
    with pytest.raises(SceneTravelError):
        verify_author(forged)


def test_canonical_cli_demo_and_round_trip(capsys):
    from skeleton.__main__ import main
    assert main(["scene-survival-author", "demo"]) == 0
    assert json.loads(capsys.readouterr().out)["phase"] == "won"
    source, _ = original_survival()
    assert cli(["new", "--source-json", json.dumps(source)]) == 0
    document = json.loads(capsys.readouterr().out)
    assert cli([
        "edit", "--document-json", json.dumps(document),
        "--edit-json", json.dumps({"kind": "set_health", "value": 4}),
        "--expected-digest", document["source_digest"],
        "--expected-revision", "0",
    ]) == 0
    updated = json.loads(capsys.readouterr().out)
    assert updated["revision"] == 1
    assert cli(["verify", "--document-json", json.dumps(updated)]) == 0
    assert json.loads(capsys.readouterr().out) == updated
    assert cli(["new", "--source-json", '{"x":1,"x":2}']) == 2
    assert "error" in json.loads(capsys.readouterr().err)
