from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton.app_services.container import AppServices
from skeleton.app_services.projects_api import build_router


def _client(tmp_path):
    svc = AppServices.open(tmp_path)
    app = FastAPI()
    app.include_router(build_router(lambda: svc))
    svc.auth.register("a@example.com", "long-password-1")
    svc.auth.register("b@example.com", "long-password-2")
    ta = svc.auth.login("a@example.com", "long-password-1").token
    tb = svc.auth.login("b@example.com", "long-password-2").token
    return TestClient(app), {"Authorization": f"Bearer {ta}"}, {"Authorization": f"Bearer {tb}"}, svc


def test_projects_routes_shapes_and_ownership(tmp_path):
    c, ha, hb, svc = _client(tmp_path)
    assert c.get("/api/app/projects").status_code == 401
    assert c.get("/api/app/projects", headers={"Authorization": "Bearer nope"}).json() == {"detail": "invalid_session"}
    r = c.post("/api/app/projects", json={"brief": "Space shooter for GB\nwith bosses"}, headers=ha)
    assert r.status_code == 201
    p = r.json()
    assert p["name"] == "Space shooter for GB" and p["brief"].startswith("Space")
    assert set(p) == {"project_id", "owner_id", "name", "brief", "settings", "created_at", "updated_at"}
    assert c.post("/api/app/projects", json={"brief": "x", "name": "Space shooter for GB"},
                  headers=ha).status_code == 409
    assert c.post("/api/app/projects", json={"brief": ""}, headers=ha).status_code == 422
    assert [x["project_id"] for x in c.get("/api/app/projects", headers=ha).json()["projects"]] == [p["project_id"]]
    assert c.get("/api/app/projects", headers=hb).json() == {"projects": []}
    pid = p["project_id"]
    assert c.get(f"/api/app/projects/{pid}", headers=ha).json() == p
    assert c.get(f"/api/app/projects/{pid}", headers=hb).status_code == 404
    b = c.post(f"/api/app/projects/{pid}/builds", json={"target": "gb", "idempotency_key": "k"},
               headers={**ha, "x-request-id": "rid-1"})
    assert b.status_code == 202 and b.json()["status"] == "queued" and b.json()["job_id"]
    assert svc.queue.get(b.json()["job_id"]).correlation_id == "rid-1"
    again = c.post(f"/api/app/projects/{pid}/builds", json={"target": "gb", "idempotency_key": "k"}, headers=ha)
    assert again.json()["job_id"] == b.json()["job_id"]
    lst = c.get(f"/api/app/projects/{pid}/builds", headers=ha).json()["builds"]
    assert b.json()["build_id"] in [x["build_id"] for x in lst]
    bid = b.json()["build_id"]
    assert c.get(f"/api/app/projects/{pid}/builds/{bid}", headers=ha).status_code == 200
    assert c.get(f"/api/app/projects/{pid}/builds/nope", headers=ha).json() == {"detail": "build_not_found"}
    assert c.post(f"/api/app/projects/{pid}/builds", json={}, headers=hb).status_code == 404
