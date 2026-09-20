"""
Session 4 deltas — Leaderboard search/sort, Emoji reactions, Daily spotlight,
Collection share card.
"""
import os
import re
import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://gemini-game-craft.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def ready_pid(session):
    """Pick a ready playable id for react/collection tests."""
    r = session.get(f"{API}/playable/list", params={"limit": 10}, timeout=30)
    assert r.status_code == 200, r.text
    items = r.json().get("playables") or r.json().get("items") or r.json().get("list") or []
    if not items:
        # fallback shape
        items = r.json() if isinstance(r.json(), list) else []
    ready = [p for p in items if (p.get("status") == "ready")]
    if not ready:
        pytest.skip("No ready playables available in the system")
    return ready[0]["playable_id"]


# ── Leaderboard search + sort ──────────────────────────────────────
class TestLeaderboardSearchSort:

    def test_leaderboard_default(self, session):
        r = session.get(f"{API}/playable/leaderboard", params={"limit": 5}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "leaderboard" in data
        assert isinstance(data["leaderboard"], list)

    def test_leaderboard_search_q(self, session):
        r = session.get(f"{API}/playable/leaderboard",
                        params={"q": "neon", "limit": 5}, timeout=30)
        assert r.status_code == 200, r.text
        board = r.json().get("leaderboard", [])
        # Every result must match 'neon' case-insensitively in title/genre
        for item in board:
            t = (item.get("title") or "").lower()
            g = (item.get("genre") or "").lower()
            assert "neon" in t or "neon" in g, f"non-matching item: {item}"

    def test_leaderboard_sort_plays(self, session):
        r = session.get(f"{API}/playable/leaderboard",
                        params={"sort": "plays", "limit": 10}, timeout=30)
        assert r.status_code == 200
        board = r.json().get("leaderboard", [])
        plays = [i.get("plays", 0) or 0 for i in board]
        assert plays == sorted(plays, reverse=True), f"plays not desc: {plays}"

    def test_leaderboard_sort_newest(self, session):
        r = session.get(f"{API}/playable/leaderboard",
                        params={"sort": "newest", "limit": 10}, timeout=30)
        assert r.status_code == 200
        board = r.json().get("leaderboard", [])
        # No created_at returned in row — can't strictly verify ordering, but should be well-formed
        assert all("playable_id" in i for i in board)

    def test_leaderboard_sort_remixed(self, session):
        r = session.get(f"{API}/playable/leaderboard",
                        params={"sort": "remixed", "limit": 10}, timeout=30)
        assert r.status_code == 200
        board = r.json().get("leaderboard", [])
        rc = [i.get("remix_count", 0) or 0 for i in board]
        assert rc == sorted(rc, reverse=True), f"remix_count not desc: {rc}"

    def test_leaderboard_sort_score_default(self, session):
        r = session.get(f"{API}/playable/leaderboard",
                        params={"sort": "score", "limit": 10}, timeout=30)
        assert r.status_code == 200
        board = r.json().get("leaderboard", [])
        scores = [i.get("score", 0) or 0 for i in board]
        assert scores == sorted(scores, reverse=True), f"score not desc: {scores}"


# ── Emoji reactions ────────────────────────────────────────────────
class TestReactions:

    def test_react_valid_emoji_increments(self, session, ready_pid):
        r = session.post(f"{API}/playable/{ready_pid}/react",
                         json={"emoji": "🔥"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("playable_id") == ready_pid
        assert "reactions" in data
        assert isinstance(data["reactions"], dict)
        assert data["reactions"].get("🔥", 0) >= 1

    def test_react_invalid_emoji(self, session, ready_pid):
        r = session.post(f"{API}/playable/{ready_pid}/react",
                         json={"emoji": "x"}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data.get("error") == "invalid emoji"
        assert "allowed" in data
        assert isinstance(data["allowed"], list) and len(data["allowed"]) >= 1

    def test_react_bad_pid(self, session):
        r = session.post(f"{API}/playable/nonexistent_pid_xyz/react",
                         json={"emoji": "🔥"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("error") == "not found"


# ── Daily spotlight ────────────────────────────────────────────────
class TestSpotlight:

    def test_spotlight_shape(self, session):
        r = session.get(f"{API}/playable/spotlight", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "spotlight" in data
        sp = data.get("spotlight")
        if sp is None:
            # acceptable when no ready games exist
            return
        # date present when spotlight is non-null
        assert "date" in data
        for key in ("playable_id", "title", "genre", "overall"):
            assert key in sp, f"missing {key} in {sp}"


# ── Collection share card ──────────────────────────────────────────
class TestCollectionCard:

    @pytest.fixture(scope="class")
    def collection_with_game(self, session, ready_pid):
        # Create collection
        r = session.post(f"{API}/collections",
                         json={"name": "TEST_session4_card"}, timeout=30)
        assert r.status_code == 200, r.text
        cid = r.json().get("collection_id")
        assert cid
        # Add game
        r2 = session.post(f"{API}/collections/{cid}/games",
                          json={"playable_id": ready_pid}, timeout=30)
        assert r2.status_code == 200, r2.text
        yield cid
        # cleanup
        try:
            session.delete(f"{API}/collections/{cid}", timeout=10)
        except Exception:
            pass

    def test_card_png_returns_image(self, session, collection_with_game):
        r = session.get(f"{API}/collections/{collection_with_game}/card.png", timeout=30)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("image/png"), r.headers
        # non-trivial bytes
        assert len(r.content) > 5000, f"image too small: {len(r.content)} bytes"
        # PNG magic bytes
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_card_bad_cid_404(self, session):
        r = session.get(f"{API}/collections/nonexistent_xyz/card.png", timeout=30)
        assert r.status_code == 404
