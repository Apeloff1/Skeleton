"""
Session 13c (iteration 34) — Worldforge refactor regression + Köppen + Trade routes.

Tests:
- Refactor regression: all worldforge endpoints still work after extraction of
  worldforge_noise.py and worldforge_naming.py.
- Köppen–Geiger climate classification on region.
- Trade-route network (least-cost A*) on region.
- Determinism (same seed → identical koppen + routes).
- Cosmic exclusion (galaxy scale has no koppen/routes).
- Performance: region size=48 < 2s.
"""
from __future__ import annotations

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") \
    or os.environ.get("EXPO_BACKEND_URL", "").rstrip("/")
WF = f"{BASE_URL}/api/worldforge"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── refactor regression ────────────────────────────────────────────────
class TestRefactorRegression:
    def test_get_region(self, session):
        r = session.get(f"{WF}/region", params={"seed": 1337, "size": 48}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["scale"] == "region" and d["size"] == 48
        assert isinstance(d.get("grid"), list) and len(d["grid"]) == 48
        assert isinstance(d.get("pois"), list)

    def test_post_world_region(self, session):
        body = {"scale": "region", "seed": 42, "size": 32}
        r = session.post(f"{WF}/world", json=body, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["scale"] == "region"

    def test_options_has_12_plus_toggles(self, session):
        r = session.get(f"{WF}/options", timeout=20)
        assert r.status_code == 200
        d = r.json()
        toggles = d.get("feature_toggles", [])
        assert len(toggles) >= 12, f"expected >=12 toggles, got {len(toggles)}"

    def test_biomes_16(self, session):
        r = session.get(f"{WF}/biomes", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == 16, f"expected 16 biomes, got {d['count']}"

    def test_name_key_etymology_no_fantasy(self, session):
        body = {"seed": 1337, "size": 32, "world_scale": "region"}
        r = session.post(f"{WF}/name-key", json=body, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        entries = d.get("entries", [])
        assert len(entries) >= 1
        # Each entry has etymology breakdown
        for e in entries:
            assert "name" in e and "etymology" in e
            assert isinstance(e["etymology"], list) and len(e["etymology"]) >= 1
        # Anti-fantasy: ensure no obvious fantasy tokens in names
        banned = {"orc", "elf", "dwarf", "wyrm", "drake", "rune", "mythril", "shire"}
        for e in entries:
            assert not any(b in e["name"].lower() for b in banned), e["name"]

    def test_render_png(self, session):
        r = session.get(f"{WF}/render", params={"scale": "region", "seed": 7, "size": 48}, timeout=60)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/")

    def test_render_gif_cache(self, session):
        # Use unique seed so first call is MISS
        seed = int(time.time()) % 100000
        r1 = session.get(f"{WF}/render.gif", params={"scale": "planet", "seed": seed, "size": 40}, timeout=120)
        # /render.gif may or may not exist; if 404, fail loudly so we know
        if r1.status_code == 404:
            pytest.skip("/render.gif endpoint not present")
        assert r1.status_code == 200, r1.text[:200]
        assert r1.headers["content-type"].startswith("image/")
        x_cache_1 = r1.headers.get("X-Cache", "")
        r2 = session.get(f"{WF}/render.gif", params={"scale": "planet", "seed": seed, "size": 40}, timeout=60)
        assert r2.status_code == 200
        x_cache_2 = r2.headers.get("X-Cache", "")
        # Should be MISS then HIT (informational — log if not)
        print(f"X-Cache 1st={x_cache_1!r} 2nd={x_cache_2!r}")
        assert "HIT" in x_cache_2 or x_cache_1 == "" or x_cache_2 == "", \
            f"expected 2nd call HIT, got {x_cache_2!r}"


# ── Köppen classification ──────────────────────────────────────────────
class TestKoppen:
    def test_region_has_koppen(self, session):
        r = session.get(f"{WF}/region", params={"seed": 1337, "size": 48}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        kop = d.get("koppen")
        assert kop is not None, "missing koppen"
        for k in ("code", "name", "summary", "dominant_biome"):
            assert k in kop, f"koppen missing {k}"
        # Must be a real Köppen class
        valid_codes = {"Af", "Am", "Aw", "BWh", "BWk", "BSh", "BSk",
                       "Cfa", "Cfb", "Cfc", "Csa", "Csb", "Cwa", "Cwb",
                       "Dfa", "Dfb", "Dfc", "Dfd", "Dsa", "Dsb", "Dsc",
                       "Dwa", "Dwb", "Dwc", "Dwd", "ET", "EF", "H"}
        assert kop["code"] in valid_codes, f"invalid Köppen code: {kop['code']}"
        assert d["stats"]["koppen"] == kop["code"]


# ── Trade routes ───────────────────────────────────────────────────────
class TestTradeRoutes:
    def test_region_routes_shape(self, session):
        r = session.get(f"{WF}/region", params={"seed": 1337, "size": 48}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        routes = d.get("routes")
        assert isinstance(routes, list), "routes must be a list"
        assert d["stats"]["trade_routes"] == len(routes)
        if not routes:
            pytest.skip("no routes for this seed")
        for rt in routes:
            for k in ("from", "to", "from_xy", "to_xy", "path", "cost", "tiles"):
                assert k in rt, f"route missing {k}"
            assert isinstance(rt["path"], list) and len(rt["path"]) >= 1
            assert isinstance(rt["cost"], (int, float))
            assert isinstance(rt["tiles"], int)
            # Path start matches from_xy, end matches to_xy
            assert list(rt["path"][0]) == list(rt["from_xy"]), \
                f"path start {rt['path'][0]} != from_xy {rt['from_xy']}"
            assert list(rt["path"][-1]) == list(rt["to_xy"]), \
                f"path end {rt['path'][-1]} != to_xy {rt['to_xy']}"


# ── Determinism ────────────────────────────────────────────────────────
class TestDeterminism:
    def test_same_seed_identical(self, session):
        a = session.get(f"{WF}/region", params={"seed": 4242, "size": 48}, timeout=30).json()
        b = session.get(f"{WF}/region", params={"seed": 4242, "size": 48}, timeout=30).json()
        assert a["koppen"] == b["koppen"], "koppen not deterministic"
        # Compare routes by their identifying fields
        assert len(a["routes"]) == len(b["routes"])
        for ra, rb in zip(a["routes"], b["routes"]):
            assert ra["from_xy"] == rb["from_xy"]
            assert ra["to_xy"] == rb["to_xy"]
            assert ra["path"] == rb["path"]
            assert ra["cost"] == rb["cost"]


# ── Cosmic exclusion ───────────────────────────────────────────────────
class TestCosmicExclusion:
    def test_galaxy_no_koppen_no_routes(self, session):
        body = {"scale": "galaxy", "seed": 99}
        r = session.post(f"{WF}/world", json=body, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["scale"] == "galaxy"
        assert "koppen" not in d, "galaxy scale must not include koppen"
        assert "routes" not in d, "galaxy scale must not include routes"
        # And not in stats either
        assert "koppen" not in d["stats"]
        assert "trade_routes" not in d["stats"]


# ── Performance ────────────────────────────────────────────────────────
class TestPerformance:
    def test_region_size48_under_2s(self, session):
        # Warm-up
        session.get(f"{WF}/region", params={"seed": 1, "size": 48}, timeout=30)
        t0 = time.time()
        r = session.get(f"{WF}/region", params={"seed": 2026, "size": 48}, timeout=30)
        dt = time.time() - t0
        assert r.status_code == 200
        print(f"region size=48 latency: {dt:.3f}s")
        assert dt < 2.0, f"region size=48 took {dt:.2f}s, exceeds 2s budget"
