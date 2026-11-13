"""Combat campaign branching: real actions, provenance, choices and export."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.combat_campaign import original_campaign
from skeleton.game.gameplay.combat_campaign_branches import (
    MAX_CANDIDATES, accept_branches, choose_branch, cli, demo_branches,
    evaluate_branches, export_branches, import_branches, normalize_branches,
    verify_branches,
)
from skeleton.game.gameplay.combat_campaign_player import (
    demo_player_campaign, new_player_campaign, verify_player_campaign,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_original_branch_replays_earned_victory_and_portable_choice():
    report = demo_branches()
    assert verify_branches(json.loads(json.dumps(report))) == report
    assert report["heuristic_candidate"] == "finish_patrol"
    assert [item["status"] for item in report["outcomes"]] == [
        "accepted", "accepted",
    ]
    selected = choose_branch(report, "finish_patrol")
    assert selected == demo_player_campaign()
    assert selected["state"]["phase"] == "won"
    assert selected["state"]["currency"] == 30
    assert verify_player_campaign(selected) == selected
    assert import_branches(export_branches(report)) == report


def test_preview_is_transactional_and_guard_is_not_a_fake_victory():
    report = demo_branches()
    checkpoint = copy.deepcopy(report["checkpoint"])
    guarded = choose_branch(report, "guard_then_reconsider")
    assert guarded["state"]["player_turns"] == checkpoint["state"]["player_turns"] + 1
    assert guarded["state"]["currency"] == checkpoint["state"]["currency"]
    assert guarded["state"]["phase"] == "active"
    assert report["checkpoint"] == checkpoint
    assert verify_player_campaign(checkpoint) == checkpoint


def test_blocked_branch_cannot_be_selected_or_mint_rewards():
    source = original_campaign()
    checkpoint = new_player_campaign(source)
    before = copy.deepcopy(checkpoint)
    report = evaluate_branches(checkpoint, [
        {"candidate_id": "wrong_actor", "actions": [
            {"kind": "attack", "actor_id": "warden", "target_id": "scout"},
        ]},
    ])
    assert report["heuristic_candidate"] is None
    assert report["outcomes"][0]["status"] == "blocked"
    assert report["outcomes"][0]["blocked_step"] == 0
    assert report["outcomes"][0]["state_digest"] is None
    assert checkpoint == before
    with pytest.raises(CombatSessionError, match="blocked"):
        choose_branch(report, "wrong_actor")


@pytest.mark.parametrize("mutate", [
    lambda r: r["checkpoint"]["state"].update(currency=900),
    lambda r: r["checkpoint"].update(state_digest="0" * 64),
    lambda r: r["outcomes"][0].update(currency=900),
    lambda r: r["outcomes"][0].update(status="blocked"),
    lambda r: r.update(heuristic_candidate="guard_then_reconsider"),
    lambda r: r.update(source_digest="0" * 64),
    lambda r: r.update(qualification="release_qualified"),
    lambda r: r["candidates"][0].update(candidate_id="forged"),
])
def test_recomputed_checksum_never_authenticates_forged_replay(mutate):
    report = copy.deepcopy(demo_branches())
    mutate(report)
    report["checksum"] = dig({k: v for k, v in report.items()
                              if k != "checksum"})
    with pytest.raises(CombatSessionError):
        verify_branches(report)


@pytest.mark.parametrize("candidates", [
    [],
    [{"candidate_id": "x", "actions": []}],
    [{"candidate_id": "x", "actions": [True]}],
    [{"candidate_id": "x", "actions": [{"kind": "teleport"}]}],
    [{"candidate_id": "x", "actions": [{"kind": "guard", "actor_id": "scout", "x": 1}]}],
    [{"candidate_id": "same", "actions": [{"kind": "guard", "actor_id": "scout"}]}] * 2,
    [{"candidate_id": "x", "actions": [{"kind": "guard", "actor_id": "scout"}]}]
    * (MAX_CANDIDATES + 1),
])
def test_invalid_plans_are_rejected_before_preview(candidates):
    with pytest.raises(CombatSessionError):
        normalize_branches(candidates)


def test_portable_bundle_rejects_source_swap_even_with_new_checksum():
    report = demo_branches()
    bundle = export_branches(report)
    forged = copy.deepcopy(bundle)
    forged["source_digest"] = "0" * 64
    forged["checksum"] = dig({k: v for k, v in forged.items()
                              if k != "checksum"})
    with pytest.raises(CombatSessionError):
        import_branches(forged)


def test_acceptance_is_real_played_campaign_not_release_claim():
    receipt = accept_branches()
    assert receipt["phase"] == "won"
    assert receipt["earned_currency"] == 30
    assert receipt["candidate_count"] == 2
    assert receipt["qualification"] == "offline_source_to_playable_replay_export_only"
    assert receipt["checksum"] == dig({k: v for k, v in receipt.items()
                                      if k != "checksum"})


def test_installed_cli_branch_evaluate_choose_export_import(capsys):
    from skeleton.__main__ import main
    assert main(["combat-campaign-player", "branch-demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert cli(["verify", "--report-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert main(["combat-campaign-player", "branch-choose",
                 "--report-json", json.dumps(report),
                 "--candidate-id", "finish_patrol"]) == 0
    selected = json.loads(capsys.readouterr().out)
    assert selected["state"]["currency"] == 30
    assert main(["combat-campaign-player", "branch-export",
                 "--report-json", json.dumps(report)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert main(["combat-campaign-player", "branch-import",
                 "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert main(["combat-campaign-player", "branch-accept"]) == 0
    assert json.loads(capsys.readouterr().out)["phase"] == "won"
    assert main(["combat-campaign-player", "branch-choose",
                 "--report-json", json.dumps(report),
                 "--candidate-id", "missing"]) == 2
    assert "error" in capsys.readouterr().err


def test_cli_duplicate_keys_fail_closed(capsys):
    assert cli(["verify", "--report-json", '{"x":1,"x":2}']) == 2
    assert "error" in capsys.readouterr().err
