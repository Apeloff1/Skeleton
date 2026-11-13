"""Combat contract acceptance crosses authored source, turns, rewards and export."""
import copy
import json

import pytest

from skeleton.game.gameplay.combat_contract import (
    original_contract,
)
from skeleton.game.gameplay.game_vertical_acceptance import (
    accept_vertical, demo_acceptance, export_acceptance,
    import_acceptance, verify_acceptance,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, original_demo,
)


def test_contract_acceptance_earns_only_verified_rewards():
    scenario, actions = original_demo()
    source = original_contract()
    assert source["scenario"] == scenario
    accepted = accept_vertical("combat_contract", source, actions)
    assert accepted["kind"] == "combat_contract"
    assert accepted["phase"] == "won"
    assert accepted["portable_bundle"]["session"]["state"]["credits"] == 14
    assert accepted["portable_bundle"]["session"]["state"]["inventory"] == {
        "bridge_pass": 1,
    }
    assert verify_acceptance(accepted) == accepted
    assert import_acceptance(export_acceptance(accepted)) == accepted


def test_contract_acceptance_resume_boundaries_and_demo():
    _, actions = original_demo()
    source = original_contract()
    for checkpoint_at in (0, 1, len(actions)):
        accepted = accept_vertical(
            "combat_contract", source, actions, checkpoint_at=checkpoint_at)
        assert accepted["checkpoint_at"] == checkpoint_at
        assert accepted["phase"] == "won"
        assert import_acceptance(export_acceptance(accepted)) == accepted
    assert demo_acceptance("combat_contract")["phase"] == "won"


def test_contract_acceptance_rejects_forged_rewards_and_actions():
    _, actions = original_demo()
    source = original_contract()
    accepted = accept_vertical("combat_contract", source, actions)
    forged = copy.deepcopy(accepted)
    forged["portable_bundle"]["session"]["state"]["credits"] = 99999
    with pytest.raises(CombatSessionError):
        verify_acceptance(forged)
    forged = copy.deepcopy(accepted)
    forged["actions"][0] = {"kind": "guard", "actor_id": "warden"}
    with pytest.raises(CombatSessionError):
        verify_acceptance(forged)
    forged = copy.deepcopy(export_acceptance(accepted))
    forged["acceptance"]["phase"] = "lost"
    with pytest.raises(CombatSessionError):
        import_acceptance(forged)


def test_contract_acceptance_cli_demo_and_portable(capsys):
    from skeleton.game.gameplay.game_vertical_acceptance import cli
    assert cli(["demo", "--kind", "combat_contract"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["phase"] == "won"
    assert cli(["verify", "--acceptance-json", json.dumps(result)]) == 0
    assert json.loads(capsys.readouterr().out) == result
    assert cli(["export", "--acceptance-json", json.dumps(result)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == result
