"""Tournament builder acceptance: atomic source edits, replay and gameplay."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.combat_tournament import original_tournament
from skeleton.game.gameplay.combat_tournament_author import (
    CombatSessionError, cli, edit_author, new_author,
    preview_author, verify_author,
)


def stat_edit(session, *, entrant="lantern_scout", field="attack", value=7):
    return {"kind": "set_stat", "entrant_id": entrant, "field": field,
            "value": value, "expected_source_digest": session["source_digest"]}


def test_author_edits_replay_and_preview_canonical_game() -> None:
    original = new_author(original_tournament())
    edited = edit_author(original, stat_edit(original))
    assert edited["source"]["entrants"][0]["attack"] == 7
    assert original["source"]["entrants"][0]["attack"] == 6
    assert verify_author(json.loads(json.dumps(edited))) == edited
    result = preview_author(edited)
    assert result["tournament"]["state"]["phase"] in ("won", "draw")
    assert result["tournament"]["source_digest"] == edited["source_digest"]
    assert result["receipt"] == dig({k: v for k, v in result.items() if k != "receipt"})


def test_swap_seed_order_changes_bracket_and_is_replayable() -> None:
    initial = new_author(original_tournament())
    changed = edit_author(initial, {"kind": "swap_seeds", "left_id": "lantern_scout",
                                    "right_id": "tide_runner",
                                    "expected_source_digest": initial["source_digest"]})
    assert changed["source"]["entrants"][0]["id"] == "tide_runner"
    assert preview_author(changed)["tournament"]["state"]["matches"][0]["left"] == "tide_runner"
    assert verify_author(changed) == changed


def test_turn_budget_edit_is_bounded_and_previewable() -> None:
    initial = new_author(original_tournament())
    changed = edit_author(initial, {"kind": "set_turn_limit", "value": 20,
                                    "expected_source_digest": initial["source_digest"]})
    assert changed["source"]["match_turn_limit"] == 20
    assert preview_author(changed)["tournament"]["source"]["match_turn_limit"] == 20


def test_stale_source_and_forged_receipt_are_rejected() -> None:
    initial = new_author(original_tournament())
    edited = edit_author(initial, stat_edit(initial))
    with pytest.raises(CombatSessionError, match="stale"):
        edit_author(edited, stat_edit(initial))
    bad = copy.deepcopy(edited)
    bad["journal"][0]["after"] = "0" * 64
    with pytest.raises(CombatSessionError, match="receipt mismatch"):
        verify_author(bad)
    bad = copy.deepcopy(edited)
    bad["source"]["entrants"][0]["attack"] = 1000
    with pytest.raises(CombatSessionError, match="mismatch"):
        verify_author(bad)


@pytest.mark.parametrize("mutate", [
    lambda e: e.update(value=True),
    lambda e: e.update(field="team"),
    lambda e: e.update(entrant_id="unknown"),
    lambda e: e.update(value=1001),
    lambda e: e.update(unsafe=True),
])
def test_invalid_edit_fails_without_mutation(mutate) -> None:
    initial = new_author(original_tournament())
    command = stat_edit(initial)
    mutate(command)
    with pytest.raises(CombatSessionError):
        edit_author(initial, command)
    assert verify_author(initial) == initial


def test_cli_new_edit_preview_verify(capsys) -> None:
    assert cli(["demo"]) == 0
    original = json.loads(capsys.readouterr().out)
    command = stat_edit(original)
    assert cli(["edit", "--session-json", json.dumps(original),
                "--edit-json", json.dumps(command)]) == 0
    edited = json.loads(capsys.readouterr().out)
    assert cli(["verify", "--session-json", json.dumps(edited)]) == 0
    assert json.loads(capsys.readouterr().out) == edited
    assert cli(["preview", "--session-json", json.dumps(edited)]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["tournament"]["source_digest"] == edited["source_digest"]


def test_cli_bad_edit_is_nonzero(capsys) -> None:
    session = new_author(original_tournament())
    assert cli(["edit", "--session-json", json.dumps(session),
                "--edit-json", '{"kind":"forged"}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
