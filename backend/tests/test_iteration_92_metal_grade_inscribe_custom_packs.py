"""Iteration 92 — Universal Forge: metal_grade axis, inscription, 10k+ catalog,
server-side search, custom style packs CRUD, by_region compose.

Validates:
- /forge/catalog category_count >= 10000 and browse_count present
- /forge/search returns procedural variant results
- /forge/styles axes include 'metal_grade' with rusty..legendary options
- /forge/generate with axes.metal_grade=legendary and inscribe color
  returns spec.style_axes.metal_grade, spec.inscription, geometry inscription=True
- Custom Style Packs CRUD: POST -> appears in /styles with custom=True -> DELETE removes
- /forge/compose still returns by_region breakdown
"""
from __future__ import annotations

import os

import pytest
import requests

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or "https://player-retention.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api/galaxy-studio/forge"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Catalog: 10000+ categories ───────────────────────────────────────────
class TestCatalog:
    def test_catalog_10k_plus(self, client):
        r = client.get(f"{API}/catalog", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        cc = d.get("category_count", 0)
        bc = d.get("browse_count", 0)
        assert cc >= 10000, f"category_count={cc} < 10000"
        assert bc > 0, f"browse_count={bc}"
        assert isinstance(d.get("categories"), list)
        assert isinstance(d.get("families"), list)


# ── Search: server-side over full procedural library ────────────────────
class TestSearch:
    def test_search_runed_sword(self, client):
        r = client.get(f"{API}/search", params={"q": "runed sword", "limit": 5}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        results = d.get("results") or d.get("items") or []
        assert len(results) >= 1, f"no results: {d}"
        # at least one result is a procedural variant (key contains 'runed')
        assert any("runed" in (it.get("key") or "") for it in results), results

    def test_search_gilded(self, client):
        r = client.get(f"{API}/search", params={"q": "gilded", "limit": 10}, timeout=20)
        assert r.status_code == 200, r.text
        results = (r.json().get("results") or [])
        assert len(results) >= 1
        assert any("gilded" in (it.get("key") or "").lower() for it in results)


# ── Styles: metal_grade axis + treatments + style_packs ────────────────
class TestStyles:
    @pytest.fixture(scope="class")
    def styles(self, client):
        r = client.get(f"{API}/styles", timeout=20)
        assert r.status_code == 200, r.text
        return r.json()

    def test_metal_grade_axis(self, styles):
        axes = styles.get("axes") or []
        mg = next((a for a in axes if a.get("key") == "metal_grade"), None)
        assert mg is not None, "metal_grade axis missing"
        opt_keys = {o["key"] for o in (mg.get("options") or [])}
        # spec requires rusty..legendary range — verify both endpoints present
        assert "rusty" in opt_keys, opt_keys
        assert "legendary" in opt_keys, opt_keys
        assert len(opt_keys) >= 5, f"only {len(opt_keys)} options"

    def test_treatments_present(self, styles):
        treats = {t["key"] for t in (styles.get("treatments") or [])}
        assert {"none", "markings", "symbols"}.issubset(treats), treats

    def test_style_packs_eight_builtin(self, styles):
        packs = styles.get("style_packs") or []
        builtin = [p for p in packs if not p.get("custom")]
        assert len(builtin) >= 8, f"only {len(builtin)} built-in packs"


# ── Generate: metal_grade + inscribe ────────────────────────────────────
class TestGenerateMetalGradeInscribe:
    def test_legendary_with_red_inscription(self, client):
        payload = {
            "category": "sword",
            "use_llm": False,
            "axes": {"metal_grade": "legendary"},
            "inscribe": "#ff0000",
            "seed": 42,
        }
        r = client.post(f"{API}/generate", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        spec = d.get("spec") or d
        sa = spec.get("style_axes") or {}
        assert sa.get("metal_grade") == "legendary", f"style_axes={sa}"
        assert spec.get("inscription") == "#ff0000", f"inscription={spec.get('inscription')}"
        geo = spec.get("geometry") or []
        inscribed = [p for p in geo if p.get("inscription")]
        assert len(inscribed) >= 1, f"no inscribed parts in geometry ({len(geo)} parts)"


# ── Custom Style Packs CRUD ─────────────────────────────────────────────
class TestCustomStylePacks:
    def test_create_list_delete(self, client):
        # Create
        payload = {
            "label": "TEST_iter92_pack",
            "skin_style": "neon",
            "axes": {"metal_grade": "legendary", "punk": "cyberpunk"},
            "treatment": "symbols",
            "intricacy": "ornate",
        }
        cr = client.post(f"{API}/style-packs", json=payload, timeout=20)
        assert cr.status_code == 200, cr.text
        body = cr.json()
        # endpoint returns the pack directly or wrapped
        pack = body.get("pack") or body
        key = pack.get("key")
        assert key, f"no key in {body}"
        assert pack.get("custom") is True, pack
        assert pack.get("label") == "TEST_iter92_pack"

        try:
            # Verify appears in /styles with custom=True
            sr = client.get(f"{API}/styles", timeout=20)
            assert sr.status_code == 200
            packs = sr.json().get("style_packs") or []
            found = next((p for p in packs if p.get("key") == key), None)
            assert found is not None, f"custom pack {key} not in /styles"
            assert found.get("custom") is True
            assert found.get("skin_style") == "neon"
            assert (found.get("axes") or {}).get("metal_grade") == "legendary"
            assert found.get("treatment") == "symbols"
        finally:
            # Delete (cleanup)
            dr = client.delete(f"{API}/style-packs/{key}", timeout=20)
            assert dr.status_code == 200, dr.text
            # Verify gone
            sr2 = client.get(f"{API}/styles", timeout=20)
            remaining = [p for p in (sr2.json().get("style_packs") or []) if p.get("key") == key]
            assert remaining == [], f"pack {key} not deleted: {remaining}"


# ── Compose still returns by_region ─────────────────────────────────────
class TestComposeByRegion:
    def test_compose_returns_by_region(self, client):
        payload = {
            "build_id": "TEST_iter92_build",
            "items": [
                {"category": "sword", "region": "weapon"},
                {"category": "oak_tree", "region": "flora"},
            ],
            "seed": 7,
            "mount": False,
            "style": {"axes": {"metal_grade": "legendary"}, "treatment": "symbols"},
            "variants": 1,
        }
        r = client.post(f"{API}/compose", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        by_region = d.get("by_region")
        assert isinstance(by_region, list) and len(by_region) >= 1, d
        first = by_region[0]
        for k in ("family", "primary", "variants", "treatment", "accent"):
            assert k in first, f"missing {k} in {first}"
