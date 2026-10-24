import pytest

from skeleton.kernel.checkpoint import CheckpointStore
from skeleton.kernel.game_save_plane import (
    ChunkReceiptStore, GameSavePlane, ReplayConflictError, ReplayJournal,
    SavePlaneError,
)

SECTIONS = {
    "world_axis": {"up": [0, 1, 0], "north": [0, 0, 1]},
    "weather": {"front": "cold", "wind": [3.5, 0.0]},
    "variants": {"biome": "tundra-v2"},
    "structures": {"tower-1": {"hp": 90}},
    "motion": {"npc-7": {"pos": [1, 2, 3], "vel": [0, 0, 1]}},
    "calibration": {"sextant": {"drift": 0.012}},
}


def test_receipts_content_addressed_and_paged():
    rs = ChunkReceiptStore(max_page_size=3)
    for i in range(7):
        rs.put(f"c{i % 2}", {"i": i})
    again = rs.put("c0", {"i": 0})
    assert again.sequence == 0
    seen, cursor = [], 0
    while cursor is not None:
        page = rs.page(cursor=cursor, limit=50)
        assert len(page.items) <= 3
        seen.extend(r.body["i"] for r in page.items)
        cursor = page.next_cursor
    assert seen == list(range(7))
    assert rs.page(chunk_id="c1").total == 3
    with pytest.raises(SavePlaneError):
        rs.page(cursor=-1)


def test_save_restore_round_trip_with_receipts():
    plane = GameSavePlane()
    rs = ChunkReceiptStore()
    rs.put("chunk-a", {"hash": "x"})
    plane.save("slot1", 1, SECTIONS, receipts=rs)
    sections, restored = plane.restore("slot1")
    assert sections == SECTIONS
    assert restored.root() == rs.root()


def test_rollback_and_backups():
    plane = GameSavePlane(store=CheckpointStore(retain=3))
    for seq in range(1, 5):
        plane.save("s", seq, {"weather": {"t": seq}})
    assert plane.backups("s") == (2, 3, 4)
    assert plane.restore("s", sequence=2)[0]["weather"]["t"] == 2
    with pytest.raises(SavePlaneError):
        plane.restore("s", sequence=1)


def test_corrupt_latest_falls_back():
    plane = GameSavePlane()
    plane.save("s", 1, {"a": {"v": 1}})
    ck = plane.save("s", 2, {"a": {"v": 2}})
    ck.state["sections"]["a"]["v"] = 99  # tamper
    assert plane.restore("s")[0]["a"]["v"] == 1


def test_migration_applied_and_future_rejected():
    old = GameSavePlane(schema_version=1)
    old.save("s", 1, {"weather": {"wind": 3}})
    new = GameSavePlane(store=old.store, schema_version=2)
    def m(state):
        state["sections"]["weather"]["wind"] = [state["sections"]["weather"]["wind"], 0]
        return state
    new.register_migration(1, m)
    assert new.restore("s")[0]["weather"]["wind"] == [3, 0]
    future = GameSavePlane(store=new.store, schema_version=1)
    new.save("s", 2, {"x": {}})
    with pytest.raises(SavePlaneError):
        future.restore("s")


def test_missing_migration_rejected():
    old = GameSavePlane(schema_version=1)
    old.save("s", 1, {})
    with pytest.raises(SavePlaneError):
        GameSavePlane(store=old.store, schema_version=3).restore("s")


def test_replay_idempotent_conflict_and_cursor():
    j = ReplayJournal(context_window=2)
    for f in range(5):
        j.append(f, {"d": 1})
    j.append(2, {"d": 1})
    with pytest.raises(ReplayConflictError):
        j.append(2, {"d": 2})
    red = lambda s, e: {"n": s["n"] + e["d"]}
    assert j.replay({"n": 0}, red) == {"n": 5}
    assert j.replay({"n": 10}, red, after=2, upto=3) == {"n": 11}
    assert len(j.ai_context()) == 2
    assert len(j.ai_context(upto=0)) == 1


def test_restore_then_replay_matches_live():
    red = lambda s, e: {**s, "x": s["x"] + e["dx"]}
    j = ReplayJournal()
    live = {"x": 0}
    plane = GameSavePlane()
    for f in range(10):
        ev = {"dx": f}
        j.append(f, ev)
        live = red(live, ev)
        if f == 4:
            plane.save("s", f, {"world": live})
    base, _ = plane.restore("s")
    assert j.replay(base["world"], red, after=4) == live
