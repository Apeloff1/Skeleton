"""
Session-2 deltas: Staff Picks toggle/list, leaderboard new fields (staff_pick, remix_count),
champions previous-week archive + plays/is_current, ranking popularity boost smoke.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = os.environ.get("EXPO_BACKEND_URL", "").rstrip("/")

assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"

API = f"{BASE_URL}/api"
TIMEOUT = 20


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def ready_pid(session):
    """Get a ready playable_id from /list."""
    r = session.get(f"{API}/playable/list?limit=10", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data.get("items") or data.get("playables") or data.get("list") or []
    # find a ready one
    for it in items:
        if it.get("status") == "ready" and it.get("playable_id"):
            return it["playable_id"]
    # fallback: just first
    assert items, "No playables returned from /list"
    return items[0]["playable_id"]


# ── Staff picks ────────────────────────────────────────────────────────────
class TestStaffPicks:
    def test_pick_true_returns_shape(self, session, ready_pid):
        r = session.post(f"{API}/playable/{ready_pid}/staff-pick", json={"pick": True}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("playable_id") == ready_pid
        assert d.get("staff_pick") is True

    def test_staff_picks_includes_pid(self, session, ready_pid):
        r = session.get(f"{API}/playable/staff-picks?limit=30", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        picks = d.get("staff_picks") or []
        ids = [p.get("playable_id") for p in picks]
        assert ready_pid in ids, f"{ready_pid} not in staff_picks {ids}"
        entry = next(p for p in picks if p["playable_id"] == ready_pid)
        # required fields
        for k in ("playable_id", "title", "genre", "overall", "difficulty",
                  "length", "plays", "remix_count", "has_cover"):
            assert k in entry, f"missing field {k} in staff_picks entry"
        assert isinstance(entry["plays"], int)
        assert isinstance(entry["remix_count"], int)
        assert isinstance(entry["has_cover"], bool)

    def test_pick_false_removes(self, session, ready_pid):
        r = session.post(f"{API}/playable/{ready_pid}/staff-pick", json={"pick": False}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("staff_pick") is False
        r2 = session.get(f"{API}/playable/staff-picks?limit=30", timeout=TIMEOUT)
        ids = [p.get("playable_id") for p in (r2.json().get("staff_picks") or [])]
        assert ready_pid not in ids

    def test_bad_pid(self, session):
        r = session.post(f"{API}/playable/does_not_exist_xxx/staff-pick", json={"pick": True}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("error") == "not found"


# ── Leaderboard new fields ─────────────────────────────────────────────────
class TestLeaderboard:
    def test_leaderboard_new_fields(self, session):
        r = session.get(f"{API}/playable/leaderboard?limit=5", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        board = d.get("leaderboard") or []
        assert isinstance(board, list)
        assert d.get("count") == len(board)
        for row in board:
            assert "staff_pick" in row
            assert isinstance(row["staff_pick"], bool)
            assert "remix_count" in row
            assert isinstance(row["remix_count"], int)
            # Session-1 fields still present
            for k in ("plays", "difficulty", "length", "score", "rank", "playable_id"):
                assert k in row, f"missing field {k}"
            assert isinstance(row["score"], (int, float))


# ── Champions: previous-week archive + plays/is_current ────────────────────
class TestChampions:
    def test_champions_shape(self, session):
        r = session.get(f"{API}/playable/champions?limit=5", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        champs = d.get("champions") or []
        # Could be empty if no playables exist this week, but should be a list and not error
        assert isinstance(champs, list)
        # Newest-first ordering by week_start
        if len(champs) >= 2:
            assert champs[0]["week_start"] >= champs[1]["week_start"]
        # Each champion should have plays + is_current
        for c in champs:
            assert "plays" in c, f"champion missing plays: {c}"
            assert isinstance(c["plays"], int)
            assert "is_current" in c
            assert isinstance(c["is_current"], bool)
        # At most one is_current=True
        currents = [c for c in champs if c.get("is_current")]
        assert len(currents) <= 1


# ── Ranking popularity boost smoke (no crash with plays bumped) ────────────
class TestRankingSmoke:
    def test_play_then_leaderboard(self, session, ready_pid):
        # bump plays a few times
        for _ in range(3):
            pr = session.post(f"{API}/playable/{ready_pid}/play", json={}, timeout=TIMEOUT)
            assert pr.status_code == 200
        # leaderboard still well-formed
        r = session.get(f"{API}/playable/leaderboard?limit=20", timeout=TIMEOUT)
        assert r.status_code == 200
        board = r.json().get("leaderboard") or []
        # numeric, sorted descending by score
        scores = [row["score"] for row in board]
        assert all(isinstance(s, (int, float)) for s in scores)
        assert scores == sorted(scores, reverse=True), f"not sorted: {scores}"
