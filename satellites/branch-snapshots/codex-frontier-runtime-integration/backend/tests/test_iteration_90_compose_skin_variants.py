"""Iteration 90 — Compose Scene skin-style + region-specific variants + Surprise me.

Coverage:
- GET /api/galaxy-studio/forge/styles returns skin_styles, complexity, intricacy,
  detail_level, regions (drives both 'Surprise me' randomizers).
- POST /forge/generate honors skin_style/complexity/intricacy/detail_level and
  echoes them back via spec.skin_style + spec.detail.
- POST /forge/save persists a generated spec (skin/detail fields included),
  and the saved doc retains skin_style + detail when fetched.
- POST /forge/compose with style + variants + region returns
  total == primary + variants, primary/variants counts match items*count,
  style.skin_style and region are echoed.
- Variant assets are mounted into the build and tagged as region variants.
- Regression: compose without style/variants (Auto + toggle off) still composes
  & mounts, returns variants=0, total=primary.
"""
from __future__ import annotations

import os
import time
import pytest
import requests


BASE_URL = os.environ.get("EXPO_BACKEND_URL") or os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL"
) or "https://player-retention.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")
FORGE = f"{BASE_URL}/api/galaxy-studio/forge"

# A unique build id per test session for clean isolation.
BUILD_ID = f"TEST_iter90_{int(time.time())}"
BUILD_ID_PLAIN = f"TEST_iter90_plain_{int(time.time())}"


