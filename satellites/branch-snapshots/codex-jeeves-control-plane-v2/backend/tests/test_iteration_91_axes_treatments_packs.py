"""Iteration 91 — Universal Forge axes + region treatments + style packs + 1000+ catalog.

Validates:
- /forge/catalog category_count >= 1000
- /forge/styles new axes, treatments, style_packs payloads
- /forge/generate applies axes, treatment + decals
- /forge/compose returns by_region with treatments/accents
- regression: plain compose works
"""
from __future__ import annotations

import os

import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "https://player-retention.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api/galaxy-studio/forge"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Catalog: 1000+ categories ────────────────────────────────────────────
class TestCatalog:
    def test_catalog_count_1000_plus(self, client):
        r = client.get(f"{API}/catalog", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("category_count", 0) >= 1000, f"only {d.get('category_count')} categories"
        assert isinstance(d.get("categories"), list)
        assert isinstance(d.get("families"), list)


# ── Styles: skin_styles, axes (5), treatments (6), style_packs (8) ───────
class TestStyles:
    @pytest.fixture(scope="class")
    def styles(self, client):
        r = client.get(f"{API}/styles", timeout=20)
        assert r.status_code == 200, r.text
        return r.json()

    def test_skin_styles_have_surface(self, styles):
        skins = styles.get("skin_styles") or []
        assert len(skins) >= 8
        for s in skins:
            assert "key" in s and "label" in s and "surface" in s

    def test_axes_five_axes_with_options(self, styles):
        axes = styles.get("axes") or []
        keys = {a["key"] for a in axes}
        assert {"art_style", "period", "realism", "fantasy", "punk"}.issubset(keys), keys
        for a in axes:
            opts = a.get("options") or []
            assert len(opts) >= 3, f"{a['key']} has only {len(opts)} options"
            for o in opts:
                assert "key" in o and "label" in o
                assert "tint" in o  # may be None

    def test_treatments_six_entries(self, styles):
        treats = styles.get("treatments") or []
        keys = {t["key"] for t in treats}
        expected = {"none", "markings", "etchings", "symbols", "signatures", "prints"}
        assert expected.issubset(keys), keys

    def test_style_packs_eight(self, styles):
        packs = styles.get("style_packs") or []
        assert len(packs) == 8, f"got {len(packs)}"
        # spot-check dark_cyber_ruins
        d = next((p for p in packs if p["key"] == "dark_cyber_ruins"), None)
        assert d is not None
        assert d.get("skin_style") and d.get("axes") and d.get("treatment")


# ── Generate: axes + treatment + decal geometry ───────────────────────────
class TestGenerate:
    def test_generate_with_axes_and_treatment(self, client):
        payload = {
            "category": "sword",
            "use_llm": False,
            "axes": {"punk": "cyberpunk", "fantasy": "mythic"},
            "treatment": "symbols",
            "region": "weapon",
            "seed": 42,
        }
        r = client.post(f"{API}/generate", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        spec = d.get("spec") or d  # endpoint may return spec directly or wrapped
        # axes applied
        sa = spec.get("style_axes") or {}
        assert sa.get("punk") == "cyberpunk", f"style_axes={sa}"
        assert sa.get("fantasy") == "mythic", f"style_axes={sa}"
        # treatment applied
        assert spec.get("treatment") == "symbols"
        assert spec.get("treatment_accent"), "missing treatment_accent"
        # decal geometry parts present
        geo = spec.get("geometry") or []
        decals = [p for p in geo if p.get("decal")]
        assert len(decals) >= 1, "no decal parts found"
        # detail mirror
        det = spec.get("detail") or {}
        assert det.get("style_axes", {}).get("punk") == "cyberpunk"
        assert det.get("treatment") == "symbols"


# ── Compose: by_region with style + variants ──────────────────────────────
class TestCompose:
    def test_compose_with_style_and_variants(self, client):
        payload = {
            "build_id": "TEST_iter91_build",
            "items": [
                {"category": "sword", "region": "weapon"},
                {"category": "oak_tree", "region": "flora"},
            ],
            "seed": 7,
            "mount": False,
            "style": {"skin_style": "neon", "axes": {"punk": "cyberpunk"}, "treatment": "symbols"},
            "variants": 1,
        }
        r = client.post(f"{API}/compose", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        by_region = d.get("by_region")
        assert isinstance(by_region, list) and len(by_region) >= 1, d
        first = by_region[0]
        for k in ("family", "primary", "variants", "treatment", "accent"):
            assert k in first, f"missing {k} in by_region entry: {first}"
        total = d.get("total")
        # total should equal sum(primary + variants) across regions
        if total is not None:
            expected = sum((br.get("primary", 0) + br.get("variants", 0)) for br in by_region)
            assert total == expected, f"total {total} != expected {expected}"

    def test_compose_plain_no_style_regression(self, client):
        """Regression: compose with no style still works."""
        payload = {
            "build_id": "TEST_iter91_plain",
            "items": [{"category": "oak_tree", "region": "flora"}],
            "seed": 1,
            "mount": False,
        }
        r = client.post(f"{API}/compose", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # should still have results
        assert d.get("by_region") is not None or d.get("constructs") is not None, d


# ── Regression: plain generate (no axes/treatment) still works ───────────
class TestRegression:
    def test_generate_plain_skin_style(self, client):
        payload = {"category": "sword", "use_llm": False, "skin_style": "metallic", "seed": 1}
        r = client.post(f"{API}/generate", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        spec = d.get("spec") or d
        assert spec.get("skin_style") == "metallic"
        assert spec.get("geometry")
