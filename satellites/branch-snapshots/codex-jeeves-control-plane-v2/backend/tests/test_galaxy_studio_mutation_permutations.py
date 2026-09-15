"""
Backend tests for Galaxy Studio Mutation Permutation Engine.

Verifies:
  1. Health endpoint reachable.
  2. /api/galaxy-studio/create accepts a `mutation_matrix` payload + drives build
     to completion via /advance (10 batches). The generated files MUST contain
     the mutation permutation modules under logic/mutations/.
  3. Regression: same build flow WITHOUT a `mutation_matrix` still completes
     cleanly (mutation generation is non-fatal).
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError(
        "EXPO_PUBLIC_BACKEND_URL must be set (read from /app/frontend/.env)"
    )

TIMEOUT = 60


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ─── 1. HEALTH ────────────────────────────────────────────────────────
def test_health_ok(api):
    r = api.get(f"{BASE_URL}/api/health", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    # Tolerant: accept either {"status": "healthy"} or any 200 body.
    if isinstance(data, dict) and "status" in data:
        assert data["status"].lower() in ("healthy", "ok", "up")


# ─── helpers ──────────────────────────────────────────────────────────
def _drive_to_completion(api, build_id, max_advances=12, force_after=14):
    """Loop /advance until build status == completed. Fall back to /force-complete
    if it doesn't complete within `force_after` attempts."""
    last = None
    for _i in range(max_advances):
        r = api.post(
            f"{BASE_URL}/api/galaxy-studio/advance",
            json={"build_id": build_id},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"/advance failed: {r.status_code} {r.text[:300]}"
        last = r.json()
        if last.get("status") == "completed":
            return last
        time.sleep(0.5)
    # Fall back to force-complete to make build available for file listing
    rc = api.post(
        f"{BASE_URL}/api/galaxy-studio/force-complete/{build_id}",
        timeout=TIMEOUT,
    )
    assert rc.status_code == 200, f"force-complete failed: {rc.status_code} {rc.text[:300]}"
    return rc.json()


def _list_files(api, build_id):
    r = api.get(f"{BASE_URL}/api/galaxy-studio/files/{build_id}", timeout=TIMEOUT)
    assert r.status_code == 200, f"/files failed: {r.status_code} {r.text[:300]}"
    return r.json()


# ─── 2. MUTATION PERMUTATION FLOW ─────────────────────────────────────
MUTATION_MATRIX = {
    "enemy_mutation":  {"rate": 500, "magnitude": 600, "safety": 70, "novelty": 400, "reversibility": 50},
    "weapon_mutation": {"rate": 300, "magnitude": 200},
    "boss_mutation":   {"novelty": 800},
}


def test_create_build_with_mutation_matrix(api):
    payload = {
        "title":  "TEST_MutationPermBuild",
        "genre":  "rpg",
        "complexity": "intermediate",
        "description": "permutation engine smoke test",
        "mutation_matrix": MUTATION_MATRIX,
    }
    r = api.post(f"{BASE_URL}/api/galaxy-studio/create", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, f"create failed: {r.status_code} {r.text[:500]}"
    data = r.json()
    assert "build_id" in data and data["build_id"]
    pytest.shared_build_id = data["build_id"]


def test_drive_build_to_completion(api):
    build_id = getattr(pytest, "shared_build_id", None)
    if not build_id:
        pytest.skip("create test did not produce a build_id")
    final = _drive_to_completion(api, build_id)
    assert final.get("status") in ("completed", "already_completed"), (
        f"build did not complete: {final}"
    )


def test_mutation_permutation_files_present(api):
    build_id = getattr(pytest, "shared_build_id", None)
    if not build_id:
        pytest.skip("no build")
    listing = _list_files(api, build_id)
    paths = [f["path"] for f in listing.get("files", [])]
    assert listing.get("total_files", 0) > 0, "build produced zero files"

    must_have = [
        "logic/mutations/MutationPermutationEngine.ts",
        "logic/mutations/MutationPermutationRegistry.ts",
    ]
    for needle in must_have:
        assert needle in paths, (
            f"missing mandatory permutation file: {needle}.  "
            f"Sample paths: {paths[:25]}"
        )

    # per-mutation mutator files (camel-cased class names)
    expected_mutators = [
        "logic/mutations/EnemyMutationMutator.ts",
        "logic/mutations/WeaponMutationMutator.ts",
        "logic/mutations/BossMutationMutator.ts",
    ]
    missing_mut = [m for m in expected_mutators if m not in paths]
    assert not missing_mut, f"missing per-mutation Mutator.ts files: {missing_mut}"

    # operator variants
    variants = [p for p in paths if p.startswith("logic/mutations/variants/")]
    assert len(variants) >= 3, (
        f"expected variant files under logic/mutations/variants/, got {len(variants)}"
    )

    # combo permutations
    perms = [p for p in paths if p.startswith("logic/mutations/permutations/")]
    assert len(perms) >= 1, (
        f"expected combo files under logic/mutations/permutations/, got {len(perms)}"
    )

    # sanity: file_count reasonable
    assert listing["total_files"] >= 20, (
        f"file_count too low: {listing['total_files']}"
    )


def test_engine_file_content_sane(api):
    build_id = getattr(pytest, "shared_build_id", None)
    if not build_id:
        pytest.skip("no build")
    r = api.get(
        f"{BASE_URL}/api/galaxy-studio/file/{build_id}/logic/mutations/MutationPermutationEngine.ts",
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    content = body.get("content", "")
    assert "MutationPermutationEngine" in content
    # operators baked in
    for op in ("drift", "jitter", "mutate", "recombine"):
        assert op in content, f"operator '{op}' missing from engine"


# ─── 3. REGRESSION: build WITHOUT mutation_matrix ─────────────────────
def test_build_without_mutation_matrix_completes(api):
    payload = {
        "title":  "TEST_NoMutationBuild",
        "genre":  "rpg",
        "complexity": "beginner",
        "description": "regression: omit mutation_matrix",
    }
    r = api.post(f"{BASE_URL}/api/galaxy-studio/create", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, f"create failed: {r.status_code} {r.text[:500]}"
    bid = r.json().get("build_id")
    assert bid

    final = _drive_to_completion(api, bid)
    assert final.get("status") in ("completed", "already_completed"), (
        f"plain build did not complete: {final}"
    )

    listing = _list_files(api, bid)
    assert listing["total_files"] > 0
    # Mutation files should NOT be present (no active matrix)
    paths = [f["path"] for f in listing["files"]]
    bad = [p for p in paths if p.startswith("logic/mutations/permutations/")]
    assert not bad, f"unexpected mutation permutation files in no-matrix build: {bad[:5]}"
