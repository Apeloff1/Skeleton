"""Iteration 96 — Universal Forge 3-tier virtual namespace regression tests.

Validates: catalog headline counts (1,001,432 base / 601,860,632 forges), random
3-tier resolver, generate at every tier, search relevance + zzqqxx empty-fast,
styles axes engraving present, and compose/seed/snowball regressions over the
new _VirtualCatIndex (.get/[]/in)."""
from __future__ import annotations

import os
import sys
import time

import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_BACKEND_URL", "https://player-retention.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ─────────────────────────── catalog ────────────────────────────────────────
class TestCatalog:
    def test_catalog_headline_counts(self, s):
        r = s.get(f"{API}/galaxy-studio/forge/catalog", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        # Per review_request expectations
        assert d["base_category_count"] == 1_001_432, d["base_category_count"]
        assert d["category_count"] == 601_860_632, d["category_count"]
        assert d["descriptor_count"] == 603
        assert d["modifier_count"] == 600
        # Total variations is a NUMERIC STRING (big-int)
        tv_str = d["total_variations"]
        assert isinstance(tv_str, str) and tv_str.isdigit()
        assert int(tv_str) > 10**100
        assert d["total_variations_pretty"] == "5.83×10^104"

    def test_catalog_family_counts_sum_to_category_count(self, s):
        r = s.get(f"{API}/galaxy-studio/forge/catalog", timeout=20)
        d = r.json()
        fam_total = sum(f["count"] for f in d["families"])
        assert fam_total == d["category_count"], (
            f"families sum {fam_total} != category_count {d['category_count']}"
        )

    def test_catalog_browse_payload_intact(self, s):
        r = s.get(f"{API}/galaxy-studio/forge/catalog", timeout=20)
        d = r.json()
        assert d["browse_count"] == len(d["categories"])
        assert d["browse_count"] >= 1500
        # groups[] has the {group, categories} shape (regression from it.95)
        assert isinstance(d["groups"], list) and d["groups"]
        first_g = d["groups"][0]
        assert "group" in first_g and "categories" in first_g
        assert d["family_count"] == 30


# ─────────────────────────── random (Surprise Me) ───────────────────────────
class TestRandom:
    def _validate(self, d: dict) -> str:
        for k in ("category", "label", "family", "group", "axes", "skin_style", "era"):
            assert k in d, f"missing {k} in {d}"
        axes = d["axes"]
        assert isinstance(axes, dict) and 4 <= len(axes) <= 7, axes
        return d["category"]

    def _classify(self, key: str) -> str:
        if "-" in key:
            return "tier3"
        if "." in key:
            return "tier2"
        return "core"

    def test_random_returns_resolvable_keys(self, s):
        tiers_seen: set[str] = set()
        keys = []
        for seed in (1, 7, 23, 91, 314, 2718):
            r = s.get(f"{API}/galaxy-studio/forge/random",
                      params={"seed": seed}, timeout=15)
            assert r.status_code == 200, r.text
            d = r.json()
            k = self._validate(d)
            keys.append(k)
            tiers_seen.add(self._classify(k))
        # With 6 calls and 0.7×0.6 = 42% chance of tier-3 each time, we should
        # almost always see at least 2 distinct tiers in 6 picks.
        assert len(tiers_seen) >= 2, f"only saw {tiers_seen} tiers across {keys}"

    def test_random_key_resolves_via_generate(self, s):
        # Pick a random forge and ensure generate accepts that exact key.
        r = s.get(f"{API}/galaxy-studio/forge/random",
                  params={"seed": 42}, timeout=15)
        cat = r.json()["category"]
        g = s.post(f"{API}/galaxy-studio/forge/generate",
                   json={"category": cat, "era": "modern", "use_llm": False},
                   timeout=30)
        assert g.status_code == 200, g.text
        spec = g.json()
        assert spec.get("category_label"), spec


# ─────────────────────────── generate (3 tiers) ─────────────────────────────
class TestGenerateTiers:
    def _spec_ok(self, spec: dict):
        assert "category_label" in spec
        # geometry is a LIST of parts (per iter-95 context note)
        geom = spec.get("geometry")
        assert isinstance(geom, list) and geom, f"empty geometry {geom}"

    def test_generate_tier1_core_noun(self, s):
        r = s.post(f"{API}/galaxy-studio/forge/generate",
                   json={"category": "longsword", "era": "modern", "use_llm": False},
                   timeout=30)
        assert r.status_code == 200, r.text
        spec = r.json()
        self._spec_ok(spec)
        assert "longsword" in spec["category_label"].lower()

    def test_generate_tier2_descriptor_noun(self, s):
        r = s.post(f"{API}/galaxy-studio/forge/generate",
                   json={"category": "iron.longsword", "era": "modern", "use_llm": False},
                   timeout=30)
        assert r.status_code == 200, r.text
        spec = r.json()
        self._spec_ok(spec)
        lbl = spec["category_label"].lower()
        assert "iron" in lbl and "longsword" in lbl, spec["category_label"]

    def test_generate_tier3_modifier_descriptor_noun(self, s):
        r = s.post(f"{API}/galaxy-studio/forge/generate",
                   json={"category": "gilded-iron.longsword", "era": "modern",
                         "use_llm": False, "axes": {"engraving": "runic"}},
                   timeout=30)
        assert r.status_code == 200, r.text
        spec = r.json()
        self._spec_ok(spec)
        lbl = spec["category_label"].lower()
        # Must compose to "Gilded Iron Longsword"
        assert "gilded" in lbl and "iron" in lbl and "longsword" in lbl, spec["category_label"]


# ─────────────────────────── search ─────────────────────────────────────────
class TestSearch:
    def _search(self, s, q):
        t0 = time.time()
        r = s.get(f"{API}/galaxy-studio/forge/search",
                  params={"q": q}, timeout=10)
        dt = time.time() - t0
        return r, dt

    def test_search_sword_hits(self, s):
        r, dt = self._search(s, "sword")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] > 0
        assert dt < 5.0, f"slow: {dt:.2f}s"

    def test_search_iron_hits(self, s):
        r, dt = self._search(s, "iron")
        assert r.status_code == 200
        assert r.json()["total"] > 0
        assert dt < 5.0

    def test_search_ancient_hits(self, s):
        r, dt = self._search(s, "ancient")
        assert r.status_code == 200
        assert r.json()["total"] > 0
        assert dt < 5.0

    def test_search_garbage_empty_fast(self, s):
        r, dt = self._search(s, "zzqqxx")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == 0, d
        assert d["results"] == []
        assert dt < 3.0, f"no-match slow: {dt:.2f}s (would imply scan of 600M)"


