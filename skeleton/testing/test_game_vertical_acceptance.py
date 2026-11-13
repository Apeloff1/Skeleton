"""Acceptance tests spanning authored source, real play, replay and export."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.game_vertical_acceptance import (
    accept_vertical, cli, demo_acceptance, export_acceptance,
    import_acceptance, verify_acceptance,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError
from skeleton.game.gameplay.arena_forge_run import original_forge
from skeleton.game.gameplay.quest_chapter_campaign import (
    original_campaign, demo_campaign_actions,
)


@pytest.mark.parametrize("kind", ["forge", "quest"])
def test_real_playable_victory_is_replay_verified_and_portable(kind):
    report = demo_acceptance(kind)
    assert report["phase"] == "won"
    assert report["kind"] == kind
    assert verify_acceptance(json.loads(json.dumps(report))) == report
    assert import_acceptance(json.loads(json.dumps(export_acceptance(report)))) == report
    if kind == "quest":
        assert report["portable_bundle"]["state_digest"] == report["state_digest"]


@pytest.mark.parametrize("kind", ["forge", "quest"])
def test_checkpoint_boundary_does_not_change_earned_outcome(kind):
    report = demo_acceptance(kind)
    source, actions = report["source"], report["actions"]
    initial = accept_vertical(kind, source, actions, checkpoint_at=0)
    assert initial["state_digest"] == report["state_digest"]
    final = accept_vertical(kind, source, actions, checkpoint_at=len(actions))
    assert final["state_digest"] == report["state_digest"]


def test_quest_source_must_be_authored_and_played():
    report = demo_acceptance("quest")
    source = original_campaign()
    source["campaign_id"] = "different_campaign"
    other = accept_vertical("quest", source, demo_campaign_actions())
    assert other["source_digest"] != report["source_digest"]
    with pytest.raises(CombatSessionError):
        verify_acceptance({**report, "source": other["source"]})


def test_unearned_forge_victory_is_rejected():
    with pytest.raises(CombatSessionError, match="victory"):
        accept_vertical("forge", original_forge(), [])


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(receipt="0" * 64),
    lambda x: x.update(phase="won", state_digest="0" * 64),
    lambda x: x["portable_bundle"].update(checksum="0" * 64),
    lambda x: x.update(checkpoint_digest="0" * 64),
    lambda x: x.update(checkpoint_at=True),
    lambda x: x.update(fake_release_certificate=True),
    lambda x: x["actions"].append({"kind": "grant", "currency": 10000}),
])
def test_tampering_cannot_create_acceptance(mutation):
    forged = copy.deepcopy(demo_acceptance("quest"))
    mutation(forged)
    with pytest.raises(CombatSessionError):
        verify_acceptance(forged)


def test_portable_acceptance_bundle_rejects_nested_tampering():
    bundle = export_acceptance(demo_acceptance("forge"))
    forged = copy.deepcopy(bundle)
    forged["acceptance"]["save_digest"] = "0" * 64
    with pytest.raises(CombatSessionError):
        import_acceptance(forged)
    forged = copy.deepcopy(bundle)
    forged["checksum"] = "0" * 64
    with pytest.raises(CombatSessionError, match="checksum"):
        import_acceptance(forged)


@pytest.mark.parametrize("checkpoint", [-1, True, 1000])
def test_invalid_checkpoint_fails_closed(checkpoint):
    with pytest.raises(CombatSessionError, match="checkpoint"):
        accept_vertical("forge", original_forge(), [], checkpoint_at=checkpoint)


def test_invalid_engine_and_action_count_are_rejected():
    with pytest.raises(CombatSessionError, match="kind"):
        accept_vertical("external", {}, [])
    with pytest.raises(CombatSessionError, match="action budget"):
        accept_vertical("forge", original_forge(), [{}] * 97)


def test_installed_cli_demo_verify_export_import_and_errors(capsys):
    from skeleton.__main__ import main
    assert main(["game-vertical-accept", "demo", "--kind", "forge"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["phase"] == "won"
    assert cli(["verify", "--acceptance-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert cli(["export", "--acceptance-json", json.dumps(report)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert cli(["run", "--kind", "forge", "--source-json",
                json.dumps(original_forge()), "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
    assert cli(["verify", "--acceptance-json", '{"a":1,"a":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
