"""Replay-authoritative quest checkpoints: real crafting, NPC, combat and endings."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.expedition_quest import (
    _advance, demo_actions, export_quest, import_quest, new_quest,
    original_quest, simulate_quest,
)
from skeleton.game.gameplay.expedition_quest_checkpoints import (
    checkpoint_at, cli, compare_quest_paths, fork_quest, original_fork,
    timeline_quest, verify_fork,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


@pytest.fixture
def played():
    return simulate_quest(original_quest(), demo_actions())


def test_timeline_is_complete_and_source_bound(played):
    report = timeline_quest(played)
    assert report["count"] == len(demo_actions()) + 1
    assert report["checkpoints"][0]["tick"] == 0
    assert report["checkpoints"][-1]["ending"] == "beacon_lit"
    assert report["checkpoints"][-1]["earned_currency"] == 25
    assert report["final_state_digest"] == played["state_digest"]
    assert report == timeline_quest(json.loads(json.dumps(played)))


@pytest.mark.parametrize("tick", [0, 1, 3, 4, 6, 7, 10, 11])
def test_checkpoint_exact_replay_at_every_gameplay_boundary(played, tick):
    bundle = checkpoint_at(played, tick)
    restored = import_quest(json.loads(json.dumps(bundle)))
    expected = simulate_quest(original_quest(), demo_actions()[:tick])
    assert restored == expected
    assert export_quest(restored) == bundle
    assert restored["state"]["tick"] == tick


def test_original_fork_has_distinct_earned_ending_and_no_free_gift():
    record = original_fork()
    result = verify_fork(json.loads(json.dumps(record)))
    assert result["state"]["ending"] == "quiet_victory"
    assert result["state"]["choices"]["guide"] == "decline"
    assert "signal_beacon" not in result["state"]["items"]
    assert record["original"]["state"]["ending"] == "beacon_lit"
    assert record["comparison"]["choice_changes"] == [
        {"npc_id": "guide", "before": "aid", "after": "decline"}
    ]
    assert record["comparison"]["item_changes"]


def test_checkpoint_resume_and_replayed_fork_are_identical(played):
    actions = demo_actions()
    record = fork_quest(played, 6, actions[6:])
    assert verify_fork(record) == played
    assert record["comparison"]["item_changes"] == []
    assert record["comparison"]["currency_delta"] == 0
    assert record["checkpoint_bundle"] == checkpoint_at(played, 6)


@pytest.mark.parametrize("tick", [-1, 12, True, 1.0, "1", None])
def test_invalid_checkpoint_tick_rejected(played, tick):
    with pytest.raises(CombatSessionError):
        checkpoint_at(played, tick)


def test_reject_source_mismatch_and_invalid_actions(played):
    other = new_quest({**original_quest(), "quest_id": "different"})
    with pytest.raises(CombatSessionError, match="source mismatch"):
        compare_quest_paths(played, other)
    with pytest.raises(CombatSessionError):
        fork_quest(played, 0, [{"kind": "finish", "ending_id": "beacon_lit"}])
    with pytest.raises(CombatSessionError):
        fork_quest(played, 0, [{"kind": "wait"}] * 97)
    with pytest.raises(CombatSessionError):
        fork_quest(played, 11, [{"kind": "wait"}])


@pytest.mark.parametrize("tamper", [
    lambda x: x.update(checksum="0" * 64),
    lambda x: x.update(fork_state_digest="0" * 64),
    lambda x: x["comparison"].update(currency_delta=100000),
    lambda x: x["result_bundle"]["session"]["state"].update(items={"ore": 99}),
    lambda x: x["checkpoint_bundle"]["session"]["state"].update(location="camp"),
    lambda x: x["actions"][0].update(decision="aid"),
    lambda x: x["original"]["state"]["choices"].update(guide="decline"),
    lambda x: x.update(checkpoint_tick=1),
    lambda x: x.update(extra=True),
])
def test_fork_rejects_forged_gameplay_or_receipts(tamper):
    record = original_fork()
    altered = copy.deepcopy(record)
    tamper(altered)
    with pytest.raises(CombatSessionError):
        verify_fork(altered)


def test_bad_portable_save_never_becomes_checkpoint(played):
    bad = copy.deepcopy(played)
    bad["state"]["expedition"]["state"]["currency"] = 999999
    with pytest.raises(CombatSessionError):
        timeline_quest(bad)
    with pytest.raises(CombatSessionError):
        checkpoint_at(bad, 0)


def test_cli_and_canonical_main_dispatch(capsys, played):
    from skeleton.__main__ import main
    assert main(["quest-checkpoints", "demo"]) == 0
    record = json.loads(capsys.readouterr().out)
    assert verify_fork(record)["state"]["ending"] == "quiet_victory"
    assert cli(["verify-fork", "--record-json", json.dumps(record)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert cli(["timeline", "--session-json", json.dumps(played)]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 12
    assert cli(["checkpoint", "--session-json", json.dumps(played),
                "--tick", "4"]) == 0
    assert import_quest(json.loads(capsys.readouterr().out))["state"]["tick"] == 4
    assert cli(["fork", "--session-json", json.dumps(played), "--tick", "6",
                "--actions-json", json.dumps(demo_actions()[6:])]) == 0
    assert verify_fork(json.loads(capsys.readouterr().out)) == played
    assert cli(["compare", "--session-json", json.dumps(played),
                "--other-session-json", json.dumps(played)]) == 0
    assert json.loads(capsys.readouterr().out)["item_changes"] == []
    assert cli(["timeline", "--session-json", json.dumps(played),
                "--source-digest", "0" * 64]) == 2
    assert "mismatch" in capsys.readouterr().err
    # Both pre-command and subcommand positions retain the same fail-closed pin.
    assert cli(["--source-digest", "0" * 64, "timeline",
                "--session-json", json.dumps(played)]) == 2
    assert "mismatch" in capsys.readouterr().err
    assert cli(["timeline", "--session-json", json.dumps(played),
                "--source-digest", played["source_digest"]]) == 0
    assert json.loads(capsys.readouterr().out)["source_digest"] == played["source_digest"]


def test_oversized_and_invalid_json_fail_closed(played):
    with pytest.raises(CombatSessionError, match="size budget"):
        from skeleton.game.gameplay.expedition_quest_checkpoints import _bounded
        _bounded({"huge": "x" * (8 * 1024 * 1024)})
    assert cli(["verify-fork", "--record-json", '{"a":1,"a":2}']) == 2
    assert cli(["fork", "--session-json", json.dumps(played), "--tick", "0",
                "--actions-json", '{"kind":"wait"}']) == 2
