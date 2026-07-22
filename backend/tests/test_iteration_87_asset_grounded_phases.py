"""Iteration 87: Asset-grounded phases, combined worldforge, regression.

Tests the new asset-grounding behaviour:
- phase_gates needs forged assets before Assets band passes
- final_build assembles from COMBINED forged assets
- forge/compose still clamps to 300
- catalog still 550 categories / 30 families
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Asset-grounded 100-phase gates ──
class TestAssetGroundedPhases:
    BUILD = "e2e_qa"

    def test_seed_then_phase_gates_asset_grounded(self, api):
        sr = api.post(f"{BASE_URL}/api/galaxy-studio/forge/seed",
                      json={"build_id": self.BUILD, "era": "modern", "genre": "rpg",
                            "seed": 1, "mount": True}, timeout=120)
        assert sr.status_code == 200, sr.text
        sd = sr.json()
        assert sd.get("total", 0) > 0, f"seed total should be > 0, got {sd}"

        pr = api.post(f"{BASE_URL}/api/galaxy-studio/vault-gdd/phase-gates",
                      json={"build_id": self.BUILD, "genre": "rpg",
                            "era": "modern", "seed": 1, "persist": True},
                      timeout=180)
        assert pr.status_code == 200, pr.text
        pd = pr.json()
        assert pd.get("asset_grounded") is True, f"asset_grounded should be True, got {pd.get('asset_grounded')}"
        assert int(pd.get("forged_assets", 0)) > 0, f"forged_assets should be >0, got {pd.get('forged_assets')}"
        families = pd.get("forged_families", [])
        assert isinstance(families, list) and len(families) > 0, f"forged_families should be non-empty list, got {families}"
        # Assets band detail mentions 'forged assets grounded'
        bands = pd.get("bands") or []
        assets_band = next((b for b in bands if b.get("band", "").lower() == "assets"
                            or b.get("gate") == "capacity"), None)
        assert assets_band, f"Assets/capacity band not found in {[b.get('band') for b in bands]}"
        assert "forged assets grounded" in str(assets_band.get("detail", "")), \
            f"Assets band detail does not mention 'forged assets grounded': {assets_band}"


class TestFreshBuildPhaseGates:
    """A brand-new build_id; just verify the route does not 500 and fields are well-typed."""

    def test_fresh_build_phase_gates_no_500(self, api):
        bid = f"fresh_noassets_qa_{int(time.time())}"
        pr = api.post(f"{BASE_URL}/api/galaxy-studio/vault-gdd/phase-gates",
                      json={"build_id": bid, "genre": "rpg",
                            "era": "modern", "seed": 1, "persist": False},
                      timeout=180)
        assert pr.status_code == 200, pr.text
        pd = pr.json()
        assert isinstance(pd.get("asset_grounded"), bool), \
            f"asset_grounded must be bool, got {type(pd.get('asset_grounded'))}"
        assert isinstance(pd.get("forged_assets"), int), \
            f"forged_assets must be int, got {type(pd.get('forged_assets'))}"


# ── Worldforge assembled from COMBINED gamefiles ──
class TestWorldforgeCombined:
    BUILD = "e2e_qa"

    def test_final_build_world_from_combined_assets(self, api):
        # Run baseline final-build using same build (which now has forged assets).
        r = api.post(f"{BASE_URL}/api/galaxy-studio/final-build/package",
                     json={"build_id": self.BUILD, "genre": "rpg",
                           "era": "modern", "seed": 1, "persist": True},
                     timeout=300)
        assert r.status_code == 200, r.text
        d = r.json()
        playable = d.get("playable") or {}
        totals = d.get("totals") or {}
        assert int(playable.get("world_assets", 0)) > 0, f"world_assets must be > 0, got {playable}"
        assert int(totals.get("forged_assets", 0)) > 0, f"totals.forged_assets must be > 0, got {totals}"
        # entities should reflect the additional forged assets (heuristic: >0)
        assert int(playable.get("entities", 0)) > 0, f"entities must be > 0, got {playable}"


# ── Regressions ──
class TestForgeComposeClamp:
    def test_compose_clamps_total_to_300(self, api):
        r = api.post(f"{BASE_URL}/api/galaxy-studio/forge/compose",
                     json={"build_id": "clamp_qa2", "era": "modern",
                           "items": [{"category": "coin", "count": 200},
                                     {"category": "gem", "count": 200}]},
                     timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert int(d.get("total", 0)) <= 300, f"total should be clamped <=300, got {d.get('total')}"
        assert d.get("clamped") is True, f"clamped should be True, got {d.get('clamped')}"


class TestForgeCatalog:
    def test_catalog_counts(self, api):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/forge/catalog", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert int(d.get("category_count", 0)) == 550, f"category_count should be 550, got {d.get('category_count')}"
        assert int(d.get("family_count", 0)) == 30, f"family_count should be 30, got {d.get('family_count')}"


class TestConstructListIsolation:
    """constructs/list & materials/list still isolated from universal-family kinds."""

    def test_constructs_list_no_universal(self, api):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/constructs/list?limit=50", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for it in (d.get("items") or []):
            assert it.get("kind") == "construct", f"constructs/list returned non-construct kind: {it.get('kind')}"

    def test_materials_list_no_universal(self, api):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/materials/list?limit=50", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for it in (d.get("items") or []):
            assert it.get("kind") == "material", f"materials/list returned non-material kind: {it.get('kind')}"
