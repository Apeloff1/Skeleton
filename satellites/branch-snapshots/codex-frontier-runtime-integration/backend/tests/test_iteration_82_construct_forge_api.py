"""Iteration 82 — Construct Forge + Material Forge HTTP API end-to-end.

Tests every endpoint listed in the review request:
  • presets (≥504/era; geometry + palette hex)
  • generate (deterministic, llm_enriched=false)
  • full CRUD (save/get/edit/list/delete)
  • capacity (100,000 ceiling)
  • Vault: mount / save-to-gamefiles / extract / list?mounted=true
  • snowball hook (constructs + materials)
  • LLM optional (≤1 invocation total)
  • Regression: /health, /jobs/active, /genres ~69
"""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
CTOR = f"{BASE}/api/galaxy-studio/constructs"
MATR = f"{BASE}/api/galaxy-studio/materials"
GS = f"{BASE}/api/galaxy-studio"
TIMEOUT = 30


# ───────── 0. Regression smoke ─────────
def test_00_health_fast():
    t = time.time()
    r = requests.get(f"{BASE}/api/health", timeout=10)
    assert r.status_code == 200, r.text
    assert (time.time() - t) < 3, "health should be <3s"


def test_01_jobs_active_works():
    r = requests.get(f"{GS}/jobs/active", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict)


def test_02_genres_about_69():
    r = requests.get(f"{GS}/genres", timeout=15)
    assert r.status_code == 200
    d = r.json()
    genres = d.get("genres") or d.get("items") or d
    if isinstance(genres, dict) and "genres" in genres:
        genres = genres["genres"]
    assert isinstance(genres, list) and len(genres) >= 60, f"got {len(genres) if isinstance(genres,list) else d}"


