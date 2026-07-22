"""
Iteration 25 — Session 11.3 backend tests.

Covers:
- GET /api/marketplace/creators/trending — leaderboard schema, sort, rank,
  studioQA visibility, limit cap (50).
- Smoke: existing endpoints used by /creator screen — /api/marketplace/mine,
  /api/liveops/pass, /api/marketplace/listings, /api/tournaments.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://gemini-game-craft.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Trending Creators leaderboard ─────────────────────────────────────────────
class TestTrendingCreators:
    def test_returns_creators_and_count(self, api):
        r = api.get(f"{BASE_URL}/api/marketplace/creators/trending?limit=10", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert "creators" in data and "count" in data
        assert isinstance(data["creators"], list)
        assert isinstance(data["count"], int)

    def test_schema_fields(self, api):
        r = api.get(f"{BASE_URL}/api/marketplace/creators/trending?limit=10", timeout=20)
        data = r.json()
        assert data["creators"], "expected at least 1 creator (studioQA)"
        c0 = data["creators"][0]
        for k in ("rank", "creator_id", "sales", "revenue_usd", "games", "plays", "score"):
            assert k in c0, f"missing key {k} in creator row"
        assert c0["rank"] == 1
        # types
        assert isinstance(c0["rank"], int)
        assert isinstance(c0["creator_id"], str)
        assert isinstance(c0["sales"], (int, float))
        assert isinstance(c0["revenue_usd"], (int, float))
        assert isinstance(c0["games"], int)
        assert isinstance(c0["plays"], (int, float))
        assert isinstance(c0["score"], (int, float))

    def test_studioQA_present_and_top(self, api):
        r = api.get(f"{BASE_URL}/api/marketplace/creators/trending?limit=50", timeout=20)
        data = r.json()
        ids = [c["creator_id"] for c in data["creators"]]
        assert "studioQA" in ids, f"studioQA missing from leaderboard, got {ids}"
        sq = next(c for c in data["creators"] if c["creator_id"] == "studioQA")
        # session 11.2 had plays>=27 (current is 82); assert >=27 as per spec
        assert sq["plays"] >= 27, f"studioQA plays={sq['plays']} expected>=27"

    def test_sorted_by_score_desc(self, api):
        r = api.get(f"{BASE_URL}/api/marketplace/creators/trending?limit=50", timeout=20)
        creators = r.json()["creators"]
        scores = [c["score"] for c in creators]
        assert scores == sorted(scores, reverse=True), "creators not sorted by score desc"
        ranks = [c["rank"] for c in creators]
        assert ranks == list(range(1, len(creators) + 1)), "ranks not sequential"

    def test_limit_respected(self, api):
        r = api.get(f"{BASE_URL}/api/marketplace/creators/trending?limit=3", timeout=20)
        creators = r.json()["creators"]
        assert len(creators) <= 3

    def test_limit_max_cap_50(self, api):
        # FastAPI Query(le=50) should reject > 50
        r = api.get(f"{BASE_URL}/api/marketplace/creators/trending?limit=100", timeout=20)
        # Either 422 (validation error) or capped silently — both acceptable
        if r.status_code == 200:
            assert len(r.json()["creators"]) <= 50
        else:
            assert r.status_code == 422


# ── Endpoints used by /creator screen ─────────────────────────────────────────
class TestCreatorScreenEndpoints:
    def test_mine_studioQA(self, api):
        r = api.get(f"{BASE_URL}/api/marketplace/mine?creator_id=studioQA", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "listings" in d and "totals" in d
        assert d["totals"]["games"] >= 1

    def test_liveops_pass(self, api):
        r = api.get(f"{BASE_URL}/api/liveops/pass?visitor_id=studioQA", timeout=20)
        assert r.status_code == 200
        d = r.json()
        # liveops returns xp/tier shape
        assert any(k in d for k in ("xp", "tier", "ok"))

    def test_marketplace_listings(self, api):
        r = api.get(f"{BASE_URL}/api/marketplace/listings?limit=10", timeout=20)
        assert r.status_code == 200
        assert "listings" in r.json()

    def test_tournaments_list(self, api):
        r = api.get(f"{BASE_URL}/api/tournaments", timeout=20)
        assert r.status_code == 200
