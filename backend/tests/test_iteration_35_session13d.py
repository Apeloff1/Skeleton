"""
Session 13d (iteration 35) — Worldforge biodiversity + natural hazards + per-POI
economy + cartographic trade-road overlay + LLM Köppen-aware lore.

Tests:
- Region payload exposes biodiversity{index, evenness, richness, rating}
  and hazards{overall, levels, ratings{seismic, volcanic, flood, drought,
  wildfire}.score/label} and pois[].economy.
- stats contains biodiversity + hazard.
- Determinism: same seed → identical biodiversity, hazards, POI economy.
- /render cartographic still 200 image/png with non-trivial bytes (roads drawn).
- Cosmic exclusion: galaxy + system scales must NOT include biodiversity/hazards.
- Regression: koppen{} + routes[] still present in region; /options ≥12 toggles;
  /biomes count 16; /name-key works; no fantasy tokens.
- LLM lore: mentions the Köppen class (code or name like 'ET' / 'Tundra' /
  'Köppen').
"""
from __future__ import annotations

import os
import re
import time
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
            or os.environ.get("EXPO_BACKEND_URL", "").rstrip("/"))
WF = f"{BASE_URL}/api/worldforge"

VALID_KOPPEN = {"Af", "Am", "Aw", "BWh", "BWk", "BSh", "BSk",
                "Cfa", "Cfb", "Cfc", "Csa", "Csb", "Cwa", "Cwb",
                "Dfa", "Dfb", "Dfc", "Dfd", "Dsa", "Dsb", "Dsc",
                "Dwa", "Dwb", "Dwc", "Dwd", "ET", "EF", "H"}
