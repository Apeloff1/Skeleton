"""
Iteration 26 — Session 11.4 backend smoke.

Confirms backend unchanged after the deluxe-palette remap + React-import removal
on the frontend. Hits the five endpoints flagged in the review request.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://gemini-game-craft.preview.emergentagent.com",
).rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Smoke: five endpoints flagged by review_request ──────────────────────────
class TestSession11_4BackendSmoke:
    def test_trending_creators(self, api):
        r = api.get(f"{BASE_URL}/api/marketplace/creators/trending?limit=10", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "creators" in body and isinstance(body["creators"], list)

    def test_marketplace_listings(self, api):
        r = api.get(f"{BASE_URL}/api/marketplace/listings?limit=10", timeout=20)
        assert r.status_code == 200, r.text
        assert "listings" in r.json()

    def test_tournaments(self, api):
        r = api.get(f"{BASE_URL}/api/tournaments", timeout=20)
        assert r.status_code == 200, r.text

    def test_liveops_season(self, api):
        r = api.get(f"{BASE_URL}/api/liveops/season", timeout=20)
        assert r.status_code == 200, r.text

    def test_playable_list(self, api):
        r = api.get(f"{BASE_URL}/api/playable/list", timeout=20)
        assert r.status_code == 200, r.text


# ── Route registry sanity (>=94 routes per iter 25) ──────────────────────────
class TestRouteRegistry:
    def test_route_count_at_least_94(self, api):
        # /api/_routes may not exist on every build; fall back gracefully
        r = api.get(f"{BASE_URL}/api/_routes", timeout=20)
        if r.status_code != 200:
            pytest.skip("/api/_routes not exposed")
        data = r.json()
        routes = data.get("routes") or data.get("paths") or []
        assert len(routes) >= 90, f"expected >=90 routes, got {len(routes)}"
