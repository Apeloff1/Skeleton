"""Beacon CAS journal: real play, bounded append, ancestry, forks and replay."""
from __future__ import annotations

from copy import deepcopy
import subprocess

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, canonical, decode, digest
from skeleton.game.gameplay.harbor_crafting_beacon_journal import (
    create_beacon_journal, append_beacon_journal, verify_beacon_journal,
    beacon_journal_at, fork_beacon_journal,
)
from skeleton.game.gameplay.harbor_crafting_beacons import (
    build_beacon_rescue, verify_beacon_rescue,
)
from skeleton.testing.test_harbor_crafting_beacons import (
    CLI, source_board, winning_actions,
)


def test_checkpoint_append_replay_historical_restore_and_terminal():
    source, board = source_board()
    actions = winning_actions()
    initial = create_beacon_journal(source, board)
    first = append_beacon_journal(initial, actions[:12], expected_tip=initial["tip"])
    final = append_beacon_journal(first, actions[12:], expected_tip=first["tip"])
    assert verify_beacon_journal(final)["rescued"]
    assert verify_beacon_journal(final)["checkpoints"] == 2
    assert beacon_journal_at(final, 0) == build_beacon_rescue(source, board, [])
    assert beacon_journal_at(final, 1) == build_beacon_rescue(source, board, actions[:12])
    restored = beacon_journal_at(final, 2)
    assert restored == build_beacon_rescue(source, board, actions, require_rescue=True)
    assert verify_beacon_rescue(decode(canonical(restored)), require_rescue=True)["rescued"]
    with pytest.raises(HarborError, match="terminal"):
        append_beacon_journal(final, [{"op": "wait"}], expected_tip=final["tip"])
    with pytest.raises(HarborError, match="stale"):
        append_beacon_journal(first, actions[12:], expected_tip="0" * 64)


def test_fork_is_independent_and_ancestry_tampering_fails_closed():
    source, board = source_board()
    actions = winning_actions()
    initial = create_beacon_journal(source, board)
    first = append_beacon_journal(initial, actions[:12], expected_tip=initial["tip"])
    full = append_beacon_journal(first, actions[12:], expected_tip=first["tip"])
    fork = fork_beacon_journal(full, 1)
    assert fork == first
    alternative = append_beacon_journal(fork, [{"op": "wait"}], expected_tip=fork["tip"])
    assert verify_beacon_journal(alternative)["actions"] == 13
    assert verify_beacon_journal(full)["rescued"]
    for field, value in (("previous", "0" * 64), ("report_digest", "0" * 64)):
        forged = deepcopy(full)
        forged["checkpoints"][1][field] = value
        forged["checkpoints"][1]["entry_digest"] = digest({
            key: item for key, item in forged["checkpoints"][1].items()
            if key != "entry_digest"
        })
        forged["tip"] = forged["checkpoints"][1]["entry_digest"]
        forged["journal_digest"] = digest({
            key: item for key, item in forged.items() if key != "journal_digest"
        })
        with pytest.raises(HarborError):
            verify_beacon_journal(forged)
    with pytest.raises(HarborError):
        beacon_journal_at(full, True)
    with pytest.raises(HarborError):
        fork_beacon_journal(full, 3)


def test_journal_cli_init_append_verify_and_historical_export(tmp_path):
    source, board = source_board()
    world_path = tmp_path / "source.json"
    board_path = tmp_path / "board.json"
    world_path.write_bytes(canonical(source))
    board_path.write_bytes(canonical(board))

    def write(name, value):
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical(value))
        return str(path)

    def call(*args):
        run = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert run.returncode == 0, run.stderr.decode()
        return decode(run.stdout)

    initial = call("journal-init", "--source", str(world_path), "--board", str(board_path))
    first = call(
        "journal-append", "--journal", write("initial", initial),
        "--actions", write("first-actions", winning_actions()[:12]),
        "--expected-digest", initial["tip"],
    )
    final = call(
        "journal-append", "--journal", write("first", first),
        "--actions", write("last-actions", winning_actions()[12:]),
        "--expected-digest", first["tip"],
    )
    journal_path = write("final", final)
    assert call("journal-verify", "--journal", journal_path)["rescued"]
    restored = call("journal-at", "--journal", journal_path, "--index", "2")
    assert verify_beacon_rescue(restored, require_rescue=True)["rescued"]
    fork = call("journal-fork", "--journal", journal_path, "--index", "1")
    assert fork == first
    bad = subprocess.run(
        CLI + ["journal-at", "--journal", journal_path, "--index", "999"],
        capture_output=True, check=False,
    )
    assert bad.returncode == 2
