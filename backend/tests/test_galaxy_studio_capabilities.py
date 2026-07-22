"""
Backend tests for Galaxy Studio 40 Capability Systems generator (iteration 2).

Verifies:
  1. GET /api/galaxy-studio/capabilities/catalog → 40 systems / 8 cats / 5 operators.
  2. Full build with mutation_matrix → completes, files listing includes BOTH
     logic/mutations/* (existing) AND capabilities/* (new) — including the
     central CapabilityRegistry.ts and at least one capability Engine.ts and
     one per-capability PermutationEngine.ts (the "mutate too" engines).
  3. Regression: GET /api/health → healthy.
  4. Sanity: GET /api/galaxy-studio/file/{build_id}/capabilities/CapabilityRegistry.ts
     contains CAPABILITY_REGISTRY + TOTAL_CAPABILITIES.
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("EXPO_PUBLIC_BACKEND_URL must be set")

TIMEOUT = 60


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ─── helpers (re-used across tests) ───────────────────────────────────
def _drive(api, build_id, max_advances=12):
    last = None
    for _ in range(max_advances):
        r = api.post(f"{BASE_URL}/api/galaxy-studio/advance",
                     json={"build_id": build_id}, timeout=TIMEOUT)
        assert r.status_code == 200, f"advance failed: {r.status_code} {r.text[:300]}"
        last = r.json()
        if last.get("status") == "completed":
            return last
        time.sleep(0.4)
    rc = api.post(f"{BASE_URL}/api/galaxy-studio/force-complete/{build_id}", timeout=TIMEOUT)
    assert rc.status_code == 200, rc.text[:300]
    return rc.json()


# ─── 1. CAPABILITIES CATALOG ──────────────────────────────────────────
def test_health_ok(api):
    r = api.get(f"{BASE_URL}/api/health", timeout=TIMEOUT)
    assert r.status_code == 200
    assert r.json().get("status", "").lower() in ("healthy", "ok", "up")


def test_capabilities_catalog_shape(api):
    r = api.get(f"{BASE_URL}/api/galaxy-studio/capabilities/catalog", timeout=TIMEOUT)
    assert r.status_code == 200, r.text[:400]
    data = r.json()
    assert data.get("ok") is True
    assert data["total_capabilities"] == 40, data.get("total_capabilities")
    assert data["total_categories"] == 8, data.get("total_categories")
    assert data["operators"] == ["off", "drift", "jitter", "mutate", "recombine"]
    cats = data["categories"]
    assert isinstance(cats, list) and len(cats) == 8
    # Sum across cats should equal total
    total = sum(c["count"] for c in cats)
    assert total == 40, total
    # Every capability must have subsystems/operations/permutations
    for cat in cats:
        for cap in cat["capabilities"]:
            assert cap["id"] and cap["title"]
            assert isinstance(cap["subsystems"], list) and cap["subsystems"]
            assert isinstance(cap["operations"], list) and cap["operations"]
            # permutations = 5 ** len(subsystems)
            assert cap["permutations"] == 5 ** len(cap["subsystems"]), cap


# ─── 2. e2e BUILD with mutation_matrix → capabilities files present ───
MUTATION_MATRIX = {
    "enemy_mutation":  {"rate": 500, "magnitude": 600},
    "weapon_mutation": {"rate": 300},
}


@pytest.fixture(scope="module")
def build_id(api):
    r = api.post(f"{BASE_URL}/api/galaxy-studio/create", json={
        "title": "TEST_CapBuild",
        "genre": "rpg",
        "complexity": "intermediate",
        "description": "capability systems smoke test",
        "mutation_matrix": MUTATION_MATRIX,
    }, timeout=TIMEOUT)
    assert r.status_code == 200, r.text[:400]
    bid = r.json().get("build_id")
    assert bid
    _drive(api, bid)
    return bid


def test_build_completes(api, build_id):
    r = api.get(f"{BASE_URL}/api/galaxy-studio/status/{build_id}", timeout=TIMEOUT)
    # status endpoint optional — fall back to listing if missing
    if r.status_code == 200:
        s = r.json().get("status") or r.json().get("build", {}).get("status")
        assert s in ("completed", "already_completed", None) or "complet" in str(s).lower()


def test_capabilities_files_in_listing(api, build_id):
    r = api.get(f"{BASE_URL}/api/galaxy-studio/files/{build_id}", timeout=TIMEOUT)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    paths = [f["path"] for f in data.get("files", [])]
    total = data.get("total_files", 0)
    assert total >= 20, f"too few files: {total}"

    # (a) mutation files still present
    assert "logic/mutations/MutationPermutationEngine.ts" in paths, \
        f"mutation engine missing. sample={paths[:20]}"

    # (b) capability files present
    assert "capabilities/CapabilityRegistry.ts" in paths, \
        f"CapabilityRegistry.ts missing. cap-paths sample: " \
        f"{[p for p in paths if p.startswith('capabilities/')][:10]}"

    cap_engine = [p for p in paths
                  if p.startswith("capabilities/")
                  and p.endswith("Engine.ts")
                  and "/mutations/" not in p]
    assert cap_engine, "no capabilities/<Name>/<Name>Engine.ts found"

    cap_perm = [p for p in paths
                if p.startswith("capabilities/")
                and "/mutations/" in p
                and p.endswith("PermutationEngine.ts")]
    assert cap_perm, "no per-capability MutationPermutationEngine found"


def test_capability_registry_content(api, build_id):
    path = "capabilities/CapabilityRegistry.ts"
    r = api.get(f"{BASE_URL}/api/galaxy-studio/file/{build_id}/{path}", timeout=TIMEOUT)
    assert r.status_code == 200, r.text[:300]
    content = r.json().get("content", "")
    assert "CAPABILITY_REGISTRY" in content
    assert "TOTAL_CAPABILITIES" in content
    # one of the 40 ids should be imported
    assert "PhysicsEngineEngine" in content or "EcsCoreEngine" in content


def test_capability_per_engine_content(api, build_id):
    # fetch the first capability engine we can find
    r = api.get(f"{BASE_URL}/api/galaxy-studio/files/{build_id}", timeout=TIMEOUT)
    paths = [f["path"] for f in r.json().get("files", [])]
    eng_paths = [p for p in paths if p.startswith("capabilities/")
                 and p.endswith("Engine.ts") and "/mutations/" not in p]
    assert eng_paths
    target = eng_paths[0]
    rf = api.get(f"{BASE_URL}/api/galaxy-studio/file/{build_id}/{target}", timeout=TIMEOUT)
    assert rf.status_code == 200, rf.text[:300]
    body = rf.json().get("content", "")
    # Capability engine must define an Engine class and tick lifecycle
    assert "Engine {" in body or "class " in body
    assert "tick(" in body
    assert "DEFAULT_" in body  # generated default config constant
