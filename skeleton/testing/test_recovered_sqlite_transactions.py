"""Transaction-failure and concurrent-connection regressions for the actual GF-B store."""
from __future__ import annotations

import json
import sqlite3

import pytest

from skeleton.kernel.checkpoint import CheckpointCorruptError, CheckpointSequenceError
from skeleton.kernel.game_save_plane import ReplayConflictError, ReplayJournal
from skeleton.persistence.game_save_sqlite import (
    SqliteCheckpointStore, SqliteReplayJournal, open_game_save_db,
)


@pytest.fixture
def pair(tmp_path):
    path = str(tmp_path / "saves.sqlite3")
    first, second = open_game_save_db(path), open_game_save_db(path)
    try:
        yield first, second
    finally:
        first.close()
        second.close()


def test_competing_checkpoint_writers_never_delete_newer_history(pair):
    a, b = (SqliteCheckpointStore(conn, retain=3) for conn in pair)
    a.save("game", 1, {"value": 1})
    b.save("game", 2, {"value": 2})
    a.save("game", 3, {"value": 3})
    assert [c.sequence for c in b.history("game")] == [1, 2, 3]
    with pytest.raises(CheckpointSequenceError):
        b.save("game", 2, {"value": 999})
    b.save("game", 4, {"value": 4})
    assert [c.sequence for c in a.history("game")] == [2, 3, 4]
    assert a.restore("game").state == {"value": 4}


def test_aborted_checkpoint_does_not_advance_sequence_or_evict_history(pair):
    first, second = pair
    a = SqliteCheckpointStore(first, retain=2)
    b = SqliteCheckpointStore(second, retain=2)
    a.save("game", 1, {"value": 1})
    a.save("game", 2, {"value": 2})
    first.execute("""
        CREATE TRIGGER reject_save BEFORE INSERT ON gf_save_checkpoints
        WHEN NEW.sequence=3 BEGIN SELECT RAISE(ABORT,'simulated disk rejection'); END
    """)
    with pytest.raises(sqlite3.IntegrityError):
        a.save("game", 3, {"value": 3})
    assert a.latest("game").sequence == 2
    assert [x.sequence for x in b.history("game")] == [1, 2]
    first.execute("DROP TRIGGER reject_save")
    a.save("game", 3, {"value": 3})
    assert [x.sequence for x in b.history("game")] == [2, 3]


def test_retention_delete_failure_rolls_back_insert_too(pair):
    first, second = pair
    a = SqliteCheckpointStore(first, retain=1)
    b = SqliteCheckpointStore(second, retain=1)
    a.save("game", 1, {"v": 1})
    first.execute("""
        CREATE TRIGGER reject_prune BEFORE DELETE ON gf_save_checkpoints
        BEGIN SELECT RAISE(ABORT,'prune cannot commit'); END
    """)
    with pytest.raises(sqlite3.IntegrityError):
        a.save("game", 2, {"v": 2})
    assert b.latest("game").sequence == 1
    first.execute("DROP TRIGGER reject_prune")
    a.save("game", 2, {"v": 2})
    assert b.latest("game").sequence == 2


def test_cross_row_identity_rejected_and_verified_fallback(pair):
    first, second = pair
    a = SqliteCheckpointStore(first)
    a.save("game", 1, {"v": 1})
    a.save("game", 2, {"v": 2})
    raw = first.execute("SELECT body FROM gf_save_checkpoints WHERE sequence=1").fetchone()[0]
    first.execute("UPDATE gf_save_checkpoints SET body=? WHERE sequence=2", (raw,))
    b = SqliteCheckpointStore(second)
    with pytest.raises(CheckpointCorruptError):
        b.latest("game")
    assert b.restore("game").sequence == 1
    assert b.restore("game", min_sequence=2) is None
    with pytest.raises(CheckpointSequenceError):
        b.save("game", 2, {"v": 3})


def test_independent_journals_agree_and_conflicting_frame_rejected(pair):
    a, b = (SqliteReplayJournal(conn, "world") for conn in pair)
    first = a.append(0, {"op": "start"})
    assert b.append(0, {"op": "start"}) == first
    with pytest.raises(ReplayConflictError):
        b.append(0, {"op": "forged"})
    b.append(1, {"op": "advance"})
    assert a.frames() == b.frames() == [(0, {"op": "start"}), (1, {"op": "advance"})]
    assert a.head_digest() == b.head_digest()
    reference = ReplayJournal()
    reference.append(0, {"op": "start"})
    reference.append(1, {"op": "advance"})
    assert a.head_digest() == reference.head_digest()


def test_journal_failure_has_no_phantom_frame(pair):
    first, second = pair
    a = SqliteReplayJournal(first, "world")
    b = SqliteReplayJournal(second, "world")
    first.execute("""
        CREATE TRIGGER reject_frame BEFORE INSERT ON gf_replay_frames
        WHEN NEW.frame=1 BEGIN SELECT RAISE(ABORT,'simulated write failure'); END
    """)
    a.append(0, {"v": 0})
    with pytest.raises(sqlite3.IntegrityError):
        a.append(1, {"v": 1})
    assert a.frames() == b.frames() == [(0, {"v": 0})]
    first.execute("DROP TRIGGER reject_frame")
    b.append(1, {"v": 2})
    assert a.frames()[-1] == (1, {"v": 2})


def test_journal_tamper_after_open_is_detected(pair):
    first, second = pair
    a = SqliteReplayJournal(first, "world")
    b = SqliteReplayJournal(second, "world")
    a.append(0, {"v": 1})
    second.execute("UPDATE gf_replay_frames SET event=? WHERE stream='world'",
                   (json.dumps({"v": 2}),))
    for read in (a.frames, a.head_digest, b.ai_context):
        with pytest.raises(CheckpointCorruptError):
            read()
    with pytest.raises(CheckpointCorruptError):
        SqliteReplayJournal(second, "world")


def test_begin_failure_does_not_rollback_other_owner_transaction(pair):
    first, second = pair
    a = SqliteCheckpointStore(first)
    first.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(sqlite3.OperationalError):
            a.save("game", 1, {"v": 1})
        assert first.in_transaction
        assert SqliteCheckpointStore(second).latest("game") is None
    finally:
        first.execute("ROLLBACK")
    a.save("game", 1, {"v": 1})
    assert a.restore("game").sequence == 1


def test_context_and_stream_isolation(pair):
    a = SqliteReplayJournal(pair[0], "world", context_window=2)
    b = SqliteReplayJournal(pair[1], "other")
    for frame in range(5):
        a.append(frame, {"frame": frame})
    b.append(0, {"other": True})
    assert a.ai_context() == [{"frame": 3}, {"frame": 4}]
    assert a.ai_context(upto=2) == [{"frame": 1}, {"frame": 2}]
    assert b.frames() == [(0, {"other": True})]
    assert a.frames(after=3) == [(4, {"frame": 4})]


def test_canonical_mirror_bytes_match():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    a = root / "skeleton/persistence/game_save_sqlite.py"
    b = root / "skeleton/ai/runtime/persistence/game_save_sqlite.py"
    assert a.read_bytes() == b.read_bytes()
