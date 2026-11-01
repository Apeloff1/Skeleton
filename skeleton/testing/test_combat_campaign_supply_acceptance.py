"""Acceptance must exercise source editing, gameplay, saves, replay and export."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.combat_campaign_supply_acceptance import (
    accept_original_supply, verify_supply_acceptance,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_full_playable_vertical_and_replay_proof():
    result = accept_original_supply()
    assert result["phase"] == "won"
    assert result["battles"] == 2
    assert result["source_unchanged"] is True
    assert result["hp"] > 0
    assert [c["kind"] for c in result["commands"]] == [
        "fight", "buy", "use", "fight",
    ]
    assert result["commands"][1]["item"] == "medkit"
    assert verify_supply_acceptance(json.loads(json.dumps(result))) == result


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(hp=999),
    lambda r: r.update(source_unchanged=False),
    lambda r: r["commands"][1].update(item="ward"),
    lambda r: r.update(portable_digest="0" * 64),
    lambda r: r.update(phase="lost"),
])
def test_forged_rehashed_acceptance_is_not_trusted(mutate):
    forged = copy.deepcopy(accept_original_supply())
    mutate(forged)
    forged["receipt"] = dig({k: v for k, v in forged.items() if k != "receipt"})
    with pytest.raises(CombatSessionError):
        verify_supply_acceptance(forged)


def test_cli_demo_verify_and_duplicate_json_rejected(capsys):
    assert main(["combat-supply-accept", "demo"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["phase"] == "won"
    assert main(["combat-supply-accept", "verify", "--receipt-json",
                 json.dumps(receipt)]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    assert main(["combat-supply-accept", "verify", "--receipt-json",
                 '{"x":1,"x":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
