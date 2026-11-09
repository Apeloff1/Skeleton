"""Iteration 89 — Universal Forge skin styles, detail/intricacy/complexity,
deterministic accuracy, /forge/styles catalogue, non-persist escalate
universal_scenes, region map de-dupe, and regression checks."""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "http://localhost:8001").rstrip("/")
FORGE = f"{BASE_URL}/api/galaxy-studio/forge"
ESCALATE = f"{BASE_URL}/api/galaxy-studio/vault-gdd/escalate"
FINAL = f"{BASE_URL}/api/galaxy-studio/final-build/package"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── /forge/styles catalogue ────────────────────────────────────────────────
class TestStylesCatalog:
    def test_styles_returns_skins_detail_regions(self, s):
        r = s.get(f"{FORGE}/styles", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # skin_styles ≥ 12, must contain matte / chrome / neon / glowing
        keys = [x["key"] for x in d.get("skin_styles", [])]
        assert len(keys) >= 12, f"skin_styles count {len(keys)}"
        for must in ("matte", "chrome", "neon", "glowing"):
            assert must in keys, f"missing skin_style: {must}"
        # detail bands
        assert isinstance(d["complexity"], list) and len(d["complexity"]) >= 4
        assert isinstance(d["intricacy"], list) and len(d["intricacy"]) >= 3
        assert isinstance(d["detail_level"], list) and len(d["detail_level"]) >= 3
        # regions: ~27 families with [x,z] anchors
        regs = d["regions"]
        assert isinstance(regs, dict)
        assert 20 <= len(regs) <= 40, f"region count {len(regs)}"
        for v in regs.values():
            assert isinstance(v, list) and len(v) == 2


# ── Detail + skin + accuracy on generate ───────────────────────────────────
class TestGenerateDetailSkinAccuracy:
    def test_generate_chrome_ultra_baroque_sota_red_crystal(self, s):
        payload = {
            "category": "sword", "era": "modern", "use_llm": False,
            "skin_style": "chrome", "complexity": "ultra",
            "intricacy": "baroque", "detail_level": "sota", "seed": 7,
            "user_prompt": "a glowing red crystal blade",
        }
        r = s.post(f"{FORGE}/generate", json=payload, timeout=45)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("skin_style") == "chrome", d.get("skin_style")
        # chrome → metalness ≈ 1.0
        assert d["surface"]["metalness"] >= 0.95, d["surface"]
        # detail block present
        assert "detail" in d and isinstance(d["detail"], dict)
        assert d["detail"]["complexity"] == "ultra"
        assert d["detail"]["intricacy"] == "baroque"
        assert d["detail"]["detail_level"] == "sota"
        # accuracy: red hex injected (#c0392b)
        acc = d.get("accuracy_colors") or []
        assert any(c.lower() == "#c0392b" for c in acc), acc
        # palette also contains red-ish
        pal = [p.lower() for p in (d.get("palette") or [])]
        assert any("#c0392b" in p for p in pal), pal

        # baseline minimal: should have FEWER geometry parts
        minimal = s.post(f"{FORGE}/generate", json={
            "category": "sword", "era": "modern", "use_llm": False,
            "complexity": "minimal", "seed": 7,
        }, timeout=45).json()
        assert len(d["geometry"]) > len(minimal["geometry"]), \
            f"ultra parts {len(d['geometry'])} not > minimal {len(minimal['geometry'])}"

    def test_complexity_scaling_robot(self, s):
        mini = s.post(f"{FORGE}/generate", json={
            "category": "robot", "era": "modern", "use_llm": False,
            "complexity": "minimal", "seed": 11,
        }, timeout=45).json()
        ultra = s.post(f"{FORGE}/generate", json={
            "category": "robot", "era": "modern", "use_llm": False,
            "complexity": "ultra", "seed": 11,
        }, timeout=45).json()
        assert len(ultra["geometry"]) >= len(mini["geometry"]), \
            f"ultra {len(ultra['geometry'])} < minimal {len(mini['geometry'])}"


# ── Non-persist escalate exposes universal_scenes (planned) ────────────────
class TestNonPersistEscalate:
    def test_non_persist_universal_scenes_planned(self, s):
        r = s.post(ESCALATE, json={
            "build_id": "np_qa", "genre": "rpg", "era": "modern",
            "seed": 2, "platoon_size": 2, "persist": False,
        }, timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        uni = d.get("universal_scenes") or []
        assert len(uni) == 6, f"expected 6 scenes, got {len(uni)}: {uni}"
        for sc in uni:
            assert sc.get("planned") is True, sc
            assert isinstance(sc.get("families"), list) and sc["families"], sc
        # first scene = world, contains flora/terrain
        first = uni[0]
        assert first.get("stage") == "world", first
        fams = set(first["families"])
        assert ({"flora", "terrain"} & fams), f"world families missing flora/terrain: {fams}"

    def test_persist_escalate_still_works(self, s):
        r = s.post(ESCALATE, json={
            "build_id": "p_qa89", "genre": "rpg", "era": "modern",
            "seed": 2, "platoon_size": 2, "persist": True,
        }, timeout=180)
        assert r.status_code == 200, r.text
        d = r.json()
        uni = d.get("universal_scenes") or []
        assert len(uni) == 6, uni
        for sc in uni:
            assert sc.get("planned") is False, sc
            assert sc.get("assets", 0) > 0, sc


# ── Regression: catalog counts, compose clamp, final-build region world ────
class TestRegression:
    def test_catalog_counts(self, s):
        r = s.get(f"{FORGE}/catalog", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["category_count"] == 550, d["category_count"]
        assert d["family_count"] == 30, d["family_count"]

    def test_compose_clamp(self, s):
        r = s.post(f"{FORGE}/compose", json={
            "build_id": "cl3", "era": "modern",
            "items": [{"category": "coin", "count": 200},
                      {"category": "gem", "count": 200}],
        }, timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("clamped") is True, d
        assert d.get("total", 0) <= 300, d

    def test_final_build_region_world(self, s):
        # ONE final build only (memory guard) — use unique id
        r = s.post(FINAL, json={
            "build_id": "np_qa89final", "genre": "rpg", "era": "modern",
            "seed": 2, "persist": True,
        }, timeout=240)
        assert r.status_code == 200, r.text
        d = r.json()
        play = d.get("playable") or {}
        assert play.get("world_assets", 0) > 0, play
