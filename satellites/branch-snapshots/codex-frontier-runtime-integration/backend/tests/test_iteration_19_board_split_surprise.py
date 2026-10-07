"""
Iteration 19 — Session 8 regression:
 * Board module move: leaderboard / champions / staff-picks now live in
   routes/playable_board.py (registered BEFORE routes/playable).
 * New GET /api/playable/surprise (in routes/playable_discovery.py).
 * No shadowing: /{pid}, /{pid}/raw, /{pid}/lineage still resolve to playable.py.
 * Discovery rails (/trending,/daily,/arena,/spotlight,/most-loved,/theme-of-week).
 * Engagement POSTs (/play, /react, /daily/enter).
"""
import os
import re
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL", "")).rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def sample_pid(client):
    r = client.get(f"{API}/playable/list?limit=10", timeout=20)
    assert r.status_code == 200, r.text
    items = r.json().get("playables") or r.json().get("items") or []
    if not items:
        pytest.skip("No playables seeded — cannot regression-test pid routes")
    return items[0].get("playable_id") or items[0].get("id")


# ───── Board module: leaderboard ─────
class TestLeaderboard:
    def test_default(self, client):
        r = client.get(f"{API}/playable/leaderboard?limit=5", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "leaderboard" in data and isinstance(data["leaderboard"], list)
        if data["leaderboard"]:
            row = data["leaderboard"][0]
            for k in ("playable_id", "title", "reactions_total", "staff_pick",
                      "champion_weeks", "remix_count", "plays", "difficulty",
                      "length", "score"):
                assert k in row, f"missing {k!r} in leaderboard row"

    @pytest.mark.parametrize("sort", ["plays", "newest", "remixed", "score"])
    def test_sort_modes(self, client, sort):
        r = client.get(f"{API}/playable/leaderboard?limit=5&sort={sort}", timeout=20)
        assert r.status_code == 200
        assert "leaderboard" in r.json()

    def test_q_search(self, client):
        r = client.get(f"{API}/playable/leaderboard?limit=5&q=a", timeout=20)
        assert r.status_code == 200
        assert "leaderboard" in r.json()


# ───── Board module: champions ─────
class TestChampions:
    def test_returns(self, client):
        r = client.get(f"{API}/playable/champions?limit=8", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "champions" in d and isinstance(d["champions"], list)
        for c in d["champions"]:
            assert "plays" in c
            assert "is_current" in c
            assert isinstance(c["is_current"], bool)


# ───── Board module: staff-picks toggle ─────
class TestStaffPicks:
    def test_list_shape(self, client):
        r = client.get(f"{API}/playable/staff-picks?limit=10", timeout=20)
        assert r.status_code == 200
        assert "staff_picks" in r.json()

    def test_toggle_round_trip(self, client, sample_pid):
        # Set pick=true
        r = client.post(f"{API}/playable/{sample_pid}/staff-pick", json={"pick": True}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("staff_pick") is True

        # Confirm appears in /staff-picks
        rl = client.get(f"{API}/playable/staff-picks?limit=30", timeout=20)
        assert rl.status_code == 200
        ids = [g.get("playable_id") for g in rl.json().get("staff_picks", [])]
        assert sample_pid in ids, "Newly picked pid should appear in /staff-picks"

        # Unpick
        r2 = client.post(f"{API}/playable/{sample_pid}/staff-pick", json={"pick": False}, timeout=20)
        assert r2.status_code == 200
        assert r2.json().get("staff_pick") is False

        rl2 = client.get(f"{API}/playable/staff-picks?limit=30", timeout=20)
        ids2 = [g.get("playable_id") for g in rl2.json().get("staff_picks", [])]
        assert sample_pid not in ids2, "Unpicked pid should NOT appear in /staff-picks"


# ───── NO SHADOWING: /{pid}, /{pid}/raw, /{pid}/lineage ─────
class TestNoShadowing:
    def test_get_pid_returns_game(self, client, sample_pid):
        r = client.get(f"{API}/playable/{sample_pid}", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        # Must look like a game doc — not the leaderboard or champions shape
        assert "leaderboard" not in d and "champions" not in d and "staff_picks" not in d
        assert d.get("playable_id") == sample_pid

    def test_get_pid_raw_html(self, client, sample_pid):
        r = client.get(f"{API}/playable/{sample_pid}/raw", timeout=20)
        assert r.status_code == 200
        # Either text/html or a JSON wrapper — accept either as long as some
        # HTML or 'html' marker is present.
        ct = r.headers.get("content-type", "")
        body = r.text
        assert "html" in ct.lower() or "<" in body[:200] or "html" in body[:200].lower()

    def test_get_pid_lineage(self, client, sample_pid):
        r = client.get(f"{API}/playable/{sample_pid}/lineage", timeout=20)
        assert r.status_code == 200
        d = r.json()
        for k in ("node", "ancestors", "children"):
            assert k in d, f"lineage missing {k!r}"


# ───── Discovery rails (regression) ─────
class TestDiscoveryRails:
    @pytest.mark.parametrize("path,key", [
        ("trending?limit=6&hours=24", "trending"),
        ("daily", "theme"),
        ("arena?limit=4", "theme"),
        ("spotlight", "spotlight"),
        ("most-loved?limit=6", "most_loved"),
        ("theme-of-week?limit=6", "games"),
    ])
    def test_rail(self, client, path, key):
        r = client.get(f"{API}/playable/{path}", timeout=20)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
        assert key in r.json(), f"{path} missing key {key!r}"


# ───── Engagement POSTs (regression) ─────
class TestEngagement:
    def test_play(self, client, sample_pid):
        r = client.post(f"{API}/playable/{sample_pid}/play", json={}, timeout=20)
        assert r.status_code == 200, r.text

    def test_react(self, client, sample_pid):
        r = client.post(f"{API}/playable/{sample_pid}/react", json={"emoji": "🔥"}, timeout=20)
        assert r.status_code == 200, r.text

    def test_daily_enter(self, client, sample_pid):
        r = client.post(f"{API}/playable/{sample_pid}/daily/enter", json={}, timeout=20)
        # 200 success or 4xx if business rules reject — both prove the route resolved.
        assert r.status_code in (200, 400, 409, 422), r.text


# ───── NEW: /surprise ─────
class TestSurprise:
    def test_default_returns_game(self, client):
        r = client.get(f"{API}/playable/surprise", timeout=20)
        assert r.status_code == 200, r.text
        s = r.json().get("surprise")
        assert s and s.get("playable_id"), "expected a surprise game"
        for k in ("title", "genre", "overall"):
            assert k in s, f"missing {k} in surprise payload"

    def test_default_is_random(self, client):
        # Across N calls expect at least 2 distinct picks (probabilistic but
        # with ≥2 ready games this is virtually certain).
        ids = set()
        for _ in range(8):
            r = client.get(f"{API}/playable/surprise", timeout=20)
            assert r.status_code == 200
            sid = (r.json().get("surprise") or {}).get("playable_id")
            if sid:
                ids.add(sid)
        # If only 1 ready game exists, skip — otherwise expect variety.
        rlist = client.get(f"{API}/playable/list?limit=50", timeout=20).json()
        items = rlist.get("playables") or rlist.get("items") or []
        ready_count = sum(1 for g in items if (g.get("status") in (None, "ready")))
        if ready_count >= 3:
            assert len(ids) >= 2, f"surprise looks deterministic: {ids}"

    def test_genre_bias_arcade(self, client):
        r = client.get(f"{API}/playable/surprise?genre=arcade", timeout=20)
        assert r.status_code == 200
        # Even with no arcade games, fallback ensures a game is returned.
        s = r.json().get("surprise")
        assert s and s.get("playable_id"), "surprise must fall back when filter empty"

    def test_genre_bias_bogus_falls_back(self, client):
        r = client.get(f"{API}/playable/surprise?genre=zzz_nonexistent_genre_xyz", timeout=20)
        assert r.status_code == 200
        s = r.json().get("surprise")
        assert s and s.get("playable_id"), "must gracefully fall back to any ready game"
