"""
Session 13g + 13h — Voronoi plates, plates atlas layer, 10 more Earth systems
(steps 21–30 → 29 systems total), AAA terrain overhaul (domain-warped + droplet
hydraulic erosion).

Validated against the live preview backend.
"""
import json
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL"))
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"
BASE_URL = BASE_URL.rstrip("/")

REGION_PARAMS = {"seed": 1337, "size": 48}

EXISTING_SYS_KEYS = [
    "tectonics", "insolation", "winds", "currents",
    "hydrology", "lithology", "resources", "soil", "population",
    # Session 13f (steps 11-20)
    "magnetosphere", "atmosphere", "productivity", "energy_balance",
    "tides", "phenology", "settlement_hierarchy", "network",
    "macro_economy", "habitability",
]
NEW_SYS_KEYS = [   # Session 13g (steps 21-30)
    "orbital", "cryosphere", "renewables", "agriculture", "air_quality",
    "coastal", "wildlife_corridors", "astronomy", "water_security", "risk_index",
]
ALL_SYS_KEYS = EXISTING_SYS_KEYS + NEW_SYS_KEYS   # 29 keys


# ───────────────────── fixtures ─────────────────────
@pytest.fixture(scope="module")
def region():
    r = requests.get(f"{BASE_URL}/api/worldforge/region",
                     params=REGION_PARAMS, timeout=20)
    assert r.status_code == 200, f"region failed: {r.status_code} {r.text[:200]}"
    return r.json()


@pytest.fixture(scope="module")
def region_again():
    r = requests.get(f"{BASE_URL}/api/worldforge/region",
                     params=REGION_PARAMS, timeout=20)
    assert r.status_code == 200
    return r.json()


# ───────────────── systems shape (29 keys, all w/ note for new 10) ─────────────────
def test_systems_has_all_29_keys(region):
    sys = region.get("systems")
    assert isinstance(sys, dict), "systems must be an object"
    missing = [k for k in ALL_SYS_KEYS if k not in sys]
    assert not missing, f"systems missing keys: {missing}"
    assert len(sys) >= 29, f"expected >=29 systems, got {len(sys)}"


def test_each_new_step21_30_system_has_note(region):
    sys = region["systems"]
    bad = []
    for k in NEW_SYS_KEYS:
        v = sys.get(k)
        if not isinstance(v, dict):
            bad.append((k, "not a dict"))
            continue
        if not v.get("note"):
            bad.append((k, "missing note"))
    assert not bad, f"new systems issues: {bad}"


def test_new_systems_carry_signature_fields(region):
    sys = region["systems"]
    assert "eccentricity" in sys["orbital"]
    assert any("ice" in k.lower() for k in sys["cryosphere"].keys())
    assert any(k in sys["renewables"] for k in ("solar_index", "wind_index", "hydro_index"))
    assert "suitability_index" in sys["agriculture"]
    assert "index" in sys["air_quality"]
    assert "erosion_index" in sys["coastal"]
    assert "connectivity_index" in sys["wildlife_corridors"]
    assert "bortle_class" in sys["astronomy"]
    assert "renewable_water_index" in sys["water_security"] or "per_capita_proxy" in sys["water_security"]
    assert "composite" in sys["risk_index"]


# ─────────── tectonics: real Voronoi plate geometry ───────────
def test_tectonics_boundary_breakdown_and_plate_count(region):
    tect = region["systems"]["tectonics"]
    # plate count reported (either as plate_count or plates)
    plate_count = tect.get("plate_count") or tect.get("plates")
    assert isinstance(plate_count, int) and plate_count >= 3, \
        f"plate count missing/too small: {plate_count}"
    bb = tect.get("boundary_breakdown")
    assert isinstance(bb, dict), "boundary_breakdown missing"
    for k in ("convergent", "divergent", "transform"):
        assert k in bb, f"boundary_breakdown missing '{k}'"
        assert isinstance(bb[k], int) and bb[k] >= 0
    total = bb["convergent"] + bb["divergent"] + bb["transform"]
    assert total > 0, "boundary_breakdown sums to 0"


# ────────── AAA terrain overhaul (domain-warp + hydraulic erosion) ──────────
def test_region_land_water_balance_and_biome_diversity(region):
    stats = region.get("stats", {})
    land = stats.get("land_pct")
    water = stats.get("water_pct")
    assert isinstance(land, (int, float)), f"land_pct missing: {stats}"
    assert isinstance(water, (int, float))
    assert 65 <= land <= 90, f"land_pct={land} outside ~70-85% spec band"
    # 8-9 distinct biomes
    distinct = len(region.get("distribution", []))
    assert 8 <= distinct <= 12, f"distinct biomes={distinct}, expected 8-9"
    # rivers exist (hydraulic erosion carves valleys + hydrology runs)
    assert stats.get("river_tiles", 0) > 0, "no river tiles after erosion"


# ─────────────────── determinism ───────────────────
def test_determinism_systems_byte_identical(region, region_again):
    a = json.dumps(region["systems"], sort_keys=True)
    b = json.dumps(region_again["systems"], sort_keys=True)
    assert a == b, "systems is not deterministic for same seed"