HAZARD_LEVELS = {"none", "low", "moderate", "high"}
BIO_RATINGS = {"barren", "sparse", "low", "moderate", "rich"}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── 1. biodiversity / hazards / economy shape ─────────────────────────
class TestBiodiversityHazardsEconomy:
    def test_region_has_biodiversity(self, session):
        r = session.get(f"{WF}/region", params={"seed": 1337, "size": 48}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        bio = d.get("biodiversity")
        assert bio is not None, "missing biodiversity"
        for k in ("index", "evenness", "richness", "rating"):
            assert k in bio, f"biodiversity missing {k}"
        assert isinstance(bio["index"], (int, float))
        assert isinstance(bio["evenness"], (int, float))
        assert isinstance(bio["richness"], int)
        assert bio["rating"] in BIO_RATINGS, bio["rating"]
        # stats mirror
        assert "biodiversity" in d["stats"], "stats.biodiversity missing"
        assert d["stats"]["biodiversity"] == bio["index"]

    def test_region_has_hazards(self, session):
        r = session.get(f"{WF}/region", params={"seed": 1337, "size": 48}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        hz = d.get("hazards")
        assert hz is not None, "missing hazards"
        assert hz["overall"] in HAZARD_LEVELS, hz["overall"]
        assert isinstance(hz["levels"], list) and set(hz["levels"]) == HAZARD_LEVELS
        ratings = hz.get("ratings")
        assert isinstance(ratings, dict)
        for key in ("seismic", "volcanic", "flood", "drought", "wildfire"):
            assert key in ratings, f"hazards.ratings missing {key}"
            entry = ratings[key]
            assert "score" in entry and "label" in entry
            assert isinstance(entry["score"], int)
            assert 0 <= entry["score"] <= 3, f"{key} score out of 0-3: {entry['score']}"
            assert entry["label"] in HAZARD_LEVELS
            # label must align with levels[score]
            assert entry["label"] == hz["levels"][entry["score"]]
        # stats.hazard mirror
        assert d["stats"].get("hazard") == hz["overall"]

    def test_pois_each_have_economy(self, session):
        r = session.get(f"{WF}/region", params={"seed": 1337, "size": 48}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        pois = d.get("pois") or []
        assert len(pois) >= 1, "region must produce at least 1 POI"
        for p in pois:
            assert "economy" in p, f"poi {p.get('name')} missing economy"
            assert isinstance(p["economy"], str) and p["economy"].strip()


# ── 2. determinism ─────────────────────────────────────────────────────
class TestDeterminism13d:
    def test_same_seed_identical_bio_hazards_economy(self, session):
        a = session.get(f"{WF}/region", params={"seed": 1337, "size": 48}, timeout=30).json()
        b = session.get(f"{WF}/region", params={"seed": 1337, "size": 48}, timeout=30).json()
        assert a["biodiversity"] == b["biodiversity"], "biodiversity not deterministic"
        assert a["hazards"] == b["hazards"], "hazards not deterministic"
        eco_a = [(p["name"], p["economy"]) for p in a["pois"]]
        eco_b = [(p["name"], p["economy"]) for p in b["pois"]]
        assert eco_a == eco_b, "per-POI economy not deterministic"


# ── 3. cartographic render (roads drawn) ──────────────────────────────
class TestRenderCartographic:
    def test_cartographic_returns_png_nontrivial(self, session):
        r = session.get(
            f"{WF}/render",
            params={"scale": "region", "seed": 1337, "size": 44, "mode": "cartographic"},
            timeout=120,
        )
        assert r.status_code == 200, r.text[:200]
        assert r.headers["content-type"].startswith("image/png")
        # roads + map should be larger than a trivial blank PNG (~5KB)
        assert len(r.content) > 50_000, f"png suspiciously small: {len(r.content)} bytes"


# ── 4. cosmic exclusion ───────────────────────────────────────────────
class TestCosmicExclusion13d:
    def test_galaxy_no_bio_no_hazards(self, session):
        r = session.post(f"{WF}/world", json={"scale": "galaxy", "seed": 99}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["scale"] == "galaxy"
        assert "biodiversity" not in d, "galaxy must not include biodiversity"
        assert "hazards" not in d, "galaxy must not include hazards"
        assert "biodiversity" not in d["stats"]
        assert "hazard" not in d["stats"]

    def test_system_no_bio_no_hazards(self, session):
        r = session.post(f"{WF}/world", json={"scale": "system", "seed": 7}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["scale"] == "system"
        assert "biodiversity" not in d
        assert "hazards" not in d
        assert "biodiversity" not in d["stats"]
        assert "hazard" not in d["stats"]


# ── 5. regression: koppen + routes + options + biomes + name-key ──────
class TestRegression13d:
    def test_koppen_and_routes_still_present(self, session):
        r = session.get(f"{WF}/region", params={"seed": 1337, "size": 48}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("koppen", {}).get("code") in VALID_KOPPEN
        assert isinstance(d.get("routes"), list)

    def test_options_ge_12_toggles(self, session):
        r = session.get(f"{WF}/options", timeout=20)
        assert r.status_code == 200
        toggles = r.json().get("feature_toggles", [])
        assert len(toggles) >= 12

    def test_biomes_count_16(self, session):
        r = session.get(f"{WF}/biomes", timeout=20)
        assert r.status_code == 200
        assert r.json()["count"] == 16

    def test_name_key_no_fantasy(self, session):
        body = {"seed": 1337, "size": 32, "world_scale": "region"}
        r = session.post(f"{WF}/name-key", json=body, timeout=30)
        assert r.status_code == 200, r.text
        entries = r.json().get("entries", [])
        assert len(entries) >= 1
        banned = {"orc", "elf", "dwarf", "wyrm", "drake", "rune", "mythril", "shire"}
        for e in entries:
            assert not any(b in e["name"].lower() for b in banned), e["name"]


# ── 6. LLM lore references the Köppen climate class ──────────────────
class TestLoreKoppenAware:
    def test_lore_mentions_koppen(self, session):
        body = {"seed": 1337, "size": 48, "world_scale": "region"}
        t0 = time.time()
        r = session.post(f"{WF}/lore", json=body, timeout=90)
        dt = time.time() - t0
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        # If LLM completely returned nothing, the route returns {error:...}
        if "error" in d and not d.get("lore"):
            pytest.skip(f"LLM lore unavailable: {d.get('error')}")
        lore = (d.get("lore") or "").strip()
        assert lore, "empty lore"
        # Build the expected anchor tokens from the actual koppen for that seed
        kop_get = session.get(f"{WF}/region", params={"seed": 1337, "size": 48}, timeout=30).json().get("koppen", {})
        code = (kop_get.get("code") or "").lower()
        name = (kop_get.get("name") or "").lower()
        text = lore.lower()
        # Accept any anchor: the Köppen code, climate name, or the literal word 'köppen'/'koppen'
        anchors = [a for a in [code, name, "köppen", "koppen"] if a]
        hits = [a for a in anchors if a and a in text]
        print(f"lore (len={len(lore)}, t={dt:.1f}s) anchors_hit={hits} anchors_tried={anchors}")
        assert hits, f"lore does not reference Köppen class. lore={lore[:400]!r}"
