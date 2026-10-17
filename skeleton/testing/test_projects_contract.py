"""Projects schema skeleton.projects.v1 matches the #4097 resource shape at 1.1.0."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.ai.runtime.contracts.projects import PROJECTS_SCHEMA_VERSION as RUNTIME_VERSION
from skeleton.contracts.projects import (
    BUILD_STATUSES,
    PROJECT_ERROR_CONFLICT,
    PROJECT_ERROR_INVALID,
    PROJECT_ERROR_UNAUTHENTICATED,
    PROJECT_HTTP_STATUS,
    PROJECT_ROUTES,
    PROJECTS_IMPLEMENTATION,
    PROJECTS_SCHEMA_VERSION,
    Build,
    BuildCreateRequest,
    BuildList,
    BuildRequestMode,
    BuildStatus,
    Project,
    ProjectBrief,
    ProjectCaller,
    ProjectContractError,
    ProjectCreateRequest,
    ProjectList,
    brief_digest,
    parse_brief,
    project_error_envelope,
    project_name,
    visible_to,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "docs/architecture/contracts/projects.schema.json"
WHEN = 1_760_720_000.0


def _project(**overrides: object) -> Project:
    payload = {
        "project_id": "prj_lantern",
        "owner_id": "usr_owner",
        "name": "Lantern coast",
        "brief": "A short mystery.",
        "settings": {},
        "created_at": WHEN,
        "updated_at": WHEN,
    }
    payload.update(overrides)
    return Project(**payload)  # type: ignore[arg-type]


def _build(**overrides: object) -> Build:
    payload = {
        "build_id": "bld_one",
        "project_id": "prj_lantern",
        "status": BuildStatus.QUEUED,
        "target": "gb",
        "job_id": "job_one",
        "result": {},
        "error": "",
        "created_at": WHEN,
        "updated_at": WHEN,
        "execution_id": "exec_one",
    }
    payload.update(overrides)
    return Build(**payload)  # type: ignore[arg-type]


def test_schema_file_matches_python_routes_and_version() -> None:
    data = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert RUNTIME_VERSION == PROJECTS_SCHEMA_VERSION
    assert data["$id"] == "skeleton.projects.v1"
    assert data["x-schema-version"] == PROJECTS_SCHEMA_VERSION == "1.1.0"
    assert data["x-typed-module"] == "skeleton/contracts/projects.py"
    assert data["x-implementation"]["commit"] == PROJECTS_IMPLEMENTATION["commit"]
    assert data["x-implementation"]["observed_prefix"] == "/api/app/projects"
    routes = tuple((item["method"], item["path"], item["status"]) for item in data["x-routes"])
    assert routes == PROJECT_ROUTES
    assert routes[3][0:2] == ("POST", "/api/v1/projects/{project_id}/builds")
    codes = data["x-error-envelope"]["properties"]["error"]["properties"]["code"]["enum"]
    assert set(codes) == set(PROJECT_HTTP_STATUS)
    assert data["$defs"]["Build"]["properties"]["status"]["enum"] == list(BUILD_STATUSES)


def test_string_and_structured_briefs_both_round_trip() -> None:
    as_text = ProjectCreateRequest(brief="Space shooter for GB\nwith bosses")
    assert as_text.as_dict()["brief"] == "Space shooter for GB\nwith bosses"
    assert project_name(as_text.brief) == "Space shooter for GB"
    assert ProjectCreateRequest.from_dict(as_text.as_dict()) == as_text

    structured = ProjectBrief(title="Lantern coast", summary="A short mystery.", genre="adventure")
    as_object = ProjectCreateRequest(brief=structured, settings={"palette": "dusk"})
    restored = ProjectCreateRequest.from_dict(as_object.as_dict())
    assert restored.brief == structured
    assert project_name(restored.brief) == "Lantern coast"
    assert isinstance(parse_brief({"title": "Lantern coast"}), ProjectBrief)
    assert len(brief_digest("plain")) == 64
    assert brief_digest(structured) != brief_digest("plain")


def test_blank_explicit_name_falls_back_and_whitespace_brief_is_untitled() -> None:
    assert project_name("   \n", name="  ") == "Untitled project"
    assert project_name(ProjectBrief(title="Coast"), name="") == "Coast"


def test_session_owner_is_not_a_request_field() -> None:
    caller = ProjectCaller(actor_id="usr_owner", tenant_id="ten_one")
    assert caller.owner_id == "usr_owner"
    project = _project()
    assert visible_to(project, caller) is True
    assert visible_to(project, ProjectCaller(actor_id="usr_other")) is False
    with pytest.raises(ProjectContractError):
        ProjectCreateRequest.from_dict({"brief": "ok", "actor_id": "usr_owner", "tenant_id": "ten_one"})
    with pytest.raises(ProjectContractError):
        ProjectCreateRequest.from_dict({"brief": ""})


def test_project_list_uses_projects_key_and_epoch_timestamps() -> None:
    project = _project(brief=ProjectBrief(title="Lantern coast"))
    listing = ProjectList(projects=(project,))
    body = listing.as_dict()
    assert set(body) == {"projects"}
    assert ProjectList.from_dict(body).projects[0] == project
    assert body["projects"][0]["created_at"] == WHEN
    assert "actor_id" not in body["projects"][0]
    assert "build_ids" not in body["projects"][0]


def test_start_build_and_optional_link() -> None:
    start = BuildCreateRequest(target="gb", idempotency_key="k", options={"region": "us"})
    assert start.mode is BuildRequestMode.START
    assert "execution_id" not in start.as_dict()
    assert BuildCreateRequest.from_dict({}) == BuildCreateRequest()
    link = BuildCreateRequest.from_dict({"execution_id": "exec_one", "target": "gb"})
    assert link.mode is BuildRequestMode.LINK
    assert link.execution_id == "exec_one"

    started = _build()
    assert started.as_dict()["status"] == "queued"
    assert started.as_dict()["execution_id"] == "exec_one"
    linked = _build(status=BuildStatus.PENDING, job_id=None, execution_id="exec_linked")
    listing = BuildList(builds=(started, linked))
    assert [item["job_id"] for item in listing.as_dict()["builds"]] == ["job_one", None]
    assert Build.from_dict(linked.as_dict()) == linked


def test_error_envelope_replaces_detail_strings() -> None:
    body = project_error_envelope(PROJECT_ERROR_UNAUTHENTICATED, "invalid session")
    assert set(body) == {"error"}
    assert set(body["error"]) == {"type", "code", "message", "context"}
    assert body["error"]["code"] == "PROJECT.UNAUTHENTICATED"
    assert PROJECT_HTTP_STATUS[PROJECT_ERROR_INVALID] == 422
    assert PROJECT_HTTP_STATUS[PROJECT_ERROR_CONFLICT] == 409
    assert "detail" not in body


def test_unknown_build_status_and_identity_on_resource_fail() -> None:
    with pytest.raises(ProjectContractError):
        Build.from_dict({**_build().as_dict(), "status": "dead"})
    with pytest.raises(ProjectContractError):
        Project.from_dict({**_project().as_dict(), "tenant_id": "ten_one"})
    with pytest.raises(ProjectContractError):
        _build(execution_id="")
