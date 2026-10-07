"""
Session 13f — Worldforge hyper-realism Earth-systems (steps 11–20) + GIS thematic atlas.

Validates:
  - Region payload exposes 19-key `systems` object (9 existing + 10 new)
  - habitability.index ∈ [0,100]; atmosphere.breathable is bool; new systems carry 'note'
  - Determinism (byte-identical systems)
  - GIS thematic render: mode=thematic & layer ∈ {elevation,temperature,moisture,fertility,seismic}
    each returns 200 image/png; unknown layer falls back gracefully
  - Cosmic exclusion: galaxy still has NO `systems`
  - Performance: region size=48 < 2 s
  - Refactor/regression: region/world/options(>=12)/biomes(16)/name-key/render cartographic/render.gif
  - koppen, routes, biodiversity, hazards present; poi.economy present
"""
import json
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"
BASE_URL = BASE_URL.rstrip("/")

REGION_PARAMS = {"seed": 1337, "size": 48}

EXISTING_SYS_KEYS = [
    "tectonics", "insolation", "winds", "currents",
    "hydrology", "lithology", "resources", "soil", "population",
]
NEW_SYS_KEYS = [
    "magnetosphere", "atmosphere", "productivity", "energy_balance",
    "tides", "phenology", "settlement_hierarchy", "network",
    "macro_economy", "habitability",
]
ALL_SYS_KEYS = EXISTING_SYS_KEYS + NEW_SYS_KEYS


# ───────────────────── fixtures ─────────────────────
@pytest.fixture(scope="module")
def region():
    r = requests.get(f"{BASE_URL}/api/worldforge/region", params=REGION_PARAMS, timeout=20)
    assert r.status_code == 200, f"region failed: {r.status_code} {r.text[:200]}"
    return r.json()


@pytest.fixture(scope="module")
def region_again():
    r = requests.get(f"{BASE_URL}/api/worldforge/region", params=REGION_PARAMS, timeout=20)
    assert r.status_code == 200
    return r.json()


# ───────────────── systems shape (19 keys) ─────────────────
def test_systems_has_all_19_keys(region):
    sys = region.get("systems")
    assert isinstance(sys, dict), "systems must be an object"
    missing = [k for k in ALL_SYS_KEYS if k not in sys]
    assert not missing, f"systems missing keys: {missing}"
    assert len(sys) >= 19, f"expected ≥19 systems, got {len(sys)}"


def test_habitability_index_bounds(region):
    h = region["systems"]["habitability"]
    assert "index" in h
    idx = h["index"]
    assert isinstance(idx, (int, float))
    assert 0 <= idx <= 100, f"habitability.index out of range: {idx}"
    assert "class" in h and isinstance(h["class"], str)


def test_atmosphere_breathable_is_bool(region):
    a = region["systems"]["atmosphere"]
    assert "breathable" in a
    assert isinstance(a["breathable"], bool), f"breathable must be bool, got {type(a['breathable']).__name__}"
    assert "o2_pct" in a and isinstance(a["o2_pct"], (int, float))
    assert "surface_pressure_bar" in a


def test_each_new_system_has_note(region):
    sys = region["systems"]
    # Note: settlement_hierarchy, network may or may not always carry note;
    # spec says "each new system has a 'note'" so we assert for all 10.
    missing_note = [k for k in NEW_SYS_KEYS
                    if not (isinstance(sys.get(k), dict) and sys[k].get("note"))]
    assert not missing_note, f"new systems missing 'note': {missing_note}"


def test_magnetosphere_fields(region):
    m = region["systems"]["magnetosphere"]
    assert "dipole_moment_earths" in m
    assert "field_strength" in m


def test_productivity_and_energy_fields(region):
    p = region["systems"]["productivity"]
    assert "npp_g_m2_yr" in p
    e = region["systems"]["energy_balance"]
    assert "bond_albedo" in e and "equilibrium_temp_c" in e


