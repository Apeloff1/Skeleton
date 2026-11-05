"""Project-owned game jobs must be authorized, bounded, and actually run."""
from __future__ import annotations

import shutil
import time

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from skeleton.api import projects_routes
from skeleton.api.hmac_seal import mint_seal
from skeleton.api.middleware import GatePolicy, install_gate
from skeleton.app_services.container import AppServices


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", "project-build-integration-secret")
    monkeypatch.delenv("GF_SEAL_KEYRING", raising=False)
    svc = AppServices.open(tmp_path)
    svc.auth.register("owner@example.test", "correct-horse-battery-staple")
    session = svc.auth.login("owner@example.test", "correct-horse-battery-staple")
    headers = {"Authorization": f"Bearer {session.token}", "x-gf-seal": mint_seal("project-test")}
    app = FastAPI()
    app.include_router(projects_routes.build_router(lambda: svc), prefix="/api/v1")
    install_gate(app, policy=GatePolicy())
    with TestClient(app) as client:
        yield client, headers, svc
    svc.close()


def test_project_build_requires_forge_charter_before_enqueue(studio, monkeypatch):
    client, headers, svc = studio
    pid = client.post("/api/v1/projects", json={"brief": "Owned game"}, headers=headers).json()["project_id"]
    def deny(**kwargs):
        raise HTTPException(status_code=403, detail="forge denied")
    monkeypatch.setattr(projects_routes, "_FORGE_BUILD_GATE", deny)
    response = client.post(f"/api/v1/projects/{pid}/builds", json={"target": "godot"}, headers=headers)
    assert response.status_code == 403
    assert not svc.db.query("SELECT job_id FROM jobs")


def test_project_build_does_not_trust_client_governance_weight(studio, monkeypatch):
    from skeleton.kernel.governance import Governance, Rule

    client, headers, svc = studio
    pid = client.post("/api/v1/projects", json={"brief": "Restricted game"}, headers=headers).json()["project_id"]
    governance = Governance()
    governance.ratify("forge", [Rule(id="forge.run", action="run", min_weight=10)])
    monkeypatch.setattr("skeleton.api.charter_gate.get_governance", lambda: governance)
    response = client.post(f"/api/v1/projects/{pid}/builds", json={"target": "godot"},
                           headers={**headers, "x-gf-actor-weight": "999"})
    assert response.status_code == 403
    assert not svc.db.query("SELECT job_id FROM jobs")


@pytest.mark.parametrize("options", [
    {"binary": "/bin/sh", "playtest": "require"},
    {"brief": "replace owned project"},
    {"deadline_s": 121}, {"deadline_s": 10**400}, {"deadline_s": True}, {"max_rounds": 4},
    {"include_files": "true"}, {"playtest": "unknown"}, {"playtest": []},
    {"repair_mode": {}},
])
def test_project_build_rejects_unsafe_or_unbounded_options(studio, options):
    client, headers, svc = studio
    pid = client.post("/api/v1/projects", json={"brief": "Safe game"}, headers=headers).json()["project_id"]
    response = client.post(f"/api/v1/projects/{pid}/builds", json={"target": "godot", "options": options}, headers=headers)
    assert response.status_code == 400
    assert not svc.db.query("SELECT job_id FROM jobs")


def test_project_build_rejects_unavailable_console_target(studio):
    client, headers, svc = studio
    pid = client.post("/api/v1/projects", json={"brief": "Console game"}, headers=headers).json()["project_id"]
    response = client.post(f"/api/v1/projects/{pid}/builds", json={"target": "gb"}, headers=headers)
    assert response.status_code == 400
    assert not svc.db.query("SELECT job_id FROM jobs")


def test_project_link_limit_rolls_back_build_and_job(studio, monkeypatch):
    from skeleton.persistence.app_foundation.projects_v1 import ProjectsV1Store

    client, headers, svc = studio
    project = client.post("/api/v1/projects", json={"brief": "Full project"}, headers=headers).json()
    store = ProjectsV1Store(svc.db)
    for index in range(64):
        store.link(project["actor_id"], project["tenant_id"], project["project_id"], f"old-{index}")
    started = []
    monkeypatch.setattr(svc.jobs, "start_worker", lambda **kwargs: started.append(True))
    response = client.post(f"/api/v1/projects/{project['project_id']}/builds", json={"target": "godot"}, headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROJECT.BUILD_CONFLICT"
    assert not svc.db.query("SELECT job_id FROM jobs")
    assert not svc.db.query("SELECT build_id FROM builds")
    assert started == [True]


def test_project_job_is_linked_before_it_can_be_claimed(studio, monkeypatch):
    client, headers, svc = studio
    pid = client.post("/api/v1/projects", json={"brief": "Atomic project"}, headers=headers).json()["project_id"]
    observations = []
    enqueue = svc.jobs.enqueue
    def observe_enqueue(*args, **kwargs):
        handle = enqueue(*args, **kwargs)
        observations.extend(svc.db.query("SELECT j.job_id, j.execution_id, l.project_id FROM jobs j "
                                        "JOIN project_build_links l ON l.execution_id = j.execution_id"))
        return handle
    monkeypatch.setattr(svc.jobs, "start_worker", lambda **kwargs: None)
    monkeypatch.setattr(svc.jobs, "enqueue", observe_enqueue)
    response = client.post(f"/api/v1/projects/{pid}/builds", json={"target": "godot"}, headers=headers)
    assert response.status_code == 202
    assert len(observations) == 1
    assert observations[0]["execution_id"] == response.json()["build_id"]
    assert observations[0]["project_id"] == pid


def test_project_worker_failure_does_not_publish_job(studio, monkeypatch):
    client, headers, svc = studio
    pid = client.post("/api/v1/projects", json={"brief": "Worker unavailable"}, headers=headers).json()["project_id"]
    def unavailable(**kwargs):
        raise RuntimeError("private worker failure")
    monkeypatch.setattr(svc.jobs, "start_worker", unavailable)
    response = client.post(f"/api/v1/projects/{pid}/builds", json={"target": "godot"}, headers=headers)
    assert response.status_code == 503
    assert "private" not in response.text
    assert not svc.db.query("SELECT job_id FROM jobs")


@pytest.mark.skipif(shutil.which("godot") is None, reason="Requires local Godot runtime")
def test_owned_project_build_runs_real_godot_playtest(studio, monkeypatch):
    client, headers, svc = studio
    monkeypatch.setenv("SKELETON_GODOT_BIN", shutil.which("godot"))
    brief = {"title": "Harbor lantern platformer", "summary": "Cross the lantern docks and reach the goal.",
             "genre": "platformer", "constraints": []}
    created = client.post("/api/v1/projects", json={"brief": brief}, headers=headers)
    assert created.status_code == 201
    pid = created.json()["project_id"]
    response = client.post(f"/api/v1/projects/{pid}/builds", json={"target": "godot", "options": {
        "playtest": "require", "include_files": True, "max_rounds": 1, "deadline_s": 120,
    }}, headers=headers)
    assert response.status_code == 202, response.text
    build_id = response.json()["build_id"]
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        build = client.get(f"/api/v1/projects/{pid}/builds/{build_id}", headers=headers).json()
        if build["status"] in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(0.1)
    assert build["status"] == "succeeded", build
    assert build["result"]["ok"] is True
    assert build["result"]["structured_brief"] == {**brief, "schema_version": "skeleton.projects.v1"}
    assert "project.godot" in build["result"]["files"]
    assert build["result"]["playtest"]["status"] == "passed"
    assert svc.jobs.get_status(response.json()["job_id"]).status == "succeeded"
