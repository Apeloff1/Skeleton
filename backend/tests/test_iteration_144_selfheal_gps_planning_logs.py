"""Iteration 144 — self-healing runtime, GPS positioning, Tier-3 planning,
universal logging + regressions (vault unified, auto-recover, delegate/execute,
map/rooms)."""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or \
           os.environ.get("EXPO_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "admin@gameforge.io"
ADMIN_PASS = "GameForge#Admin2026"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token")
    assert tok, "no access_token"
    return tok


# ── self-healing runtime ───────────────────────────────────────────────
class TestSelfHealingRuntime:
    def test_reap_endpoint(self, api):
        r = api.post(f"{BASE_URL}/api/gameforge/runtime/reap", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert isinstance(j.get("reaped"), int)

    def test_health_auto_heals_dead_to_zero(self, api):
        r1 = api.get(f"{BASE_URL}/api/gameforge/runtime/health",
                     params={"auto_heal": "true"}, timeout=30)
        assert r1.status_code == 200
        j1 = r1.json()
        assert j1["ok"] is True
        for k in ("healthy", "stale", "dead", "reaped"):
            assert isinstance(j1.get(k), int), f"{k} not int: {j1.get(k)}"
        # second call should show 0 dead after auto-heal
        r2 = api.get(f"{BASE_URL}/api/gameforge/runtime/health",
                     params={"auto_heal": "true"}, timeout=30)
        assert r2.status_code == 200
        j2 = r2.json()
        assert j2["dead"] == 0, f"dead should be 0 after auto-heal, got {j2['dead']}"


# ── GPS positioning ─────────────────────────────────────────────────────
class TestGPSPositioning:
    def test_positions_returns_agents_and_rooms(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/runtime/positions", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert isinstance(j.get("positions"), list)
        assert isinstance(j.get("rooms"), dict)
        assert isinstance(j.get("active_rooms"), int)
        if j["positions"]:
            p = j["positions"][0]
            for k in ("agent_id", "room_id", "category", "task", "health"):
                assert k in p, f"position missing {k}: {p}"

    def test_set_position(self, api):
        # spawn a temp agent
        sp = api.post(f"{BASE_URL}/api/gameforge/runtime/spawn",
                      json={"category": "engineering", "count": 1}, timeout=30)
        assert sp.status_code == 200
        aid = sp.json()["spawned"][0]
        r = api.post(f"{BASE_URL}/api/gameforge/runtime/position/{aid}",
                     json={"room_id": "code_room", "task": "x"}, timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True


# ── Tier-3 planning ─────────────────────────────────────────────────────
class TestPlanning:
    def test_strategic_plan(self, api):
        payload = {"objective": "TEST_iter144", "horizon_days": 45,
                   "base_risk": 0.25, "scenario": "aggressive_timeline"}
        r = api.post(f"{BASE_URL}/api/gameforge/planning/strategic-plan",
                     json=payload, timeout=60)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert "forecast" in j
        assert "curve" in j["risk"] and "final_risk" in j["risk"]
        assert "critical_path" in j["dependency"]
        assert "success_probability" in j["simulation"]
        assert "recommendation" in j["simulation"]
        assert isinstance(j["workflow"], list) and len(j["workflow"]) > 0

    def test_plans_list(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/planning/plans", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert isinstance(j["plans"], list)

    def test_forecast_endpoint(self, api):
        r = api.post(f"{BASE_URL}/api/gameforge/planning/forecast",
                     json={"horizon_days": 30}, timeout=30)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_risk_endpoint(self, api):
        r = api.post(f"{BASE_URL}/api/gameforge/planning/risk",
                     json={"base_risk": 0.3, "horizon_days": 45}, timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True and "curve" in j

    def test_simulate_endpoint(self, api):
        r = api.post(f"{BASE_URL}/api/gameforge/planning/simulate",
                     json={"base_risk": 0.3, "horizon_days": 45,
                           "scenario": "aggressive_timeline"}, timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True and "success_probability" in j


# ── Universal logging ──────────────────────────────────────────────────
class TestUniversalLogs:
    def test_logs_default(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/studio/logs",
                    params={"limit": 20}, timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert isinstance(j["logs"], list)
        if j["logs"]:
            e = j["logs"][0]
            for k in ("component", "severity", "event"):
                assert k in e, f"log missing {k}"

    def test_logs_component_filter_audit(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/studio/logs",
                    params={"component": "audit", "limit": 20}, timeout=30)
        assert r.status_code == 200
        j = r.json()
        for e in j["logs"]:
            assert e["component"] == "audit"

    def test_logs_severity_filter_error(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/studio/logs",
                    params={"severity": "error", "limit": 20}, timeout=30)
        assert r.status_code == 200
        j = r.json()
        for e in j["logs"]:
            assert e["severity"] == "error"


# ── Regressions ────────────────────────────────────────────────────────
class TestRegressions:
    def test_vault_unified(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/studio/vault/unified", timeout=45)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_auto_recover_admin(self, api, admin_token):
        r = api.post(f"{BASE_URL}/api/gameforge/studio/auto-recover",
                     headers={"Authorization": f"Bearer {admin_token}"},
                     json={}, timeout=45)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_delegate_execute(self, api):
        r = api.post(f"{BASE_URL}/api/gameforge/runtime/delegate/execute",
                     json={"from_agent": "jeeves", "to_category": "engineering",
                           "task": "TEST_iter144 verify"}, timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert j.get("assignee")
        # verify posted to groupchat
        gc = api.get(f"{BASE_URL}/api/gameforge/runtime/groupchat",
                     params={"channel": "general", "limit": 5}, timeout=30)
        assert gc.status_code == 200
        assert isinstance(gc.json()["messages"], list)
        assert len(gc.json()["messages"]) > 0

    def test_map_rooms_1000(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/map/rooms", timeout=30)
        assert r.status_code == 200
        j = r.json()
        count = j.get("total") or j.get("count") or 0
        assert count == 1000, f"expected 1000 rooms, got {count}"
