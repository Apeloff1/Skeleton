"""
Iteration 32 — Worldforge REALISM DOCTRINE backend tests (Session 13).

Validates that fantasy/Tolkien tropes have been fully replaced with NASA-grade
scientific realism in /api/worldforge endpoints:

  • /region — POI kinds in realistic set, real-world toponyms, region name shape
  • Determinism — same seed → identical name + POIs (names + order)
  • /world (galaxy/system) — real astronomical catalogue designations
  • /options — >=12 feature_toggles with realistic keys + labels
  • /world feature toggle — explicitly toggled realistic kinds appear
  • /lore — scientific lore (no magic/monsters)
  • /quest — branching DAG, realistic factions, real fieldwork objectives
  • Regression — /biomes (16), /presets (>=100), /render still 200
"""
import os
import re
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "https://gemini-game-craft.preview.emergentagent.com").rstrip("/")
TIMEOUT = 60
LLM_TIMEOUT = 90

# Realism doctrine: allowed POI kinds (capital is the auto-promoted city/town/village)
REALISTIC_KINDS = {
    "city", "town", "village", "farmstead", "harbor", "fishing_village",
    "lighthouse", "mine", "quarry", "logging_camp", "observatory",
    "research_station", "weather_station", "ghost_town", "cave_system",
    "basecamp", "capital",
}
FANTASY_KINDS = {"castle", "dungeon", "temple", "shrine", "monolith",
                 "ruin", "watchtower", "fortress", "tower", "altar"}

# fantasy syllables/suffixes that must NOT appear in any names
FANTASY_NAME_PATTERNS = [
    r"\b\w*(?:dor|ond|iel|rim|gorn|dur|moth|wraith|drak|elf|orc|troll|mage|wyrm|rune)\w*\b",
]
FANTASY_COSMIC_SUFFIX = re.compile(r"\b(Maw|Verge|Prime|Nebula(?!.*NGC|.*Messier|.*IC|.*UGC|.*Abell|.*Caldwell|.*PGC|.*HD|.*HIP|.*Gliese|.*Kepler|.*TRAPPIST|.*Wolf|.*Ross|.*Bayer))\b")

