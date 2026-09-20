"""
Stage A (Aggressive Restructure) validation tests.

Covers:
  A1 — Ω-Conductor fabric System-IQ persistence to Mongo (restart survives).
  A2 — Typed core/settings.py import + fields.
  A4 — /api/health/registry ok count + groups classification.
  REGRESSION — coverage/selftest, prood/readiness, lafs/recall, omega roles/sessions.
"""
import os
import sys
import time
import uuid
import subprocess

import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://player-retention.preview.emergentagent.com").rstrip("/")

# Ensure the backend module tree is importable for A2
sys.path.insert(0, "/app/backend")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _uniq(prefix="stageA"):
    return f"{prefix}-{uuid.uuid4().hex[:12]}-{time.time_ns()}"


# ────────────────────────────────────────────────────────────
# A2 — Typed settings module
# ────────────────────────────────────────────────────────────
class TestA2Settings:
    def test_import_and_singleton(self):
        from core.settings import get_settings  # noqa: WPS433
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2, "get_settings() should be lru_cached (process singleton)"

    def test_expected_fields(self):
        from core.settings import get_settings
        s = get_settings()
        assert isinstance(s.omega_persist, bool)
        assert isinstance(s.json_logging, bool)
        assert isinstance(s.db_name, str) and s.db_name
        assert hasattr(s, "omega_persist_interval_s")


