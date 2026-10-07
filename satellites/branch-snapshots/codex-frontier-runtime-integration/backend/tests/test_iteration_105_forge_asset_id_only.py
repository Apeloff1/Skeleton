"""Iteration 105 — Targeted ID-only forge asset endpoint + regressions.

Covers (a) /asset light vs full (geometry strip), (b) part_count/thumb_palette,
(c) determinism across calls with same id+era+seed, (d) unknown-id graceful
fallback, and regression checks on /catalog /random /styles."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://player-retention.preview.emergentagent.com").rstrip("/")
FORGE = f"{BASE_URL}/api/galaxy-studio/forge"


@pytest.fixture
def s():
    sess = requests.Session()
    sess.headers.update({"Accept": "application/json"})
    return sess


# ── New endpoint: /asset (ID-only architecture) ─────────────────────────
class TestAssetEndpoint:
    def test_light_default_strips_geometry(self, s):
        r = s.get(f"{FORGE}/asset", params={"id": "tree", "era": "modern", "seed": 42}, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "geometry" not in body, "light mode must NOT include geometry"
        assert body.get("light") is True
        assert isinstance(body.get("part_count"), int) and body["part_count"] >= 0
        tp = body.get("thumb_palette")
        assert isinstance(tp, list) and len(tp) <= 5

    def test_full_includes_geometry(self, s):
        r = s.get(f"{FORGE}/asset", params={"id": "tree", "era": "modern", "seed": 42, "full": 1}, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "geometry" in body, "full=1 must include geometry"
        assert isinstance(body["geometry"], list)

    def test_full_matches_light_part_count(self, s):
        light = s.get(f"{FORGE}/asset", params={"id": "tree", "era": "modern", "seed": 42}, timeout=20).json()
        full  = s.get(f"{FORGE}/asset", params={"id": "tree", "era": "modern", "seed": 42, "full": 1}, timeout=20).json()
        assert light["part_count"] == len(full.get("geometry") or [])

    @pytest.mark.parametrize("aid", ["tree", "sword", "house"])
    def test_determinism_same_seed(self, s, aid):
        a = s.get(f"{FORGE}/asset", params={"id": aid, "era": "modern", "seed": 42}, timeout=20).json()
        b = s.get(f"{FORGE}/asset", params={"id": aid, "era": "modern", "seed": 42}, timeout=20).json()
        assert a.get("part_count") == b.get("part_count"), f"part_count not deterministic for {aid}"
        assert a.get("thumb_palette") == b.get("thumb_palette"), f"palette not deterministic for {aid}"

    def test_unknown_id_graceful(self, s):
        r = s.get(f"{FORGE}/asset", params={"id": "TEST_no_such_asset_xyz_999"}, timeout=20)
        # Should be 200 with fallback, not 500
        assert r.status_code == 200, f"unknown id should NOT 500: got {r.status_code} {r.text[:200]}"
        body = r.json()
        assert body.get("light") is True
        assert "part_count" in body


# ── Regression: existing forge endpoints still functional ───────────────
class TestForgeRegression:
    def test_catalog(self, s):
        r = s.get(f"{FORGE}/catalog", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        # catalog should have families/categories
        assert isinstance(body, dict)
        assert any(k in body for k in ("families", "categories", "groups", "count")), f"unexpected catalog shape: {list(body)[:8]}"

    def test_random(self, s):
        r = s.get(f"{FORGE}/random", params={"seed": 7}, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        # should produce a category at minimum
        assert isinstance(body, dict)
        assert body.get("category") or body.get("id") or body.get("category_label"), \
            f"random must surface a category: keys={list(body)[:10]}"

    def test_styles(self, s):
        r = s.get(f"{FORGE}/styles", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, dict)
        # styles catalog typically exposes skin styles + bands
        assert len(body) > 0