# real astronomical catalogue tokens (for cosmic naming validation)
STAR_CATS = ("HD", "HIP", "HR", "Gliese", "Kepler", "TOI", "Wolf", "Ross", "LHS", "GJ", "TRAPPIST")
DEEPSKY_CATS = ("NGC", "Messier", "IC", "UGC", "Abell", "Caldwell", "PGC")
GREEK = ("Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta",
         "Iota", "Kappa", "Lambda", "Mu", "Nu", "Xi", "Omicron", "Sigma", "Tau", "Upsilon")


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── REGION: realistic POIs + toponyms + region name ──────────────────────────
class TestRegionRealism:
    def test_region_poi_kinds_are_realistic(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/region",
                  params={"seed": 1337, "size": 48}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        kinds = [p["kind"] for p in j["pois"]]
        assert kinds, "expected at least one POI"
        bad = [k for k in kinds if k not in REALISTIC_KINDS]
        assert not bad, f"non-realistic POI kinds present: {bad}"
        fantasy_overlap = set(kinds) & FANTASY_KINDS
        assert not fantasy_overlap, f"fantasy kinds present: {fantasy_overlap}"

    def test_region_poi_names_are_realworld(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/region",
                  params={"seed": 1337, "size": 48}, timeout=TIMEOUT)
        j = r.json()
        for p in j["pois"]:
            nm = p["name"]
            assert isinstance(nm, str) and len(nm) >= 2
            for pat in FANTASY_NAME_PATTERNS:
                assert not re.search(pat, nm, re.I), f"fantasy syllable in '{nm}'"
            # plausible real-world toponym: ASCII letters, optional space/hyphen
            assert re.fullmatch(r"[A-Za-z][A-Za-z' \-]+", nm), \
                f"non-realistic name shape: {nm!r}"

    def test_region_name_pattern(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/region",
                  params={"seed": 1337, "size": 48}, timeout=TIMEOUT)
        j = r.json()
        name = j["name"]
        # <Descriptor> <Region generic>  e.g. "Granite Basin", "Green Plateau"
        generics = {"Basin", "Plateau", "Lowlands", "Highlands", "Plains", "Valley",
                    "Range", "Coast", "Peninsula", "Delta", "Steppe", "Uplands",
                    "Watershed", "Province", "Territory", "Flats", "Massif", "Escarpment"}
        parts = name.split()
        assert len(parts) >= 2, f"unexpected region name shape: {name!r}"
        assert parts[-1] in generics, f"region name does not end in real generic: {name!r}"


# ── DETERMINISM ──────────────────────────────────────────────────────────────
class TestDeterminism:
    def test_region_same_seed_identical(self, s):
        params = {"seed": 1337, "size": 48}
        a = s.get(f"{BASE_URL}/api/worldforge/region", params=params, timeout=TIMEOUT).json()
        b = s.get(f"{BASE_URL}/api/worldforge/region", params=params, timeout=TIMEOUT).json()
        assert a["name"] == b["name"]
        an = [(p["name"], p["kind"], p["x"], p["y"]) for p in a["pois"]]
        bn = [(p["name"], p["kind"], p["x"], p["y"]) for p in b["pois"]]
        assert an == bn, "POI list (names + order) must be identical for same seed"


# ── COSMIC NAMES: real catalogue designations ────────────────────────────────
def _looks_like_catalogue(name: str) -> bool:
    # accept "NGC 1234", "Messier 31", "HD 209458", "Gliese 581", "Alpha Centauri", etc.
    if any(name.startswith(c + " ") for c in DEEPSKY_CATS):
        return True
    if any(name.startswith(c + " ") for c in STAR_CATS):
        return True
    parts = name.split(None, 1)
    if len(parts) == 2 and parts[0] in GREEK:
        return True
    return False


class TestCosmicNaming:
    def test_galaxy_uses_real_catalogues(self, s):
        r = s.post(f"{BASE_URL}/api/worldforge/world",
                   json={"scale": "galaxy", "seed": 99, "size": 32}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert _looks_like_catalogue(j["name"]), \
            f"galaxy name not a real catalogue designation: {j['name']!r}"
        bad = [p["name"] for p in j["pois"] if not _looks_like_catalogue(p["name"])]
        assert not bad, f"POIs with non-catalogue names: {bad}"
        # forbidden fantasy cosmic suffixes
        all_names = " ".join([j["name"]] + [p["name"] for p in j["pois"]])
        assert "Maw" not in all_names.split()
        assert "Verge" not in all_names.split()
        assert "Prime" not in all_names.split()

    def test_system_uses_real_star_designations(self, s):
        r = s.post(f"{BASE_URL}/api/worldforge/world",
                   json={"scale": "system", "seed": 7, "size": 32}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert _looks_like_catalogue(j["name"]), \
            f"system name not a real star designation: {j['name']!r}"
        for p in j["pois"]:
            assert _looks_like_catalogue(p["name"]), \
                f"non-catalogue POI name in system: {p['name']!r}"


# ── OPTIONS: realistic feature_toggles ───────────────────────────────────────
class TestOptions:
    def test_feature_toggles_realistic(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/options", timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        toggles = j["feature_toggles"]
        assert len(toggles) >= 12, f"expected >=12 toggles, got {len(toggles)}"
        keys = {t["key"] for t in toggles}
        # all keys must be realistic kinds (no fantasy)
        bad = keys - REALISTIC_KINDS
        assert not bad, f"non-realistic toggle keys: {bad}"
        fantasy = keys & FANTASY_KINDS
        assert not fantasy, f"fantasy toggle keys: {fantasy}"
        # human-readable labels present
        for t in toggles:
            assert isinstance(t.get("label"), str) and len(t["label"]) >= 2
        # defaults include the classic settlement set
        defaults_on = {t["key"] for t in toggles if t.get("default")}
        for need in ("town", "village", "harbor", "farmstead"):
            assert need in defaults_on, f"default-on missing: {need}"


# ── FEATURE TOGGLE EFFECT ────────────────────────────────────────────────────
class TestFeatureToggles:
    def test_toggle_changes_pois(self, s):
        body = {"scale": "region", "seed": 555, "size": 40, "settlement_density": 2.0,
                "features": {"city": True, "cave_system": True, "mine": True,
                             "ghost_town": True, "village": True}}
        r = s.post(f"{BASE_URL}/api/worldforge/world", json=body, timeout=TIMEOUT)
        assert r.status_code == 200
        j = r.json()
        kinds = {p["kind"] for p in j["pois"]}
        assert kinds & {"city", "cave_system", "mine", "ghost_town"}, \
            f"none of the toggled realistic kinds appeared: {kinds}"
        assert not (kinds & FANTASY_KINDS), f"fantasy kinds leaked: {kinds & FANTASY_KINDS}"


# ── LORE: scientific, no fantasy ─────────────────────────────────────────────
class TestLoreRealism:
    @pytest.mark.timeout(120)
    def test_lore_is_scientific(self, s):
        r = s.post(f"{BASE_URL}/api/worldforge/lore",
                   json={"seed": 1337, "size": 48, "world_scale": "region"},
                   timeout=LLM_TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        if "error" in j:
            pytest.fail(f"lore error: {j['error']}")
        lore = j.get("lore", "")
        assert isinstance(lore, str) and len(lore) > 40
        # disallow obvious fantasy/magic vocabulary
        forbidden = ["magic", "wizard", "sorcer", "dragon", "demon", "elf ", "orc ",
                     "troll", "goblin", "necromanc", "warlock", "ancient gods",
                     "treasure hoard", "monster"]
        low = lore.lower()
        hits = [w for w in forbidden if w in low]
        assert not hits, f"fantasy vocab in lore: {hits}\n---\n{lore}"


# ── QUEST: branching DAG + realistic factions + fieldwork ────────────────────
class TestQuestRealism:
    @pytest.mark.timeout(180)
    def test_quest_is_realistic_dag(self, s):
        r = s.post(f"{BASE_URL}/api/worldforge/quest",
                   json={"seed": 1337, "size": 48, "world_scale": "region"},
                   timeout=120)
        assert r.status_code == 200, r.text
        j = r.json()
        if "error" in j:
            pytest.fail(f"quest error: {j['error']} raw={j.get('raw')}")
        cons = j.get("consistency", {})
        assert cons.get("ok") is True, f"consistency not OK: {cons}"
        q = j["quest"]
        assert isinstance(q, dict)
        nodes = q.get("nodes") or []
        assert len(nodes) >= 2
        # at least one node should have ≥1 branch (DAG)
        assert any((nd.get("branches") or []) for nd in nodes if isinstance(nd, dict)), \
            "no branching found — not a DAG"
        # factions: 2 realistic stakeholder groups
        factions = q.get("factions") or []
        assert isinstance(factions, list) and len(factions) >= 2
        # no fantasy in objectives
        full = (q.get("premise", "") + " " + q.get("epilogue", "") + " "
                + " ".join(str(nd.get("objective", "")) for nd in nodes)
                + " ".join(str(nd.get("title", "")) for nd in nodes)).lower()
        forbidden = ["dragon", "wizard", "magic", "treasure", "monster",
                     "demon", "orc", "elf ", "necromanc", "ancient evil"]
        hits = [w for w in forbidden if w in full]
        assert not hits, f"fantasy tropes leaked into quest: {hits}"


# ── REGRESSION: biomes(16), presets(>=100), render(200) ──────────────────────
class TestRegression:
    def test_biomes_count_16(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/biomes", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["count"] == 16

    def test_presets_100plus(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/presets", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["total"] >= 100

    def test_render_region_200(self, s):
        r = s.get(f"{BASE_URL}/api/worldforge/render",
                  params={"scale": "region", "seed": 1337, "size": 32},
                  timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/")
