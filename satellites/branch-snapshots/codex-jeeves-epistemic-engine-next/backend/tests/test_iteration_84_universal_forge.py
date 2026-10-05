"""
Iteration 84 — Universal Forge backend regression.

Covers:
  - GET /api/galaxy-studio/forge/catalog (~215 categories, 11 families)
  - GET /api/galaxy-studio/forge/presets (category=tree&era=modern → total 36, family flora)
  - POST /api/galaxy-studio/forge/generate across all 11 families (no 500s, geometry present)
  - POST /api/galaxy-studio/forge/generate with use_llm=true (must not 500 — deterministic
    spec is acceptable if LLM call fails)
  - Vault CRUD: save → list → mount → get → put → delete
  - GET /api/galaxy-studio/forge/capacity
  - Regression: constructs/list, materials/list, constructs/presets, constructs/snowball/forge
    still work AND universal-forge assets do not pollute construct/material lists.
"""
from __future__ import annotations

import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "http://localhost:8001").rstrip("/")

FORGE = f"{BASE_URL}/api/galaxy-studio/forge"
GS = f"{BASE_URL}/api/galaxy-studio"

# 12 representative categories the review request asks for, mapped to expected family.
REPRESENTATIVE = [
    ("character", "character"),
    ("npc", "character"),
    ("clothing", "wearable"),
    ("critter", "creature"),
    ("vehicle", "vehicle"),
    ("weapons", "prop"),
    ("tree", "flora"),
    ("planet", "world"),
    ("fire", "fx"),
    ("sound", "sound"),
    ("stone", "surface"),
    ("city", "structure"),
]


