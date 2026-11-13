"""Boundary tests for cooperative vault recovery CLI and report custody."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_market_party import original_party, simulate_party
from skeleton.game.gameplay.scene_market_party_vault import new_vault, transact_vault
from skeleton.game.gameplay.scene_market_party_vault_history import (
    apply_recovery, cli, diff_vault, history_vault, preview_recovery,
    seek_vault, verify_history_vault, verify_recovery,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _vault():
    source, turns = original_party()
    first = simulate_party(source, turns[:2])
    second = simulate_party(source, turns[:3])
    vault = transact_vault(new_vault(source), {
        "kind": "put", "slot": "primary", "expected_revision": 0,
        "expected_slot_digest": None, "checkpoint": first})
    vault = transact_vault(vault, {
        "kind": "put", "slot": "primary", "expected_revision": 1,
        "expected_slot_digest": first["state_digest"], "checkpoint": second})
    return vault


def test_replayed_reverse_diff_and_page_terminal_digest():
    vault = _vault()
    reverse = diff_vault(vault, 2, 0)
    assert reverse["changes"][0]["after_slot_digest"] is None
    assert reverse["changes"][0]["before_turns"] == 3
    page = history_vault(vault, start=2)
    assert page["entries"] == []
    assert page["page_terminal_state_digest"] == vault["state_digest"]
    assert page["next_revision"] == 2


def test_recovery_rejects_changed_parent_source_and_slot_without_mutation():
    vault = _vault()
    original = copy.deepcopy(vault)
    report = preview_recovery(
        vault, target_revision=1, slot="primary", expected_revision=2)
    other = copy.deepcopy(vault)
    other["journal"][1]["action"]["slot"] = "other"
    with pytest.raises(SceneTravelError):
        apply_recovery(other, report)
    changed = copy.deepcopy(report)
    changed["slot"] = "other"
    with pytest.raises(SceneTravelError):
        verify_recovery(vault, changed)
    assert vault == original


def test_recovery_receipt_is_not_actor_signature():
    vault = _vault()
    report = preview_recovery(
        vault, target_revision=1, slot="primary", expected_revision=2)
    assert "not_history_rewrite_or_authentication" in report["qualification"]
    assert "checksum" in report
    assert "signature" not in report
    assert "authorization" not in report


def test_cli_diff_verify_and_invalid_input(capsys):
    vault = _vault()
    serialized = json.dumps(vault)
    assert cli(["diff", "--vault-json", serialized,
                "--from-revision", "0", "--to-revision", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["changes"][0]["slot"] == "primary"
    report = history_vault(vault)
    assert cli(["verify-history", "--vault-json", serialized,
                "--report-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert cli(["history", "--vault-json", serialized, "--limit", "0"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)


@pytest.mark.parametrize("revision", [0, 1, 2])
def test_revision_seek_round_trip_json_is_identical(revision):
    vault = _vault()
    assert seek_vault(json.loads(json.dumps(vault)), revision) == seek_vault(
        vault, revision)


def test_no_recovery_history_report_can_validate_against_another_vault():
    vault = _vault()
    history = history_vault(vault)
    recovery = preview_recovery(
        vault, target_revision=1, slot="primary", expected_revision=2)
    changed = apply_recovery(vault, recovery)
    with pytest.raises(SceneTravelError):
        verify_history_vault(changed, history)
    with pytest.raises(SceneTravelError):
        verify_recovery(changed, recovery)