@pytest.fixture(scope="module")
def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── /forge/styles drives Surprise me on both screens ────────────────────────
class TestStylesCatalog:
    def test_styles_returns_all_required_fields(self, session):
        r = session.get(f"{FORGE}/styles", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ("skin_styles", "complexity", "intricacy", "detail_level", "regions"):
            assert key in data, f"missing key '{key}' in styles catalog: {list(data.keys())}"
        # skin_styles must carry {key,label}
        assert isinstance(data["skin_styles"], list) and data["skin_styles"], "skin_styles empty"
        sample = data["skin_styles"][0]
        assert "key" in sample and "label" in sample
        # Bands must be non-empty lists
        for band in ("complexity", "intricacy", "detail_level"):
            assert isinstance(data[band], list) and data[band], f"band {band} empty"
        # Regions: {family: [x,z]}
        assert isinstance(data["regions"], dict) and data["regions"]


# ── /forge/generate honors skin/complexity/intricacy/detail_level ───────────
class TestForgeGenerate:
    def test_generate_with_style_params_echoes_back(self, session):
        body = {
            "category": "sword",
            "era": "modern",
            "use_llm": False,  # deterministic, fast
            "skin_style": "weathered",
            "complexity": "ultra",
            "intricacy": "baroque",
            "detail_level": "sota",
        }
        r = session.post(f"{FORGE}/generate", json=body, timeout=30)
        assert r.status_code == 200, r.text
        spec = r.json()
        assert spec.get("skin_style") == "weathered", f"expected skin_style=weathered, got {spec.get('skin_style')}"
        detail = spec.get("detail") or {}
        assert detail.get("complexity") == "ultra", f"detail.complexity wrong: {detail}"
        assert detail.get("intricacy") == "baroque", f"detail.intricacy wrong: {detail}"
        assert detail.get("detail_level") == "sota", f"detail.detail_level wrong: {detail}"
        # Sanity: geometry / palette emitted
        assert isinstance(spec.get("geometry"), list) and spec["geometry"], "no geometry"
        assert isinstance(spec.get("palette"), list) and spec["palette"], "no palette"


# ── /forge/save persists skin/detail fields ─────────────────────────────────
class TestForgeSavePersists:
    def test_generated_spec_with_skin_persists_via_save_and_get(self, session):
        gen = session.post(
            f"{FORGE}/generate",
            json={"category": "tree", "era": "modern", "use_llm": False,
                  "skin_style": "painted", "complexity": "standard",
                  "intricacy": "ornate", "detail_level": "standard"},
            timeout=30,
        )
        assert gen.status_code == 200, gen.text
        spec = gen.json()
        save = session.post(f"{FORGE}/save", json={"spec": spec}, timeout=20)
        assert save.status_code == 200, save.text
        cid = save.json().get("construct_id")
        assert cid, f"no construct_id returned: {save.json()}"
        # GET back and verify skin_style + detail persisted
        got = session.get(f"{FORGE}/item/{cid}", timeout=20)
        assert got.status_code == 200, got.text
        doc = got.json()
        assert doc.get("skin_style") == "painted", f"saved doc skin_style wrong: {doc.get('skin_style')}"
        det = doc.get("detail") or {}
        assert det.get("intricacy") == "ornate", f"saved doc detail wrong: {det}"
        # Cleanup
        session.delete(f"{FORGE}/item/{cid}", timeout=15)


# ── /forge/compose with style + variants + region ───────────────────────────
class TestComposeWithStyleAndVariants:
    def test_compose_returns_total_primary_variants_style_region(self, session):
        items = [{"category": "tree", "count": 3}, {"category": "sword", "count": 2}]
        body = {
            "build_id": BUILD_ID,
            "era": "modern",
            "items": items,
            "style": {"skin_style": "weathered", "intricacy": "ornate"},
            "variants": 1,
            "region": "weathered",
            "mount": True,
        }
        r = session.post(f"{FORGE}/compose", json=body, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        # primary = 3 + 2 = 5, variants = 5 * 1 = 5, total = 10
        assert d.get("primary") == 5, f"primary wrong: {d}"
        assert d.get("variants") == 5, f"variants wrong: {d}"
        assert d.get("total") == d["primary"] + d["variants"] == 10, f"total mismatch: {d}"
        assert d.get("region") == "weathered", f"region not echoed: {d.get('region')}"
        style_echo = d.get("style") or {}
        assert style_echo.get("skin_style") == "weathered", f"style.skin_style wrong: {style_echo}"
        assert d.get("mounted") is True

    def test_variants_mounted_to_build_and_tagged(self, session):
        # The previous test composed into BUILD_ID. Fetch the saved assets and
        # verify variants are mounted + tagged.
        r = session.get(
            f"{FORGE}/list",
            params={"build_id": BUILD_ID, "limit": 100},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        assert len(items) >= 10, f"expected >=10 mounted items, got {len(items)}"
        variants = [it for it in items if it.get("variant") is True]
        assert len(variants) >= 5, f"expected >=5 variant items mounted, got {len(variants)}"
        # variant_of and region tagging
        for v in variants[:3]:
            assert v.get("variant_of"), f"variant missing variant_of: {v.get('name')}"
            assert v.get("region") == "weathered" or v.get("region"), (
                f"variant missing region tag: {v.get('name')} region={v.get('region')}"
            )
            assert " variant" in (v.get("name") or "").lower(), (
                f"variant name not suffixed: {v.get('name')}"
            )


# ── Regression: compose without skin/variants ────────────────────────────────
class TestComposeRegressionPlain:
    def test_compose_without_style_or_variants_still_works(self, session):
        body = {
            "build_id": BUILD_ID_PLAIN,
            "era": "modern",
            "items": [{"category": "tree", "count": 4}],
            # No style, no variants, no region — toggle OFF on the UI
            "variants": 0,
            "mount": True,
        }
        r = session.post(f"{FORGE}/compose", json=body, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("primary") == 4, f"plain primary wrong: {d}"
        assert d.get("variants") == 0, f"plain variants should be 0: {d}"
        assert d.get("total") == 4, f"plain total wrong: {d}"
        assert d.get("region") is None
        assert d.get("mounted") is True
        # And the build now has 4 mounted assets
        lr = session.get(
            f"{FORGE}/list",
            params={"build_id": BUILD_ID_PLAIN, "limit": 50},
            timeout=20,
        )
        assert lr.status_code == 200
        assert len(lr.json().get("items", [])) >= 4


# ── Regression: /forge/catalog still works (compose search depends on it) ──
class TestCatalogRegression:
    def test_catalog_returns_categories(self, session):
        r = session.get(f"{FORGE}/catalog", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("categories"), list) and len(d["categories"]) > 100, (
            f"catalog short: {len(d.get('categories', []))} categories"
        )
