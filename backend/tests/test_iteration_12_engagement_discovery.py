"""
Iteration 12 — Engagement & Discovery + Marketplace Quality tests.

FAST endpoints only (no live LLM calls except a light cover/options touch).
Covers: /trending, /play, /daily, /daily/enter, /arena, /leaderboard fields.
Cover endpoints exercised lightly via cover/options with count=2 with a long
timeout; skipped (not failed) if slow.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
assert BASE_URL, "Missing EXPO_PUBLIC_BACKEND_URL / EXPO_BACKEND_URL"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api/playable"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def ready_pid(session):
    r = session.get(f"{API}/list?limit=10", timeout=30)
    assert r.status_code == 200, f"/list failed: {r.status_code}"
    data = r.json()
    items = data.get("playables") or data.get("items") or []
    ready = [d for d in items if d.get("status") == "ready" and d.get("playable_id")]
    assert ready, "No ready playables found to test against"
    return ready[0]["playable_id"]


# ─── Engagement: /play increments + /trending picks it up ───
class TestPlayAndTrending:
    def test_play_increments_counter(self, session, ready_pid):
        # baseline
        r1 = session.post(f"{API}/{ready_pid}/play", timeout=30)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1.get("playable_id") == ready_pid
        assert isinstance(d1.get("plays"), int)
        before = d1["plays"]
        r2 = session.post(f"{API}/{ready_pid}/play", timeout=30)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["plays"] == before + 1, f"plays did not increment: {before} → {d2['plays']}"

    def test_play_unknown_pid_returns_error(self, session):
        r = session.post(f"{API}/__nope_xyz__/play", timeout=30)
        # Endpoint returns 200 with {"error": "not found"}
        assert r.status_code == 200
        assert (r.json().get("error") or "").lower() == "not found"

    def test_trending_shape_and_window(self, session, ready_pid):
        # Make sure ready_pid has activity
        session.post(f"{API}/{ready_pid}/play", timeout=30)
        session.post(f"{API}/{ready_pid}/play", timeout=30)
        r = session.get(f"{API}/trending?hours=24&limit=20", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "trending" in data and "count" in data and "window_hours" in data
        assert data["window_hours"] == 24
        assert isinstance(data["trending"], list)
        if data["trending"]:
            row = data["trending"][0]
            for key in ("rank", "playable_id", "title", "velocity",
                        "plays_window", "votes_window", "plays",
                        "overall", "difficulty", "length"):
                assert key in row, f"missing field in trending row: {key}"
            # velocity formula: plays + votes*2
            assert row["velocity"] == row["plays_window"] + row["votes_window"] * 2
            # rank starts at 1, monotonic
            ranks = [r["rank"] for r in data["trending"]]
            assert ranks == sorted(ranks)
            assert ranks[0] == 1

    def test_played_pid_in_trending(self, session, ready_pid):
        session.post(f"{API}/{ready_pid}/play", timeout=30)
        r = session.get(f"{API}/trending?hours=24&limit=50", timeout=30)
        ids = [row["playable_id"] for row in r.json().get("trending", [])]
        assert ready_pid in ids, "played pid not surfacing in trending"


# ─── Daily Challenge ───
class TestDailyChallenge:
    def test_daily_shape(self, session):
        r = session.get(f"{API}/daily", timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("date", "theme", "prompt", "entries", "count"):
            assert k in d, f"missing key {k}"
        assert isinstance(d["entries"], list)
        assert d["count"] == len(d["entries"])
        assert len(d["theme"]) > 0 and len(d["prompt"]) > 0

    def test_daily_enter_then_appears(self, session, ready_pid):
        r = session.post(f"{API}/{ready_pid}/daily/enter", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("entered") is True
        assert d.get("playable_id") == ready_pid
        assert d.get("daily_date")

        r2 = session.get(f"{API}/daily?limit=50", timeout=30)
        assert r2.status_code == 200
        entries = r2.json().get("entries", [])
        ids = [e["playable_id"] for e in entries]
        assert ready_pid in ids, "entered pid not present in daily entries"
        # rank should be int and ascending
        ranks = [e["rank"] for e in entries]
        assert ranks == sorted(ranks)

    def test_daily_enter_unknown_pid(self, session):
        r = session.post(f"{API}/__nope__/daily/enter", timeout=30)
        assert r.status_code == 200
        assert (r.json().get("error") or "").lower() == "not found"


# ─── Weekly Arena ───
class TestArena:
    def test_arena_shape(self, session):
        r = session.get(f"{API}/arena", timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("week_start", "theme", "prompt", "entries_this_week", "resets_at"):
            assert k in d, f"missing key {k}"
        assert isinstance(d["entries_this_week"], int)
        # week_start should be ISO-like YYYY-MM-DD
        assert len(d["week_start"]) == 10 and d["week_start"][4] == "-"


# ─── Leaderboard now includes plays / difficulty / length ───
class TestLeaderboardFields:
    def test_leaderboard_returns_new_fields(self, session):
        r = session.get(f"{API}/leaderboard?limit=5", timeout=30)
        assert r.status_code == 200
        rows = r.json().get("leaderboard", [])
        assert rows, "leaderboard empty"
        for row in rows:
            assert "plays" in row, "missing plays"
            assert "difficulty" in row, "missing difficulty"
            assert "length" in row, "missing length"
            # plays must be int; difficulty/length may be None
            assert isinstance(row["plays"], int)
            if row["difficulty"] is not None:
                assert row["difficulty"] in ("easy", "medium", "hard")
            if row["length"] is not None:
                assert row["length"] in ("short", "medium", "long")


# ─── Cover endpoints (LIGHT touch — live image-gen, may be slow) ───
class TestCoverEndpoints:
    def test_cover_options_light(self, session, ready_pid):
        """Calls Nano Banana live — give it a generous timeout; skip if it
        times out (not a defect per spec)."""
        try:
            r = session.post(f"{API}/{ready_pid}/cover/options?count=2", timeout=180)
        except requests.exceptions.ReadTimeout:
            pytest.skip("cover/options live image-gen exceeded 180s (slow but not a defect)")
        assert r.status_code == 200, r.text
        d = r.json()
        if d.get("error"):
            pytest.skip(f"cover gen returned error (live LLM): {d.get('error')}")
        assert d.get("count") in (2, 3)
        assert isinstance(d.get("options"), list)
        # at least one option should be reachable as PNG
        if d.get("options"):
            idx = d["options"][0]
            r2 = session.get(f"{API}/{ready_pid}/cover/opt/{idx}.png", timeout=30)
            assert r2.status_code == 200
            assert r2.headers.get("content-type", "").startswith("image/")
            assert len(r2.content) > 200
