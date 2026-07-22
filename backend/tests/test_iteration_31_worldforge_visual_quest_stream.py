"""
Iteration 31 — Worldforge visual-fidelity push + quest graph + streaming.

Validates:
- /api/worldforge/options exposes render_modes for region/planet/system/galaxy/cosmos
- /api/worldforge/render returns PNG for each mode (region/galaxy), distinct bytes per mode
- /api/worldforge/render with zoom+pan returns PNG
- /api/worldforge/render.gif returns image/gif for planet (spin)
- /api/worldforge/export returns PNG with Content-Disposition (hi-res)
- /api/worldforge/quest returns >=2 nodes, consistency.ok true, node_count, places
- /api/worldforge/stream/manifest returns lods pyramid + total_addressable_chunks
- /api/worldforge/stream/chunk.png returns PNG
- Regression: /api/worldforge/world & /api/worldforge/lore still healthy
"""
import os
import hashlib
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
if not BASE_URL:
    raise RuntimeError("EXPO_PUBLIC_BACKEND_URL / EXPO_BACKEND_URL must be set")
BASE_URL = BASE_URL.rstrip("/")

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
GIF_MAGIC = b"GIF8"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Accept": "*/*"})
    return sess


# ── options & render_modes ───────────────────────────────────────────────
class TestOptions:
    def test_options_render_modes_keys(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/options", timeout=30)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        rm = data.get("render_modes")
        assert isinstance(rm, dict), f"render_modes missing: {data.keys()}"
        for k in ("region", "planet", "system", "galaxy", "cosmos"):
            assert k in rm, f"missing render_mode key: {k}"
            assert isinstance(rm[k], list) and len(rm[k]) >= 1
        # specific modes
        assert {"cartographic", "atlas", "blueprint"}.issubset(set(rm["region"]))
        assert {"nasa", "bloom"}.issubset(set(rm["galaxy"]))


# ── /render PNG modes ────────────────────────────────────────────────────
class TestRender:
    def _png(self, s, **q):
        r = s.get(f"{BASE_URL}/api/worldforge/render", params=q, timeout=90)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        assert r.headers.get("content-type", "").startswith("image/png")
        assert r.content[:8] == PNG_MAGIC
        return r.content

    def test_region_cartographic(self, s):
        png = self._png(s, scale="region", mode="cartographic", seed=42, size=48)
        assert len(png) > 4000

    def test_region_modes_distinct(self, s):
        carto = self._png(s, scale="region", mode="cartographic", seed=42, size=48)
        atlas = self._png(s, scale="region", mode="atlas", seed=42, size=48)
        blue = self._png(s, scale="region", mode="blueprint", seed=42, size=48)
        h = {hashlib.md5(b).hexdigest() for b in (carto, atlas, blue)}
        assert len(h) == 3, "region modes must produce distinct images"

    def test_galaxy_nasa_and_bloom(self, s):
        nasa = self._png(s, scale="galaxy", mode="nasa", seed=42, size=48)
        bloom = self._png(s, scale="galaxy", mode="bloom", seed=42, size=48)
        assert hashlib.md5(nasa).hexdigest() != hashlib.md5(bloom).hexdigest()

    def test_zoom_pan(self, s):
        base = self._png(s, scale="region", mode="cartographic", seed=42, size=48)
        zoomed = self._png(s, scale="region", mode="cartographic",
                            seed=42, size=48, zoom=3, pan_x=5, pan_y=2)
        assert hashlib.md5(base).hexdigest() != hashlib.md5(zoomed).hexdigest()


# ── /render.gif (planet spin) ────────────────────────────────────────────
class TestSpinGif:
    def test_planet_gif(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/render.gif",
                  params={"scale": "planet", "seed": 42, "size": 40}, timeout=120)
        assert r.status_code == 200, r.text[:200]
        ct = r.headers.get("content-type", "")
        assert ct.startswith("image/gif"), f"ct={ct}"
        assert r.content[:4] == GIF_MAGIC


# ── /export (hi-res w/ Content-Disposition) ──────────────────────────────
class TestExport:
    def test_export_region(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/export",
                  params={"scale": "region", "name": "Testland", "seed": 42, "size": 48},
                  timeout=120)
        assert r.status_code == 200, r.text[:200]
        assert r.headers.get("content-type", "").startswith("image/png")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd.lower() or "filename" in cd.lower(), f"missing CD: {cd!r}"
        assert r.content[:8] == PNG_MAGIC
        assert len(r.content) > 20_000


# ── /quest LLM ───────────────────────────────────────────────────────────
class TestQuest:
    def test_quest_region(self, s):
        body = {
            "seed": 42, "world_scale": "region",
            "palette": "natural", "climate": "temperate", "arc": "a lost relic",
        }
        r = s.post(f"{BASE_URL}/api/worldforge/quest", json=body, timeout=120)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert "quest" in data and isinstance(data["quest"], dict), data
        nodes = data["quest"].get("nodes") or []
        assert len(nodes) >= 2, f"only {len(nodes)} nodes"
        cons = data.get("consistency") or {}
        assert cons.get("ok") is True, f"consistency not ok: {cons}"
        assert isinstance(cons.get("node_count"), int) and cons["node_count"] >= 2
        # "places" lives at the top-level of the response
        assert isinstance(data.get("places"), list) and len(data["places"]) > 0


# ── /stream manifest + chunk ────────────────────────────────────────────
class TestStream:
    def test_manifest(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/stream/manifest",
                  params={"seed": 42, "scale": "region", "max_lod": 3}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert isinstance(data.get("lods"), list) and len(data["lods"]) >= 1
        assert isinstance(data.get("total_addressable_chunks"), int) and data["total_addressable_chunks"] > 0

    def test_chunk_png(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/stream/chunk.png",
                  params={"seed": 42, "lod": 2, "cx": 1, "cy": 1}, timeout=60)
        assert r.status_code == 200, r.text[:200]
        assert r.headers.get("content-type", "").startswith("image/png")
        assert r.content[:8] == PNG_MAGIC


# ── Regression: /world & /lore ───────────────────────────────────────────
class TestRegression:
    def test_world_post(self, s):
        r = s.post(f"{BASE_URL}/api/worldforge/world",
                   json={"scale": "region", "seed": 42, "size": 36, "noise_scale": 0.08},
                   timeout=60)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        for k in ("name", "grid", "distribution", "pois", "stats"):
            assert k in data, f"missing {k}"
        assert isinstance(data["grid"], list) and len(data["grid"]) > 0

    def test_lore_post(self, s):
        body = {"seed": 42, "size": 32, "world_scale": "region",
                "palette": "natural", "climate": "temperate"}
        r = s.post(f"{BASE_URL}/api/worldforge/lore", json=body, timeout=90)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("name"), data
        assert data.get("region") is not None
        assert data.get("lore"), "lore text empty"
        assert data.get("summary"), "summary missing"
