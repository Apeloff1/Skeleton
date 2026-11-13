"""Source-fenced market commission editing and exact receipt replay."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market_contract import (
    normalize_contract_source, original_contract, simulate_contract,
)
from skeleton.game.gameplay.scene_market_contract_author import (
    cli, edit_contract, verify_contract_edit,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_author_changes_campaign_without_changing_canonical_market():
    source, actions = original_contract()
    canonical = normalize_contract_source(source)
    receipt = edit_contract(source, [{
        "kind": "set_reward_score", "contract_id": "sanctuary_commission",
        "value": 40,
    }], dig(canonical))
    assert verify_contract_edit(json.loads(json.dumps(receipt))) == receipt
    assert receipt["before"]["market_source"] == receipt["after"]["market_source"]
    assert simulate_contract(receipt["after"], actions)["state"]["score"] == 40
    assert simulate_contract(source, actions)["state"]["score"] == 25


def test_author_rejects_stale_lease_and_nonexistent_contract():
    source, _ = original_contract()
    with pytest.raises(SceneTravelError, match="changed since read"):
        edit_contract(source, [{"kind": "set_reward_score",
                               "contract_id": "sanctuary_commission",
                               "value": 40}], "0" * 64)
    with pytest.raises(SceneTravelError, match="unknown"):
        edit_contract(source, [{"kind": "set_deadline",
                               "contract_id": "unknown", "value": 10}],
                      dig(normalize_contract_source(source)))


@pytest.mark.parametrize("value", [True, 0, -1, 1001, "5"])
def test_author_rejects_invalid_reward(value):
    source, _ = original_contract()
    with pytest.raises(SceneTravelError):
        edit_contract(source, [{"kind": "set_reward_score",
                               "contract_id": "sanctuary_commission",
                               "value": value}],
                      dig(normalize_contract_source(source)))


def test_author_noop_and_forged_receipts_fail():
    source, _ = original_contract()
    with pytest.raises(SceneTravelError, match="no changes"):
        edit_contract(source, [{"kind": "set_reward_score",
                               "contract_id": "sanctuary_commission",
                               "value": 25}], dig(normalize_contract_source(source)))
    receipt = edit_contract(source, [{"kind": "set_deadline",
                                     "contract_id": "sanctuary_commission",
                                     "value": 20}], dig(normalize_contract_source(source)))
    bad = copy.deepcopy(receipt)
    bad["after"]["contracts"][0]["deadline_tick"] = 19
    bad["checksum"] = dig({k: v for k, v in bad.items() if k != "checksum"})
    with pytest.raises(SceneTravelError, match="replay"):
        verify_contract_edit(bad)


def test_author_cli_demo_and_verify(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-contract-author", "demo"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert cli(["verify", "--receipt-json", json.dumps(receipt)]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
