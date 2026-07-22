"""Iteration 143 — P5 runtime (delegate/execute, groupchat, health, heartbeat)
and P6 error-recovery (alarms + auto-recover) tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@gameforge.io"
ADMIN_PASS = "GameForge#Admin2026"

RT = f"{BASE_URL}/api/gameforge/runtime"
GS = f"{BASE_URL}/api/gameforge/studio"


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(sess):
    r = sess.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Content-Type": "application/json", "Authorization": f"Bearer {admin_token}"}


# ── P5: Multi-Agent Runtime ────────────────────────────────────────────────
class TestP5Runtime:
    def test_delegate_execute(self, sess):
        r = sess.post(f"{RT}/delegate/execute",
                      json={"to_category": "engineering", "task": "TEST_iter143 build feature X"},
                      timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("assignee")
        assert d.get("role")
        assert isinstance(d.get("result"), str) and len(d["result"]) > 0

    def test_groupchat_list_after_execute(self, sess):
        r = sess.get(f"{RT}/groupchat?limit=10", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        msgs = d.get("messages") or []
        assert isinstance(msgs, list)
        assert len(msgs) >= 1
        m = msgs[0]
        assert "agent_id" in m and "content" in m and "ts" in m

    def test_groupchat_post(self, sess):
        r = sess.post(f"{RT}/groupchat",
                      json={"agent_id": "jeeves", "content": "TEST_iter143 hi from tests"}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("message_id")

    def test_health_endpoint(self, sess):
        r = sess.get(f"{RT}/health", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        for k in ("healthy", "stale", "dead"):
            assert isinstance(d.get(k), int), f"{k} not int"
        assert isinstance(d.get("agents"), list)

    def test_heartbeat_for_spawned_agent(self, sess):
        # spawn first to obtain a valid agent_id
        r = sess.post(f"{RT}/spawn", json={"category": "engineering", "count": 1}, timeout=15)
        assert r.status_code == 200
        spawned = r.json().get("spawned") or []
        assert spawned
        aid = spawned[0]
        r2 = sess.post(f"{RT}/heartbeat/{aid}", timeout=15)
        assert r2.status_code == 200
        d = r2.json()
        assert d.get("ok") is True
        assert d.get("agent_id") == aid

    def test_status_has_groupchat_count(self, sess):
        r = sess.get(f"{RT}/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        assert "groupchat" in d
        assert isinstance(d.get("groupchat"), int)


# ── P6: Error Recovery ────────────────────────────────────────────────────
class TestP6Recovery:
    def test_alarm_unauth(self, sess):
        r = sess.post(f"{GS}/alarm",
                      json={"kind": "test", "detail": "d", "severity": "warning"}, timeout=15)
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"

    def test_alarm_admin(self, sess, admin_headers):
        r = sess.post(f"{GS}/alarm",
                      json={"kind": "TEST_iter143", "detail": "d", "severity": "warning"},
                      headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert isinstance(d.get("alarm"), dict)
        assert d["alarm"].get("kind") == "TEST_iter143"

    def test_alarms_list(self, sess):
        r = sess.get(f"{GS}/alarms?limit=10", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert isinstance(d.get("alarms"), list)
        assert isinstance(d.get("unresolved"), int)

    def test_auto_recover_unauth(self, sess):
        r = sess.post(f"{GS}/auto-recover", json={"reason": "test"}, timeout=15)
        assert r.status_code == 401

    def test_auto_recover_admin(self, sess, admin_headers):
        r = sess.post(f"{GS}/auto-recover", json={"reason": "TEST_iter143"},
                      headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        # If a multi-version vault file exists, recovered:true and details are returned
        if d.get("recovered"):
            assert d.get("file_id")
            assert isinstance(d.get("restored_from"), int)
            assert isinstance(d.get("new_version"), int)
