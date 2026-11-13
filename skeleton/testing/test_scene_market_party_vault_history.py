"""Canonical cooperative vault history, recovery and portability contracts."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market_party import (
    export_party, import_party, original_party, resume_party, simulate_party,
)
from skeleton.game.gameplay.scene_market_party_vault import (
    export_vault, import_vault, new_vault, read_slot, transact_vault, verify_vault,
)
from skeleton.game.gameplay.scene_market_party_vault_history import (
    accept_recovery, apply_recovery, cli, diff_vault, history_vault,
    preview_recovery, seek_vault, verify_history_vault, verify_recovery,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


@pytest.fixture
def played():
    source, turns = original_party()
    first = simulate_party(source, turns[:2])
    second = simulate_party(source, turns[:3])
    vault = transact_vault(new_vault(source), {
        "kind": "put", "slot": "campaign", "expected_revision": 0,
        "expected_slot_digest": None, "checkpoint": first})
    vault = transact_vault(vault, {
        "kind": "put", "slot": "campaign", "expected_revision": 1,
        "expected_slot_digest": first["state_digest"], "checkpoint": second})
    return source, turns, first, second, vault


def _preview(played, target=1):
    return preview_recovery(
        played[4], target_revision=target, slot="campaign",
        expected_revision=played[4]["revision"])


def test_seek_rebuilds_every_revision_with_portable_exports(played):
    source, _, first, second, vault = played
    initial = seek_vault(vault, 0)
    assert initial == new_vault(source)
    assert read_slot(seek_vault(vault, 1), "campaign") == first
    assert read_slot(seek_vault(vault, 2), "campaign") == second
    for revision in range(3):
        historic = seek_vault(vault, revision)
        assert verify_vault(historic) == historic
        assert import_vault(export_vault(historic)) == historic


def test_paged_history_is_replay_derived_and_deterministic(played):
    vault = played[4]
    first = history_vault(vault, start=0, limit=1)
    second = history_vault(vault, start=first["next_revision"], limit=1)
    assert first["has_more"] and not second["has_more"]
    assert first["entries"][0]["before_slot_digest"] is None
    assert first["entries"][0]["after_slot_digest"] == played[2]["state_digest"]
    assert second["entries"][0]["before_slot_digest"] == played[2]["state_digest"]
    assert second["entries"][0]["after_slot_digest"] == played[3]["state_digest"]
    assert verify_history_vault(vault, first) == first
    assert verify_history_vault(vault, second) == second
    assert first == history_vault(json.loads(json.dumps(vault)), start=0, limit=1)


def test_history_diff_only_exposes_digests_and_turn_counts(played):
    _, _, first, second, vault = played
    diff = diff_vault(vault, 1, 2)
    assert len(diff["changes"]) == 1
    assert diff["changes"][0]["before_slot_digest"] == first["state_digest"]
    assert diff["changes"][0]["after_slot_digest"] == second["state_digest"]
    assert diff["changes"][0]["before_turns"] == 2
    assert diff["changes"][0]["after_turns"] == 3
    assert diff_vault(vault, 2, 2)["changes"] == []
    assert "checkpoint" not in json.dumps(diff)


def test_preview_is_not_a_mutation_and_apply_is_new_cas_event(played):
    _, _, first, _, vault = played
    original = copy.deepcopy(vault)
    preview = _preview(played)
    assert vault == original
    assert preview["parent_revision"] == 2
    assert preview["result_revision"] == 3
    assert preview["action"]["kind"] == "put"
    assert verify_recovery(vault, preview) == preview
    updated = apply_recovery(vault, preview)
    assert vault == original
    assert updated["journal"][:2] == vault["journal"]
    assert updated["revision"] == 3
    assert read_slot(updated, "campaign") == first
    assert import_vault(export_vault(updated)) == updated


def test_recovered_checkpoint_can_replay_to_earned_campaign(played):
    source, turns, first, _, vault = played
    updated = apply_recovery(vault, _preview(played))
    recovered = read_slot(updated, "campaign")
    assert recovered == first
    assert resume_party(recovered, turns[2:]) == simulate_party(source, turns)
    assert import_party(export_party(recovered)) == recovered


def test_recovery_to_empty_revision_uses_delete_event(played):
    vault = played[4]
    preview = _preview(played, target=0)
    assert preview["action"]["kind"] == "delete"
    updated = apply_recovery(vault, preview)
    assert updated["slots"] == {}
    assert updated["revision"] == 3
    assert seek_vault(updated, 2) == vault
    assert diff_vault(updated, 2, 3)["changes"][0]["after_slot_digest"] is None


def test_deleted_slot_can_be_restored_without_minting_state(played):
    vault = played[4]
    delete = _preview(played, target=0)
    deleted = apply_recovery(vault, delete)
    restore = preview_recovery(
        deleted, target_revision=1, slot="campaign", expected_revision=3)
    restored = apply_recovery(deleted, restore)
    assert read_slot(restored, "campaign") == played[2]
    assert restored["journal"][:3] == deleted["journal"]
    assert verify_vault(restored) == restored


def test_recovery_rejects_stale_parent_even_if_report_checksum_is_rehashed(played):
    vault = played[4]
    report = _preview(played)
    changed = apply_recovery(vault, report)
    with pytest.raises(SceneTravelError, match="stale|altered"):
        apply_recovery(changed, report)
    forged = copy.deepcopy(report)
    forged["action"]["expected_revision"] = 0
    forged["checksum"] = dig({k: v for k, v in forged.items()
                               if k != "checksum"})
    with pytest.raises(SceneTravelError, match="altered"):
        verify_recovery(vault, forged)


def test_history_tampering_rejected_even_with_recomputed_checksum(played):
    vault = played[4]
    report = history_vault(vault)
    altered = copy.deepcopy(report)
    altered["entries"][0]["after_slot_digest"] = "0" * 64
    altered["checksum"] = dig({k: v for k, v in altered.items()
                                if k != "checksum"})
    with pytest.raises(SceneTravelError, match="altered"):
        verify_history_vault(vault, altered)


@pytest.mark.parametrize("bad", [-1, True, 3, 1.5, "1", None])
def test_invalid_revision_types_fail_closed(played, bad):
    vault = played[4]
    with pytest.raises(SceneTravelError):
        seek_vault(vault, bad)
    with pytest.raises(SceneTravelError):
        preview_recovery(vault, target_revision=bad, slot="campaign",
                         expected_revision=2)


@pytest.mark.parametrize("bad", [0, 1, -1, True, "2"])
def test_invalid_expected_revision_or_stale_lease_fails_closed(played, bad):
    vault = played[4]
    with pytest.raises(SceneTravelError):
        preview_recovery(vault, target_revision=1, slot="campaign",
                         expected_revision=bad)


@pytest.mark.parametrize("bad", [0, -1, True, 17, 1.5])
def test_invalid_history_page_budget_fails_closed(played, bad):
    with pytest.raises(SceneTravelError):
        history_vault(played[4], limit=bad)


def test_noop_and_nonexistent_slot_recovery_fail_closed(played):
    vault = played[4]
    with pytest.raises(SceneTravelError, match="would not change"):
        _preview(played, target=2)
    with pytest.raises(SceneTravelError, match="would not change"):
        preview_recovery(vault, target_revision=0, slot="missing",
                         expected_revision=2)
    with pytest.raises(SceneTravelError):
        preview_recovery(vault, target_revision=1, slot="x" * 41,
                         expected_revision=2)


def test_corrupt_checkpoint_and_source_lineage_rejected(played):
    vault = copy.deepcopy(played[4])
    vault["slots"]["campaign"]["state"]["market"]["state"]["credits"] += 900
    with pytest.raises(SceneTravelError):
        history_vault(vault)
    with pytest.raises(SceneTravelError):
        preview_recovery(vault, target_revision=1, slot="campaign",
                         expected_revision=2)


def test_end_to_end_play_recover_restart_export_acceptance():
    receipt = accept_recovery()
    assert receipt["phase"] == "won"
    assert receipt["revision"] == 3
    assert receipt["checksum"] == dig({k: v for k, v in receipt.items()
                                       if k != "checksum"})


def test_cli_dispatch_and_fail_closed_error_channel(capsys, played):
    from skeleton.__main__ import main
    assert main(["scene-market-party-vault-history", "accept"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["phase"] == "won"
    vault_json = json.dumps(played[4])
    assert cli(["history", "--vault-json", vault_json, "--limit", "1"]) == 0
    page = json.loads(capsys.readouterr().out)
    assert page["next_revision"] == 1
    assert cli(["preview", "--vault-json", vault_json, "--target-revision", "1",
                "--slot", "campaign", "--expected-revision", "2"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert cli(["apply", "--vault-json", vault_json,
                "--report-json", json.dumps(report)]) == 0
    updated = json.loads(capsys.readouterr().out)
    assert updated["revision"] == 3
    assert cli(["seek", "--vault-json", "{}", "--revision", "0"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
