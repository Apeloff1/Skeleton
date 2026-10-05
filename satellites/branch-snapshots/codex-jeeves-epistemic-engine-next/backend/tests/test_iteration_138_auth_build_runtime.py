"""
Iteration 138 backend tests:
  1) Auth (JWT + RBAC seed admin)
  2) Real Build tool integration (web / source zip / download)
  3) Multi-agent runtime (spawn / message / delegate / complete / status / terminate)
  4) RBAC dev-mode passthrough (vault put/rollback still work without token)
  5) Regression: activate 4/4, observability 100, map/systems 19/19, vault CRUD
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE = os.environ["EXPO_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@gameforge.io"
ADMIN_PASS = "GameForge#Admin2026"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------- 1) AUTH ----------
class TestAuth:
    def test_login_admin(self, s):
        r = s.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("role") == "admin"
        assert d.get("access_token")
        pytest.admin_token = d["access_token"]

    def test_me_with_token(self, s):
        tok = pytest.admin_token
        r = s.get(f"{BASE}/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        d = r.json()
        assert d.get("authenticated") is True
        assert d.get("enforced") is False
        assert d["user"].get("role") == "admin"

    def test_login_wrong_password(self, s):
        r = s.post(f"{BASE}/api/auth/login",
                   json={"email": ADMIN_EMAIL, "password": "wrong-pass"})
        assert r.status_code == 401

    def test_register_local_email_rejected(self, s):
        r = s.post(f"{BASE}/api/auth/register",
                   json={"email": "someone@example.local", "password": "password123"})
        assert r.status_code == 422

    def test_register_viewer_ok(self, s):
        u = f"TEST_{uuid.uuid4().hex[:6]}@gameforge.io"
        r = s.post(f"{BASE}/api/auth/register", json={"email": u, "password": "password123"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("role") == "viewer"
        assert d.get("access_token")


# ---------- 2) REAL BUILD ----------
class TestRealBuild:
    def test_toolchains(self, s):
        r = s.get(f"{BASE}/api/gameforge/build/toolchains")
        assert r.status_code == 200
        tc = r.json()["toolchains"]
        assert tc["web"] is True
        assert tc["source_zip"] is True
        assert tc["godot"] is False
        assert tc["unity"] is False
        assert tc["pyinstaller"] is False

    def test_build_web_produces_zip(self, s):
        r = s.post(f"{BASE}/api/gameforge/build/web", json={"game_name": "Studio"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["size_bytes"] > 0
        assert len(d.get("sha256", "")) == 64
        assert d.get("download_url")
        pytest.web_build_id = d["build_id"]

    def test_build_source_produces_zip(self, s):
        r = s.post(f"{BASE}/api/gameforge/build/source", json={"game_name": "Studio"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["size_bytes"] > 0
        pytest.src_build_id = d["build_id"]

    def test_download_web_zip(self, s):
        bid = pytest.web_build_id
        r = s.get(f"{BASE}/api/gameforge/build/download/{bid}")
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "zip" in ct.lower(), ct
        # Zip magic bytes
        assert r.content[:2] == b"PK"

    def test_list_builds(self, s):
        r = s.get(f"{BASE}/api/gameforge/build/list")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d.get("builds"), list)
        assert len(d["builds"]) >= 2


# ---------- 3) MULTI-AGENT RUNTIME ----------
class TestRuntime:
    def test_spawn_three(self, s):
        r = s.post(f"{BASE}/api/gameforge/runtime/spawn",
                   json={"category": "engineering", "count": 3})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert len(d["spawned"]) == 3
        assert d["role"].get("role_name")
        pytest.spawned = d["spawned"]

    def test_list_agents(self, s):
        r = s.get(f"{BASE}/api/gameforge/runtime/agents")
        assert r.status_code == 200
        d = r.json()
        assert d["counts"]["active"] >= 3

    def test_delegate_task(self, s):
        r = s.post(f"{BASE}/api/gameforge/runtime/delegate",
                   json={"to_category": "art", "task": "design a hero sprite"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d.get("task_id")
        assert d.get("assignee")
        pytest.task_id = d["task_id"]
        pytest.assignee = d["assignee"]

    def test_message_and_inbox(self, s):
        a = pytest.spawned[0]
        b = pytest.spawned[1]
        r = s.post(f"{BASE}/api/gameforge/runtime/message",
                   json={"from_agent": a, "to_agent": b, "content": "hello, teammate"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        r2 = s.get(f"{BASE}/api/gameforge/runtime/inbox/{b}")
        assert r2.status_code == 200
        msgs = r2.json()["messages"]
        assert any(m["content"] == "hello, teammate" for m in msgs)

    def test_complete_task(self, s):
        r = s.post(f"{BASE}/api/gameforge/runtime/complete",
                   json={"task_id": pytest.task_id, "result": "done"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["status"] == "done"

    def test_status(self, s):
        r = s.get(f"{BASE}/api/gameforge/runtime/status")
        assert r.status_code == 200
        d = r.json()
        for k in ("active_agents", "terminated_agents", "messages", "tasks_open", "tasks_done"):
            assert k in d
        assert d["tasks_done"] >= 1

    def test_terminate(self, s):
        aid = pytest.spawned[-1]
        r = s.post(f"{BASE}/api/gameforge/runtime/terminate", json={"agent_id": aid})
        assert r.status_code == 200
        assert r.json()["ok"] is True


# ---------- 4) RBAC dev-mode passthrough ----------
class TestVaultDevMode:
    def test_vault_put_without_token(self, s):
        payload = {"game_name": "Studio", "filename": f"TEST_{uuid.uuid4().hex[:6]}.txt",
                   "content": "hello vault", "metadata": {"kind": "note"}}
        r = s.post(f"{BASE}/api/gameforge/studio/vault/put", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        pytest.vault_file_id = d.get("file_id") or d.get("id")

    def test_vault_rollback_without_token(self, s):
        # push one more version to have something to rollback
        payload = {"game_name": "Studio", "filename": f"TEST_rb_{uuid.uuid4().hex[:6]}.txt",
                   "content": "v1", "metadata": {"kind": "note"}}
        p1 = s.post(f"{BASE}/api/gameforge/studio/vault/put", json=payload).json()
        fid = p1.get("file_id") or p1.get("id")
        assert fid, p1
        # bump version
        payload["content"] = "v2"
        p2 = s.post(f"{BASE}/api/gameforge/studio/vault/put",
                    json={**payload, "file_id": fid}).json()
        # rollback
        r = s.post(f"{BASE}/api/gameforge/studio/vault/{fid}/rollback", json={"to_version": 1})
        assert r.status_code == 200, r.text


# ---------- 5) REGRESSION ----------
class TestRegression:
    def test_activate(self, s):
        r = s.post(f"{BASE}/api/gameforge/activate", json={})
        assert r.status_code == 200
        d = r.json()
        assert d.get("activated") == 4
        assert d.get("total") == 4
        assert d.get("status") == "live"

    def test_observability(self, s):
        r = s.get(f"{BASE}/api/gameforge/studio/observability")
        assert r.status_code == 200
        d = r.json()
        hs = d.get("health_score") or d.get("score")
        assert hs == 100, d

    def test_map_systems(self, s):
        r = s.get(f"{BASE}/api/gameforge/map/systems")
        assert r.status_code == 200
        d = r.json()
        systems = d.get("systems") or d.get("items") or []
        total = d.get("total") or len(systems)
        assert total == 19, d
