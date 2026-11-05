"""Playable expedition checkpoint custody and divergent replay acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.arena_bundle import import_bundle
from skeleton.game.gameplay.arena_checkpoint_timeline import (
    checkpoint_at, cli, fork_expedition, original_fork,
    timeline_expedition, verify_fork,
)
from skeleton.game.gameplay.arena_expedition import (
    original_expedition, simulate_expedition,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError

ACTIONS = [
    {"kind": "fight"},
    {"kind": "buy", "item_id": "tide_tonic"},
    {"kind": "use", "item_id": "tide_tonic"},
    {"kind": "fight"},
]


def played():
    return simulate_expedition(original_expedition(), ACTIONS)


def test_timeline_replays_all_historical_saves_and_economy():
    saved = played()
    report = timeline_expedition(saved)
    assert report["count"] == len(ACTIONS) + 1
    assert report["final_state_digest"] == saved["state_digest"]
    assert [p["tick"] for p in report["checkpoints"]] == list(range(5))
    assert report["checkpoints"][0]["currency"] == 0
    assert report["checkpoints"][-1]["phase"] == "won"
    assert timeline_expedition(json.loads(json.dumps(saved))) == report


def test_all_checkpoints_export_and_restore_exact_history():
    saved = played()
    for tick in range(len(ACTIONS) + 1):
        checkpoint = import_bundle(checkpoint_at(saved, tick))
        assert checkpoint["state"]["tick"] == tick
        assert checkpoint["source_digest"] == saved["source_digest"]
        assert len(checkpoint["journal"]) == tick


def test_fork_is_replayable_and_comparable():
    record = original_fork()
    final = verify_fork(json.loads(json.dumps(record)))
    assert final["state"]["phase"] == "won"
    assert record["comparison"]["same_state"] is True
    assert record["checkpoint_tick"] == 1
    assert record["fork_state_digest"] == final["state_digest"]


def test_alternate_branch_has_distinct_earned_state():
    saved = played()
    record = fork_expedition(saved, 1, [{"kind": "fight"}])
    final = verify_fork(record)
    assert record["comparison"]["same_state"] is False
    assert final["state"]["tick"] == 2
    assert final["source_digest"] == saved["source_digest"]


@pytest.mark.parametrize("field,value", [
    ("checksum", "0" * 64),
    ("fork_state_digest", "0" * 64),
    ("fork_economy_checksum", "0" * 64),
    ("checkpoint_tick", 0),
    ("comparison", {}),
    ("result_bundle", {}),
])
def test_tampered_fork_is_rejected(field, value):
    record = original_fork()
    forged = copy.deepcopy(record)
    forged[field] = value
    with pytest.raises(CombatSessionError):
        verify_fork(forged)


def test_recomputed_checksum_cannot_forge_rewards():
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig
    record = original_fork()
    record["result_bundle"]["session"]["state"]["currency"] = 99999
    record["checksum"] = dig({k: v for k, v in record.items() if k != "checksum"})
    with pytest.raises(CombatSessionError):
        verify_fork(record)


@pytest.mark.parametrize("tick", [-1, True, 5, 999])
def test_invalid_checkpoint_index_is_rejected(tick):
    with pytest.raises(CombatSessionError, match="tick"):
        checkpoint_at(played(), tick)


def test_invalid_action_does_not_mutate_source_checkpoint():
    original = played()
    before = copy.deepcopy(original)
    with pytest.raises(CombatSessionError):
        fork_expedition(original, 1, [{"kind": "buy", "item_id": "missing"}])
    assert original == before


def test_installed_cli_and_fork_verification(capsys):
    from skeleton.__main__ import main
    assert main(["combat-checkpoints", "demo"]) == 0
    record = json.loads(capsys.readouterr().out)
    assert cli(["verify-fork", "--record-json", json.dumps(record)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True

def test_verify_cli_rejects_duplicate_and_nonfinite_json(capsys):
    assert cli(["verify-fork", "--record-json", '{"x":1,"x":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
    assert cli(["verify-fork", "--record-json", '{"x":NaN}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
