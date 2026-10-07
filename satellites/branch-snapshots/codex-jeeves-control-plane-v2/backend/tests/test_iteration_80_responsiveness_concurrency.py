"""
Iteration 80 — Validate just-shipped GIL/responsiveness fixes + concurrency guard.

Strategy:
  Phase A: catalogs / health / eras / item-foundry / vault-gdd (BEFORE any build).
  Phase B: start ONE build, sample /health + /jobs/active latency, verify 429
           guard, then IMMEDIATELY force-complete (to keep RSS under HARD limit).
  Phase C: downstream — files, stats, vault zip, final-build pipeline.
"""
import os
import time
import statistics
import zipfile
import io
import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"
GS = f"{API}/galaxy-studio"

S = requests.Session()
S.headers.update({"Content-Type": "application/json"})

# A single shared build_id reused across the responsiveness + downstream tests.
_STATE: dict = {"build_id": None}


def _create_build(title="TEST_iter80"):
    r = S.post(f"{GS}/create", json={"title": title, "genre": "Action"}, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    bid = j.get("build_id") or j.get("id")
    assert bid, f"no build_id in {j}"
    return bid


def _start_build(bid, mins=1):
    return S.post(
        f"{GS}/start-build",
        json={"build_id": bid, "build_duration_minutes": mins},
        timeout=20,
    )


def _force_complete(bid):
    return S.post(f"{GS}/force-complete/{bid}", timeout=60)


def _wait_jobs_active_zero(timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = S.get(f"{GS}/jobs/active", timeout=5)
            if r.status_code == 200 and r.json().get("count", 1) == 0:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


# ───────────────────────── Phase A: catalogs / health (no build) ─────────────


def test_00_health():
    r = S.get(f"{API}/health", timeout=10)
    assert r.status_code == 200


def test_01_clean_baseline():
    # Make sure no live build is running before we start the heavy phase
    r = S.get(f"{GS}/jobs/active", timeout=10)
    assert r.status_code == 200
    for j in r.json().get("jobs", []):
        try:
            _force_complete(j["build_id"])
        except Exception:
            pass
    assert _wait_jobs_active_zero(40), "could not get jobs/active back to 0"


@pytest.mark.parametrize(
    "path",
    [
        "/manifest", "/genres", "/domains", "/capabilities/catalog",
        "/datasets/catalog", "/pipeline/catalog", "/mega-dbs/list", "/flair/stats",
        "/my-builds", "/resumable", "/workers", "/watchdog/health", "/db-status",
        "/eras", "/eras/8bit", "/eras/modern",
    ],
)
def test_02_catalogs_and_health(path):
    r = S.get(f"{GS}{path}", timeout=30)
    assert r.status_code == 200, f"{path} → {r.status_code} {r.text[:200]}"


def test_03_genres_count_about_69():
    r = S.get(f"{GS}/genres", timeout=20)
    j = r.json()
    genres = j.get("genres") or j.get("data") or j
    if isinstance(genres, dict):
        genres = list(genres.values())
    assert len(genres) >= 60, f"expected ~69 genres, got {len(genres)}"


def test_04_eras_count_7():
    r = S.get(f"{GS}/eras", timeout=20)
    j = r.json()
    eras = j.get("eras") or j.get("data") or j
    if isinstance(eras, dict) and "list" in eras:
        eras = eras["list"]
    if isinstance(eras, dict):
        eras = list(eras.values())
    assert len(eras) == 7, f"expected 7 eras, got {len(eras)}"


# ───────────────────────── Phase B: start build → responsiveness + 429 ───────


def test_10_create_and_start_build():
    bid = _create_build("TEST_iter80_live")
    r = _start_build(bid, mins=1)
    assert r.status_code in (200, 202), f"start-build failed: {r.status_code} {r.text}"
    _STATE["build_id"] = bid
    time.sleep(2)


def test_11_responsiveness_during_build():
    """Critical fix validation: /health and /jobs/active must respond <2s while a build runs."""
    bid = _STATE["build_id"]
    assert bid, "no live build from test_10"

    health_lat, jobs_lat, files_seen = [], [], []

    for _ in range(15):
        t0 = time.time()
        rh = S.get(f"{API}/health", timeout=5)
        health_lat.append(time.time() - t0)
        assert rh.status_code == 200

        t0 = time.time()
        rj = S.get(f"{GS}/jobs/active", timeout=5)
        jobs_lat.append(time.time() - t0)
        assert rj.status_code == 200

        jj = rj.json()
        cur_files = 0
        for job in jj.get("jobs", []):
            if job.get("build_id") == bid:
                cur_files = job.get("files", 0)
                assert job.get("kind") == "build", f"kind != build: {job}"
                assert "phase" in (job.get("stage") or ""), f"stage missing phase: {job}"
        files_seen.append(cur_files)
        time.sleep(1)

    print(
        f"\n[LATENCY] /health  mean={statistics.mean(health_lat):.3f}s "
        f"max={max(health_lat):.3f}s  p95={sorted(health_lat)[int(len(health_lat)*0.95)]:.3f}s"
    )
    print(
        f"[LATENCY] /jobs/active mean={statistics.mean(jobs_lat):.3f}s "
        f"max={max(jobs_lat):.3f}s  p95={sorted(jobs_lat)[int(len(jobs_lat)*0.95)]:.3f}s"
    )
    print(f"[FILES] file_count samples: {files_seen}")

    assert max(health_lat) < 2.0, f"/health max latency {max(health_lat):.2f}s > 2s — GIL not yielding"
    assert max(jobs_lat) < 2.0, f"/jobs/active max latency {max(jobs_lat):.2f}s > 2s — GIL not yielding"

    if max(files_seen) > 0:
        assert max(files_seen) >= min(files_seen), "file_count moved backward"


def test_12_jobs_active_reports_running_build():
    bid = _STATE["build_id"]
    r = S.get(f"{GS}/jobs/active", timeout=5)
    j = r.json()
    assert j["count"] >= 1
    found = [jb for jb in j["jobs"] if jb["build_id"] == bid]
    assert found, f"build {bid} not in active jobs {j}"
    assert found[0]["kind"] == "build"


def test_13_concurrency_guard_429():
    """While one build runs, a 2nd start-build MUST return 429 by design."""
    bid2 = _create_build("TEST_iter80_second")
    r = _start_build(bid2, mins=1)
    assert r.status_code == 429, f"expected 429, got {r.status_code} {r.text[:200]}"
    body = r.text.lower()
    assert any(k in body for k in ("one build", "already", "running", "wait", "memory"))


def test_14_force_complete_to_free_slot():
    bid = _STATE["build_id"]
    r = _force_complete(bid)
    assert r.status_code in (200, 202), f"{r.status_code} {r.text[:300]}"


def test_15_jobs_active_back_to_zero():
    assert _wait_jobs_active_zero(60), "jobs/active still > 0 after force-complete"


def test_16_new_build_starts_after_complete():
    """After the first build is complete, /start-build must succeed (no stale 429)."""
    bid = _create_build("TEST_iter80_after")
    r = _start_build(bid, mins=1)
    assert r.status_code in (200, 202), f"{r.status_code} {r.text[:200]}"
    time.sleep(1)
    _force_complete(bid)
    _wait_jobs_active_zero(60)


# ───────────────────────── Phase C: downstream off shared build ─────────────


def test_20_files_and_stats():
    bid = _STATE["build_id"]
    rf = S.get(f"{GS}/files/{bid}", timeout=30)
    assert rf.status_code == 200
    j = rf.json()
    files = j.get("files") or j.get("file_list") or j.get("data") or []
    if isinstance(files, dict):
        files = list(files.keys())
    assert len(files) > 0, "force-completed build returned 0 files"

    rs = S.get(f"{GS}/stats", timeout=10)
    assert rs.status_code == 200


def test_21_pipeline_diagnostics():
    bid = _STATE["build_id"]
    for p in ["/pipeline", "/diagnose", "/parity", "/choices"]:
        r = S.get(f"{GS}{p}/{bid}", timeout=20)
        assert r.status_code in (200, 404), f"{p}/{bid} → {r.status_code}"


def test_22_vault_zip_no_500():
    """Regression: POST /vault/zip/{bid} previously 500'd with FileNotFoundError."""
    bid = _STATE["build_id"]
    r = S.post(f"{GS}/vault/zip/{bid}", timeout=60)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    j = r.json()
    url = j.get("download_url") or j.get("url")
    assert url, f"no download_url in {j}"
    if url.startswith("/"):
        url = f"{BASE}{url}"
    rd = S.get(url, timeout=60)
    assert rd.status_code == 200


def test_30_final_build_package_sync():
    bid = _STATE["build_id"]
    payload = {
        "build_id": bid, "genre": "Action", "era": "8bit",
        "seed": 1, "persist": True,
        "config": {"graphic_style": "cel_shaded", "dimension": "3d"},
    }
    r = S.post(f"{GS}/final-build/package", json=payload, timeout=120)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    j = r.json()
    assert "can_ship" in j or "ok" in j or "verdict" in j


def test_31_final_build_package_async_streams():
    bid = _STATE["build_id"]
    payload = {
        "build_id": bid, "genre": "Action", "era": "8bit",
        "seed": 2, "persist": True,
        "config": {"graphic_style": "cel_shaded", "dimension": "3d"},
    }
    r = S.post(f"{GS}/final-build/package/async", json=payload, timeout=60)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    job_id = r.json().get("job_id")
    assert job_id

    stages_seen = set()
    playable = False
    for _ in range(40):
        rj = S.get(f"{GS}/final-build/job/{job_id}", timeout=15)
        assert rj.status_code == 200
        jd = rj.json()
        for s in jd.get("stages", []) or []:
            if isinstance(s, dict) and s.get("status") in ("done", "completed", "ok"):
                stages_seen.add(s.get("name") or s.get("id") or s.get("stage"))
        if jd.get("status") in ("done", "completed", "playable", "ok") or jd.get("playable"):
            playable = True
            break
        time.sleep(2)
    assert playable or len(stages_seen) >= 5, f"stages={stages_seen}"


def test_32_final_build_play_and_zip():
    bid = _STATE["build_id"]
    rp = S.get(f"{GS}/final-build/{bid}/play", timeout=30)
    assert rp.status_code == 200
    assert "<html" in rp.text.lower() or "<!doctype" in rp.text.lower()

    rz = S.get(f"{GS}/final-build/{bid}/game.zip", timeout=60)
    assert rz.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(rz.content))
    assert len(z.namelist()) > 0


# ───────────────────────── Phase D: extra regression (depends on bid) ────────


def test_40_vault_gdd_phase_gates_and_questionnaire():
    bid = _STATE["build_id"]
    r1 = S.post(f"{GS}/vault-gdd/phase-gates",
                json={"build_id": bid, "phase": 1, "approved": True}, timeout=30)
    assert r1.status_code in (200, 201), f"{r1.status_code} {r1.text[:200]}"
    r2 = S.post(f"{GS}/vault-gdd/questionnaire",
                json={"build_id": bid, "answers": {"q1": "yes"}}, timeout=30)
    assert r2.status_code in (200, 201)
    r3 = S.get(f"{GS}/vault-gdd/era-ladder/{bid}", timeout=20)
    assert r3.status_code == 200


def test_41_item_foundry():
    bid = _STATE["build_id"]
    r1 = S.post(f"{GS}/items/forge-build", json={"build_id": bid, "count": 3}, timeout=60)
    assert r1.status_code in (200, 201), f"{r1.status_code} {r1.text[:200]}"
    r2 = S.get(f"{GS}/items/build/{bid}", timeout=20)
    assert r2.status_code == 200


def test_42_swarm_planner_job():
    bid = _STATE["build_id"]
    # accept 200 or 404 — job_id is the swarm_job_id (we don't have it cleanly)
    r = S.get(f"{GS}/swarm/planner/job/{bid}", timeout=20)
    assert r.status_code in (200, 404)


def test_43_gamefiles_zip_and_gdd_md():
    bid = _STATE["build_id"]
    rz = S.get(f"{GS}/vault-gdd/gamefiles.zip/{bid}", timeout=60)
    if rz.status_code == 200:
        z = zipfile.ZipFile(io.BytesIO(rz.content))
        assert len(z.namelist()) > 0
    else:
        rz2 = S.get(f"{GS}/gamefiles.zip/{bid}", timeout=60)
        assert rz2.status_code in (200, 404)
    rm = S.get(f"{GS}/vault-gdd/gdd.md/{bid}", timeout=30)
    assert rm.status_code in (200, 404)
