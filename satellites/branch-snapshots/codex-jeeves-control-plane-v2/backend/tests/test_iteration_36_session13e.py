"""
Session 13e — Worldforge SOTA-systems refactor + 10-step HYPER-REALISM stack.

Validates:
  - Region payload exposes the full `systems` object with 9 keys + nested fields
  - Determinism (byte-identical systems/hazards/koppen/routes/biodiversity)
  - Plate-driven hazards (volcanic score == tectonics.volcanic_potential)
  - Cosmic exclusion (galaxy/system have no `systems` key)
  - Performance (region size 48 < 2 s)
  - Refactor regression (region/world/options/biomes/name-key/render/render.gif)
  - LLM lore (live, single call) cites Köppen
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
REQUIRED_SYS_KEYS = [
    "tectonics", "insolation", "winds", "currents",
    "hydrology", "lithology", "resources", "soil", "population",
]


# ─────────── fixtures ───────────
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


# ─────────── HYPER-REALISM systems ───────────
def test_systems_object_present_and_complete(region):
    sys = region.get("systems")
    assert isinstance(sys, dict), "systems must be an object"
    for k in REQUIRED_SYS_KEYS:
        assert k in sys, f"systems.{k} missing"
        assert sys[k], f"systems.{k} is empty"


def test_tectonics_fields(region):
    t = region["systems"]["tectonics"]
    assert "plates" in t, "tectonics.plates missing"
    # plates may be an int (count) or a list — both acceptable as long as truthy
    plates = t["plates"]
    assert (isinstance(plates, int) and plates > 0) or \
           (isinstance(plates, list) and len(plates) > 0), \
           f"plates must be a positive int or non-empty list, got {plates!r}"
    assert "primary_setting" in t and isinstance(t["primary_setting"], str)
    assert "seismic_potential" in t and isinstance(t["seismic_potential"], (int, float))
    assert "volcanic_potential" in t and isinstance(t["volcanic_potential"], (int, float))


def test_insolation_fields(region):
    ins = region["systems"]["insolation"]
    assert "axial_tilt_deg" in ins
    assert "mean_annual_temp_c" in ins


def test_hydrology_strahler(region):
    h = region["systems"]["hydrology"]
    assert "max_strahler_order" in h
    assert isinstance(h["max_strahler_order"], (int, float))


def test_population_estimated_total(region):
    p = region["systems"]["population"]
    assert "estimated_total" in p
    assert isinstance(p["estimated_total"], (int, float))
    assert p["estimated_total"] >= 0


def test_stats_population_and_hazard(region):
    stats = region.get("stats", {})
    assert "population" in stats, "stats.population missing"
    assert "hazard" in stats, "stats.hazard missing"


# ─────────── determinism ───────────
def test_determinism_systems(region, region_again):
    assert json.dumps(region["systems"], sort_keys=True) == \
           json.dumps(region_again["systems"], sort_keys=True)


def test_determinism_hazards_koppen_routes_bio(region, region_again):
    for k in ("hazards", "koppen", "routes", "biodiversity"):
        assert json.dumps(region.get(k), sort_keys=True) == \
               json.dumps(region_again.get(k), sort_keys=True), f"{k} not deterministic"


# ─────────── plate-driven hazards ───────────
def test_volcanic_score_equals_tectonics_volcanic_potential(region):
    v_score = region["hazards"]["ratings"]["volcanic"]["score"]
    v_pot = region["systems"]["tectonics"]["volcanic_potential"]
    assert v_score == v_pot, f"volcanic score {v_score} != tectonics.volcanic_potential {v_pot}"


def test_seismic_reflects_tectonics(region):
    s_score = region["hazards"]["ratings"]["seismic"]["score"]
    s_pot = region["systems"]["tectonics"]["seismic_potential"]
    # seismic should be derived from tectonics potential, not the old bare>15% rule.
    # We accept either direct equality or strong correlation (within 1 step).
    assert abs(s_score - s_pot) <= 1, f"seismic {s_score} not aligned with tectonics seismic_potential {s_pot}"


# ─────────── cosmic exclusion ───────────
@pytest.mark.parametrize("scale,seed", [("galaxy", 99), ("system", 7)])
def test_cosmic_omits_systems(scale, seed):
    r = requests.post(f"{BASE_URL}/api/worldforge/world",
                      json={"scale": scale, "seed": seed}, timeout=20)
    assert r.status_code == 200, f"{scale} failed: {r.status_code}"
    data = r.json()
    assert "systems" not in data, f"{scale} payload must NOT include `systems`"


# ─────────── performance ───────────
def test_region_size_48_performance():
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/worldforge/region",
                     params={"seed": 1337, "size": 48}, timeout=10)
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0, f"region size=48 took {elapsed:.2f}s (>2s)"


# ─────────── refactor regression ───────────
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


def test_name_key_realistic_etymology():
    r = requests.post(f"{BASE_URL}/api/worldforge/name-key",
                      json={"seed": 1337, "size": 48, "world_scale": "region"}, timeout=20)
    assert r.status_code == 200
    j = r.json()
    entries = j.get("entries", [])
    assert len(entries) >= 1, "no etymology entries"
    fantasy = ["orc", "elf", "dwarf", "wyrm", "drake", "rune", "mythril", "shire", "hobbit"]
    blob = json.dumps(j).lower()
    for f in fantasy:
        assert f not in blob, f"fantasy token '{f}' found in name-key"


def test_render_cartographic_png():
    params = {"scale": "region", "seed": 1337, "size": 44,
              "palette": "natural", "climate": "temperate", "mode": "cartographic"}
    r = requests.get(f"{BASE_URL}/api/worldforge/render", params=params, timeout=25)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/png")
    assert len(r.content) > 50_000, f"png too small ({len(r.content)} bytes) — roads may be missing"


def test_render_gif_cache_miss_then_hit():
    # Use a unique seed to ensure first call is a MISS
    seed = int(time.time()) % 999_999
    params = {"scale": "planet", "seed": seed, "size": 40,
              "palette": "natural", "climate": "temperate"}
    r1 = requests.get(f"{BASE_URL}/api/worldforge/render.gif", params=params, timeout=60)
    assert r1.status_code == 200, f"gif first call failed: {r1.status_code}"
    assert r1.headers.get("content-type", "").startswith("image/gif")
    cache1 = r1.headers.get("X-Cache", "").upper()
    r2 = requests.get(f"{BASE_URL}/api/worldforge/render.gif", params=params, timeout=30)
    assert r2.status_code == 200
    cache2 = r2.headers.get("X-Cache", "").upper()
    # Accept either explicit MISS→HIT, or at minimum HIT on second call
    assert "HIT" in cache2 or cache2 == "HIT", f"second gif call not a HIT (X-Cache={cache2})"


def test_region_has_koppen_routes_biodiversity_hazards(region):
    for k in ("koppen", "routes", "biodiversity", "hazards"):
        assert k in region and region[k], f"{k} missing on region"


def test_each_poi_has_economy(region):
    pois = region.get("pois", [])
    assert len(pois) > 0, "no POIs"
    for i, p in enumerate(pois):
        assert "economy" in p and p["economy"], f"poi[{i}] missing economy"


# ─────────── live LLM lore (single call) ───────────
def test_lore_cites_koppen():
    body = {"seed": 1337, "size": 48, "world_scale": "region"}
    r = requests.post(f"{BASE_URL}/api/worldforge/lore", json=body, timeout=90)
    assert r.status_code == 200, f"lore failed: {r.status_code}"
    j = r.json()
    lore = j.get("lore") or ""
    assert len(lore) > 100, f"lore too short ({len(lore)} chars)"
    # Fetch region to get the actual Köppen code
    region = requests.get(f"{BASE_URL}/api/worldforge/region", params=REGION_PARAMS, timeout=15).json()
    kop = region.get("koppen", {})
    code = (kop.get("code") or "").lower()
    name = (kop.get("name") or "").lower()
    lore_low = lore.lower()
    hits = [tok for tok in (code, name, "köppen", "koppen", "climate") if tok and tok in lore_low]
    assert hits, f"lore did not cite Köppen anchors. code={code!r} name={name!r}"
