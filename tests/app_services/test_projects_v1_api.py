import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton.api.projects_routes import build_router
from skeleton.app_services.container import AppServices


@pytest.fixture
def env(tmp_path):
    svc = AppServices.open(tmp_path)
    app = FastAPI()
    app.include_router(build_router(lambda: svc), prefix="/api/v1")
    a = svc.auth.register("a@example.com", "long-password-1")
    svc.auth.register("b@example.com", "long-password-2")
    ha = {"Authorization": "Bearer " + svc.auth.login("a@example.com", "long-password-1").token}
    hb = {"Authorization": "Bearer " + svc.auth.login("b@example.com", "long-password-2").token}
    return TestClient(app), ha, hb, svc, a


def err(r, status, code):
    assert r.status_code == status, r.text
    e = r.json()["error"]
    assert e["code"] == code and e["type"] == "ProjectContractError" and e["message"]


def test_auth_required_everywhere(env):
    c, *_ = env
    for m, path in [("post", "/api/v1/projects"), ("get", "/api/v1/projects"), ("get", "/api/v1/projects/p1"),
                    ("post", "/api/v1/projects/p1/builds"), ("get", "/api/v1/projects/p1/builds"),
                    ("get", "/api/v1/projects/p1/builds/b1")]:
        err(getattr(c, m)(path, headers={"Authorization": "Bearer bad"}), 401, "PROJECT.UNAUTHENTICATED")


def test_create_list_get(env):
    c, ha, hb, svc, a = env
    r = c.post("/api/v1/projects", json={"brief": "Space shooter\nboss rush"}, headers=ha)
    assert r.status_code == 201
    p = r.json()
    assert p["schema_version"] == "1.0.0" and p["status"] == "draft" and p["actor_id"] == a.user_id
    assert p["brief"] == {"title": "Space shooter", "summary": "boss rush", "genre": "", "constraints": []}
    assert p["created_at"].endswith("Z") and p["build_ids"] == []
    r2 = c.post("/api/v1/projects", json={"brief": {"title": "Puzzle", "genre": "puzzle", "constraints": ["gb"]}},
                headers={**ha, "Idempotency-Key": "k1"})
    assert r2.status_code == 201
    r3 = c.post("/api/v1/projects", json={"brief": {"title": "Puzzle"}}, headers={**ha, "Idempotency-Key": "k1"})
    assert r3.status_code == 200 and r3.json()["project_id"] == r2.json()["project_id"]
    err(c.post("/api/v1/projects", json={"brief": "Space shooter"}, headers=ha), 409, "PROJECT.NAME_CONFLICT")
    err(c.post("/api/v1/projects", json={"brief": ""}, headers=ha), 400, "PROJECT.INVALID")
    err(c.post("/api/v1/projects", json={"brief": "x", "owner": 1}, headers=ha), 400, "PROJECT.INVALID")
    err(c.post("/api/v1/projects", json={"brief": "x", "actor_id": "someone"}, headers=ha), 400, "PROJECT.INVALID")
    err(c.post("/api/v1/projects", json={}, headers=ha), 400, "PROJECT.INVALID")
    lst = c.get("/api/v1/projects?limit=1", headers=ha).json()
    assert len(lst["items"]) == 1 and lst["next_cursor"]
    lst2 = c.get(f"/api/v1/projects?limit=1&cursor={lst['next_cursor']}", headers=ha).json()
    assert lst2["items"][0]["project_id"] != lst["items"][0]["project_id"] and lst2["next_cursor"] is None
    err(c.get("/api/v1/projects?limit=0", headers=ha), 400, "PROJECT.INVALID")
    assert c.get("/api/v1/projects", headers=hb).json()["items"] == []
    assert c.get(f"/api/v1/projects/{p['project_id']}", headers=ha).json() == p
    err(c.get(f"/api/v1/projects/{p['project_id']}", headers=hb), 404, "PROJECT.NOT_FOUND")


