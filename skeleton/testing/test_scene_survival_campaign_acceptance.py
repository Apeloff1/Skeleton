"""End-to-end source→runtime→checkpoint→export campaign acceptance."""
import copy
import json

import pytest

from skeleton.game.gameplay.scene_survival_campaign import (
    original_campaign,
)
from skeleton.game.gameplay.scene_survival_campaign_acceptance import (
    accept_campaign, cli, export_acceptance,
    import_acceptance, verify_acceptance,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_campaign_acceptance_at_every_checkpoint_boundary():
    source, actions = original_campaign()
    for checkpoint_at in (0, 1, len(actions) // 2, len(actions)):
        accepted = accept_campaign(
            source, actions, checkpoint_at=checkpoint_at)
        assert accepted["phase"] == "won"
        assert accepted["score"] == 30
        assert len(accepted["completed"]) == 2
        assert accepted["checkpoint_at"] == checkpoint_at
        assert verify_acceptance(accepted) == accepted
        assert import_acceptance(export_acceptance(accepted)) == accepted


def test_unfinished_campaign_does_not_receive_victory_receipt():
    source, actions = original_campaign()
    with pytest.raises(SceneTravelError, match="earned victory"):
        accept_campaign(source, actions[:2])
    with pytest.raises(SceneTravelError):
        accept_campaign(source, actions, checkpoint_at=-1)
    with pytest.raises(SceneTravelError):
        accept_campaign(source, actions, checkpoint_at=True)


def test_tampered_score_rewards_checkpoint_and_actions_rejected():
    source, actions = original_campaign()
    accepted = accept_campaign(source, actions)
    for field, value in (
        ("score", 1000),
        ("completed", []),
        ("checkpoint_digest", "0" * 64),
        ("save_digest", "0" * 64),
        ("state_digest", "0" * 64),
        ("receipt", "0" * 64),
    ):
        forged = copy.deepcopy(accepted)
        forged[field] = value
        with pytest.raises(SceneTravelError):
            verify_acceptance(forged)
    forged = copy.deepcopy(accepted)
    forged["actions"][0] = {"kind": "rest"}
    with pytest.raises(SceneTravelError):
        verify_acceptance(forged)
    forged = copy.deepcopy(export_acceptance(accepted))
    forged["acceptance"]["score"] = 1000
    with pytest.raises(SceneTravelError):
        import_acceptance(forged)


def test_cli_demo_verify_export_import(capsys):
    assert cli(["demo"]) == 0
    accepted = json.loads(capsys.readouterr().out)
    assert accepted["phase"] == "won"
    assert cli(["verify", "--acceptance-json", json.dumps(accepted)]) == 0
    assert json.loads(capsys.readouterr().out) == accepted
    assert cli(["export", "--acceptance-json", json.dumps(accepted)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == accepted
