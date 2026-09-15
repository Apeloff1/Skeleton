"""
Session 7 regression — discovery module split out of routes/playable.py into
routes/playable_discovery.py. Verifies:
- all discovery endpoints (literal paths) still 200 with correct shapes
- catch-all GET /{pid}, /{pid}/raw, /{pid}/lineage are NOT intercepted
- POST /{pid}/play, /{pid}/react, /{pid}/daily/enter work
- leaderboard, champions, staff-picks, vote remained healthy
"""
import os
import re
import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE:
    # fallback to frontend/.env load (pytest-run cwd is /app)
    try:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("EXPO_PUBLIC_BACKEND_URL="):
                    BASE = ln.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass
API = f"{BASE}/api"


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def sample_pid(sess):
    r = sess.get(f"{API}/playable/list?limit=10", timeout=30)
    assert r.status_code == 200, r.text
    items = r.json().get("playables") or r.json().get("items") or []
    assert items, "no playables available to test"
    pid = items[0].get("playable_id") or items[0].get("id")
    assert pid
    return pid


# ── DISCOVERY RAILS (moved to playable_discovery.py) ──
class TestDiscoveryRails:
    def test_trending(self, sess):
        r = sess.get(f"{API}/playable/trending?limit=12&hours=24", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "trending" in d and isinstance(d["trending"], list)
        assert "window_hours" in d

    def test_daily(self, sess):
        r = sess.get(f"{API}/playable/daily", timeout=20)
        assert r.status_code == 200
        d = r.json()
        for k in ("date", "theme", "prompt", "entries", "count"):
            assert k in d, f"missing {k}"

    def test_arena(self, sess):
        r = sess.get(f"{API}/playable/arena", timeout=20)
        assert r.status_code == 200
        d = r.json()
        for k in ("week_start", "theme", "prompt", "entries_this_week", "resets_at"):
            assert k in d

    def test_spotlight(self, sess):
        r = sess.get(f"{API}/playable/spotlight", timeout=20)
        assert r.status_code == 200
        assert "spotlight" in r.json()

    def test_most_loved(self, sess):
        r = sess.get(f"{API}/playable/most-loved?limit=12", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "most_loved" in d and isinstance(d["most_loved"], list)
        assert "count" in d

    def test_theme_of_week(self, sess):
        r = sess.get(f"{API}/playable/theme-of-week?limit=12", timeout=20)
        assert r.status_code == 200
        d = r.json()
        for k in ("theme", "prompt", "week", "games", "count"):
            assert k in d


# ── CATCH-ALL NOT SHADOWED by discovery router ──
class TestCatchAllNotShadowed:
    def test_get_pid_returns_full_game(self, sess, sample_pid):
        r = sess.get(f"{API}/playable/{sample_pid}", timeout=20)
        assert r.status_code == 200
        d = r.json()
        # If shadowed by discovery router, we'd get a discovery shape, not this.
        assert d.get("playable_id") == sample_pid
        assert "title" in d, f"shadowed? body={d}"

    def test_get_raw_returns_html(self, sess, sample_pid):
        r = sess.get(f"{API}/playable/{sample_pid}/raw", timeout=20)
        assert r.status_code == 200
        ctype = r.headers.get("content-type", "").lower()
        assert "html" in ctype
        body = r.text.lower()
        assert "<html" in body or "<!doctype" in body

    def test_lineage(self, sess, sample_pid):
        r = sess.get(f"{API}/playable/{sample_pid}/lineage", timeout=20)
        assert r.status_code == 200
        d = r.json()
        for k in ("node", "ancestors", "children"):
            assert k in d, f"missing {k} in lineage"


# ── ENGAGEMENT POSTS (moved to discovery module) ──
class TestEngagementPosts:
    def test_play_increments(self, sess, sample_pid):
        r = sess.post(f"{API}/playable/{sample_pid}/play", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("playable_id") == sample_pid
        assert "plays" in d and isinstance(d["plays"], int)

    def test_react_valid_emoji(self, sess, sample_pid):
        r = sess.post(f"{API}/playable/{sample_pid}/react", json={"emoji": "🔥"}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("playable_id") == sample_pid
        assert isinstance(d.get("reactions"), dict)

    def test_react_invalid_emoji(self, sess, sample_pid):
        r = sess.post(f"{API}/playable/{sample_pid}/react", json={"emoji": "x"}, timeout=20)
        assert r.status_code == 200
        assert r.json().get("error") == "invalid emoji"

    def test_daily_enter(self, sess, sample_pid):
        r = sess.post(f"{API}/playable/{sample_pid}/daily/enter", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("entered") is True
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", d.get("daily_date", ""))


# ── ROUTES STILL IN playable.py ──
class TestRemainingRoutes:
    def test_leaderboard(self, sess):
        r = sess.get(f"{API}/playable/leaderboard?limit=10", timeout=25)
        assert r.status_code == 200
        d = r.json()
        assert "leaderboard" in d and isinstance(d["leaderboard"], list)

    def test_leaderboard_q_sort(self, sess):
        r = sess.get(f"{API}/playable/leaderboard?q=a&sort=plays&limit=5", timeout=25)
        assert r.status_code == 200
        assert "leaderboard" in r.json()

    def test_champions(self, sess):
        r = sess.get(f"{API}/playable/champions", timeout=25)
        assert r.status_code == 200
        assert "champions" in r.json()

    def test_staff_picks(self, sess):
        r = sess.get(f"{API}/playable/staff-picks?limit=10", timeout=20)
        assert r.status_code == 200
        assert "staff_picks" in r.json()

    def test_vote_validation(self, sess, sample_pid):
        # without opponent_id → should return error (validates endpoint still routed)
        r = sess.post(f"{API}/playable/{sample_pid}/vote",
                      json={"opponent_id": "", "winner_id": ""}, timeout=20)
        assert r.status_code == 200
        assert "error" in r.json()
