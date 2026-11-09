"""Validate ProjectsClient request bodies against skeleton.projects.v1's JSON schema.

The schema (docs/architecture/contracts/projects.schema.json) lands with #4112;
this module skips when the file or ``jsonschema`` is absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

jsonschema = pytest.importorskip("jsonschema")

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "docs/architecture/contracts/projects.schema.json"
if not SCHEMA_PATH.is_file():
    pytest.skip(f"{SCHEMA_PATH.name} not on this branch (#4112)", allow_module_level=True)

from skeleton.client import GatewayClient, ProjectBrief, ProjectsClient  # noqa: E402

SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
PROJECT = {
    "schema_version": "1.0.0", "project_id": "p1", "actor_id": "u1", "tenant_id": "default",
    "brief": {"title": "t", "summary": "", "genre": "", "constraints": []}, "status": "draft",
    "build_ids": [], "created_at": "2026-10-17T16:00:00Z", "updated_at": "2026-10-17T16:00:00Z",
}
BUILD = {
    "schema_version": "1.0.0", "schema_id": "skeleton.projects.v1", "build_id": "b1",
    "execution_id": "b1", "project_id": "p1", "status": "queued", "target": "", "job_id": "j1",
    "result": {}, "error": "", "created_at": "2026-10-17T16:00:00Z",
    "updated_at": "2026-10-17T16:00:00Z", "replayed": False,
}
LINK = {"schema_version": "1.0.0", "project_id": "p1", "execution_id": "e1",
        "linked_at": "2026-10-17T16:00:00Z", "replayed": False}


def _validator(name):
    sub = {"$schema": SCHEMA.get("$schema"), "$defs": SCHEMA["$defs"], "$ref": f"#/$defs/{name}"}
    return jsonschema.Draft202012Validator(sub)


def _capture():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if req.url.path.endswith("/builds"):
            return httpx.Response(201 if "execution_id" in body else 202,
                                  json=LINK if "execution_id" in body else BUILD)
        return httpx.Response(201, json=PROJECT)

    gw = GatewayClient("http://t", client=httpx.Client(base_url="http://t",
                                                        transport=httpx.MockTransport(handler)))
    return ProjectsClient(gw, session_token="tok"), bodies


def test_schema_responses_used_here_are_valid():
    _validator("Project").validate(PROJECT)
    _validator("Build").validate(BUILD)
    _validator("ProjectBuildLink").validate(LINK)


def test_request_bodies_match_schema():
    pc, bodies = _capture()
    pc.create("A text brief\\nwith a summary")
    pc.create(ProjectBrief(title="Space", summary="s", genre="arcade", constraints=("2D",)))
    pc.create(ProjectBrief(title="Minimal"))
    for body in bodies[:3]:
        _validator("ProjectCreateRequest").validate(body)
    pc.start_build("p1")
    pc.start_build("p1", target="web", options={"opt": 1}, idempotency_key="k" * 128)
    for body in bodies[3:5]:
        _validator("BuildStartRequest").validate(body)
    pc.link_execution("p1", "e1")
    _validator("ProjectBuildLinkRequest").validate(bodies[5])
    for body in bodies:
        assert "actor_id" not in body and "tenant_id" not in body
