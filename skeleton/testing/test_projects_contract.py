"""Projects schema skeleton.projects.v1 stays aligned with its JSON schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.contracts.projects import (
    PROJECTS_SCHEMA_VERSION,
    PROJECT_ERROR_INVALID,
    PROJECT_HTTP_STATUS,
    PROJECT_ROUTES,
    Project,
    ProjectBrief,
    ProjectBuildLink,
    ProjectBuildLinkRequest,
    ProjectContractError,
    ProjectCreateRequest,
    ProjectList,
    ProjectStatus,
    brief_digest,
    link_build,
    project_error_envelope,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "docs/architecture/contracts/projects.schema.json"
WHEN = "2026-10-17T15:00:00Z"


def _brief() -> ProjectBrief:
    return ProjectBrief(title="Lantern coast", summary="A short mystery.", genre="adventure")


def _project(*build_ids: str, status: ProjectStatus = ProjectStatus.DRAFT) -> Project:
    return Project(
        project_id="proj_lantern",
        actor_id="actor-1",
        tenant_id="tenant-1",
        brief=_brief(),
        status=status,
        build_ids=build_ids,
        created_at=WHEN,
        updated_at=WHEN,
    )


def test_schema_file_matches_python_routes_and_version() -> None:
    data = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert data["$id"] == "skeleton.projects.v1"
    assert data["x-schema-version"] == PROJECTS_SCHEMA_VERSION
    assert data["x-typed-module"] == "skeleton/contracts/projects.py"
    routes = tuple((item["method"], item["path"]) for item in data["x-routes"])
    assert routes == PROJECT_ROUTES
    assert set(data["x-error-envelope"]["properties"]["error"]["properties"]["code"]["enum"]) == set(
        PROJECT_HTTP_STATUS
    )


def test_create_from_brief_round_trip() -> None:
    request = ProjectCreateRequest(actor_id="actor-1", tenant_id="tenant-1", brief=_brief())
    restored = ProjectCreateRequest.from_dict(request.as_dict())
    assert restored == request
    assert restored.schema_version == "1.0.0"
    digest = brief_digest(restored.brief)
    assert len(digest) == 64
    assert brief_digest(restored.brief) == digest


def test_list_and_get_round_trip() -> None:
    project = _project()
    listing = ProjectList(items=(project,), next_cursor=None)
    assert ProjectList.from_dict(listing.as_dict()).items[0] == project
    assert Project.from_dict(project.as_dict()) == project


def test_link_appends_execution_and_replays() -> None:
    project, link = link_build(_project(), "exec_1", linked_at="2026-10-17T16:00:00Z")
    assert link.replayed is False
    assert project.status is ProjectStatus.ACTIVE
    assert project.build_ids == ("exec_1",)
    again, replay = link_build(project, "exec_1", linked_at="2026-10-17T17:00:00Z")
    assert again is project
    assert replay.replayed is True
    assert ProjectBuildLink.from_dict(replay.as_dict()) == replay


def test_link_request_uses_execution_id() -> None:
    body = ProjectBuildLinkRequest(actor_id="actor-1", tenant_id="tenant-1", execution_id="exec_1")
    assert body.as_dict()["execution_id"] == "exec_1"
    assert ProjectBuildLinkRequest.from_dict(body.as_dict()) == body


def test_unknown_fields_and_bad_brief_fail() -> None:
    with pytest.raises(ProjectContractError):
        ProjectBrief.from_dict({"title": "Ok", "pipeline": "secret"})
    with pytest.raises(ProjectContractError):
        ProjectBrief(title="  padded")
    with pytest.raises(ProjectContractError):
        ProjectBuildLink.from_dict(
            {
                "schema_version": "1.0.0",
                "project_id": "proj_lantern",
                "execution_id": "exec_1",
                "linked_at": WHEN,
                "replayed": "false",
            }
        )


def test_error_envelope_matches_skeleton_api_shape() -> None:
    body = project_error_envelope(PROJECT_ERROR_INVALID, "title must be non-empty")
    assert set(body) == {"error"}
    assert set(body["error"]) == {"type", "code", "message", "context"}
    assert PROJECT_HTTP_STATUS[body["error"]["code"]] == 400