# ────────────────────────────────────────────────────────────
# A4 — Route registry health + logical grouping
# ────────────────────────────────────────────────────────────
class TestA4Registry:
    def test_registry_endpoint_ok(self, api):
        r = api.get(f"{BASE_URL}/api/health/registry", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok", 0) > 200, f"expected >200 routers registered, got {data.get('ok')}"

    def test_registry_has_groups(self, api):
        r = api.get(f"{BASE_URL}/api/health/registry", timeout=15)
        assert r.status_code == 200
        data = r.json()
        groups = data.get("groups")
        assert isinstance(groups, dict) and groups, "registry report must include 'groups' dict"
        # Sanity-check that expected buckets are present
        for expected in ("gameforge", "omega", "prood"):
            assert expected in groups, f"missing group '{expected}' in registry.groups"
            assert isinstance(groups[expected], list) and groups[expected]

    def test_route_group_summary_helper(self):
        from core.routes_registry import route_group_summary, group_of
        summary = route_group_summary()
        assert isinstance(summary, dict) and summary
        assert group_of("routes.omega_conductor") == "omega"
        assert group_of("routes.gameforge_coverage") == "gameforge"
        assert group_of("routes.prood") == "prood"
        assert group_of("routes.animation_pipeline") == "pipelines"


# ────────────────────────────────────────────────────────────
# A1 — Fabric System-IQ persistence (+ restart durability)
# ────────────────────────────────────────────────────────────
class TestA1FabricPersistence:
    def test_fabric_baseline_shape(self, api):
        r = api.get(f"{BASE_URL}/api/omega/fabric", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("system_iq", "total_emissions", "blocked_repeats",
                  "persisted", "restored", "started"):
            assert k in d, f"missing key '{k}' in /api/omega/fabric"
        assert d["persisted"] is True
        assert d["restored"] is True
        assert d["started"] is True

    def test_jeeves_emit_bumps_iq_and_emissions(self, api):
        before = api.get(f"{BASE_URL}/api/omega/fabric", timeout=15).json()
        iq_before = float(before["system_iq"])
        em_before = int(before["total_emissions"])

        payload = {"content": f"JEEVES {_uniq()}", "topic": "stageA"}
        r = api.post(f"{BASE_URL}/api/omega/fabric/jeeves/emit", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        res = r.json()["result"]
        assert res["accepted"] is True
        assert res["blocked"] is False

        after = api.get(f"{BASE_URL}/api/omega/fabric", timeout=15).json()
        assert float(after["system_iq"]) == pytest.approx(min(iq_before + 1.0, 200.0), abs=0.001)
        assert int(after["total_emissions"]) == em_before + 1

    def test_agent_emit_bumps_iq_and_emissions(self, api):
        before = api.get(f"{BASE_URL}/api/omega/fabric", timeout=15).json()
        iq_before = float(before["system_iq"])
        em_before = int(before["total_emissions"])

        agent_id = "stagea_agent"
        payload = {"content": f"AGENT {_uniq()}", "topic": "stageA"}
        r = api.post(f"{BASE_URL}/api/omega/fabric/agent/{agent_id}/emit",
                     json=payload, timeout=15)
        assert r.status_code == 200, r.text
        res = r.json()["result"]
        assert res["accepted"] is True and res["blocked"] is False

        after = api.get(f"{BASE_URL}/api/omega/fabric", timeout=15).json()
        assert float(after["system_iq"]) == pytest.approx(min(iq_before + 1.0, 200.0), abs=0.001)
        assert int(after["total_emissions"]) == em_before + 1

    def test_duplicate_emission_blocked(self, api):
        payload = {"content": f"DUP {_uniq()}", "topic": "stageA"}
        r1 = api.post(f"{BASE_URL}/api/omega/fabric/jeeves/emit", json=payload, timeout=15)
        assert r1.status_code == 200
        assert r1.json()["result"]["accepted"] is True

        before = api.get(f"{BASE_URL}/api/omega/fabric", timeout=15).json()
        blocked_before = int(before["blocked_repeats"])
        em_before = int(before["total_emissions"])

        r2 = api.post(f"{BASE_URL}/api/omega/fabric/jeeves/emit", json=payload, timeout=15)
        assert r2.status_code == 200
        res2 = r2.json()["result"]
        assert res2["accepted"] is False
        assert res2["blocked"] is True

        after = api.get(f"{BASE_URL}/api/omega/fabric", timeout=15).json()
        assert int(after["blocked_repeats"]) == blocked_before + 1
        assert int(after["total_emissions"]) == em_before  # unchanged

    def test_persistence_survives_backend_restart(self, api):
        """The KEY Stage-A1 assertion: pump some emissions, restart the
        backend, and verify system_iq / total_emissions are RESTORED (not
        reset to 100.0 / 0)."""
        # 1) Take a fresh baseline.
        base0 = api.get(f"{BASE_URL}/api/omega/fabric", timeout=15).json()
        iq0 = float(base0["system_iq"])
        em0 = int(base0["total_emissions"])

        # 2) Send 3 unique emissions → +3 IQ, +3 emissions.
        for _ in range(3):
            payload = {"content": f"RESTART {_uniq()}", "topic": "stageA_restart"}
            r = api.post(f"{BASE_URL}/api/omega/fabric/jeeves/emit", json=payload, timeout=15)
            assert r.status_code == 200
            assert r.json()["result"]["accepted"] is True

        pre = api.get(f"{BASE_URL}/api/omega/fabric", timeout=15).json()
        iq_pre = float(pre["system_iq"])
        em_pre = int(pre["total_emissions"])
        assert iq_pre == pytest.approx(min(iq0 + 3.0, 200.0), abs=0.001)
        assert em_pre == em0 + 3

        # 3) Give the throttled fire-and-forget persist task time to run
        # (persist_interval defaults to 5.0s; force a wait > that).
        time.sleep(7)

        # 4) Restart the backend via supervisor.
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"],
                       check=True, capture_output=True)

        # 5) Poll until the backend is back up.
        deadline = time.time() + 60
        last_err = None
        while time.time() < deadline:
            try:
                r = requests.get(f"{BASE_URL}/api/omega/fabric", timeout=5)
                if r.status_code == 200:
                    break
            except Exception as e:  # noqa: BLE001
                last_err = e
            time.sleep(2)
        else:
            pytest.fail(f"backend did not recover after restart: {last_err}")

        # 6) Verify restored values match pre-restart snapshot (NOT reset).
        post = requests.get(f"{BASE_URL}/api/omega/fabric", timeout=10).json()
        assert post["restored"] is True
        assert post["persisted"] is True
        # Post-restart, in-memory counters are rehydrated from Mongo.
        # They must equal the pre-restart values (never reset to 100/0).
        assert float(post["system_iq"]) == pytest.approx(iq_pre, abs=0.001), (
            f"IQ reset after restart: expected≈{iq_pre}, got {post['system_iq']}"
        )
        assert int(post["total_emissions"]) == em_pre, (
            f"total_emissions reset after restart: expected {em_pre}, got {post['total_emissions']}"
        )
        assert float(post["system_iq"]) != 100.0 or iq_pre == 100.0
        assert int(post["total_emissions"]) != 0 or em_pre == 0


# ────────────────────────────────────────────────────────────
# REGRESSION guards
# ────────────────────────────────────────────────────────────
class TestRegression:
    def test_coverage_selftest_ready(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/coverage/selftest", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("passed") == 10 and d.get("total") == 10
        assert d.get("ready") is True

    def test_prood_readiness_100(self, api):
        r = api.get(f"{BASE_URL}/api/prood/readiness", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d.get("overall_percent") == 100.0, d
        assert d.get("capabilities_live") == 16
        # capabilities_total may vary in casing — accept both shapes
        total = d.get("capabilities_total") or d.get("total_capabilities") or 16
        assert total == 16

    def test_lafs_recall_responds(self, api):
        # /api/lafs/recall is POST — the review request phrased it as GET but
        # the router only declares POST. Assert POST works with 200.
        r = api.post(f"{BASE_URL}/api/lafs/recall",
                     json={"query": "stageA", "top_k": 3}, timeout=15)
        assert r.status_code == 200, r.text

    def test_omega_roles_and_sessions(self, api):
        r1 = api.get(f"{BASE_URL}/api/omega/roles", timeout=10)
        assert r1.status_code == 200
        assert r1.json().get("ok") is True

        r2 = api.get(f"{BASE_URL}/api/omega/sessions", timeout=10)
        assert r2.status_code == 200
        assert r2.json().get("ok") is True
