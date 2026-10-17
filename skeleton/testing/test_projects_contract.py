"""skeleton.projects.v1 matches the #4097 router at commit 959eec134."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.ai.runtime.contracts.projects import (
    PROJECTS_SCHEMA_VERSION as RUNTIME_VERSION,
)
from skeleton.contracts.projects import (
    BUILD_STATUSES,
    PROJECT_ERROR_IDEMPOTENCY_MISMATCH,
    PROJECT_ERROR_NAME_CONFLICT,
    PROJECT_ERROR_UNAUTHENTICATED,
    PROJECT_ERROR_UNAVAILABLE,
    PROJECT_HTTP_STATUS,
    PROJECT_ROUTES,
    PROJECTS_IMPLEMENTATION,
    PROJECTS_SCHEMA_ID,
    PROJECTS_SCHEMA_VERSION,
    Build,
    BuildList,
    BuildRequestMode,
    BuildStartRequest,
    BuildStatus,
    Project,
    ProjectBrief,
    ProjectBuildLink,
    ProjectBuildLinkRequest,
    ProjectContractError,
    ProjectCreateRequest,
    ProjectList,
    ProjectStatus,
    assert_session_scope,
    brief_digest,
    build_idempotency_scope,
    create_idempotency_scope,
    link_build,
    page_cursor,
    page_limit,
    parse_brief,
    parse_build_request,
    project_error_envelope,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "docs/architecture/contracts/projects.schema.json"
WHEN = "2026-10-17T16:00:00.000000Z"


def _project(*build_ids: str, status: ProjectStatus = ProjectStatus.DRAFT) -> Project:
    return Project(
        project_id="prj_lantern",
        actor_id="usr_owner",
        tenant_id="default",
        brief=ProjectBrief(title="Lantern coast", summary="A short mystery.", genre="adventure"),
        status=status,
        build_ids=build_ids,
        created_at=WHEN,
        updated_at=WHEN,
    )


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
        "execution_id": "bld_one",
        "replayed": False,
    }
    payload.update(overrides)
    return Build(**payload)  # type: ignore[arg-type]


def test_schema_file_matches_the_checked_router() -> None:
    data = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert RUNTIME_VERSION == PROJECTS_SCHEMA_VERSION == "1.0.0"
    assert data["$id"] == PROJECTS_SCHEMA_ID == "skeleton.projects.v1"
    assert data["x-schema-version"] == PROJECTS_SCHEMA_VERSION
    assert data["x-implementation"]["commit"] == PROJECTS_IMPLEMENTATION["commit"]
    assert data["x-implementation"]["job_queue"] == "docs/contracts/job_queue.md"
    routes = tuple((item["method"], item["path"], item["status"]) for item in data["x-routes"])
    assert routes == PROJECT_ROUTES
    codes = data["x-error-envelope"]["properties"]["error"]["properties"]["code"]["enum"]
    assert set(codes) == set(PROJECT_HTTP_STATUS)
    assert data["$defs"]["Build"]["properties"]["status"]["enum"] == list(BUILD_STATUSES)
    assert (ROOT / "docs/contracts/job_queue.md").is_file()


def test_string_brief_becomes_title_and_summary() -> None:
    brief = parse_brief("Space shooter\nboss rush")
    assert brief.as_dict() == {
        "title": "Space shooter",
        "summary": "boss rush",
        "genre": "",
        "constraints": [],
    }
    structured = parse_brief({"title": "Puzzle", "genre": "puzzle", "constraints": ["gb"]})
    assert structured.title == "Puzzle" and structured.constraints == ("gb",)
    created = ProjectCreateRequest.from_dict({"brief": "Space shooter\nboss rush"})
    assert created.actor_id is None and created.brief == brief
    assert ProjectCreateRequest.from_dict(created.as_dict()).brief == brief
    with pytest.raises(ProjectContractError):
        parse_brief("")
    with pytest.raises(ProjectContractError):
        ProjectCreateRequest.from_dict({"brief": "x", "owner": 1})
    with pytest.raises(ProjectContractError):
        assert_session_scope({"brief": "x", "actor_id": "someone"}, actor_id="usr_owner", tenant_id="default")
    assert_session_scope({"actor_id": "usr_owner"}, actor_id="usr_owner", tenant_id="default")
    assert len(brief_digest(brief)) == 64


def test_project_list_keeps_actor_tenant_and_cursor() -> None:
    project = _project()
    listing = ProjectList(items=(project,), next_cursor="r:1")
    body = listing.as_dict()
    assert set(body) == {"schema_version", "items", "next_cursor"}
    assert body["items"][0]["actor_id"] == "usr_owner"
    assert body["items"][0]["brief"]["title"] == "Lantern coast"
    assert ProjectList.from_dict(body).items[0] == project
    assert page_limit("50") == 50
    with pytest.raises(ProjectContractError):
        page_limit("0")
    with pytest.raises(ProjectContractError):
        page_cursor("zzz")
    assert page_cursor("r:12") == "r:12"


def test_start_build_and_optional_link() -> None:
    start = parse_build_request({"target": "gb", "idempotency_key": "x"})
    assert isinstance(start, BuildStartRequest)
    assert start.mode is BuildRequestMode.START
    assert build_idempotency_scope("default", "usr_owner", "prj_lantern", "x") == (
        "default:usr_owner:game.build:prj_lantern:x"
    )
    assert create_idempotency_scope("default", "usr_owner", "ck") == "default:usr_owner:ck"
    link = parse_build_request({"execution_id": "exec-42"})
    assert isinstance(link, ProjectBuildLinkRequest)
    assert link.execution_id == "exec-42"
    with pytest.raises(ProjectContractError):
        parse_build_request({"execution_id": "e", "target": "gb"})
    with pytest.raises(ProjectContractError):
        parse_build_request({"execution_id": "bad id"})

    started = _build()
    assert started.as_dict()["execution_id"] == started.build_id
    assert started.as_dict()["schema_id"] == "skeleton.projects.v1"
    assert started.as_dict()["replayed"] is False
    replay = _build(replayed=True)
    listing = BuildList(items=(replay,), next_cursor=None)
    assert listing.as_dict()["items"][0]["status"] == "queued"
    assert Build.from_dict(started.as_dict()) == started


def test_link_appends_execution_and_replays() -> None:
    project, link = link_build(_project(), "exec-42", linked_at=WHEN)
    assert link.replayed is False
    assert project.status is ProjectStatus.ACTIVE
    assert project.build_ids == ("exec-42",)
    again, replay = link_build(project, "exec-42", linked_at="2026-10-17T17:00:00.000000Z")
    assert again is project and replay.replayed is True
    assert ProjectBuildLink.from_dict(replay.as_dict()) == replay


def test_error_envelope_includes_the_409_and_503_codes() -> None:
    body = project_error_envelope(PROJECT_ERROR_IDEMPOTENCY_MISMATCH, "key reused with a different body")
    assert set(body["error"]) == {"type", "code", "message", "context"}
    assert body["error"]["code"] == "PROJECT.IDEMPOTENCY_MISMATCH"
    assert PROJECT_HTTP_STATUS[PROJECT_ERROR_NAME_CONFLICT] == 409
    assert PROJECT_HTTP_STATUS[PROJECT_ERROR_UNAUTHENTICATED] == 401
    assert PROJECT_HTTP_STATUS[PROJECT_ERROR_UNAVAILABLE] == 503
    assert "detail" not in body