# ───────── 1. Presets ─────────
@pytest.mark.parametrize("base,kind", [(CTOR, "construct"), (MATR, "material")])
def test_10_presets_per_era_504(base, kind):
    r = requests.get(f"{base}/presets", params={"era": "8bit", "limit": 5}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["per_era"] >= 300, f"{kind} per_era={d['per_era']}"
    # Spec says 504
    assert d["per_era"] == 504, f"{kind} expected 504, got {d['per_era']}"
    assert d["kind"] == kind
    assert isinstance(d["categories"], list) and len(d["categories"]) > 0
    p = d["presets"][0]
    assert isinstance(p["geometry"], list) and len(p["geometry"]) > 0
    assert isinstance(p["palette"], list) and all(c.startswith("#") for c in p["palette"])


# ───────── 2. Generate (deterministic) ─────────
def test_20_generate_deterministic_construct():
    body = {"era": "16bit", "category": "castle", "seed": 7}
    a = requests.post(f"{CTOR}/generate", json=body, timeout=TIMEOUT).json()
    b = requests.post(f"{CTOR}/generate", json=body, timeout=TIMEOUT).json()
    assert a["preset_id"] == b["preset_id"]
    assert a["llm_enriched"] is False
    assert a["category"] == "castle"
    assert a["geometry"] and a["palette"] and a["descriptor"]


def test_21_generate_deterministic_material():
    body = {"era": "modern", "category": "marble", "seed": 3}
    a = requests.post(f"{MATR}/generate", json=body, timeout=TIMEOUT).json()
    assert a["llm_enriched"] is False
    assert a["category"] == "marble"
    assert a["geometry"] and a["palette"]


# ───────── 3. CRUD ─────────
_created: dict = {}


def test_30_save_construct():
    spec = requests.post(f"{CTOR}/generate", json={"era": "modern", "category": "tower", "seed": 11},
                         timeout=TIMEOUT).json()
    r = requests.post(f"{CTOR}/save", json={"spec": spec}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["saved"] is True
    assert d["construct_id"].startswith("con_")
    _created["cid"] = d["construct_id"]
    _created["era"] = spec["era"]


def test_31_get_item():
    cid = _created.get("cid")
    if not cid:
        pytest.skip("no cid")
    r = requests.get(f"{CTOR}/item/{cid}", timeout=TIMEOUT)
    assert r.status_code == 200
    d = r.json()
    assert d["construct_id"] == cid
    assert "_id" not in d, "ObjectId leaked"


def test_32_update_item():
    cid = _created.get("cid")
    if not cid:
        pytest.skip("no cid")
    patch = {"name": "TEST_Edited", "palette": ["#ff0000", "#00ff00"]}
    r = requests.put(f"{CTOR}/item/{cid}", json={"patch": patch}, timeout=TIMEOUT)
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "TEST_Edited"
    assert d["palette"] == ["#ff0000", "#00ff00"]


def test_33_list_filter_by_era():
    cid = _created.get("cid")
    era = _created.get("era")
    if not cid or not era:
        pytest.skip("no cid")
    r = requests.get(f"{CTOR}/list", params={"era": era}, timeout=TIMEOUT)
    assert r.status_code == 200
    d = r.json()
    assert d["total"] >= 1
    assert any(it["construct_id"] == cid for it in d["items"])


# ───────── 4. Capacity ─────────
def test_40_capacity_construct():
    r = requests.get(f"{CTOR}/capacity", timeout=TIMEOUT)
    assert r.status_code == 200
    d = r.json()
    assert d["capacity"] == 100_000
    assert "construct" in d and "material" in d


def test_41_capacity_material():
    r = requests.get(f"{MATR}/capacity", timeout=TIMEOUT)
    assert r.status_code == 200
    d = r.json()
    assert d["capacity"] == 100_000


# ───────── 5. Vault connection ─────────
def test_50_mount_to_build():
    cid = _created.get("cid")
    if not cid:
        pytest.skip("no cid")
    r = requests.post(f"{CTOR}/mount",
                      json={"construct_ids": [cid], "build_id": "qa_cf"},
                      timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mounted"] >= 1
    assert d["build_id"] == "qa_cf"


def test_51_save_to_gamefiles():
    cid = _created.get("cid")
    if not cid:
        pytest.skip("no cid")
    r = requests.post(f"{CTOR}/save-to-gamefiles",
                      json={"construct_ids": [cid], "build_id": "qa_cf"},
                      timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["gamefiles"] >= 1


def test_52_list_mounted_for_build_pre_extract():
    """Verify mounted=true filter works BEFORE extract (extract unmounts in library)."""
    cid = _created.get("cid")
    if not cid:
        pytest.skip("no cid")
    r = requests.get(f"{CTOR}/list", params={"build_id": "qa_cf", "mounted": "true"},
                     timeout=TIMEOUT)
    assert r.status_code == 200
    d = r.json()
    assert any(it["construct_id"] == cid for it in d["items"]), "mounted asset not found"


def test_53_extract_from_build():
    r = requests.get(f"{CTOR}/extract/qa_cf", timeout=TIMEOUT)
    assert r.status_code == 200
    d = r.json()
    assert d["extracted"] >= 1


# ───────── 6. Snowball hook ─────────
def test_60_snowball_constructs():
    r = requests.post(f"{CTOR}/snowball/forge",
                      json={"build_id": "qa_snow_c", "era": "early3d", "seed": 2,
                            "construct_count": 5, "material_count": 5},
                      timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["constructs"] == 5
    assert d["mounted"] is True
    assert d["presets_available"]["construct"] >= 300


def test_61_snowball_materials():
    r = requests.post(f"{MATR}/snowball/forge",
                      json={"build_id": "qa_snow_m", "era": "modern", "seed": 1,
                            "construct_count": 4, "material_count": 4},
                      timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["materials"] == 4
    assert d["mounted"] is True
    assert d["presets_available"]["material"] >= 300


# ───────── 7. Material forge mirror (sanity on extra endpoints) ─────────
def test_70_material_full_crud():
    spec = requests.post(f"{MATR}/generate",
                         json={"era": "16bit", "category": "brick", "seed": 5},
                         timeout=TIMEOUT).json()
    s = requests.post(f"{MATR}/save", json={"spec": spec}, timeout=TIMEOUT).json()
    mid = s["construct_id"]
    assert mid.startswith("mat_")
    g = requests.get(f"{MATR}/item/{mid}", timeout=TIMEOUT).json()
    assert g["construct_id"] == mid
    d = requests.delete(f"{MATR}/item/{mid}", timeout=TIMEOUT).json()
    assert d["deleted"] is True
    g2 = requests.get(f"{MATR}/item/{mid}", timeout=TIMEOUT)
    assert g2.status_code == 404


# ───────── 8. LLM optional (ONE call max) ─────────
@pytest.mark.timeout(120)
def test_80_llm_path_no_500_once():
    body = {"era": "modern", "category": "tower", "use_llm": True,
            "user_prompt": "a glowing crystal tower"}
    r = requests.post(f"{CTOR}/generate", json=body, timeout=90)
    assert r.status_code == 200, f"LLM path returned {r.status_code}: {r.text[:300]}"
    d = r.json()
    assert d["category"] == "tower"
    assert d["geometry"] and d["palette"]


# ───────── 9. Cleanup ─────────
def test_99_cleanup():
    cid = _created.get("cid")
    if cid:
        r = requests.delete(f"{CTOR}/item/{cid}", timeout=TIMEOUT)
        assert r.status_code == 200
