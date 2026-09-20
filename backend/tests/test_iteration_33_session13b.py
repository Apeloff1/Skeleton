"""
Iteration 33 / Session 13b — Worldforge user action-items + SOTA hardening.

Surface under test:
  • GET /api/worldforge/render.gif  — planet GIF speedup + in-process LRU cache (X-Cache MISS→HIT)
  • POST /api/worldforge/name-key   — NEW deterministic scientific toponym-etymology endpoint
  • POST /api/worldforge/simulate   — realistic settlement kinds + toponym-named founded settlements
  • POST /api/worldforge/quest      — JSON-parse retry (branching DAG, consistency.ok)
  • REGRESSION /region /options /biomes
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "http://localhost:8001").rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── 1. render.gif: cache MISS→HIT, fast HIT, different seed → MISS ───────────
class TestRenderGifCache:
    def test_render_gif_first_call_miss_then_hit(self, api):
        url = f"{BASE_URL}/api/worldforge/render.gif"
        params = {"scale": "planet", "seed": 42, "size": 40}

        t0 = time.time()
        r1 = api.get(url, params=params, timeout=120)
        miss_elapsed = time.time() - t0
        assert r1.status_code == 200, r1.text
        assert r1.headers.get("content-type", "").startswith("image/gif")
        assert r1.headers.get("X-Cache") == "MISS"
        assert len(r1.content) > 1000  # actual gif bytes
        assert r1.content[:6] in (b"GIF87a", b"GIF89a")

        t1 = time.time()
        r2 = api.get(url, params=params, timeout=30)
        hit_elapsed = time.time() - t1
        assert r2.status_code == 200
        assert r2.headers.get("X-Cache") == "HIT"
        # HIT must be much faster than the MISS render
        assert hit_elapsed < max(0.5, miss_elapsed * 0.5), (
            f"HIT ({hit_elapsed:.2f}s) not faster than MISS ({miss_elapsed:.2f}s)"
        )

    def test_render_gif_different_seed_is_miss(self, api):
        url = f"{BASE_URL}/api/worldforge/render.gif"
        r = api.get(url, params={"scale": "planet", "seed": 4242, "size": 40}, timeout=120)
        assert r.status_code == 200
        assert r.headers.get("X-Cache") == "MISS"


# ── 2. /name-key: deterministic scientific toponym etymology ─────────────────
class TestNameKey:
    def test_name_key_region_shape_and_determinism(self, api):
        url = f"{BASE_URL}/api/worldforge/name-key"
        body = {"seed": 1337, "size": 48, "world_scale": "region"}
        r1 = api.post(url, json=body, timeout=30)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()

        assert "region_name" in d1 and isinstance(d1["region_name"], str) and d1["region_name"]
        assert "convention" in d1 and isinstance(d1["convention"], str) and len(d1["convention"]) > 20
        entries = d1.get("entries")
        assert isinstance(entries, list) and len(entries) >= 1

        for e in entries:
            assert e.get("name"), f"entry missing name: {e}"
            assert "kind" in e, f"entry missing kind: {e}"
            ety = e.get("etymology")
            assert isinstance(ety, list) and len(ety) >= 1, f"bad etymology: {e}"
            for comp in ety:
                assert "part" in comp and "meaning" in comp, f"bad component: {comp}"
                assert isinstance(comp["part"], str) and comp["part"]
                assert isinstance(comp["meaning"], str) and comp["meaning"]

        # determinism — identical entries on repeat
        r2 = api.post(url, json=body, timeout=30)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d1["entries"] == d2["entries"], "name-key not deterministic"
        assert d1["region_name"] == d2["region_name"]

    def test_name_key_galaxy_uses_astronomical_catalogue(self, api):
        url = f"{BASE_URL}/api/worldforge/name-key"
        r = api.post(url, json={"seed": 99, "size": 32, "world_scale": "galaxy"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        entries = data.get("entries", [])
        # galaxy scale CAN have zero notable POIs at size 32 — only enforce shape when present
        for e in entries:
            assert e.get("etymology"), f"missing etymology: {e}"
            # convention should describe astronomical cataloguing (no Earth toponymy gloss)
            text = " ".join(c.get("meaning", "") for c in e["etymology"]).lower()
            assert any(tok in text for tok in (
                "astronomical", "catalogue", "bayer", "ngc", "messier",
                "hd", "hip", "gliese", "kepler", "trappist", "constellation",
            )), f"galaxy entry does not reference an astronomical catalogue: {e}"
            # must NOT use Earth toponymy keywords
            bad = ("old english", "oe ", "norse", "latin villa", "estuary", "valley", "harbour")
            assert not any(b in text for b in bad), f"earth-toponymy gloss leaked into galaxy: {e}"
        # convention string itself should reference astronomy
        conv = (data.get("convention") or "").lower()
        assert "astronomical" in conv or "catalogu" in conv


# ── 3. /simulate: realistic kinds + toponym-named founded settlements ───────
class TestSimulate:
    def test_simulate_shape_and_realistic_naming(self, api):
        url = f"{BASE_URL}/api/worldforge/simulate"
        r = api.post(url, json={"seed": 1337, "size": 48, "ticks": 24}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()

        agents = d.get("agents")
        series = d.get("series")
        assert isinstance(agents, list) and len(agents) >= 1
        assert isinstance(series, list) and len(series) >= 4
        for s in series:
            assert "tick" in s and "total_pop" in s and "settlements" in s

        summary = d.get("summary") or {}
        for k in ("final_pop", "settlements", "peak_pop", "founded"):
            assert k in summary, f"missing summary.{k}"

        # realistic settlement kinds — no fantasy tropes
        FORBIDDEN = {"castle", "dungeon", "temple", "shrine", "monolith", "tower", "ruin"}
        for a in agents:
            assert a["kind"] not in FORBIDDEN, f"fantasy kind in sim agents: {a}"

        # founded-events: 'name' must be a real toponym (NOT 'New <x>' lazy fallback)
        founded = [e for e in d.get("events", []) if e.get("type") == "settlement_founded"]
        for e in founded:
            nm = e.get("name") or ""
            assert nm, f"founded event missing name: {e}"
            assert not nm.startswith("New "), f"lazy 'New X' name in founded event: {e}"


# ── 4. /quest: branching DAG, consistency.ok, realistic factions ─────────────
class TestQuest:
    def test_quest_live_llm_branching_dag(self, api):
        url = f"{BASE_URL}/api/worldforge/quest"
        # live LLM ~15–45s — single call only
        r = api.post(url, json={"seed": 1337, "size": 48, "world_scale": "region"}, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        # The route may return either the quest directly or wrapped — accept both shapes
        quest = d.get("quest") if isinstance(d.get("quest"), dict) else d
        nodes = quest.get("nodes") or d.get("nodes")
        assert isinstance(nodes, list) and len(nodes) >= 4, f"too few nodes: {nodes}"
        consistency = quest.get("consistency") or d.get("consistency") or {}
        assert consistency.get("ok") is True, f"consistency.ok not true: {consistency}"

        # realism check: no fantasy faction/objective vocabulary
        blob = (str(quest) + str(d)).lower()
        FORBIDDEN = ("dragon", "wizard", "necromancer", "lich", "orc", "elf", "goblin", "treasure",
                     "demon", "magic spell", "enchanted sword")
        leaked = [t for t in FORBIDDEN if t in blob]
        assert not leaked, f"fantasy vocab leaked into quest: {leaked}"


# ── 5. REGRESSION ────────────────────────────────────────────────────────────
class TestRegression:
    def test_region_realistic_pois(self, api):
        r = api.get(f"{BASE_URL}/api/worldforge/region", params={"seed": 1337}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        pois = d.get("pois", [])
        assert isinstance(pois, list) and len(pois) >= 1
        FORBIDDEN = {"castle", "dungeon", "temple", "shrine", "monolith", "ruin"}
        for p in pois:
            assert p.get("kind") not in FORBIDDEN, f"fantasy poi kind: {p}"

    def test_options_at_least_12_toggles(self, api):
        r = api.get(f"{BASE_URL}/api/worldforge/options", timeout=10)
        assert r.status_code == 200
        d = r.json()
        toggles = d.get("feature_toggles", [])
        assert len(toggles) >= 12, f"only {len(toggles)} toggles"

    def test_biomes_count_16(self, api):
        r = api.get(f"{BASE_URL}/api/worldforge/biomes", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("count") == 16, f"biomes count {d.get('count')}"