def test_builds_start_link_list_get(env):
    c, ha, hb, svc, a = env
    pid = c.post("/api/v1/projects", json={"brief": "G"}, headers=ha).json()["project_id"]
    r = c.post(f"/api/v1/projects/{pid}/builds", json={"target": "gb", "idempotency_key": "x"},
               headers={**ha, "x-request-id": "rid"})
    assert r.status_code == 202
    b = r.json()
    assert b["status"] == "queued" and b["execution_id"] == b["build_id"] and b["job_id"] and not b["replayed"]
    again = c.post(f"/api/v1/projects/{pid}/builds", json={"target": "gb", "idempotency_key": "x"}, headers=ha)
    assert again.status_code == 202 and again.json()["build_id"] == b["build_id"] and again.json()["replayed"]
    proj = c.get(f"/api/v1/projects/{pid}", headers=ha).json()
    assert proj["status"] == "active" and proj["build_ids"] == [b["build_id"]]
    ln = c.post(f"/api/v1/projects/{pid}/builds", json={"execution_id": "exec-42"}, headers=ha)
    assert ln.status_code == 201 and ln.json()["replayed"] is False and ln.json()["schema_version"] == "1.0.0"
    ln2 = c.post(f"/api/v1/projects/{pid}/builds", json={"execution_id": "exec-42"}, headers=ha)
    assert ln2.status_code == 200 and ln2.json()["replayed"] is True
    err(c.post(f"/api/v1/projects/{pid}/builds", json={"execution_id": "bad id"}, headers=ha), 400, "PROJECT.INVALID")
    err(c.post(f"/api/v1/projects/{pid}/builds", json={"execution_id": "e", "target": "gb"}, headers=ha),
        400, "PROJECT.INVALID")
    err(c.post(f"/api/v1/projects/{pid}/builds", json={}, headers=hb), 404, "PROJECT.NOT_FOUND")
    items = c.get(f"/api/v1/projects/{pid}/builds", headers=ha).json()["items"]
    assert [i["build_id"] for i in items] == [b["build_id"]]
    assert c.get(f"/api/v1/projects/{pid}/builds/{b['build_id']}", headers=ha).json()["status"] == "queued"
    err(c.get(f"/api/v1/projects/{pid}/builds/nope", headers=ha), 404, "PROJECT.NOT_FOUND")
    err(c.get(f"/api/v1/projects/{pid}/builds", headers=hb), 404, "PROJECT.NOT_FOUND")


def test_storage_error_is_clean_503(env, monkeypatch):
    import sqlite3
    from skeleton.persistence.app_foundation import projects_v1
    c, ha, *_ = env

    def boom(*a, **k):
        raise sqlite3.OperationalError("disk I/O error at /secret/path")
    monkeypatch.setattr(projects_v1.ProjectsV1Store, "list", boom)
    r = c.get("/api/v1/projects", headers=ha)
    err(r, 503, "PROJECT.UNAVAILABLE")
    assert "secret" not in r.text


def test_create_app_mounts_projects_behind_gate(monkeypatch):
    from skeleton.api.middleware import GatePolicy
    assert GatePolicy().required_domain("/api/v1/projects/x") == "projects"


def test_seal_and_session_both_required(env, monkeypatch):
    from skeleton.api.hmac_seal import mint_seal
    from skeleton.api.middleware import GatePolicy, install_gate
    _, ha, _, svc, _ = env
    monkeypatch.setenv("GF_SEAL_SECRET", "test-seal-secret")
    monkeypatch.delenv("GF_SEAL_KEYRING", raising=False)
    app = FastAPI()
    app.include_router(build_router(lambda: svc), prefix="/api/v1")
    install_gate(app, policy=GatePolicy(open_prefixes=("/api/v1/health",)))
    c = TestClient(app)
    assert c.get("/api/v1/projects", headers=ha).status_code == 401  # no seal
    seal = {"x-gf-seal": mint_seal("sdk")}
    err(c.get("/api/v1/projects", headers=seal), 401, "PROJECT.UNAUTHENTICATED")  # seal, no session
    assert c.get("/api/v1/projects", headers={**seal, **ha}).status_code == 200
