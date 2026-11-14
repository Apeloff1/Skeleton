"""Source-bound combat supply timeline acceptance and hostile input tests."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.combat_campaign_supply import (
    finish_supply, new_supply, original_supply, verify_supply,
)
from skeleton.game.gameplay.combat_campaign_supply_timeline import (
    checkpoint_supply, cli, compare_supply, fork_supply, import_timeline,
    package_timeline, timeline_supply, verify_fork, verify_timeline,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _saved():
    return finish_supply(original_supply())


def test_earned_economy_replays_to_same_final_state():
    saved = _saved()
    timeline = timeline_supply(saved)
    assert timeline["phase"] == "won"
    assert timeline["total_earned"] - timeline["total_spent"] == timeline["balance"]
    assert timeline["balance"] == saved["state"]["currency"]
    assert timeline["steps"][-1]["after"] == saved["state_digest"]
    assert len(timeline["steps"]) == len(saved["state"]["journal"])
    assert verify_timeline(json.loads(json.dumps(timeline)), session=saved) == timeline


@pytest.mark.parametrize("index", [0, 1, 2])
def test_checkpoint_replay(index):
    saved = _saved()
    restored = checkpoint_supply(saved, index)
    assert restored["state"]["journal"] == saved["state"]["journal"][:index]
    assert verify_supply(json.loads(json.dumps(restored))) == restored


def test_fork_spends_earned_currency_and_keeps_original_immutable():
    origin = _saved()
    copy_of_origin = copy.deepcopy(origin)
    record = fork_supply(origin, 1, [
        {"kind": "buy", "item": "medkit"},
        {"kind": "use", "item": "medkit"},
        {"kind": "fight"},
    ])
    assert origin == copy_of_origin
    assert record["branch"]["state"]["phase"] == "won"
    assert verify_fork(json.loads(json.dumps(record))) == record
    comparison = compare_supply(origin, record["branch"])
    assert comparison["common_commands"] == 1
    assert comparison["same_state"] is False
    assert comparison["right"]["phase"] == "won"


def test_portable_package_round_trip():
    saved = _saved()
    package = package_timeline(saved)
    assert import_timeline(json.loads(json.dumps(package))) == saved
    assert package["timeline"] == timeline_supply(saved)


@pytest.mark.parametrize("field", ["receipt", "state_digest", "source_digest"])
def test_tampered_package_fails_closed(field):
    package = package_timeline(_saved())
    package[field] = "0" * 64
    with pytest.raises(CombatSessionError):
        import_timeline(package)


@pytest.mark.parametrize("mutation", [
    lambda x: x["branch"]["state"].update(currency=99999),
    lambda x: x.update(receipt="0" * 64),
    lambda x: x["suffix"][0].update(item="ward"),
    lambda x: x["origin"]["state"]["inventory"].update(medkit=9),
    lambda x: x.update(checkpoint_index=0),
])
def test_forged_fork_is_rejected(mutation):
    record = fork_supply(_saved(), 1, [{"kind": "buy", "item": "medkit"}])
    mutation(record)
    with pytest.raises(CombatSessionError):
        verify_fork(record)


def test_timeline_tamper_rejected():
    saved = _saved()
    report = timeline_supply(saved)
    report["steps"][0]["earned"] = 99999
    with pytest.raises(CombatSessionError):
        verify_timeline(report, session=saved)


def test_reject_bad_index_and_oversize_or_unearned_suffix():
    saved = _saved()
    for index in (-1, 3, True, 1.5, "1"):
        with pytest.raises(CombatSessionError):
            checkpoint_supply(saved, index)
    with pytest.raises(CombatSessionError):
        fork_supply(saved, 0, [{"kind": "fight"}] * 41)
    with pytest.raises(CombatSessionError):
        fork_supply(saved, 0, [{"kind": "buy", "item": "ward"}])
    with pytest.raises(CombatSessionError):
        fork_supply(saved, 2, [{"kind": "fight"}])


def test_cross_source_comparison_fails_closed():
    changed = original_supply()
    changed["prices"]["ward"] += 1
    with pytest.raises(CombatSessionError, match="different authored sources"):
        compare_supply(_saved(), finish_supply(changed))


def test_main_cli_dispatch_portable_and_error(capsys):
    from skeleton.__main__ import main
    assert main(["combat-supply-timeline", "demo"]) == 0
    assert json.loads(capsys.readouterr().out)["phase"] == "won"
    saved = _saved()
    assert cli(["checkpoint", "--session-json", json.dumps(saved),
                "--index", "1"]) == 0
    checkpoint = json.loads(capsys.readouterr().out)
    assert checkpoint["state"]["journal"] == [{"kind": "fight"}]
    assert cli(["package", "--session-json", json.dumps(saved)]) == 0
    package = json.loads(capsys.readouterr().out)
    assert cli(["import", "--package-json", json.dumps(package)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert cli(["timeline", "--session-json", "{bad"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_empty_save_has_no_unearned_rewards():
    fresh = new_supply(original_supply())
    assert timeline_supply(fresh)["balance"] == 0
    assert checkpoint_supply(fresh, 0) == fresh
    with pytest.raises(CombatSessionError):
        fork_supply(fresh, 0, [{"kind": "buy", "item": "medkit"}])
