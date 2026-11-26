"""Replay journal append, CAS, fork, import, export and tamper regression."""
from copy import deepcopy
from pathlib import Path
import pytest
from skeleton.game.gameplay.ridge_rescue.schema import parse_world
from skeleton.game.gameplay.ridge_rescue.journal import (
    open_journal, append_journal, verify_journal, fork_journal, export_journal, import_run, JournalError
)
from skeleton.game.gameplay.ridge_rescue.custody import verify_run, digest

WORLD = parse_world((Path(__file__).resolve().parents[1] / "game/gameplay/ridge_rescue/cinder_ridge_acceptance.json").read_bytes())

def test_journal_roundtrip_and_portable_run():
    first = open_journal(WORLD)
    second = append_journal(first, {"verb": "rescue", "target": "tavi"}, expected_head=first["head"])
    assert first["state"]["turn"] == 0
    assert second["state"]["turn"] == 1
    assert verify_journal(second)["head"] == second["head"]
    bundle = export_journal(second)
    assert verify_run(bundle)["state"] == second["state"]
    restored = import_run(bundle)
    assert restored == second

def test_stale_revision_fails_without_modifying_original():
    first = open_journal(WORLD)
    old = deepcopy(first)
    with pytest.raises(JournalError, match="stale"):
        append_journal(first, {"verb": "rest"}, expected_head="0" * 64)
    assert first == old

def test_fork_from_historical_head_replays_exact_prefix():
    first = open_journal(WORLD)
    second = append_journal(first, {"verb": "rescue", "target": "tavi"}, expected_head=first["head"])
    third = append_journal(second, {"verb": "gather", "target": "kindling"}, expected_head=second["head"])
    fork = fork_journal(third, expected_head=third["head"], sequence=1)
    assert fork == second
    diverged = append_journal(fork, {"verb": "rest"}, expected_head=fork["head"])
    assert diverged["head"] != third["head"]
    assert verify_journal(diverged)["state"]["turn"] == 2

def test_rehashed_state_and_entry_tampering_rejected():
    first = open_journal(WORLD)
    second = append_journal(first, {"verb": "rest"}, expected_head=first["head"])
    forged = deepcopy(second)
    forged["state"]["status"] = "won:protect"
    with pytest.raises(JournalError):
        verify_journal(forged)
    forged = deepcopy(second)
    forged["entries"][0]["action"] = {"verb": "move", "direction": "west"}
    forged["entries"][0]["sha256"] = digest({"schema": "ridge.rescue.entry.v1", "previous": first["head"], "sequence": 1, "action": forged["entries"][0]["action"]})
    forged["head"] = forged["entries"][0]["sha256"]
    with pytest.raises(JournalError):
        verify_journal(forged)

def test_invalid_fork_and_oversize_rejected():
    first = open_journal(WORLD)
    with pytest.raises(JournalError):
        fork_journal(first, expected_head=first["head"], sequence=1)
    with pytest.raises(JournalError):
        verify_journal(b"z" * 256001)