def test_tides_phenology_hierarchy_network_macro(region):
    sys = region["systems"]
    assert "moons" in sys["tides"]
    assert "growing_season_days" in sys["phenology"]
    assert "primacy_index" in sys["settlement_hierarchy"]
    assert "nodes" in sys["network"] and "corridors" in sys["network"]
    assert "est_gdp_proxy" in sys["macro_economy"]


# ───────────────────── determinism ─────────────────────
def test_determinism_systems(region, region_again):
    a = json.dumps(region["systems"], sort_keys=True)
    b = json.dumps(region_again["systems"], sort_keys=True)
    assert a == b, "systems is not deterministic for same seed"


# ───────────────────── GIS thematic atlas ─────────────────────
@pytest.mark.parametrize("layer", ["elevation", "temperature", "moisture", "fertility", "seismic"])
def test_thematic_layer_returns_png(layer):
    params = {"scale": "region", "seed": 1337, "size": 48,
              "mode": "thematic", "layer": layer}
    r = requests.get(f"{BASE_URL}/api/worldforge/render", params=params, timeout=25)
    assert r.status_code == 200, f"layer={layer} → {r.status_code} {r.text[:120]}"
    ct = r.headers.get("content-type", "")
    assert ct.startswith("image/png"), f"layer={layer} ct={ct!r}"
    assert len(r.content) > 1500, f"layer={layer} png too small ({len(r.content)} bytes)"


def test_thematic_unknown_layer_falls_back():
    params = {"scale": "region", "seed": 1337, "size": 48,
              "mode": "thematic", "layer": "bogus_layer_xyz"}
    r = requests.get(f"{BASE_URL}/api/worldforge/render", params=params, timeout=25)
    assert r.status_code == 200, f"unknown layer → {r.status_code}"
    assert r.headers.get("content-type", "").startswith("image/png")
    assert len(r.content) > 1500


# ───────────────────── cosmic exclusion ─────────────────────
def test_galaxy_omits_systems():
    r = requests.post(f"{BASE_URL}/api/worldforge/world",
                      json={"scale": "galaxy", "seed": 99}, timeout=20)
    assert r.status_code == 200, f"galaxy failed: {r.status_code}"
    data = r.json()
    assert "systems" not in data, "galaxy payload must NOT include `systems`"


# ───────────────────── performance ─────────────────────
def test_region_size_48_under_2s():
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/worldforge/region",
                     params={"seed": 1337, "size": 48}, timeout=10)
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0, f"region size=48 took {elapsed:.2f}s (>2s)"


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


def test_name_key_no_fantasy():
    r = requests.post(f"{BASE_URL}/api/worldforge/name-key",
                      json={"seed": 1337, "size": 48, "world_scale": "region"}, timeout=20)
    assert r.status_code == 200
    blob = json.dumps(r.json()).lower()
    for f in ("orc", "elf", "dwarf", "wyrm", "mythril", "hobbit"):
        assert f not in blob, f"fantasy token '{f}' in name-key"


def test_render_cartographic_png():
    params = {"scale": "region", "seed": 1337, "size": 44,
              "palette": "natural", "climate": "temperate", "mode": "cartographic"}
    r = requests.get(f"{BASE_URL}/api/worldforge/render", params=params, timeout=25)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/png")
    assert len(r.content) > 10_000


def test_render_gif():
    params = {"scale": "planet", "seed": int(time.time()) % 999_999, "size": 40,
              "palette": "natural", "climate": "temperate"}
    r = requests.get(f"{BASE_URL}/api/worldforge/render.gif", params=params, timeout=60)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/gif")


def test_region_has_koppen_routes_bio_hazards(region):
    for k in ("koppen", "routes", "biodiversity", "hazards"):
        assert k in region and region[k], f"{k} missing on region"


def test_each_poi_has_economy(region):
    pois = region.get("pois", [])
    assert len(pois) > 0, "no POIs"
    for i, p in enumerate(pois):
        assert "economy" in p and p["economy"], f"poi[{i}] missing economy"
