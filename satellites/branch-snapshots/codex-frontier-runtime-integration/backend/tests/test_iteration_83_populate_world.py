"""Iteration 83 — Construct/Material Forge backend sanity for the new
'Populate my world' Done-screen card. Verifies the exact endpoints + payloads
the frontend POSTs."""
import os
import time
import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── health / regression ──────────────────────────────────────────────────
def test_health_fast(session):
    t0 = time.time()
    r = session.get(f"{BASE}/api/health", timeout=10)
    elapsed = time.time() - t0
    assert r.status_code == 200, r.text
    assert elapsed < 3.0, f"health too slow: {elapsed:.2f}s"


def test_jobs_active(session):
    r = session.get(f"{BASE}/api/galaxy-studio/jobs/active", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d, dict)


# ── presets ──────────────────────────────────────────────────────────────
def test_construct_presets_8bit_per_era_300(session):
    r = session.get(
        f"{BASE}/api/galaxy-studio/constructs/presets?era=8bit&limit=1",
        timeout=20,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("per_era", 0) >= 300, f"per_era too low: {d.get('per_era')}"
    assert isinstance(d.get("presets"), list)
    assert isinstance(d.get("categories"), list) and len(d["categories"]) > 0


def test_material_presets_8bit_per_era_300(session):
    r = session.get(
        f"{BASE}/api/galaxy-studio/materials/presets?era=8bit&limit=1",
        timeout=20,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("per_era", 0) >= 300


# ── snowball / populate-my-world chain ───────────────────────────────────
QA_BUILD = "qa_pop"


def test_constructs_snowball_forge_24_mounted(session):
    payload = {"build_id": QA_BUILD, "era": "modern", "construct_count": 24}
    r = session.post(
        f"{BASE}/api/galaxy-studio/constructs/snowball/forge",
        json=payload,
        timeout=60,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("constructs") == 24, f"expected 24, got {d.get('constructs')}"
    assert d.get("mounted") is True, f"mounted not True: {d}"


def test_materials_snowball_forge_24(session):
    payload = {"build_id": QA_BUILD, "era": "modern", "material_count": 24}
    r = session.post(
        f"{BASE}/api/galaxy-studio/materials/snowball/forge",
        json=payload,
        timeout=60,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("materials") == 24, f"expected 24, got {d.get('materials')}"


def test_constructs_list_for_build_mounted(session):
    r = session.get(
        f"{BASE}/api/galaxy-studio/constructs/list?build_id={QA_BUILD}&mounted=true",
        timeout=20,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("total", 0) > 0, f"no mounted constructs: {d}"
    # endpoint returns items[] (not constructs[]) — verified iter-83
    assert isinstance(d.get("items"), list) and len(d["items"]) > 0


def test_materials_list_for_build_mounted(session):
    r = session.get(
        f"{BASE}/api/galaxy-studio/materials/list?build_id={QA_BUILD}&mounted=true",
        timeout=20,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("total", 0) > 0, f"no mounted materials: {d}"
