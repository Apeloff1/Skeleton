"""
Iteration 98 — Galaxy Studio Universal Forge: forge_dna engine regression.

Covers:
  - Backend boot/health triage (/api/health, /api/health/tunnel)
  - GET /api/galaxy-studio/forge/catalog  (100k taxonomy, ~1.8B categories)
  - GET /api/galaxy-studio/forge/components  (ECS bit registry)
  - GET /api/galaxy-studio/forge/cache-stats  (token LRU stats, dna_bits=2048)
  - POST /api/galaxy-studio/forge/dna  (2048-bit DNA + determinism)
  - POST /api/galaxy-studio/forge/dna  (contextual semantic pruning of metal_grade on food)
  - POST /api/galaxy-studio/forge/generate  (tier-3 inscribed key)
  - Regression: /catalog, /styles, /search, /random, /compose, /seed
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://player-retention.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
GS = f"{API}/galaxy-studio"
FORGE = f"{GS}/forge"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ─────────────────────────── Boot / health triage ───────────────────────────
class TestBootTriage:
    def test_health(self, s):
        t0 = time.time()
        r = s.get(f"{API}/health", timeout=10)
        dur = time.time() - t0
        assert r.status_code == 200, r.text
        assert dur < 2.0, f"health slow: {dur:.2f}s"

    def test_health_tunnel(self, s):
        r = s.get(f"{API}/health/tunnel", timeout=10)
        assert r.status_code == 200
        j = r.json()
        assert j.get("ok") is True or j.get("status") == "ok"


# ─────────────────────────── Forge: catalog (100k taxonomy) ─────────────────
class TestForgeCatalog:
    def test_catalog_shape_and_speed(self, s):
        t0 = time.time()
        r = s.get(f"{FORGE}/catalog", timeout=10)
        dur = time.time() - t0
        assert r.status_code == 200, r.text
        assert dur < 2.0, f"catalog too slow ({dur:.2f}s) — likely materialized"
        j = r.json()

        # family taxonomy
        fc = j.get("family_count")
        assert isinstance(fc, int) and 99_000 <= fc <= 101_000, f"family_count={fc}"
        tax = j.get("family_taxonomy") or {}
        assert tax.get("macro") == 11, tax
        assert tax.get("meso") == 101, tax
        assert tax.get("micro") == 99990, tax

        bcc = j.get("base_category_count")
        cc = j.get("category_count")
        assert isinstance(bcc, int) and bcc >= 3_000_000, f"base_category_count={bcc}"
        assert isinstance(cc, int) and cc >= 1_000_000_000, f"category_count={cc}"

        pretty = j.get("total_variations_pretty") or j.get("total_variations") or ""
        assert "×10^" in str(pretty) or "10^" in str(pretty), f"total_variations_pretty={pretty!r}"


# ─────────────────────────── Forge: ECS components ──────────────────────────
class TestForgeComponents:
    def test_components_registry(self, s):
        r = s.get(f"{FORGE}/components", timeout=10)
        assert r.status_code == 200, r.text
        j = r.json()
        # Find list of components — try common keys
        comps = j.get("components") or j.get("registry") or j.get("bits") or j
        if isinstance(comps, dict):
            comps_list = list(comps.values()) if comps and isinstance(next(iter(comps.values()), None), (int, dict)) else []
            # If it's a dict of name->bit:
            bit_values = []
            for v in comps.values():
                if isinstance(v, int):
                    bit_values.append(v)
                elif isinstance(v, dict) and "bit" in v:
                    bit_values.append(v["bit"])
            if bit_values:
                comps_list = bit_values
        else:
            comps_list = comps

        assert isinstance(comps_list, list), f"unexpected components shape: {type(comps_list)}"
        assert len(comps_list) >= 16, f"only {len(comps_list)} bits — expected ~18"

        # Validate each is a power-of-two integer
        for v in comps_list:
            if isinstance(v, dict):
                v = v.get("bit") or v.get("value")
            assert isinstance(v, int), f"non-int bit: {v!r}"
            assert v > 0 and (v & (v - 1)) == 0, f"not power-of-two: {v}"


# ─────────────────────────── Forge: cache-stats ─────────────────────────────
class TestForgeCacheStats:
    def test_cache_stats(self, s):
        r = s.get(f"{FORGE}/cache-stats", timeout=10)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("dna_bits") == 2048, j
        tc = j.get("token_cache") or {}
        for k in ("size", "capacity", "hits", "misses", "evictions", "hit_rate"):
            assert k in tc, f"missing token_cache.{k}: {tc}"
        assert tc["capacity"] == 4096, f"capacity={tc['capacity']}"


# ─────────────────────────── Forge: DNA (determinism) ───────────────────────
class TestForgeDNA:
    payload_a = {
        "category": "gilded-iron.longsword",
        "era": "medieval",
        "axes": {"script": "runic"},
    }

    def test_dna_shape_and_determinism(self, s):
        r1 = s.post(f"{FORGE}/dna", json=self.payload_a, timeout=15)
        assert r1.status_code == 200, r1.text
        j1 = r1.json()
        dna1 = j1.get("dna") or {}
        assert dna1.get("bits") == 2048, dna1
        hex1 = dna1.get("hex")
        assert isinstance(hex1, str) and len(hex1) == 512, f"hex len={len(hex1) if hex1 else None}"
        assert "short" in dna1 and dna1["short"], dna1
        assert "checksum" in dna1 and dna1["checksum"], dna1

        cmask = j1.get("component_mask")
        assert isinstance(cmask, int) and cmask > 0, f"component_mask={cmask}"
        assert isinstance(j1.get("components"), list) and len(j1["components"]) > 0, j1.get("components")
        assert "pruned_axes" in j1 and isinstance(j1["pruned_axes"], list), j1

        # Determinism — call again with identical body
        r2 = s.post(f"{FORGE}/dna", json=self.payload_a, timeout=15)
        assert r2.status_code == 200, r2.text
        hex2 = (r2.json().get("dna") or {}).get("hex")
        assert hex1 == hex2, f"DNA hex not deterministic:\n  hex1={hex1[:64]}…\n  hex2={hex2[:64]}…"

    def test_dna_contextual_pruning_food(self, s):
        body = {
            "category": "apple",
            "era": "modern",
            "axes": {"metal_grade": "gilded", "realism": "photoreal"},
        }
        r = s.post(f"{FORGE}/dna", json=body, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        pruned = j.get("pruned_axes") or []
        assert "metal_grade" in pruned, f"metal_grade should be pruned for 'apple'; pruned={pruned}"

        # And metal_grade must NOT be in any "applied" / style_axes structure
        applied = j.get("style_axes") or j.get("applied_axes") or j.get("axes") or {}
        if isinstance(applied, dict):
            assert "metal_grade" not in applied, f"metal_grade leaked into style_axes: {applied}"


# ─────────────────────────── Forge: generate (tier-3) ───────────────────────
class TestForgeGenerate:
    def test_generate_tier3(self, s):
        body = {
            "category": "gilded-iron.longsword",
            "era": "medieval",
            "axes": {"script": "runic", "mesh": "low_poly"},
            "inscription": {"script": "runic", "text": "VALOR", "placement": "blade"},
            "use_llm": False,
        }
        r = s.post(f"{FORGE}/generate", json=body, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()

        assert "dna" in j and (j["dna"] or {}).get("bits") == 2048, j.get("dna")
        assert j.get("dna_token"), "missing dna_token"
        assert isinstance(j.get("component_mask"), int) and j["component_mask"] > 0
        assert isinstance(j.get("components"), list) and j["components"]
        geom = j.get("geometry") or {}
        assert geom, "missing geometry"

        # glyph parts: search for keyword 'glyph' anywhere in geometry
        import json as _json
        geom_str = _json.dumps(geom).lower()
        assert "glyph" in geom_str, f"geometry missing glyph parts; keys={list(geom.keys())}"

        # inscription_text echoed (may be string OR object with .text)
        itxt = j.get("inscription_text") or j.get("inscription")
        if isinstance(itxt, dict):
            itxt = itxt.get("text")
        assert itxt == "VALOR", f"inscription_text={itxt}"


# ─────────────────────────── Regression: prior endpoints ────────────────────
class TestRegression:
    def test_root_catalog(self, s):
        r = s.get(f"{FORGE}/catalog", timeout=10)
        assert r.status_code == 200, r.text
        j = r.json()
        assert isinstance(j, (dict, list)), j

    def test_styles(self, s):
        r = s.get(f"{FORGE}/styles", timeout=10)
        assert r.status_code == 200, r.text
        j = r.json()
        # 119 axes including script/tattoo/mesh + basic/advanced tiers
        axes = j.get("axes") if isinstance(j, dict) else None
        # axes may be list or dict
        if isinstance(axes, dict):
            names = list(axes.keys())
            count = len(names)
        elif isinstance(axes, list):
            names = [a.get("name") or a.get("id") or a.get("key") for a in axes if isinstance(a, dict)]
            count = len(axes)
        else:
            # fallback: try top-level
            names, count = [], 0
            for k, v in (j.items() if isinstance(j, dict) else []):
                if isinstance(v, list) and k.lower().endswith("axes"):
                    count = len(v)
                    names = [x.get("name") or x.get("id") for x in v if isinstance(x, dict)]
                    break
        assert count >= 115, f"axes count={count} (expected ~119)"
        joined = " ".join([n for n in names if n]).lower()
        for needle in ("script", "tattoo", "mesh"):
            assert needle in joined, f"missing axis '{needle}' in styles: count={count}"

    def test_search(self, s):
        r = s.get(f"{FORGE}/search", params={"q": "mech"}, timeout=10)
        assert r.status_code == 200, r.text
        j = r.json()
        # accept list or {results:[...]}
        results = j.get("results") if isinstance(j, dict) else j
        assert isinstance(results, list), f"search returned {type(results)}"
        assert len(results) > 0, "search 'mech' returned empty"

    def test_random_resolvable(self, s):
        r = s.get(f"{FORGE}/random", timeout=10)
        assert r.status_code == 200, r.text
        j = r.json()
        key = j.get("category") or j.get("key") or j.get("category_key")
        assert key, f"random missing category key: {j}"

    def test_compose(self, s):
        body = {
            "build_id": "TEST_iter98_compose",
            "era": "medieval",
            "items": [{"category": "gilded-iron.longsword", "axes": {"mesh": "low_poly"}}],
        }
        r = s.post(f"{FORGE}/compose", json=body, timeout=20)
        assert r.status_code == 200, r.text

    def test_seed(self, s):
        body = {"build_id": "TEST_iter98_seed", "era": "medieval", "genre": "fantasy"}
        r = s.post(f"{FORGE}/seed", json=body, timeout=20)
        assert r.status_code == 200, f"seed status={r.status_code} body={r.text[:300]}"
