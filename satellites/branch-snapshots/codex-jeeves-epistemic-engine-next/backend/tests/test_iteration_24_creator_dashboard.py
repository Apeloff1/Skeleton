"""
Session 11.2 — Creator Dashboard + Deluxe restyle regression tests.

Covers:
  - GET /api/marketplace/mine?creator_id=studioQA (>=1 listing + hydration + totals)
  - GET /api/marketplace/mine?creator_id=<unknown> (empty + zeroed totals)
  - Regression smoke: listings, tournaments, liveops/season, playable/list,
    liveops/pass, registered count.
"""
import os
import pytest
import requests

BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_PUBLIC_BACKEND_URL") else \
    "https://gemini-game-craft.preview.emergentagent.com"

TIMEOUT = 30


# --- /api/marketplace/mine ---------------------------------------------------
class TestCreatorDashboardMine:
    def test_studioqa_has_listings_and_totals(self):
        r = requests.get(f"{BASE}/api/marketplace/mine", params={"creator_id": "studioQA"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "listings" in data and "totals" in data
        listings = data["listings"]
        totals = data["totals"]
        assert isinstance(listings, list)
        assert len(listings) >= 1, f"expected >=1 listing for studioQA, got {len(listings)}"
        # Hydration fields on each listing
        for l in listings:
            for k in ("playable_id", "title", "genre", "has_cover", "plays", "price_usd"):
                assert k in l, f"listing missing field: {k}"
            assert isinstance(l["has_cover"], bool)
        # Totals contract
        for k in ("games", "active", "sales", "revenue_usd", "plays"):
            assert k in totals, f"totals missing field: {k}"
        assert totals["games"] == len(listings)
        assert totals["plays"] >= 0
        assert totals["revenue_usd"] >= 0

    def test_unknown_creator_empty_totals(self):
        r = requests.get(f"{BASE}/api/marketplace/mine",
                         params={"creator_id": "ghost_no_such_creator_xyz_TEST"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["listings"] == []
        t = data["totals"]
        assert t == {"games": 0, "active": 0, "sales": 0, "revenue_usd": 0.0, "plays": 0} \
            or (t["games"] == 0 and t["active"] == 0 and t["sales"] == 0
                and t["revenue_usd"] == 0 and t["plays"] == 0)


# --- Regression smoke --------------------------------------------------------
class TestRegressionSmoke:
    def test_marketplace_listings(self):
        r = requests.get(f"{BASE}/api/marketplace/listings", timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        assert "listings" in body and isinstance(body["listings"], list)

    def test_tournaments(self):
        r = requests.get(f"{BASE}/api/tournaments", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_liveops_season(self):
        r = requests.get(f"{BASE}/api/liveops/season", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_playable_list(self):
        # Note: "registered=94" from main agent refers to routes_registry boot
        # count (seen in backend log: routes_registry registered=94), NOT the
        # number of playables. playable/list is paginated, default limit=20.
        r = requests.get(f"{BASE}/api/playable/list", timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, dict)
        assert "playables" in body and isinstance(body["playables"], list)
        assert body.get("count", 0) >= 1

    def test_liveops_pass_default_visitor(self):
        r = requests.get(f"{BASE}/api/liveops/pass", params={"visitor_id": "studioQA"}, timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        for k in ("xp", "tier"):
            assert k in body, f"pass missing {k}"
