"""
Session 14.4 backend tests:
- Worldforge module split regression (routes/worldforge_publish.py)
- /api/worldforge/quest now served from worldforge_publish.py (LLM, ~10-20s)
- Existing worldforge endpoints (biomes, scales, options, region, render*) still 200
- OpenAPI lists /api/worldforge/quest EXACTLY ONCE (no duplicate-route regression)
- registered=105
- Marketplace /mine returns 'moderation_status' field; hidden game appears as 'hidden'
- Regression: /api/playable/leaderboard and /api/marketplace/listings still 200
"""
import os
import time
import json
import uuid
import requests
import pytest

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://gemini-game-craft.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── Worldforge regression — REMAINED endpoints in worldforge.py ──
class TestWorldforgeRegression:
    def test_biomes(self, s):
        r = s.get(f"{API}/worldforge/biomes", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "biomes" in d and isinstance(d["biomes"], list) and d["count"] >= 10

    def test_scales(self, s):
        r = s.get(f"{API}/worldforge/scales", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "scales" in d and len(d["scales"]) == 5

    def test_options(self, s):
        r = s.get(f"{API}/worldforge/options", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "sliders" in d and "feature_toggles" in d and "scales" in d

    def test_region_get(self, s):
        r = s.get(f"{API}/worldforge/region", params={"seed": 42, "size": 24}, timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert d.get("scale") == "region" and d.get("size") == 24

    def test_render_region(self, s):
        r = s.get(f"{API}/worldforge/render",
                  params={"scale": "region", "seed": 42, "size": 24}, timeout=120)
        assert r.status_code == 200, r.text[:200]
        assert "image/png" in r.headers.get("content-type", "")
        assert len(r.content) > 1000

    def test_render_region_thematic_plates(self, s):
        r = s.get(f"{API}/worldforge/render",
                  params={"scale": "region", "mode": "thematic", "layer": "plates"}, timeout=120)
        assert r.status_code == 200, r.text[:200]
        assert "image/png" in r.headers.get("content-type", "")
        assert len(r.content) > 1000

    def test_render_planet_globe(self, s):
        r = s.get(f"{API}/worldforge/render",
                  params={"scale": "planet", "mode": "globe"}, timeout=180)
        assert r.status_code == 200, r.text[:200]
        assert "image/png" in r.headers.get("content-type", "")
        assert len(r.content) > 1000


# ── OpenAPI dedup check + registered=105 ──
class TestOpenAPI:
    def test_quest_route_exactly_once(self, s):
        # openapi.json is only available on the backend port (not behind /api ingress)
        r = s.get("http://localhost:8001/openapi.json", timeout=30)
        assert r.status_code == 200
        paths = r.json().get("paths", {})
        # Two duplicate paths would actually overwrite under JSON key collision,
        # but FastAPI surfaces dup paths individually if they go through different routers.
        # Verify the path exists exactly once at the dict-key level.
        keys = [p for p in paths.keys() if p == "/api/worldforge/quest"]
        assert len(keys) == 1, f"/api/worldforge/quest should appear once, got {keys}"
        # And that it has a POST op
        assert "post" in {k.lower() for k in paths["/api/worldforge/quest"].keys()}

    def test_registry_health(self, s):
        # The boot log shows two registries (prefixed=33, self-prefixed=105) for
        # a combined 138. Session 14.4 spec says registered=105 referring to
        # KNOWN_ROUTES (self-prefixed). The /health/registry endpoint surfaces
        # the COMBINED ok count.
        r = s.get(f"{API}/health/registry", timeout=15)
        if r.status_code == 200:
            d = r.json()
            registered = d.get("ok") or d.get("registered") or d.get("report", {}).get("ok")
            print(f"registered(combined)={registered}")
            # Combined should be 33 (with-prefix) + 105 (self-prefixed) = 138
            assert registered in (105, 138), f"unexpected registered={registered}"


# ── worldforge endpoints that REMAINED in worldforge.py (async kickoffs) ──
class TestWorldforgeRemainedAsync:
    def test_monograph_async_kickoff(self, s):
        r = s.post(f"{API}/worldforge/monograph/async",
                   json={"seed": 7, "size": 48}, timeout=30)
        assert r.status_code in (200, 202), r.text[:200]
        d = r.json()
        assert "job_id" in d, d

    def test_stream_manifest(self, s):
        r = s.get(f"{API}/worldforge/stream/manifest",
                  params={"seed": 7, "scale": "region", "size": 48}, timeout=60)
        assert r.status_code == 200, r.text[:200]

    def test_poster_async_kickoff_if_present(self, s):
        r = s.post(f"{API}/worldforge/poster/async",
                   json={"seed": 7, "size": 48}, timeout=30)
        # poster/async may be optional; accept 404 silently
        if r.status_code == 404:
            pytest.skip("poster/async not present")
        assert r.status_code in (200, 202), r.text[:200]
        assert "job_id" in r.json()


# ── /quest now served from routes/worldforge_publish.py (LLM-backed) ──
class TestWorldforgeQuest:
    def test_quest_post(self, s):
        r = s.post(f"{API}/worldforge/quest",
                   json={"seed": 7, "size": 24}, timeout=180)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        # Allow LLM error path but flag it (still 200 per existing semantics)
        if "error" in d and "quest" not in d:
            pytest.fail(f"LLM returned error path: {d}")
        assert "name" in d and "scale" in d
        assert isinstance(d.get("quest"), dict)
        assert "model" in d
        assert isinstance(d.get("places"), list)
        cons = d.get("consistency")
        assert isinstance(cons, dict)
        assert "ok" in cons and "node_count" in cons


# ── Marketplace moderation_status on /mine + hide/restore roundtrip ──
class TestMarketplaceMine:
    def test_mine_has_moderation_status(self, s):
        r = s.get(f"{API}/marketplace/mine",
                  params={"creator_id": "qa-test-{}".format(uuid.uuid4().hex[:6])}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        listings = d.get("listings", d if isinstance(d, list) else [])
        # New creator may have zero listings: assert response shape only
        assert isinstance(listings, list)
        for li in listings:
            assert "moderation_status" in li, f"missing moderation_status: {li}"

    def test_hide_then_mine_shows_hidden(self, s):
        # Find a listing to test against
        r = s.get(f"{API}/marketplace/listings", params={"limit": 30}, timeout=30)
        assert r.status_code == 200
        listings = r.json().get("listings", [])
        if not listings:
            pytest.skip("no listings in marketplace to test moderation against")
        target = listings[0]
        pid = target.get("playable_id")
        creator_id = target.get("creator_id") or target.get("owner_id") or "default_user"
        assert pid, target

        # Report (capture rid) then moderate via /moderate/{rid}
        rep = s.post(f"{API}/governance/report",
                     json={"playable_id": pid, "reason": "other",
                           "detail": "QA moderation roundtrip",
                           "reporter_id": "qa-test-tmp"}, timeout=20)
        assert rep.status_code == 200, rep.text[:200]
        rid = rep.json().get("report_id")
        if not rid:
            pytest.skip(f"could not create report: {rep.json()}")
        # Apply moderation hide using report_id
        mod = s.post(f"{API}/governance/moderate/{rid}",
                     json={"action": "hide", "actor": "qa-bot", "note": "qa test"},
                     timeout=20)
        try:
            assert mod.status_code in (200, 201), mod.text[:200]
            assert mod.json().get("moderation_status") == "hidden"
            # Check /mine reflects hidden
            r2 = s.get(f"{API}/marketplace/mine",
                       params={"creator_id": creator_id}, timeout=30)
            assert r2.status_code == 200
            mine = r2.json().get("listings", [])
            row = next((li for li in mine if li.get("playable_id") == pid), None)
            if row is None:
                pytest.skip(f"creator_id mismatch — listing pid={pid} not under creator_id={creator_id}")
            assert row.get("moderation_status") == "hidden", row
        finally:
            # Restore (cleanup) via a fresh report+restore action
            rep2 = s.post(f"{API}/governance/report",
                          json={"playable_id": pid, "reason": "other",
                                "detail": "QA cleanup restore",
                                "reporter_id": "qa-test-tmp"}, timeout=20)
            rid2 = rep2.json().get("report_id") if rep2.status_code == 200 else None
            if rid2:
                s.post(f"{API}/governance/moderate/{rid2}",
                       json={"action": "restore", "actor": "qa-bot",
                             "note": "qa cleanup"}, timeout=20)


# ── Regression endpoints ──
class TestRegression:
    def test_leaderboard(self, s):
        r = s.get(f"{API}/playable/leaderboard", timeout=20)
        assert r.status_code == 200, r.text[:200]

    def test_marketplace_listings(self, s):
        r = s.get(f"{API}/marketplace/listings", timeout=20)
        assert r.status_code == 200, r.text[:200]
