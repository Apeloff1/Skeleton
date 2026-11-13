import asyncio

import pytest

from core import game_frontier_authoring as gfa

SCOPE = {"tenant_id": "t1", "owner_id": "o1"}


@pytest.fixture(autouse=True)
def _plane(monkeypatch, tmp_path):
    calls = []

    async def fake_source(scope, project_id):
        calls.append((scope["tenant_id"], project_id))
        return {"version": 1}, {}

    monkeypatch.setattr(gfa, "_source", fake_source)
    monkeypatch.setenv(gfa.GAME_SAVE_DB_ENV, str(tmp_path / "gf.db"))
    gfa._reset_save_plane()
    yield calls
    gfa._reset_save_plane()


def run(coro):
    return asyncio.run(coro)


def test_save_restore_paged_receipts_survive_reopen(_plane):
    receipts = [{"chunk_id": f"c{i}", "body": {"i": i}} for i in range(5)]
    out = run(gfa.save_game_state(SCOPE, "p1", "main", 1,
                                  {"world_axis": {"up": [0, 1, 0]}}, receipts))
    assert out["receipt_root"]
    run(gfa.save_game_state(SCOPE, "p1", "main", 2, {"world_axis": {"up": [0, 0, 1]}}))
    gfa._reset_save_plane()  # reopen from disk
    latest = run(gfa.restore_game_state(SCOPE, "p1", "main"))
    assert latest["sections"]["world_axis"]["up"] == [0, 0, 1]
    assert latest["backups"] == [1, 2] and latest["receipts"] is None
    first = run(gfa.restore_game_state(SCOPE, "p1", "main", sequence=1,
                                       receipt_cursor=0, receipt_limit=2))
    page = first["receipts"]
    assert [r["body"]["i"] for r in page["items"]] == [0, 1]
    assert page["next_cursor"] == 2 and page["total"] == 5
    assert ("t1", "p1") in _plane


def test_scopes_isolated():
    run(gfa.save_game_state(SCOPE, "p1", "main", 1, {"a": {}}))
    with pytest.raises(gfa.SavePlaneError):
        run(gfa.restore_game_state({"tenant_id": "t2", "owner_id": "o1"}, "p1", "main"))


def test_replay_frames_record_and_window():
    rec = run(gfa.record_replay_frames(
        SCOPE, "p1", "run", [{"frame": f, "event": {"d": f}} for f in range(6)]))
    assert rec["frames"] == 6
    out = run(gfa.replay_frames(SCOPE, "p1", "run", after=1, upto=3, context_upto=4))
    assert [f["frame"] for f in out["frames"]] == [2, 3]
    assert out["head_digest"] == rec["head_digest"]
    assert out["ai_context"][-1] == {"d": 4}
