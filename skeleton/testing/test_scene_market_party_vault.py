"""Fail-closed source-bound cooperative vault and real gameplay acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market_party import (
    original_party, simulate_party, export_party, import_party,
)
from skeleton.game.gameplay.scene_market_party_vault import (
    accept_vault, cli, export_vault, import_vault, new_vault,
    read_slot, transact_vault, verify_vault,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


@pytest.fixture
def campaign():
    source, turns = original_party()
    return source, turns, simulate_party(source, turns[:2])


def _put(checkpoint, *, revision=0, expected=None, slot="save"):
    return {"kind": "put", "slot": slot, "expected_revision": revision,
            "expected_slot_digest": expected, "checkpoint": checkpoint}


def test_played_checkpoint_roundtrips_vault_and_canonical_party(campaign):
    source, _, checkpoint = campaign
    vault = transact_vault(new_vault(source), _put(checkpoint))
    assert read_slot(vault, "save") == checkpoint
    assert verify_vault(json.loads(json.dumps(vault))) == vault
    assert import_vault(json.loads(json.dumps(export_vault(vault)))) == vault
    assert import_party(export_party(read_slot(vault, "save"))) == checkpoint


def test_stale_revision_and_slot_lease_rejected_without_mutation(campaign):
    source, turns, checkpoint = campaign
    vault = transact_vault(new_vault(source), _put(checkpoint))
    original = copy.deepcopy(vault)
    later = simulate_party(source, turns[:3])
    with pytest.raises(SceneTravelError, match="stale.*revision"):
        transact_vault(vault, _put(later, revision=0, expected=checkpoint["state_digest"]))
    with pytest.raises(SceneTravelError, match="stale.*slot"):
        transact_vault(vault, _put(later, revision=1, expected=None))
    assert vault == original
    updated = transact_vault(vault, _put(
        later, revision=1, expected=checkpoint["state_digest"]))
    assert read_slot(updated, "save") == later
    assert updated["revision"] == 2


def test_delete_slot_is_replayable_and_cannot_be_repeated(campaign):
    source, _, checkpoint = campaign
    vault = transact_vault(new_vault(source), _put(checkpoint))
    deleted = transact_vault(vault, {
        "kind": "delete", "slot": "save", "expected_revision": 1,
        "expected_slot_digest": checkpoint["state_digest"]})
    assert deleted["slots"] == {}
    assert import_vault(export_vault(deleted)) == deleted
    with pytest.raises(SceneTravelError):
        read_slot(deleted, "save")
    with pytest.raises(SceneTravelError):
        transact_vault(deleted, {
            "kind": "delete", "slot": "save", "expected_revision": 2,
            "expected_slot_digest": None})


def test_cross_source_and_unearned_checkpoint_rejected(campaign):
    source, _, checkpoint = campaign
    wrong = copy.deepcopy(source)
    wrong["players"][0]["player_id"] = "different"
    with pytest.raises(SceneTravelError, match="source mismatch"):
        transact_vault(new_vault(wrong), _put(checkpoint))
    forged = copy.deepcopy(checkpoint)
    forged["state"]["market"]["state"]["credits"] += 500
    with pytest.raises(SceneTravelError):
        transact_vault(new_vault(source), _put(forged))


@pytest.mark.parametrize("field", ["revision", "state_digest", "source_digest", "slots", "journal"])
def test_tampered_vault_rejected_even_when_export_checksum_recomputed(campaign, field):
    source, _, checkpoint = campaign
    vault = transact_vault(new_vault(source), _put(checkpoint))
    forged = copy.deepcopy(vault)
    if field == "revision":
        forged[field] = 5
    elif field == "slots":
        forged[field]["save"]["state"]["market"]["state"]["credits"] = 999
    elif field == "journal":
        forged[field][0]["after_state_digest"] = "0" * 64
    else:
        forged[field] = "0" * 64
    bundle = {"schema_version": "skeleton.scene_market_party_vault_bundle.v1",
              "vault": forged, "source_digest": forged["source_digest"],
              "state_digest": forged["state_digest"]}
    bundle["checksum"] = dig(bundle)
    with pytest.raises(SceneTravelError):
        import_vault(bundle)


@pytest.mark.parametrize("value", [True, -1, 1.5, "0", 24])
def test_invalid_revision_fails_closed(campaign, value):
    source, _, checkpoint = campaign
    with pytest.raises(SceneTravelError):
        transact_vault(new_vault(source), _put(checkpoint, revision=value))


def test_duplicate_slot_and_bad_names_fail_closed(campaign):
    source, _, checkpoint = campaign
    vault = transact_vault(new_vault(source), _put(checkpoint))
    with pytest.raises(SceneTravelError, match="unchanged"):
        transact_vault(vault, _put(
            checkpoint, revision=1, expected=checkpoint["state_digest"]))
    with pytest.raises(SceneTravelError):
        transact_vault(vault, _put(
            checkpoint, revision=1, slot="x" * 41))
    with pytest.raises(SceneTravelError):
        transact_vault(vault, {"kind": "put", "slot": "x",
                               "expected_revision": 1,
                               "expected_slot_digest": None,
                               "checkpoint": checkpoint, "untrusted": True})


def test_end_to_end_restart_and_export_acceptance():
    receipt = accept_vault()
    assert receipt["phase"] == "won"
    assert receipt["revision"] == 2
    assert receipt["checksum"] == dig({k: v for k, v in receipt.items()
                                      if k != "checksum"})


def test_cli_main_dispatch_and_error_channel(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-party-vault", "accept"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["phase"] == "won"
    assert cli(["verify", "--vault-json", "{}"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
