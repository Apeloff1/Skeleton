"""
Iteration 88 — Per-scene forging from FIRST scene + region-placed worldforge.

Validates Session 22 changes:
 - snowball_forge.escalate now forges a PER-SCENE universal batch inside the
   stage loop (starts at idx 0 = first scene 'world'); response includes
   universal_assets_per_scene > 0 and universal_scenes[] with 6 entries.
 - playable_game._asset_entities places forged assets into themed regions by
   family — final-build/package's playable.world_assets > 0.
 - vault-gdd/phase-gates verdict surfaces asset_grounded, forged_assets,
   forged_families.
 - Regression: forge/compose total clamp ≤ 300, forge/catalog 550/30,
   constructs/list & materials/list isolated from universal families.
"""
import os
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL") or "").rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── PER-SCENE FORGING (escalate from FIRST scene) ──
class TestPerSceneForging:
    BUILD = "scene_qa"

    def test_escalate_per_scene_universal_assets(self, api):
        r = api.post(f"{BASE_URL}/api/galaxy-studio/vault-gdd/escalate",
                     json={"build_id": self.BUILD, "genre": "rpg", "era": "modern",
                           "seed": 3, "platoon_size": 3, "persist": True},
                     timeout=120)
        assert r.status_code == 200, f"escalate failed: {r.status_code} {r.text[:300]}"
        data = r.json()
        # 6 scenes expected (world, narrative, mechanics, procedural, tileset, assets)
        scenes = data.get("universal_scenes") or []
        assert len(scenes) == 6, f"expected 6 universal_scenes, got {len(scenes)}: {scenes}"
        # Per-scene total > 0
        total = int(data.get("universal_assets_per_scene", 0))
        assert total > 0, f"universal_assets_per_scene must be > 0, got {total}"
        # FIRST scene must be 'world' AND have assets>0 and flora/terrain family
        first = scenes[0]
        assert first.get("stage") == "world", f"first stage must be 'world': {first}"
        assert int(first.get("assets", 0)) > 0, f"first scene assets must be > 0: {first}"
        fams_first = set(first.get("families") or [])
        assert fams_first & {"flora", "terrain", "world"}, \
            f"first scene must include flora/terrain/world family, got {fams_first}"

    def test_escalate_scenes_correlated_families(self, api):
        # Re-use already escalated build (snowball persists between calls)
        r = api.post(f"{BASE_URL}/api/galaxy-studio/vault-gdd/escalate",
                     json={"build_id": self.BUILD, "genre": "rpg", "era": "modern",
                           "seed": 3, "platoon_size": 3, "persist": True},
                     timeout=120)
        assert r.status_code == 200
        scenes = r.json().get("universal_scenes") or []
        assert len(scenes) == 6
        # Map stage → at least one expected family appears in returned families
        expected = {
            "narrative":  {"character", "npc", "banner", "book"},
            "mechanics":  {"weapon", "trap"},
            "procedural": {"creature", "mushroom", "gem"},
            "tileset":    {"door", "shrine"},
            "assets":     {"coin", "light", "container"},
        }
        by_stage = {s.get("stage"): set(s.get("families") or []) for s in scenes}
        for stg, expect_fams in expected.items():
            fams = by_stage.get(stg, set())
            assert fams & expect_fams, \
                f"stage '{stg}' families {fams} must intersect expected {expect_fams}"


# ── REGION-PLACED WORLDFORGE (single final build — memory guard) ──
class TestRegionWorldforge:
    def test_final_build_places_assets_into_regions(self, api):
        r = api.post(f"{BASE_URL}/api/galaxy-studio/final-build/package",
                     json={"build_id": "scene_qa", "genre": "rpg", "era": "modern",
                           "seed": 3, "persist": True},
                     timeout=180)
        assert r.status_code == 200, f"final-build failed: {r.status_code} {r.text[:300]}"
        data = r.json()
        playable = data.get("playable") or {}
        assert int(playable.get("world_assets", 0)) > 0, \
            f"playable.world_assets must be > 0, got {playable}"
        ents = playable.get("entities")
        # playable.entities is a summarised count (int) — capped at 300 in playable_game.py
        assert isinstance(ents, int) and ents > 0, f"playable.entities must be a positive count, got {ents!r}"


# ── GATES asset verdict ──
class TestGatesAssetVerdict:
    def test_phase_gates_asset_grounded(self, api):
        r = api.post(f"{BASE_URL}/api/galaxy-studio/vault-gdd/phase-gates",
                     json={"build_id": "scene_qa", "genre": "rpg", "era": "modern",
                           "seed": 1, "persist": True},
                     timeout=90)
        assert r.status_code == 200, f"phase-gates failed: {r.status_code} {r.text[:300]}"
        d = r.json()
        assert d.get("asset_grounded") is True, f"asset_grounded must be true, got {d.get('asset_grounded')}"
        assert int(d.get("forged_assets", 0)) > 0, f"forged_assets must be >0, got {d.get('forged_assets')}"
        fams = d.get("forged_families") or []
        assert isinstance(fams, list) and len(fams) > 0, f"forged_families non-empty required, got {fams}"


# ── REGRESSION ──
class TestRegression:
    def test_forge_compose_clamps_total_to_300(self, api):
        r = api.post(f"{BASE_URL}/api/galaxy-studio/forge/compose",
                     json={"build_id": "cl_qa", "era": "modern",
                           "items": [{"category": "coin", "count": 200},
                                     {"category": "gem", "count": 200}]},
                     timeout=60)
        assert r.status_code == 200, f"compose failed: {r.status_code} {r.text[:300]}"
        d = r.json()
        total = int(d.get("total", 0))
        assert total <= 300, f"total must be <=300, got {total}"
        assert d.get("clamped") is True, f"clamped must be true, got {d.get('clamped')}"

    def test_forge_catalog_550_30(self, api):
        r = api.get(f"{BASE_URL}/api/galaxy-studio/forge/catalog", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert int(d.get("category_count", 0)) == 550, f"category_count must be 550, got {d.get('category_count')}"
        assert int(d.get("family_count", 0)) == 30, f"family_count must be 30, got {d.get('family_count')}"

    def test_constructs_and_materials_isolated_from_universal_kinds(self, api):
        # constructs/list should have its OWN kinds, not universal-family kinds
        cr = api.get(f"{BASE_URL}/api/galaxy-studio/constructs/list?limit=20", timeout=30)
        assert cr.status_code == 200
        ck = {it.get("kind") for it in (cr.json().get("items") or []) if isinstance(it, dict)}
        # universal family kinds should NOT bleed into constructs
        forbidden_uni = {"coin", "gem", "flora", "mushroom", "shrine", "door"}
        assert not (ck & forbidden_uni), f"constructs/list leaked universal kinds: {ck & forbidden_uni}"

        mr = api.get(f"{BASE_URL}/api/galaxy-studio/materials/list?limit=20", timeout=30)
        assert mr.status_code == 200
        mk = {it.get("kind") for it in (mr.json().get("items") or []) if isinstance(it, dict)}
        assert not (mk & forbidden_uni), f"materials/list leaked universal kinds: {mk & forbidden_uni}"
