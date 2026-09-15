"""Backend tests for Galaxy Studio Universal Forge — iteration 97.

Validates:
- /catalog: family/category counts, total_variations huge string, new families non-zero
- /styles: new script/tattoo/mesh axes, basic_count, per-option tier, inscription block
- /generate with inscription text (script, tattoo, mesh axes + glyph decals)
- /generate with CUSTOM placement string
- /generate with EMPTY inscription text -> no inscription_text, no glyph parts
- /random x3 returns resolvable keys across tiers
- /search for mech/potion/runic/zzzz
- REGRESSION: /compose, /seed
"""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE = os.environ["EXPO_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_BACKEND_URL") else \
    "https://player-retention.preview.emergentagent.com"
API = f"{BASE}/api/galaxy-studio/forge"
TIMEOUT = 45


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------- /catalog ----------
class TestCatalog:
    def test_catalog_counts_and_families(self, s):
        r = s.get(f"{API}/catalog", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["family_count"] == 101, d["family_count"]
        assert d["base_category_count"] >= 2_000_000, d["base_category_count"]
        # ~1.2 billion forges (allow some slack)
        assert 1_100_000_000 <= d["category_count"] <= 1_300_000_000, d["category_count"]
        # total_variations must be a STRING and very large
        tv = d["total_variations"]
        assert isinstance(tv, str), type(tv)
        assert len(tv) > 50, f"too small: {tv}"
        # pretty: 1.07×10^110 format
        pretty = d["total_variations_pretty"]
        assert "×10^" in pretty or "x10^" in pretty, pretty
        assert "10^110" in pretty or "10^109" in pretty or "10^111" in pretty, pretty
        # families[].count must sum to category_count
        fams = d["families"]
        assert len(fams) == 101
        ssum = sum(f["count"] for f in fams)
        assert ssum == d["category_count"], (ssum, d["category_count"])

    def test_new_families_present_nonzero(self, s):
        r = s.get(f"{API}/catalog", timeout=TIMEOUT)
        d = r.json()
        by_key = {f["key"]: f for f in d["families"]}
        for need in ["mount", "demon", "spaceship", "potion", "tower"]:
            assert need in by_key, f"missing family {need}"
            assert by_key[need]["count"] > 0, f"family {need} count zero"


# ---------- /styles ----------
class TestStyles:
    def test_new_axes_present(self, s):
        r = s.get(f"{API}/styles", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        axes = d["axes"]
        by = {a["key"]: a for a in axes}
        # script axis
        assert "script" in by
        assert len(by["script"]["options"]) >= 24
        keys = {o["key"] for o in by["script"]["options"]}
        for n in ["runic", "latin", "babylonian", "egyptian"]:
            assert n in keys, f"script missing {n}"
        # tattoo axis
        assert "tattoo" in by
        assert len(by["tattoo"]["options"]) >= 20
        # mesh axis
        assert "mesh" in by
        assert len(by["mesh"]["options"]) >= 20

    def test_basic_count_and_tiers(self, s):
        d = s.get(f"{API}/styles", timeout=TIMEOUT).json()
        for a in d["axes"]:
            opts = a.get("options", [])
            bc = a.get("basic_count")
            assert bc is not None, f"axis {a['key']} missing basic_count"
            # basic_count must be <= 6 and equal min(6, total)
            assert bc == min(6, len(opts)), f"{a['key']} basic_count={bc} options={len(opts)}"
            for i, o in enumerate(opts):
                tier = o.get("tier")
                assert tier in ("basic", "advanced"), f"{a['key']} opt {o.get('key')} bad tier"
                expect = "basic" if i < bc else "advanced"
                assert tier == expect, f"{a['key']} opt {o.get('key')} tier mismatch"

    def test_inscription_block(self, s):
        d = s.get(f"{API}/styles", timeout=TIMEOUT).json()
        ins = d["inscription"]
        scripts = ins["scripts"]
        placements = ins["placements"]
        assert len(scripts) >= 24, len(scripts)
        place_keys = {p["key"] for p in placements}
        for need in ["auto", "blade", "handle", "body", "base", "wrap", "custom"]:
            assert need in place_keys, f"placement {need} missing"


# ---------- /generate with inscription ----------
class TestGenerateInscription:
    def test_generate_with_inscription_runic_blade(self, s):
        body = {
            "category": "iron.longsword",
            "era": "medieval",
            "use_llm": False,
            "axes": {"script": "runic", "tattoo": "tribal", "mesh": "low_poly"},
            "inscription": {"script": "runic", "text": "VALOR", "placement": "blade"},
        }
        r = s.post(f"{API}/generate", json=body, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        sa = d.get("style_axes") or {}
        assert sa.get("script") == "runic", sa
        assert sa.get("tattoo") == "tribal", sa
        assert sa.get("mesh") == "low_poly", sa
        # geometry is a flat list of parts; must include glyph decal parts
        geom = d.get("geometry") or []
        parts = geom if isinstance(geom, list) else (geom.get("parts") or [])
        glyph_parts = [p for p in parts if isinstance(p, dict) and p.get("glyph") is True]
        assert len(glyph_parts) > 0, f"no glyph parts present: {parts[:3]}"
        ins = d.get("inscription_text") or {}
        assert ins.get("text") == "VALOR", ins
        assert ins.get("script") == "runic", ins
        assert ins.get("placement") == "blade", ins
        assert "tint" in ins, ins

    def test_generate_custom_placement(self, s):
        body = {
            "category": "iron.longsword",
            "era": "medieval",
            "use_llm": False,
            "inscription": {"script": "latin", "text": "Memento",
                            "placement": "across the pommel"},
        }
        r = s.post(f"{API}/generate", json=body, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        ins = d.get("inscription_text") or {}
        assert ins.get("text") == "Memento", ins
        assert ins.get("placement") == "across the pommel", ins

    def test_generate_empty_inscription_no_glyphs(self, s):
        body = {
            "category": "iron.longsword",
            "era": "medieval",
            "use_llm": False,
            "inscription": {"script": "runic", "text": "", "placement": "auto"},
        }
        r = s.post(f"{API}/generate", json=body, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("inscription_text") in (None, {}, ""), d.get("inscription_text")
        geom = d.get("geometry") or []
        parts = geom if isinstance(geom, list) else (geom.get("parts") or [])
        glyph_parts = [p for p in parts if isinstance(p, dict) and p.get("glyph") is True]
        assert glyph_parts == [], f"unexpected glyph parts: {glyph_parts}"


# ---------- /random ----------
class TestRandom:
    def test_random_resolvable_3x(self, s):
        for i in range(3):
            r = s.get(f"{API}/random", params={"seed": 100 + i}, timeout=TIMEOUT)
            assert r.status_code == 200, r.text
            d = r.json()
            key = d.get("category") or d.get("key")
            assert key and isinstance(key, str), d
            # Tier 1 (noun) / Tier 2 (desc.noun) / Tier 3 (mod-desc.noun)
            # Must resolve via generate (use it as smoke test for _CAT_BY_KEY)
            gr = s.post(f"{API}/generate",
                        json={"category": key, "use_llm": False},
                        timeout=TIMEOUT)
            assert gr.status_code == 200, f"key={key} -> {gr.status_code} {gr.text[:200]}"


# ---------- /search ----------
class TestSearch:
    def test_search_mech(self, s):
        t = time.time()
        r = s.get(f"{API}/search", params={"q": "mech", "limit": 30}, timeout=TIMEOUT)
        dt = time.time() - t
        assert r.status_code == 200, r.text
        d = r.json()
        results = d.get("results") or d.get("hits") or d.get("items") or []
        assert len(results) > 0, d
        assert dt < 10, f"search too slow: {dt:.2f}s"

    def test_search_potion(self, s):
        r = s.get(f"{API}/search", params={"q": "potion", "limit": 30}, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        results = d.get("results") or d.get("hits") or d.get("items") or []
        assert len(results) > 0

    def test_search_runic(self, s):
        r = s.get(f"{API}/search", params={"q": "runic", "limit": 30}, timeout=TIMEOUT)
        assert r.status_code == 200
        # runic is a script/style — query may still return 0 or more; just no error
        d = r.json()
        assert isinstance(d.get("results") or d.get("hits") or d.get("items") or [], list)

    def test_search_zzzz_empty_fast(self, s):
        t = time.time()
        r = s.get(f"{API}/search", params={"q": "zzzz", "limit": 30}, timeout=TIMEOUT)
        dt = time.time() - t
        assert r.status_code == 200
        d = r.json()
        results = d.get("results") or d.get("hits") or d.get("items") or []
        assert len(results) == 0, results[:3]
        assert dt < 5, f"zzzz too slow: {dt:.2f}s"


# ---------- regression: /compose, /seed ----------
class TestRegression:
    def test_compose(self, s):
        body = {
            "build_id": "TEST_iter97_build",
            "era": "medieval",
            "items": [{"category": "iron.longsword"}, {"category": "mount"}],
            "seed": 7,
            "mount": False,
            "variants": 0,
        }
        r = s.post(f"{API}/compose", json=body, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        # Some shape returned
        assert isinstance(d, dict)
        items = d.get("items") or d.get("constructs") or d.get("results") or []
        assert isinstance(items, list)

    def test_seed(self, s):
        body = {"build_id": "TEST_iter97_seed", "era": "medieval",
                "genre": "rpg", "seed": 5, "mount": False}
        r = s.post(f"{API}/seed", json=body, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
