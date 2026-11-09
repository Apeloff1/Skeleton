"""Iteration 93 — Universal Forge: 8 new thematic style axes (elemental, magic,
curse, dripping, light_emanation, aura, exotic, fashion) + finish axis, and the
procedural forge library scaled past 100,000 items.

Validates:
- /forge/catalog: category_count >= 100_000 (currently 107097), browse_count present,
  response payload stays small (browse list only — no full 100k dump).
- /forge/styles: 15 axes including 9 new keys, each with options[{key,label,tint}].
  finish axis exposes matte/metallic/sheen/glean/polish/reflection/contour/luster/gloss/shine.
- /forge/generate with axes={'elemental':'fire','finish':'gloss','aura':'holy_aura','magic':'runic'}
  (use_llm=false) -> spec.style_axes contains all four, returns vfx + valid geometry/palette.
- /forge/search?q=molten%20dragon returns procedural variants from the 100k library.
- Regression: metal_grade legendary + inscribe still works, custom style packs CRUD,
  compose by_region still returns per-region breakdown.
"""
from __future__ import annotations

import os

import pytest
import requests

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
).rstrip("/")
API = f"{BASE_URL}/api/galaxy-studio/forge"

NEW_THEMATIC_AXES = {
    "finish",
    "elemental",
    "magic",
    "curse",
    "dripping",
    "light_emanation",
    "aura",
    "exotic",
    "fashion",
}