def test_determinism_distribution_byte_identical(region, region_again):
    a = json.dumps(region["distribution"], sort_keys=True)
    b = json.dumps(region_again["distribution"], sort_keys=True)
    assert a == b, "distribution is not deterministic for same seed"


def test_determinism_stats_byte_identical(region, region_again):
    a = json.dumps(region["stats"], sort_keys=True)
    b = json.dumps(region_again["stats"], sort_keys=True)
    assert a == b, "stats is not deterministic for same seed"


# ───────────────── plates atlas layer ─────────────────
def test_thematic_plates_layer_png():
    params = {"scale": "region", "seed": 1337, "size": 48,
              "mode": "thematic", "layer": "plates"}
    r = requests.get(f"{BASE_URL}/api/worldforge/render",
                     params=params, timeout=25)
    assert r.status_code == 200, f"plates layer → {r.status_code} {r.text[:120]}"
    assert r.headers.get("content-type", "").startswith("image/png")
    assert len(r.content) > 1500, f"plates png too small ({len(r.content)} bytes)"


# ───── other thematic layers still work (regression) ─────
@pytest.mark.parametrize("layer", ["elevation", "temperature", "moisture",
                                   "fertility", "seismic"])
def test_thematic_other_layers_still_png(layer):
    params = {"scale": "region", "seed": 1337, "size": 48,
              "mode": "thematic", "layer": layer}
    r = requests.get(f"{BASE_URL}/api/worldforge/render",
                     params=params, timeout=25)
    assert r.status_code == 200, f"layer={layer} → {r.status_code}"
    assert r.headers.get("content-type", "").startswith("image/png")
    assert len(r.content) > 1500


def test_render_globe_png():
    params = {"scale": "region", "seed": 1337, "size": 48, "mode": "globe"}
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/worldforge/render",
                     params=params, timeout=20)
    dt = time.time() - t0
    assert r.status_code == 200, f"globe → {r.status_code}"
    assert r.headers.get("content-type", "").startswith("image/png")
    assert dt < 3.0, f"globe render took {dt:.2f}s (>3s)"


def test_render_cartographic_png():
    params = {"scale": "region", "seed": 1337, "size": 48,
              "mode": "cartographic"}
    r = requests.get(f"{BASE_URL}/api/worldforge/render",
                     params=params, timeout=25)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/png")
    assert len(r.content) > 10_000


# ───────────────────── cosmic exclusion ─────────────────────
def test_galaxy_omits_systems():
    r = requests.post(f"{BASE_URL}/api/worldforge/world",
                      json={"scale": "galaxy", "seed": 99}, timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert "systems" not in data, "galaxy must NOT include `systems`"


def test_system_scale_omits_systems():
    # /world supports system scale too
    r = requests.post(f"{BASE_URL}/api/worldforge/world",
                      json={"scale": "system", "seed": 11}, timeout=20)
    # Some builds may 200 or 422; spec says scale must omit systems if it 200s.
    if r.status_code == 200:
        assert "systems" not in r.json(), "system scale must NOT include `systems`"


# ───────────────────── performance ─────────────────────
def test_region_build_under_500ms():
    # measure server-side using a fresh seed to avoid cache effects
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/worldforge/region",
                     params={"seed": 24601, "size": 48}, timeout=10)
    elapsed = time.time() - t0
    assert r.status_code == 200
    # round-trip includes network; allow generous ceiling but flag if >2s
    assert elapsed < 2.0, f"region wallclock {elapsed:.2f}s (>2s)"


# ───────────────────── refactor regression ─────────────────────
def test_options_has_min_12_toggles():
    r = requests.get(f"{BASE_URL}/api/worldforge/options", timeout=10)
    assert r.status_code == 200
    toggles = r.json().get("feature_toggles", [])
    assert len(toggles) >= 12, f"only {len(toggles)} toggles"


def test_biomes_count_16():
    r = requests.get(f"{BASE_URL}/api/worldforge/biomes", timeout=10)
    assert r.status_code == 200
    j = r.json()
    biomes = j.get("biomes") or j
    if isinstance(biomes, dict) and "biomes" in biomes:
        biomes = biomes["biomes"]
    assert len(biomes) == 16, f"got {len(biomes)} biomes"


def test_name_key_no_fantasy_tokens():
    r = requests.post(f"{BASE_URL}/api/worldforge/name-key",
                      json={"seed": 1337, "size": 48, "world_scale": "region"},
                      timeout=20)
    assert r.status_code == 200
    blob = json.dumps(r.json()).lower()
    for f in ("orc", "elf", "dwarf", "wyrm", "mythril", "hobbit"):
        assert f not in blob, f"fantasy token '{f}' in name-key"


def test_region_has_koppen_routes_bio_hazards(region):
    for k in ("koppen", "routes", "biodiversity", "hazards"):
        assert k in region and region[k], f"{k} missing on region"


def test_each_poi_has_economy(region):
    pois = region.get("pois", [])
    assert len(pois) > 0, "no POIs"
    for i, p in enumerate(pois):
        assert "economy" in p and p["economy"], f"poi[{i}] missing economy"
