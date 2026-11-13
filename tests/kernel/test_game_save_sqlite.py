
import pytest

from skeleton.kernel.game_save_plane import (
    ChunkReceiptStore, GameSavePlane, ReplayConflictError,
)
from skeleton.persistence.game_save_sqlite import (
    SqliteCheckpointStore, SqliteReplayJournal, open_game_save_db,
)


def test_durable_round_trip_across_reopen(tmp_path):
    db = str(tmp_path / "s.db")
    conn = open_game_save_db(db)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    plane = GameSavePlane(store=SqliteCheckpointStore(conn, retain=2))
    rs = ChunkReceiptStore()
    rs.put("c", {"h": 1})
    for seq in (1, 2, 3):
        plane.save("slot", seq, {"weather": {"t": seq}}, receipts=rs)
    conn.close()
    conn2 = open_game_save_db(db)
    plane2 = GameSavePlane(store=SqliteCheckpointStore(conn2, retain=2))
    assert plane2.backups("slot") == (2, 3)
    sections, rec = plane2.restore("slot")
    assert sections == {"weather": {"t": 3}} and rec.root() == rs.root()
    assert plane2.restore("slot", sequence=2)[0]["weather"]["t"] == 2
    n = conn2.execute("SELECT COUNT(*) FROM gf_save_checkpoints").fetchone()[0]
    assert n == 2
    with pytest.raises(Exception):
        plane2.save("slot", 3, {})  # monotonic survives reopen


def test_tampered_row_skipped_on_restore(tmp_path):
    db = str(tmp_path / "s.db")
    conn = open_game_save_db(db)
    plane = GameSavePlane(store=SqliteCheckpointStore(conn))
    plane.save("s", 1, {"a": {"v": 1}})
    plane.save("s", 2, {"a": {"v": 2}})
    body = conn.execute("SELECT body FROM gf_save_checkpoints WHERE sequence=2").fetchone()[0]
    conn.execute("UPDATE gf_save_checkpoints SET body=? WHERE sequence=2",
                 (body.replace('"v": 2', '"v": 9'),))
    plane2 = GameSavePlane(store=SqliteCheckpointStore(open_game_save_db(db)))
    assert plane2.restore("s")[0]["a"]["v"] == 1


def test_replay_journal_durable(tmp_path):
    db = str(tmp_path / "s.db")
    conn = open_game_save_db(db)
    j = SqliteReplayJournal(conn, "run-1", context_window=2)
    for f in range(4):
        j.append(f, {"d": f})
    j.append(1, {"d": 1})
    with pytest.raises(ReplayConflictError):
        j.append(1, {"d": 5})
    head = j.head_digest()
    j2 = SqliteReplayJournal(open_game_save_db(db), "run-1", context_window=2)
    assert j2.head_digest() == head
    assert j2.replay({"n": 0}, lambda s, e: {"n": s["n"] + e["d"]}) == {"n": 6}
    assert [e["d"] for e in j2.ai_context()] == [2, 3]
    assert SqliteReplayJournal(conn, "other").frames() == []