FINISH_OPTIONS_EXPECTED = {
    "matte", "metallic", "sheen", "glean", "polish",
    "reflection", "contour", "luster", "gloss", "shine",
}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Catalog: 100k+ procedural library, small browse payload ─────────────
class TestCatalog100k:
    def test_catalog_over_100k(self, client):
        r = client.get(f"{API}/catalog", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        cc = d.get("category_count", 0)
        bc = d.get("browse_count", 0)
        assert cc >= 100_000, f"category_count={cc} < 100000"
        assert bc > 0, f"browse_count={bc}"
        # Payload stays small — browse only. We require the returned
        # `categories` browse list to be far smaller than the full library.
        cats = d.get("categories") or []
        assert isinstance(cats, list)
        assert len(cats) < 5000, (
            f"browse payload too big: len(categories)={len(cats)} — "
            "must be a small browse list, not the full 100k catalog"
        )
        # And browse_count must roughly match the returned browse list size.
        assert abs(len(cats) - bc) <= max(50, int(bc * 0.1)), (
            f"browse_count={bc} mismatches len(categories)={len(cats)}"
        )


# ── Styles: 15 axes, 9 new thematic + finish; option shape correct ─────
class TestThematicAxes:
    @pytest.fixture(scope="class")
    def styles(self, client):
        r = client.get(f"{API}/styles", timeout=20)
        assert r.status_code == 200, r.text
        return r.json()

    def test_axis_count_is_15(self, styles):
        axes = styles.get("axes") or []
        assert len(axes) == 15, f"expected 15 axes, got {len(axes)}: " \
            f"{[a.get('key') for a in axes]}"

    def test_all_nine_new_axes_present(self, styles):
        axes = styles.get("axes") or []
        keys = {a.get("key") for a in axes}
        missing = NEW_THEMATIC_AXES - keys
        assert not missing, f"missing new axes: {missing}; got {keys}"

    @pytest.mark.parametrize("axis_key", sorted(NEW_THEMATIC_AXES))
    def test_axis_options_shape(self, styles, axis_key):
        axes = styles.get("axes") or []
        ax = next((a for a in axes if a.get("key") == axis_key), None)
        assert ax is not None, f"axis {axis_key} missing"
        opts = ax.get("options") or []
        assert len(opts) >= 3, f"{axis_key} has too few options: {opts}"
        for o in opts:
            assert "key" in o, f"{axis_key} option missing key: {o}"
            assert "label" in o, f"{axis_key} option missing label: {o}"
            assert "tint" in o, f"{axis_key} option missing tint: {o}"

    def test_finish_options_cover_all_ten(self, styles):
        axes = styles.get("axes") or []
        finish = next((a for a in axes if a.get("key") == "finish"), None)
        assert finish is not None, "finish axis missing"
        opt_keys = {o["key"] for o in (finish.get("options") or [])}
        missing = FINISH_OPTIONS_EXPECTED - opt_keys
        assert not missing, f"finish missing options: {missing}; got {opt_keys}"

    def test_existing_axes_still_present(self, styles):
        """Regression: previously-verified axes must still be present."""
        axes = styles.get("axes") or []
        keys = {a.get("key") for a in axes}
        for k in ("art_style", "period", "realism", "fantasy",
                  "punk", "metal_grade"):
            assert k in keys, f"existing axis {k} missing"


# ── Generate: new axes applied + vfx + geometry/palette ─────────────────
class TestGenerateNewAxes:
    def test_four_new_axes_applied(self, client):
        payload = {
            "category": "sword",
            "use_llm": False,
            "axes": {
                "elemental": "fire",
                "finish": "gloss",
                "aura": "holy_aura",
                "magic": "runic",
            },
            "seed": 13,
        }
        r = client.post(f"{API}/generate", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        spec = d.get("spec") or d
        sa = spec.get("style_axes") or {}
        assert sa.get("elemental") == "fire", sa
        assert sa.get("finish") == "gloss", sa
        assert sa.get("aura") == "holy_aura", sa
        assert sa.get("magic") == "runic", sa

        # vfx must be returned and non-empty. The backend may emit vfx as a
        # short keyword string ("glow"), a dict {effect: params}, or a list of
        # effects — all three are acceptable as "a vfx set".
        vfx = spec.get("vfx")
        assert vfx is not None, "spec.vfx missing"
        if isinstance(vfx, dict):
            assert len(vfx) >= 1, f"empty vfx dict: {vfx}"
        elif isinstance(vfx, list):
            assert len(vfx) >= 1, "empty vfx list"
        elif isinstance(vfx, str):
            assert vfx.strip(), f"empty vfx string: {vfx!r}"
        else:
            pytest.fail(f"vfx has unexpected type: {type(vfx).__name__} -> {vfx}")

        # palette + geometry must be valid
        palette = spec.get("palette") or []
        geometry = spec.get("geometry") or []
        assert len(palette) >= 3, f"palette too small: {palette}"
        assert len(geometry) >= 1, f"geometry empty"
        for p in geometry:
            assert isinstance(p, dict), p


# ── Search: 'molten dragon' over 100k procedural library ────────────────
class TestSearchMoltenDragon:
    def test_molten_dragon_returns_variants(self, client):
        r = client.get(f"{API}/search", params={"q": "molten dragon", "limit": 10}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        results = d.get("results") or d.get("items") or []
        assert len(results) >= 1, f"no results for 'molten dragon': {d}"
        # at least one result has 'molten' in its key (procedural variant)
        assert any(
            "molten" in (it.get("key") or "").lower() for it in results
        ), f"no procedural 'molten' variants: {[r.get('key') for r in results]}"

    def test_search_remains_fast(self, client):
        """Server-side search should respond in under 5 seconds."""
        import time
        t0 = time.time()
        r = client.get(f"{API}/search", params={"q": "dragon", "limit": 20}, timeout=10)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        assert elapsed < 5.0, f"search took {elapsed:.2f}s — too slow for 100k library"


# ── Regression: metal_grade + inscribe still works ──────────────────────
class TestRegressionMetalGradeInscribe:
    def test_legendary_with_inscription(self, client):
        payload = {
            "category": "sword",
            "use_llm": False,
            "axes": {"metal_grade": "legendary"},
            "inscribe": "#00ff00",
            "seed": 99,
        }
        r = client.post(f"{API}/generate", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        spec = r.json().get("spec") or r.json()
        assert (spec.get("style_axes") or {}).get("metal_grade") == "legendary"
        assert spec.get("inscription") == "#00ff00"
        inscribed = [p for p in (spec.get("geometry") or []) if p.get("inscription")]
        assert len(inscribed) >= 1


# ── Regression: custom style packs CRUD ─────────────────────────────────
class TestRegressionCustomStylePacks:
    def test_create_list_delete(self, client):
        payload = {
            "label": "TEST_iter93_pack",
            "skin_style": "neon",
            "axes": {"finish": "gloss", "elemental": "fire", "aura": "holy_aura"},
            "treatment": "symbols",
            "intricacy": "ornate",
        }
        cr = client.post(f"{API}/style-packs", json=payload, timeout=20)
        assert cr.status_code == 200, cr.text
        pack = cr.json().get("pack") or cr.json()
        key = pack.get("key")
        assert key, pack
        try:
            sr = client.get(f"{API}/styles", timeout=20)
            packs = sr.json().get("style_packs") or []
            found = next((p for p in packs if p.get("key") == key), None)
            assert found is not None, f"pack {key} not in /styles"
            assert found.get("custom") is True
            # new axes round-trip through the pack
            ax = found.get("axes") or {}
            assert ax.get("finish") == "gloss"
            assert ax.get("elemental") == "fire"
            assert ax.get("aura") == "holy_aura"
        finally:
            dr = client.delete(f"{API}/style-packs/{key}", timeout=20)
            assert dr.status_code == 200, dr.text


# ── Regression: compose by_region still works ───────────────────────────
class TestRegressionComposeByRegion:
    def test_compose_returns_by_region_with_new_axes(self, client):
        payload = {
            "build_id": "TEST_iter93_build",
            "items": [
                {"category": "sword", "region": "weapon"},
                {"category": "oak_tree", "region": "flora"},
            ],
            "seed": 17,
            "mount": False,
            "style": {
                "axes": {"finish": "gloss", "elemental": "fire", "aura": "holy_aura"},
                "treatment": "symbols",
            },
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
