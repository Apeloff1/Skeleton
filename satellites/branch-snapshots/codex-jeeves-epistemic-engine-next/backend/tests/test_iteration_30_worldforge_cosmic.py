"""
Iteration 30 — Worldforge COSMIC + CUSTOMIZE + VAULT BRIDGE backend tests.

Covers:
  - POST /api/worldforge/world for all 5 scales (region/planet/system/galaxy/cosmos)
  - Determinism: same body → identical full response (incl. cosmic scales)
  - REGION back-compat: GET & POST /api/worldforge/region unchanged shape
  - GET /api/worldforge/options (>=16 sliders, 12 toggles)
  - GET /api/worldforge/presets total >= 100
  - GET /api/worldforge/palettes & /scales
  - Feature toggles actually shift POI kinds
  - Vault bridge: /sources, /from-game (save=true → vault asset tagged WG), /worlds, /worlds/{id}
  - AI lore for cosmic scale (LIVE LLM, ~5-15s, single call)
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL",
                          "https://gemini-game-craft.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TIMEOUT = 45


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c
    c.close()


# ── COSMIC SCALES ──────────────────────────────────────────────────────────
class TestCosmicScales:
    @pytest.mark.parametrize("scale", ["region", "planet", "system", "galaxy", "cosmos"])
    def test_world_post_all_scales(self, s, scale):
        body = {"scale": scale, "seed": 1337, "size": 32}
        r = s.post(f"{BASE_URL}/api/worldforge/world", json=body, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["scale"] == scale
        assert isinstance(j["name"], str) and len(j["name"]) >= 2
        assert isinstance(j["grid"], list) and len(j["grid"]) == 32
        assert len(j["grid"][0]) == 32
        assert isinstance(j["distribution"], list) and len(j["distribution"]) >= 1
        assert isinstance(j["pois"], list)
        stats = j["stats"]
        for k in ("tiles", "biomes", "land_pct", "water_pct", "settlements"):
            assert k in stats

    def test_world_post_determinism(self, s):
        body = {"scale": "galaxy", "seed": 9001, "size": 28, "palette": "twilight"}
        a = s.post(f"{BASE_URL}/api/worldforge/world", json=body, timeout=TIMEOUT).json()
        b = s.post(f"{BASE_URL}/api/worldforge/world", json=body, timeout=TIMEOUT).json()
        assert a == b

    def test_cosmos_determinism(self, s):
        body = {"scale": "cosmos", "seed": 4242, "size": 24}
        a = s.post(f"{BASE_URL}/api/worldforge/world", json=body, timeout=TIMEOUT).json()
        b = s.post(f"{BASE_URL}/api/worldforge/world", json=body, timeout=TIMEOUT).json()
        assert a == b
        # cosmos must have some non-void biomes among "spiral|elliptical|nebula|cluster|quasar|filament"
        biomes = {d["biome"] for d in a["distribution"]}
        assert biomes - {"void"}, "cosmos should have non-void objects"


# ── REGION BACK-COMPAT ─────────────────────────────────────────────────────
class TestRegionBackCompat:
    def test_get_region_shape(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/region?seed=42&size=24&rx=0&ry=0&scale=0.08",
                  timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert j["scale"] == "region"
        for k in ("name", "grid", "distribution", "rivers", "pois", "stats"):
            assert k in j

    def test_post_region_matches_get(self, s):
        body = {"seed": 314, "size": 16, "rx": 1, "ry": 1, "scale": 0.08}
        a = s.post(f"{BASE_URL}/api/worldforge/region", json=body, timeout=TIMEOUT).json()
        b = s.get(f"{BASE_URL}/api/worldforge/region"
                  f"?seed=314&size=16&rx=1&ry=1&scale=0.08", timeout=TIMEOUT).json()
        assert a == b


# ── CUSTOMIZATION ENDPOINTS ────────────────────────────────────────────────
class TestCustomization:
    def test_options(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/options", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert isinstance(j["sliders"], list) and len(j["sliders"]) >= 16
        assert isinstance(j["feature_toggles"], list) and len(j["feature_toggles"]) >= 12
        slider_keys = {sl["key"] for sl in j["sliders"]}
        for k in ("size", "sea_level", "mountain_level", "moisture_bias",
                  "temperature_bias", "river_density", "settlement_density"):
            assert k in slider_keys
        toggle_keys = {t["key"] for t in j["feature_toggles"]}
        for k in ("cave_system", "city", "mine", "ghost_town"):
            assert k in toggle_keys
        assert isinstance(j["palettes"], list) and len(j["palettes"]) >= 8
        assert isinstance(j["climates"], list) and len(j["climates"]) >= 8
        assert isinstance(j["scales"], list) and len(j["scales"]) == 5

    def test_presets_100plus(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/presets", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert j["total"] >= 100, f"expected >=100 presets got {j['total']}"
        for p in j["presets"][:3]:
            for k in ("id", "name", "scale", "palette", "climate", "features", "seed"):
                assert k in p

    def test_palettes_endpoint(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/palettes", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert isinstance(j["palettes"], list) and len(j["palettes"]) >= 8
        assert isinstance(j["climates"], list)
        assert isinstance(j["structures"], list)

    def test_scales_endpoint(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/scales", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert j["count"] == 5
        ids = {sc["id"] for sc in j["scales"]}
        assert ids == {"region", "planet", "system", "galaxy", "cosmos"}

    def test_feature_toggle_changes_pois(self, s):
        """Enabling realistic structures should produce those POI kinds."""
        body = {"scale": "region", "seed": 555, "size": 40,
                "settlement_density": 2.0,
                "features": {"city": True, "cave_system": True, "mine": True,
                             "ghost_town": True, "village": True}}
        r = s.post(f"{BASE_URL}/api/worldforge/world", json=body, timeout=TIMEOUT)
        assert r.status_code == 200
        kinds = {p["kind"] for p in r.json()["pois"]}
        # at least one of the explicitly toggled structures must appear (in addition to capital)
        assert kinds & {"city", "cave_system", "mine", "ghost_town"}, f"no toggled structure placed: {kinds}"


# ── VAULT BRIDGE ───────────────────────────────────────────────────────────
class TestVaultBridge:
    def test_sources_list(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/sources?limit=20", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        assert isinstance(j["games"], list)

    def test_from_game_saves_to_vault(self, s, mongo):
        # find a playable to forge from
        sr = s.get(f"{BASE_URL}/api/worldforge/sources?limit=30", timeout=TIMEOUT).json()
        playables = [g for g in sr["games"] if g["source"] == "playable"]
        if not playables:
            pytest.skip("no playable sources available")
        gid = playables[0]["id"]
        before = mongo.codedock_vault.assets.count_documents({"tags": "WG"})
        r = s.post(f"{BASE_URL}/api/worldforge/from-game",
                   json={"source": "playable", "source_id": gid, "save": True},
                   timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["saved"] is True, j
        assert j["vault_id"] and isinstance(j["vault_id"], str)
        assert j["world_id"] and isinstance(j["world_id"], str)
        assert j["world"]["name"]
        assert j["world"]["scale"] in ("region", "planet", "system", "galaxy", "cosmos")
        assert isinstance(j["parsed_config"]["features"], list)
        # mongo verification
        after = mongo.codedock_vault.assets.count_documents({"tags": "WG"})
        assert after == before + 1, f"vault asset not written (before={before} after={after})"
        asset = mongo.codedock_vault.assets.find_one({"id": j["vault_id"]})
        assert asset is not None
        assert "WG" in asset["tags"] and "WORLD GENERATED" in asset["tags"]
        assert asset["name"].startswith("(WG) ")
        # persist for the next tests
        pytest.world_id_persist = j["world_id"]
        pytest.vault_id_persist = j["vault_id"]

    def test_from_game_bad_id(self, s):
        r = s.post(f"{BASE_URL}/api/worldforge/from-game",
                   json={"source": "playable", "source_id": "DEFINITELY_NOT_A_REAL_PID", "save": False},
                   timeout=TIMEOUT)
        assert r.status_code == 404

    def test_from_game_missing_id(self, s):
        r = s.post(f"{BASE_URL}/api/worldforge/from-game",
                   json={"source": "playable", "source_id": "", "save": False},
                   timeout=TIMEOUT)
        assert r.status_code == 400

    def test_worlds_list_and_fetch(self, s):
        wid = getattr(pytest, "world_id_persist", None)
        if not wid:
            pytest.skip("from_game test did not run")
        lr = s.get(f"{BASE_URL}/api/worldforge/worlds?limit=10", timeout=TIMEOUT)
        assert lr.status_code == 200
        worlds = lr.json()["worlds"]
        assert any(w["world_id"] == wid for w in worlds), "world not in /worlds list"
        gr = s.get(f"{BASE_URL}/api/worldforge/worlds/{wid}", timeout=TIMEOUT)
        assert gr.status_code == 200
        gj = gr.json()
        assert gj["meta"]["world_id"] == wid
        assert isinstance(gj["world"]["grid"], list)
        assert gj["world"]["name"] == gj["meta"]["name"]

    def test_world_fetch_404(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/worlds/no-such-world-id-xyz", timeout=TIMEOUT)
        assert r.status_code == 404


# ── AI LORE (LIVE LLM, single cosmic call) ─────────────────────────────────
class TestLoreCosmic:
    @pytest.mark.timeout(120)
    def test_lore_cosmos_scale(self, s):
        r = s.post(f"{BASE_URL}/api/worldforge/lore",
                   json={"seed": 1337, "size": 24, "rx": 0, "ry": 0, "scale": 0.07,
                         "world_scale": "galaxy", "palette": "twilight", "climate": "temperate"},
                   timeout=90)
        assert r.status_code == 200, r.text
        j = r.json()
        if "error" in j:
            pytest.fail(f"lore returned error: {j['error']} model={j.get('model')}")
        assert isinstance(j.get("name"), str) and len(j["name"]) >= 3
        assert isinstance(j.get("lore"), str) and len(j["lore"]) > 30
        assert j.get("scale") == "galaxy"
        assert isinstance(j.get("model"), str) and len(j["model"]) > 0


# ── CLEANUP ───────────────────────────────────────────────────────────────
def test_zzz_cleanup(mongo):
    """Remove the WG asset + worldforge_worlds entry created in this run."""
    wid = getattr(pytest, "world_id_persist", None)
    vid = getattr(pytest, "vault_id_persist", None)
    if vid:
        mongo.codedock_vault.assets.delete_one({"id": vid})
    if wid:
        # default DB is test_database
        from os import environ
        db = mongo[environ.get("DB_NAME", "test_database")]
        db.worldforge_worlds.delete_one({"world_id": wid})
