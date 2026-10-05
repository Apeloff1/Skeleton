"""
Iteration 4 — Regression tests for the routes/galaxy_studio.py decomposition
into sub-routers (catalogs / agents / vault-admin), plus the NEW
once-over /history endpoint (MongoDB-backed) and verification that the
dynamic /pipeline/{build_id} route still functions after the catalogs
sub-router was mounted BEFORE it (route-ordering bug fix).
"""
import os
import time

import pytest
import requests


def _base_url() -> str:
    base = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
    if not base:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                    base = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                    break
    assert base, "EXPO_PUBLIC_BACKEND_URL must be set"
    return base


BASE_URL = _base_url()


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Sub-router: catalogs (3 endpoints, mounted EARLY to win route matching) ─
class TestCatalogsSubrouter:
    def test_capabilities_catalog(self, client):
        r = client.get(f"{BASE_URL}/api/galaxy-studio/capabilities/catalog", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # tolerant shape check: must be a payload with capability data
        assert isinstance(data, dict) and len(data) > 0
        # common keys we expect
        has_signal = any(
            k in data
            for k in ("ok", "capabilities", "total_capabilities", "systems", "categories", "total")
        )
        assert has_signal, f"unexpected capabilities catalog shape: {list(data.keys())[:8]}"

    def test_pipeline_catalog_static_wins(self, client):
        """CRITICAL: /pipeline/catalog must hit the catalog handler, not the
        dynamic /pipeline/{build_id} handler. Mounted-early sub-router ensures
        this. Confirms 8-stage / 41-task pipeline catalog."""
        r = client.get(f"{BASE_URL}/api/galaxy-studio/pipeline/catalog", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True, f"not ok: {data}"
        assert data.get("total_stages") == 8
        assert data.get("total_tasks") == 41
        stages = data["stages"]
        assert isinstance(stages, list) and len(stages) == 8
        for s in stages:
            assert {"id", "title", "gate", "tasks"}.issubset(s.keys())

    def test_datasets_catalog(self, client):
        r = client.get(f"{BASE_URL}/api/galaxy-studio/datasets/catalog", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("total_datasets") == 16
        assert data.get("total_records") == 100
        assert isinstance(data.get("datasets"), list) and len(data["datasets"]) == 16


# ── Dynamic /pipeline/{build_id} must NOT be shadowed by /pipeline/catalog ─
class TestDynamicPipelineRouteStillWorks:
    def test_bogus_build_id_does_not_collide_with_catalog(self, client):
        """A bogus build_id MUST NOT return the catalog payload — it should
        return a build-lookup response (200 with not-found semantics, or 404,
        or 400). The KEY assertion: the response is NOT the catalog payload
        (no 'total_stages':8 / 'stages' list of 8 items)."""
        bogus = "TEST_bogus_build_id_does_not_exist_42"
        r = client.get(
            f"{BASE_URL}/api/galaxy-studio/pipeline/{bogus}", timeout=15
        )
        # Accept any non-5xx — the route must dispatch to the dynamic handler.
        assert r.status_code < 500, f"server error on dynamic route: {r.status_code} {r.text[:300]}"
        # If 200, the payload must NOT be the catalog shape.
        if r.status_code == 200:
            try:
                data = r.json()
            except Exception:
                data = {}
            if isinstance(data, dict):
                is_catalog = (
                    data.get("total_stages") == 8
                    and isinstance(data.get("stages"), list)
                    and len(data.get("stages") or []) == 8
                )
                assert not is_catalog, (
                    "ROUTE-ORDERING REGRESSION: /pipeline/{bogus} returned the "
                    "catalog payload — dynamic route is being shadowed!"
                )


# ── Vault admin sub-router ─────────────────────────────────────────────
class TestVaultAdminSubrouter:
    def test_vault_stats(self, client):
        r = client.get(f"{BASE_URL}/api/galaxy-studio/admin/vault/stats", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        for k in ("builds", "total_files", "disk_bytes", "disk_mb", "compression_ratio", "keep_target"):
            assert k in data, f"missing key {k} in vault stats: {list(data.keys())}"
        assert isinstance(data["builds"], int)
        assert isinstance(data["disk_bytes"], int)


# ── Agents Once-Over orchestrator + persisted history ──────────────────
class TestOnceOverHistory:
    def test_history_before_and_after_run(self, client):
        # Snapshot baseline history count
        r0 = client.get(
            f"{BASE_URL}/api/galaxy-studio/agents/once-over/history?limit=30",
            timeout=15,
        )
        assert r0.status_code == 200, r0.text
        h0 = r0.json()
        assert h0.get("ok") is True
        assert isinstance(h0.get("history"), list)
        baseline_count = h0.get("count", len(h0["history"]))
        # MongoDB-backed: history may persist across reloads — just snapshot it.

        # Run a full once-over (slow ~50-60s)
        r1 = client.post(
            f"{BASE_URL}/api/galaxy-studio/agents/once-over",
            json={}, timeout=240,
        )
        assert r1.status_code == 200, r1.text
        rep = r1.json()
        assert rep.get("ok") is True
        assert rep.get("total_agents") == 16
        assert isinstance(rep.get("healthy"), int)
        assert "health_pct" in rep
        assert isinstance(rep.get("results"), list) and len(rep["results"]) == 16
        assert isinstance(rep.get("blockers"), list)

        # /last reflects cached
        r2 = client.get(
            f"{BASE_URL}/api/galaxy-studio/agents/once-over/last", timeout=15
        )
        assert r2.status_code == 200, r2.text
        last = r2.json()
        assert last["ok"] is True and last["ran"] is True
        assert last["report"]["total_agents"] == 16

        # /history grew by at least 1 (it may cap at 30 — handle that case)
        r3 = client.get(
            f"{BASE_URL}/api/galaxy-studio/agents/once-over/history?limit=30",
            timeout=15,
        )
        assert r3.status_code == 200, r3.text
        h1 = r3.json()
        assert h1["ok"] is True
        # If we weren't already at the cap (30), count must grow by ≥1.
        if baseline_count < 30:
            assert h1["count"] >= baseline_count + 1, (
                f"history did not grow: was {baseline_count}, now {h1['count']}"
            )
        # Validate ordering (oldest → newest by ran_at)
        ran_ats = [e["ran_at"] for e in h1["history"] if "ran_at" in e]
        assert ran_ats == sorted(ran_ats), f"history not oldest→newest: {ran_ats[:5]}…"
        # Latest entry matches the report we just ran
        latest = h1["history"][-1]
        assert latest["total_agents"] == 16
        assert latest["health_pct"] == rep["health_pct"]

    def test_history_limit_param(self, client):
        r = client.get(
            f"{BASE_URL}/api/galaxy-studio/agents/once-over/history?limit=5", timeout=15
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert isinstance(data["history"], list)
        assert len(data["history"]) <= 5
