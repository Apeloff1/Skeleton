"""Role edits are optimistic, replayable and cannot invalidate party coverage."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market_party import (
    normalize_party, original_party,
)
from skeleton.game.gameplay.scene_market_party_author import (
    edit_party, verify_party_edit,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_editor_grants_role_with_replayable_playable_preview():
    source, turns = original_party()
    receipt = edit_party(
        source, [{"kind": "grant_role", "player_id": "mira",
                  "role": "merchant"}], dig(normalize_party(source)), turns)
    assert receipt["preview_phase"] == "won"
    assert receipt["source"]["players"][1]["roles"] == [
        "artisan", "merchant", "navigator"]
    assert verify_party_edit(json.loads(json.dumps(receipt))) == receipt
    assert source["players"][1]["roles"] == ["navigator", "artisan"]


def test_cas_stale_and_role_coverage_fail_closed():
    source, _ = original_party()
    before = copy.deepcopy(source)
    with pytest.raises(SceneTravelError, match="changed since editor"):
        edit_party(source, [{"kind": "grant_role", "player_id": "mira",
                             "role": "merchant"}], "0" * 64)
    with pytest.raises(SceneTravelError, match="uncovered"):
        edit_party(source, [{"kind": "revoke_role", "player_id": "tavi",
                             "role": "courier"}], dig(normalize_party(source)))
    assert source == before


def test_editor_rejects_duplicate_noop_unknown_and_preview_failure():
    source, turns = original_party()
    sha = dig(normalize_party(source))
    with pytest.raises(SceneTravelError, match="no effect"):
        edit_party(source, [{"kind": "grant_role", "player_id": "rowan",
                             "role": "merchant"}], sha)
    with pytest.raises(SceneTravelError, match="not authored"):
        edit_party(source, [{"kind": "grant_role", "player_id": "ghost",
                             "role": "artisan"}], sha)
    with pytest.raises(SceneTravelError):
        edit_party(source, [{"kind": "grant_role", "player_id": "mira",
                             "role": "merchant"}], sha, turns[:-1] + [
                                 {"player_id": "ghost", "action": {"kind": "pass"}}])


def test_forged_editor_receipt_rejected():
    source, _ = original_party()
    receipt = edit_party(
        source, [{"kind": "grant_role", "player_id": "mira",
                  "role": "merchant"}], dig(normalize_party(source)))
    forged = copy.deepcopy(receipt)
    forged["source"]["players"][1]["roles"].remove("merchant")
    with pytest.raises(SceneTravelError):
        verify_party_edit(forged)


def test_author_cli_user_reachable(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-party-author", "demo"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["preview_phase"] == "won"
    assert main(["scene-market-party-author", "verify",
                 "--receipt-json", json.dumps(receipt)]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
