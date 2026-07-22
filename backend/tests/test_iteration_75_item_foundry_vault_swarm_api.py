"""Public-URL integration tests for Item Foundry + Vault GDD + Swarm Planner async/diff.

Hits the EXPO_BACKEND_URL (preview ingress) so we test what the user/UI sees.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

# Use frontend env value (preview URL) since that's how the UI hits the API.
def _base_url() -> str:
    # Try frontend/.env first, fall back to backend env
    try:
        with open("/app/frontend/.env", "r") as fh:
            for line in fh:
                if line.startswith("EXPO_PUBLIC_BACKEND_URL"):
                    return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    except Exception:
        pass
    v = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
    if not v:
        raise RuntimeError("No EXPO_PUBLIC_BACKEND_URL available")
    return v.rstrip("/")


BASE_URL = _base_url()
BID = f"TEST_it75_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ── Item Foundry ───────────────────────────────────────────────────────
def test_forge_build_returns_24_items_above_base(s):
    r = s.post(
        f"{BASE_URL}/api/galaxy-studio/items/forge-build",
        json={"build_id": BID, "genre": "rpg", "seed": 1, "platoon_size": 4, "persist": True},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["totals"]["items_forged"] == 24, j["totals"]
    assert j["totals"]["grade_above_base"] is True
    assert j["totals"]["accepted"] == 24
    assert len(j["stages"]) == 6
    # every item carries definition+skin+code+placement
    sample = j["stages"][0]["items"][0]
    for k in ("definition", "skin", "code", "placement", "grade", "name"):
        assert sample[k], f"missing {k}"


def test_list_build_returns_persisted_items(s):
    r = s.get(f"{BASE_URL}/api/galaxy-studio/items/build/{BID}", timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert j["build_id"] == BID
    assert len(j["items"]) == 24


# ── Vault GDD + Mount ──────────────────────────────────────────────────
def test_vault_mount_returns_gdd_and_stats(s):
    r = s.post(
        f"{BASE_URL}/api/galaxy-studio/vault-gdd/mount",
        json={"build_id": BID, "seed": 1, "forge_if_empty": True, "persist": True},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["gdd_chars"] > 200
    assert j["vault_gamefiles"] > 0
    assert j["coverage_pct"] > 0
    assert "stats" in j and j["stats"]["total_items"] > 0
    assert j["stats"]["grade_histogram"]
    assert j["stats"]["archetypes"]


def test_vault_stats_endpoint(s):
    r = s.get(f"{BASE_URL}/api/galaxy-studio/vault-gdd/stats/{BID}", timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert j["build_id"] == BID
    st = j["stats"]
    assert st["total_items"] > 0
    assert st["grade_histogram"]
    assert st["archetypes"]
    assert st["top_agents"]


def test_get_mount_returns_persisted(s):
    r = s.get(f"{BASE_URL}/api/galaxy-studio/vault-gdd/{BID}", timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["build_id"] == BID
    assert j["gdd_chars"] > 200


def test_gdd_md_export(s):
    r = s.get(f"{BASE_URL}/api/galaxy-studio/vault-gdd/{BID}/gdd.md", timeout=30)
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    cd = r.headers.get("content-disposition", "")
    assert "markdown" in ct or "text/" in ct
    assert "attachment" in cd and "_GDD.md" in cd
    assert "# " in r.text  # markdown


# ── Swarm Planner ──────────────────────────────────────────────────────
def test_plan_diff_seeds_show_shuffle(s):
    r = s.get(
        f"{BASE_URL}/api/galaxy-studio/swarm/planner/plan-diff",
        params={"phases": 8, "platoon_size": 5, "seed_a": 1, "seed_b": 2},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["phase_count"] == 8
    assert len(j["rows"]) == 8
    # different seeds -> low stability
    assert j["plan_hash_a"] != j["plan_hash_b"]
    assert j["stability_pct"] < 70, f"expected shuffle but got {j['stability_pct']}%"
    assert all("similarity" in row for row in j["rows"])


def test_plan_diff_same_seed_100pct(s):
    r = s.get(
        f"{BASE_URL}/api/galaxy-studio/swarm/planner/plan-diff",
        params={"phases": 5, "platoon_size": 5, "seed_a": 7, "seed_b": 7},
        timeout=30,
    )
    assert r.status_code == 200
    j = r.json()
    assert j["stability_pct"] == 100.0
    assert j["plan_hash_a"] == j["plan_hash_b"]


def test_async_execute_polls_to_done(s):
    body = {
        "build_id": f"{BID}_async",
        "phases": ["p01", "p02", "p03"],
        "seed": 1,
        "platoon_size": 3,
        "rounds": 1,
        "persist": False,
    }
    r = s.post(f"{BASE_URL}/api/galaxy-studio/swarm/planner/execute/async", json=body, timeout=30)
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    assert job_id

    # poll up to 60s
    final = None
    for _ in range(30):
        jr = s.get(f"{BASE_URL}/api/galaxy-studio/swarm/planner/job/{job_id}", timeout=15)
        assert jr.status_code == 200
        jd = jr.json()
        if jd["status"] in ("done", "error"):
            final = jd
            break
        time.sleep(2)
    assert final is not None, "job did not finish in time"
    assert final["status"] == "done", final.get("error")
    res = final["result"]
    assert res["execution"]["execution_complete"] is True
    assert res["execution"]["phases_executed"] == 3
    assert "participation" in res


def test_run_diff_after_two_executes(s):
    bid = f"{BID}_diff"
    body = {
        "build_id": bid,
        "phases": ["p01", "p02", "p03"],
        "seed": 1,
        "platoon_size": 3,
        "rounds": 1,
        "persist": True,
    }
    # Run 1
    r1 = s.post(f"{BASE_URL}/api/galaxy-studio/swarm/planner/execute", json=body, timeout=60)
    assert r1.status_code == 200, r1.text
    # Run 2 (different seed)
    body2 = {**body, "seed": 2}
    r2 = s.post(f"{BASE_URL}/api/galaxy-studio/swarm/planner/execute", json=body2, timeout=60)
    assert r2.status_code == 200, r2.text

    d = s.get(f"{BASE_URL}/api/galaxy-studio/swarm/planner/diff/{bid}", timeout=30)
    assert d.status_code == 200, d.text
    j = d.json()
    assert "stability_pct" in j