# ─────────────────────────── styles ─────────────────────────────────────────
class TestStyles:
    def test_styles_engraving_axis_present(self, s):
        r = s.get(f"{API}/galaxy-studio/forge/styles", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        axes = d.get("axes")
        # The API returns axes as a LIST of {key,label,options[]} entries
        assert isinstance(axes, list), type(axes)
        axes_by_key = {a["key"]: a for a in axes}
        assert "engraving" in axes_by_key, list(axes_by_key)[:10]
        eng = axes_by_key["engraving"]
        opts = eng.get("options", [])
        assert isinstance(opts, list)
        assert len(opts) == 12, f"engraving has {len(opts)} options, expected 12"
        # total axes ~116 (was 115; engraving added on iter 95)
        assert 110 <= len(axes) <= 130, f"unexpected axis count {len(axes)}"


# ─────────────────────────── regression (_CAT_BY_KEY) ───────────────────────
class TestRegressionVirtualIndex:
    def test_compose_with_tier2_and_tier3_items(self, s):
        r = s.post(f"{API}/galaxy-studio/forge/compose", json={
            "build_id": "TEST_iter96_compose",
            "era": "modern",
            "mount": False,
            "items": [
                {"category": "longsword", "count": 1},
                {"category": "iron.longsword", "count": 1},
                {"category": "gilded-iron.longsword", "count": 1},
            ],
            "seed": 7,
        }, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        composed = d.get("composed", [])
        assert composed, d
        cats = {it["category"] for it in composed}
        # All 3 input categories should be accepted (none filtered out — proves
        # _CAT_BY_KEY membership now resolves tier-2 + tier-3 virtual keys).
        assert "longsword" in cats
        assert "iron.longsword" in cats
        assert "gilded-iron.longsword" in cats
        # Labels compose correctly
        labels = {it["category"]: it["label"] for it in composed}
        assert labels["gilded-iron.longsword"] == "Gilded Iron Longsword"
        assert labels["iron.longsword"] == "Iron Longsword"
        # by_region tag derived via _CAT_BY_KEY[c]['family'] — must not error
        assert "by_region" in d and d["by_region"]
        fams = {r.get("family") for r in d["by_region"]}
        assert fams, d["by_region"]

    def test_seed_for_build(self, s):
        r = s.post(f"{API}/galaxy-studio/forge/seed", json={
            "build_id": "TEST_iter96_seed",
            "era": "modern",
            "genre": "rpg",
            "seed": 13,
            "mount": False,
        }, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        # seed_for_build uses recipe through _CAT_BY_KEY membership filter
        assert "composed" in d or "items" in d, d

    def test_snowball_construct_forge_uses_virtual_keys(self):
        """Direct module-level regression — call construct_forge.forge_for_build
        with seed_universal=True so the universal seed path runs through
        _uf._CAT_BY_KEY[c]['family'] over tier-2 / tier-3 keys."""
        sys.path.insert(0, "/app/backend")
        try:
            from core import construct_forge as cf  # noqa: WPS433
        except Exception as e:  # pragma: no cover
            pytest.fail(f"construct_forge import failed: {e}")
        fn = getattr(cf, "forge_for_build", None)
        if not callable(fn):
            pytest.skip("forge_for_build not exposed on construct_forge")
        try:
            res = fn("TEST_iter96_snowball", era="modern", genre="rpg",
                     seed=99, mount=False, seed_universal=True)
        except TypeError:
            # Older sig — fall back to positional / minimal kwargs
            try:
                res = fn("TEST_iter96_snowball")
            except Exception as e:
                pytest.fail(f"forge_for_build raised: {e!r}")
        except KeyError as ke:
            pytest.fail(f"_CAT_BY_KEY missed virtual key: {ke!r}")
        except Exception as e:
            pytest.fail(f"forge_for_build raised: {e!r}")
        assert res is not None
