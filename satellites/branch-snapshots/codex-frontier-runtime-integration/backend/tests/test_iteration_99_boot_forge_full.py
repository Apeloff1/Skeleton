"""Iteration 99 — Full Forge / DNA / ECS regression for boot-orchestrator fix sweep.

Verifies all endpoints listed in the iteration 99 review request:
- /api/health, /api/health/tunnel
- /api/galaxy-studio/forge/{catalog, styles, components, cache-stats, random, dna, generate, search, compose, seed, decode}

Targets the PUBLIC preview backend (EXPO_PUBLIC_BACKEND_URL).
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://player-retention.preview.emergentagent.com",
).rstrip("/")
PFX = f"{BASE_URL}/api/galaxy-studio/forge"
TIMEOUT = 30


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers["Content-Type"] = "application/json"
    return sess


# ─── HEALTH ───────────────────────────────────────────────────────────
def test_health(s):
    r = s.get(f"{BASE_URL}/api/health", timeout=TIMEOUT)
    assert r.status_code == 200, r.text


def test_health_tunnel(s):
    r = s.get(f"{BASE_URL}/api/health/tunnel", timeout=TIMEOUT)
    assert r.status_code == 200, r.text


# ─── CATALOG: 1.1M families, ~1.8B categories ────────────────────────
def test_catalog_taxonomy(s):
    r = s.get(f"{PFX}/catalog", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    # family_count ~1,110,000
    fc = d.get("family_count")
    assert isinstance(fc, int) and 1_000_000 <= fc <= 1_200_000, f"family_count={fc}"
    # taxonomy: macro 10000 / meso 100000 / micro 1000000
    tax = d.get("family_taxonomy", {})
    assert tax.get("macro", 0) >= 10, tax
    assert tax.get("meso", 0) >= 100, tax
    assert tax.get("micro", 0) >= 99000, tax
    # category_count ~1.8B
    cc = d.get("category_count")
    assert isinstance(cc, int) and cc > 1_000_000_000, f"category_count={cc}"
    # total_variations_pretty present and contains scientific notation
    pretty = d.get("total_variations_pretty", "")
    assert "10^" in pretty or "×" in pretty, f"pretty={pretty}"


# ─── STYLES: 119 axes incl. script/tattoo/mesh, basic/advanced ──────
def test_styles_axes(s):
    r = s.get(f"{PFX}/styles", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    axes = d.get("style_axes") or d.get("axes") or []
    assert len(axes) >= 100, f"only {len(axes)} axes"
    keys = {a.get("key") for a in axes}
    for need in ("script", "tattoo", "mesh"):
        assert need in keys, f"missing axis {need}"
    # basic_count present per axis, tier per option
    for ax in axes[:5]:
        assert "basic_count" in ax, ax
        for opt in ax.get("options", [])[:3]:
            assert opt.get("tier") in ("basic", "advanced"), opt
    # inscription block
    insc = d.get("inscription", {})
    assert len(insc.get("scripts", [])) >= 20
    assert len(insc.get("placements", [])) >= 5


# ─── COMPONENTS: 18+ ECS bits ────────────────────────────────────────
def test_components(s):
    r = s.get(f"{PFX}/components", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    # Endpoint returns {bits: {name: int, ...}, count: 18}
    bits = d.get("bits", {})
    assert isinstance(bits, dict) and len(bits) >= 14, d
    assert d.get("count") == len(bits)
    # Validate powers of two
    for name, val in bits.items():
        assert isinstance(val, int) and val > 0 and (val & (val - 1)) == 0, (name, val)


# ─── CACHE-STATS: token_cache + dna_bits=2048 ────────────────────────
def test_cache_stats(s):
    r = s.get(f"{PFX}/cache-stats", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("dna_bits") == 2048, d
    tc = d.get("token_cache", {})
    assert "capacity" in tc and "size" in tc, tc


# ─── RANDOM with require=metallic,script ─────────────────────────────
def test_random_require(s):
    r = s.get(f"{PFX}/random?require=metallic,script", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    comps = d.get("components") or []
    comp_names = {c if isinstance(c, str) else c.get("name") for c in comps}
    # Both required components must be present
    assert any("metal" in (c or "").lower() for c in comp_names), comp_names
    assert any("script" in (c or "").lower() or "inscri" in (c or "").lower() for c in comp_names), comp_names


# ─── GENERATE with use_llm:false → DNA 2048-bit, hex 512, forge_code ─
@pytest.fixture(scope="module")
def generated(s):
    payload = {"category": "iron.longsword", "use_llm": False, "seed": 42}
    r = s.post(f"{PFX}/generate", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    return r.json()


def test_generate_dna_shape(generated):
    dna = generated.get("dna", {})
    assert dna.get("bits") == 2048, dna
    hx = dna.get("hex", "")
    assert len(hx) == 512, f"hex len={len(hx)}"
    assert re.fullmatch(r"[0-9a-fA-F]{512}", hx), "hex not hex"
    assert isinstance(generated.get("component_mask"), int)
    assert isinstance(generated.get("components"), list)
    assert generated.get("forge_code"), generated.keys()


# ─── DETERMINISM: same body → same hex ───────────────────────────────
def test_dna_determinism(s):
    body = {"category": "gilded-iron.longsword", "treatments": ["runic"], "seed": 7}
    r1 = s.post(f"{PFX}/dna", json=body, timeout=TIMEOUT)
    r2 = s.post(f"{PFX}/dna", json=body, timeout=TIMEOUT)
    assert r1.status_code == 200 and r2.status_code == 200
    # /dna returns {dna:{bits,hex,short,checksum}, component_mask, ...}
    h1 = r1.json()["dna"]["hex"]
    h2 = r2.json()["dna"]["hex"]
    assert h1 == h2 and len(h1) == 512


# ─── DECODE: forge_code → rebuild same category ──────────────────────
def test_decode_roundtrip(s, generated):
    fc = generated["forge_code"]
    # endpoint expects `code` (not `forge_code`)
    r = s.post(f"{PFX}/decode", json={"code": fc}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True, d
    assert d.get("category") == generated.get("category"), (d.get("category"), generated.get("category"))


# ─── SEARCH ──────────────────────────────────────────────────────────
def test_search(s):
    r = s.get(f"{PFX}/search?q=sword", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    hits = d.get("hits") or d.get("results") or []
    assert len(hits) > 0


# ─── COMPOSE / SEED regression ───────────────────────────────────────
def test_compose(s):
    body = {"build_id": "TEST_iter99_compose", "era": "Medieval",
            "items": [{"key": "iron.longsword"}]}
    r = s.post(f"{PFX}/compose", json=body, timeout=TIMEOUT)
    assert r.status_code == 200, r.text


def test_seed(s):
    body = {"build_id": "TEST_iter99_seed", "era": "Modern",
            "items": [{"key": "mount"}]}
    r = s.post(f"{PFX}/seed", json=body, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
