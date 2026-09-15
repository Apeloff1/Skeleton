"""
Stage B (Distributed rigor) validation for GameForge / PROOD:
  B1 — Real Byzantine quorum (POST /api/prood/quorum + GET /api/prood/quorum/status)
  B2 — Ship saga with compensation (POST /api/gameforge/studio/ship, POST /api/prood/saga/deploy)
  B3 — Durable event log (GET /api/prood/logs, GET /api/prood/events)
  B4 — Idempotency guard on ship
  REGRESSION — coverage/selftest, prood/readiness, omega/fabric persistence
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://player-retention.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@gameforge.io"
ADMIN_PASSWORD = "GameForge#Admin2026"


# ─────────────────────────── fixtures ───────────────────────────
@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code} {r.text[:200]}")
    tok = r.json().get("access_token")
    assert tok, "no access_token in login response"
    return tok


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ═══════════════════════ B1 — Byzantine Quorum ══════════════════════
class TestB1Quorum:
    def test_a_all_honest_decides(self, api):
        r = api.post(f"{BASE_URL}/api/prood/quorum",
                     json={"value": "canonical", "n": 7, "f": 2, "faulty": []}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert j.get("decided") is True
        assert j.get("quorum_needed") == 5
        assert j.get("commit_count", 0) >= 5, f"commit_count={j.get('commit_count')}"
        assert j.get("n") == 7 and j.get("f") == 2

    def test_b_within_fault_budget_decides(self, api):
        r = api.post(f"{BASE_URL}/api/prood/quorum",
                     json={"value": "canonical", "n": 7, "f": 2, "faulty": [0, 1]}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert j.get("decided") is True, f"decided must be True within f budget, got {j}"
        assert j.get("commit_count", 0) >= 5

    def test_c_exceeds_fault_budget_fails_safely(self, api):
        r = api.post(f"{BASE_URL}/api/prood/quorum",
                     json={"value": "canonical", "n": 7, "f": 2, "faulty": [0, 1, 2]}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert j.get("decided") is False, f"must NOT decide when faults exceed budget: {j}"
        # commit_count should be small (below quorum_needed=5)
        assert j.get("commit_count", 99) < 5

    def test_d_invalid_n_returns_error(self, api):
        r = api.post(f"{BASE_URL}/api/prood/quorum",
                     json={"value": "canonical", "n": 3, "f": 2}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is False
        assert "error" in j and j["error"], f"expected error, got {j}"
        assert "3f" in j["error"] or "BFT" in j["error"]

    def test_e_status_endpoint(self, api):
        r = api.get(f"{BASE_URL}/api/prood/quorum/status", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert j.get("n") == 7
        assert j.get("f") == 2
        assert j.get("quorum_needed") == 5
        assert "safety_bound" in j


# ═══════════════════════ B2 — Ship saga + compensation ══════════════════
class TestB2ShipSaga:
    def test_ship_completes_full_saga(self, api, admin_headers):
        r = api.post(f"{BASE_URL}/api/gameforge/studio/ship",
                     json={"game_name": f"B2ShipTest_{uuid.uuid4().hex[:6]}", "push": False},
                     headers=admin_headers, timeout=120)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "saga" in j, f"missing saga object: {list(j.keys())}"
        saga = j["saga"]
        assert saga.get("status") == "completed", f"saga status={saga.get('status')} err={saga.get('error')}"
        fwd = saga.get("forward_trace") or []
        names = [s.get("step") for s in fwd]
        for expected in ("web_build", "source_build", "git_commit"):
            assert expected in names, f"missing step {expected} in {names}"
        for step in fwd:
            if step["step"] in ("web_build", "source_build", "git_commit"):
                assert step.get("status") == "ok", f"step {step['step']} not ok: {step}"

    def test_saga_compensation_register_fail(self, api):
        r = api.post(f"{BASE_URL}/api/prood/saga/deploy",
                     json={"project_name": f"CompRegister_{uuid.uuid4().hex[:6]}",
                           "fail_at": "register"}, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("status") == "compensated", f"expected compensated, got {j.get('status')}: {j.get('error')}"
        ctrace = j.get("compensation_trace") or []
        # 'build' was completed, 'register' failed → build should be in comp trace (no_compensation is ok)
        build_comp = next((c for c in ctrace if c.get("step") == "build"), None)
        assert build_comp is not None, f"no build compensation entry: {ctrace}"

    def test_saga_compensation_deliver_fail_rolls_back_register(self, api):
        r = api.post(f"{BASE_URL}/api/prood/saga/deploy",
                     json={"project_name": f"CompDeliver_{uuid.uuid4().hex[:6]}",
                           "fail_at": "deliver"}, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("status") == "compensated", f"expected compensated, got {j}"
        ctrace = j.get("compensation_trace") or []
        register_comp = next((c for c in ctrace if c.get("step") == "register"), None)
        assert register_comp is not None, f"no register compensation entry: {ctrace}"
        assert register_comp.get("status") == "compensated", \
            f"register step must be 'compensated', got {register_comp}"


# ═══════════════════════ B3 — Durable event log ══════════════════════
class TestB3DurableLog:
    def test_quorum_and_omega_emit_persisted(self, api):
        # trigger a quorum decision
        q = api.post(f"{BASE_URL}/api/prood/quorum",
                     json={"value": f"b3-{uuid.uuid4().hex[:8]}", "n": 7, "f": 2, "faulty": []},
                     timeout=30)
        assert q.status_code == 200

        # unique omega emission — Bloom guard rejects duplicates
        unique = f"b3-unique-{uuid.uuid4().hex}"
        e = api.post(f"{BASE_URL}/api/omega/fabric/jeeves/emit",
                     json={"content": unique, "topic": "test.b3"}, timeout=30)
        assert e.status_code == 200, e.text

        # give the async persist a beat
        time.sleep(1.0)

        r = api.get(f"{BASE_URL}/api/prood/logs?limit=50", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert j.get("count", 0) > 0, f"expected log rows, got {j}"
        types = {row.get("event_type") for row in j.get("logs", [])}
        assert any(t in types for t in ("quorum.decided", "quorum.failed")), \
            f"no quorum.* in recent logs: {sorted(types)[:20]}"
        assert "iq.grow" in types, f"no iq.grow in recent logs: {sorted(types)[:20]}"

    def test_events_endpoint_still_returns_bus_stats(self, api):
        r = api.get(f"{BASE_URL}/api/prood/events", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        # event_bus.stats returns a dict with counts / recent history — check any well-known key
        assert isinstance(j, dict)
        # accept either 'published' | 'total' | 'history' — just ensure non-trivial payload
        assert len(j) > 1


# ═══════════════════════ B4 — Idempotency ══════════════════════
class TestB4Idempotency:
    def test_ship_idempotent_key_replay(self, api, admin_headers):
        key = f"idem-{uuid.uuid4().hex}"
        game = f"B4Idem_{uuid.uuid4().hex[:6]}"
        r1 = api.post(f"{BASE_URL}/api/gameforge/studio/ship",
                      json={"game_name": game, "push": False, "idempotency_key": key},
                      headers=admin_headers, timeout=120)
        assert r1.status_code == 200, r1.text
        j1 = r1.json()
        assert not j1.get("idempotent_replay"), f"first call must not be a replay: {j1}"
        assert "saga" in j1

        r2 = api.post(f"{BASE_URL}/api/gameforge/studio/ship",
                      json={"game_name": game, "push": False, "idempotency_key": key},
                      headers=admin_headers, timeout=60)
        assert r2.status_code == 200, r2.text
        j2 = r2.json()
        assert j2.get("idempotent_replay") is True, f"replay must be flagged: {j2}"
        assert "note" in j2 and "duplicate" in j2["note"].lower()


# ═══════════════════════ REGRESSION ══════════════════════
class TestRegression:
    def test_coverage_selftest_ready(self, api):
        r = api.get(f"{BASE_URL}/api/gameforge/coverage/selftest", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ready") is True, f"coverage/selftest not ready: {j}"
        # expect 10/10 form — accept either explicit count or passed/total
        passed = j.get("passed") or j.get("ok_count") or j.get("live")
        total = j.get("total") or j.get("count") or 10
        if passed is not None:
            assert passed == total, f"selftest {passed}/{total}"

    def test_prood_readiness_100(self, api):
        r = api.get(f"{BASE_URL}/api/prood/readiness", timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("overall_percent") == 100, f"overall_percent={j.get('overall_percent')}"
        assert j.get("capabilities_live") == 16, f"live={j.get('capabilities_live')}"
        assert j.get("capabilities_total") == 16, f"total={j.get('capabilities_total')}"

    def test_omega_fabric_persistence_flags(self, api):
        r = api.get(f"{BASE_URL}/api/omega/fabric", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "system_iq" in j, f"missing system_iq: {list(j.keys())}"
        assert j.get("persisted") is True, f"persisted={j.get('persisted')}"
        assert j.get("restored") is True, f"restored={j.get('restored')}"
        assert isinstance(j.get("recent_growth"), list), f"recent_growth not a list: {type(j.get('recent_growth'))}"