@pytest.fixture(scope="session")
def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── catalog ────────────────────────────────────────────────────────────────
class TestCatalog:
    def test_catalog_shape(self, session):
        r = session.get(f"{FORGE}/catalog", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["category_count"] >= 190, d["category_count"]
        assert d["family_count"] == 11
        assert isinstance(d["families"], list) and len(d["families"]) == 11
        assert isinstance(d["groups"], list) and len(d["groups"]) >= 4
        assert isinstance(d["categories"], list) and len(d["categories"]) == d["category_count"]
        # family count consistency
        fam_total = sum(f["count"] for f in d["families"])
        assert fam_total == d["category_count"]


# ── presets ────────────────────────────────────────────────────────────────
class TestPresets:
    def test_presets_tree_modern(self, session):
        r = session.get(f"{FORGE}/presets",
                        params={"category": "tree", "era": "modern"}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == 36, d["total"]
        assert d["family"] == "flora"
        assert d["era"] == "modern"
        first = d["presets"][0]
        assert isinstance(first.get("geometry"), list) and len(first["geometry"]) > 0
        assert first.get("preset_id", "").startswith("uni_")


# ── generate across families ───────────────────────────────────────────────
class TestGenerateFamilies:
    @pytest.mark.parametrize("category,expected_family", REPRESENTATIVE)
    def test_generate_no_llm(self, session, category, expected_family):
        body = {"category": category, "era": "modern", "use_llm": False}
        r = session.post(f"{FORGE}/generate", json=body, timeout=20)
        assert r.status_code == 200, f"{category} → {r.status_code} {r.text}"
        spec = r.json()
        assert spec.get("family") == expected_family, (category, spec.get("family"))
        assert spec.get("category") == category
        assert isinstance(spec.get("geometry"), list) and len(spec["geometry"]) > 0, \
            f"{category} returned empty geometry"
        assert spec.get("llm_enriched") is False


# ── one LLM-enriched call ──────────────────────────────────────────────────
class TestGenerateLLM:
    def test_generate_with_llm(self, session):
        body = {
            "category": "tree",
            "era": "modern",
            "use_llm": True,
            "user_prompt": "a glowing crystal willow",
        }
        # LLM can take 10-30s; deterministic fallback is acceptable.
        r = session.post(f"{FORGE}/generate", json=body, timeout=60)
        assert r.status_code == 200, r.text
        spec = r.json()
        assert spec.get("family") == "flora"
        assert isinstance(spec.get("geometry"), list) and len(spec["geometry"]) > 0
        # Either enriched or fell back deterministically — both are PASS.
        assert "llm_enriched" in spec


# ── Vault CRUD ─────────────────────────────────────────────────────────────
class TestVaultCRUD:
    def test_save_list_mount_get_put_delete(self, session):
        # 1) generate a spec
        g = session.post(f"{FORGE}/generate",
                         json={"category": "tree", "era": "modern", "use_llm": False},
                         timeout=20)
        assert g.status_code == 200, g.text
        spec = g.json()

        # 2) save
        s = session.post(f"{FORGE}/save", json={"spec": spec}, timeout=20)
        assert s.status_code == 200, s.text
        construct_id = s.json().get("construct_id")
        assert construct_id, s.json()

        try:
            # 3) list?category=tree must include this id
            lst = session.get(f"{FORGE}/list", params={"category": "tree"}, timeout=20)
            assert lst.status_code == 200, lst.text
            items = lst.json().get("items", [])
            assert any(it.get("construct_id") == construct_id for it in items), \
                "saved construct not in /forge/list?category=tree"

            # 4) mount
            m = session.post(f"{FORGE}/mount",
                             json={"construct_ids": [construct_id], "build_id": "uni_test"},
                             timeout=20)
            assert m.status_code == 200, m.text
            assert m.json().get("mounted") == 1

            # 5) get item
            one = session.get(f"{FORGE}/item/{construct_id}", timeout=20)
            assert one.status_code == 200, one.text
            assert one.json().get("construct_id") == construct_id

            # 6) update name
            up = session.put(f"{FORGE}/item/{construct_id}",
                             json={"patch": {"name": "TEST_RenamedX"}}, timeout=20)
            assert up.status_code == 200, up.text
            assert up.json().get("name") == "TEST_RenamedX"

            # confirm persisted via GET
            verify = session.get(f"{FORGE}/item/{construct_id}", timeout=20)
            assert verify.status_code == 200
            assert verify.json().get("name") == "TEST_RenamedX"
        finally:
            # 7) delete
            d = session.delete(f"{FORGE}/item/{construct_id}", timeout=20)
            assert d.status_code == 200, d.text
            assert d.json().get("deleted") is True

        # 8) confirm 404 after delete
        gone = session.get(f"{FORGE}/item/{construct_id}", timeout=20)
        assert gone.status_code == 404


# ── capacity ───────────────────────────────────────────────────────────────
class TestCapacity:
    def test_capacity_shape(self, session):
        r = session.get(f"{FORGE}/capacity", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("capacity") == 100000
        assert "forge" in d and isinstance(d["forge"], int)
        assert isinstance(d.get("by_family"), dict)
        # the 11 families must all be present (count >= 0)
        for fam in ["structure", "surface", "world", "flora", "creature", "fx",
                    "character", "wearable", "vehicle", "prop", "sound"]:
            assert fam in d["by_family"], f"missing family {fam}"


# ── Regression vs construct / material forges ──────────────────────────────
class TestRegression:
    def test_constructs_list_ok(self, session):
        r = session.get(f"{GS}/constructs/list", timeout=20)
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        # Universal forge assets (families like flora/world/sound/fx/etc.) must NOT
        # leak into the construct list. Construct list is for construct-kind only.
        leak_kinds = {"flora", "world", "sound", "fx", "character",
                      "wearable", "vehicle", "prop", "creature", "surface"}
        leaked = [it for it in items if it.get("kind") in leak_kinds]
        assert not leaked, f"universal assets leaked into constructs/list: {leaked[:3]}"

    def test_materials_list_ok(self, session):
        r = session.get(f"{GS}/materials/list", timeout=20)
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        # Materials list must be material-kind only — no universal-family leakage.
        leak_kinds = {"flora", "world", "sound", "fx", "character",
                      "wearable", "vehicle", "prop", "creature", "structure"}
        leaked = [it for it in items if it.get("kind") in leak_kinds]
        assert not leaked, f"universal assets leaked into materials/list: {leaked[:3]}"

    def test_constructs_presets_8bit_per_era(self, session):
        r = session.get(f"{GS}/constructs/presets",
                        params={"era": "8bit"}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        per_era = d.get("per_era") or d.get("total") or 0
        assert per_era >= 300, f"constructs/presets per_era={per_era}, expected >=300"

    def test_constructs_snowball_forge_still_mounts(self, session):
        # Mirror prior contract — must still 200 and report mounted.
        r = session.post(f"{GS}/constructs/snowball/forge",
                         json={"build_id": f"uni_reg_{int(time.time())}",
                               "era": "modern"},
                         timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        # snowball/forge should at minimum mount something
        mounted = body.get("mounted") or body.get("mounted_count") \
            or len(body.get("construct_ids") or [])
        assert mounted and int(mounted) >= 1, body


# ── Universal save MUST NOT pollute construct/material lists (full loop) ───
class TestNoPollution:
    def test_save_universal_does_not_leak(self, session):
        # generate + save a flora asset
        g = session.post(f"{FORGE}/generate",
                         json={"category": "tree", "era": "modern", "use_llm": False},
                         timeout=20)
        assert g.status_code == 200
        spec = g.json()
        s = session.post(f"{FORGE}/save", json={"spec": spec}, timeout=20)
        assert s.status_code == 200
        cid = s.json().get("construct_id")
        try:
            # constructs/list must not contain it
            c = session.get(f"{GS}/constructs/list", timeout=20).json().get("items", [])
            assert not any(it.get("construct_id") == cid for it in c), \
                "universal flora leaked into constructs/list"
            # materials/list must not contain it
            m = session.get(f"{GS}/materials/list", timeout=20).json().get("items", [])
            assert not any(it.get("construct_id") == cid for it in m), \
                "universal flora leaked into materials/list"
            # but forge/list must contain it
            f = session.get(f"{FORGE}/list", params={"category": "tree"},
                            timeout=20).json().get("items", [])
            assert any(it.get("construct_id") == cid for it in f)
        finally:
            session.delete(f"{FORGE}/item/{cid}", timeout=20)
