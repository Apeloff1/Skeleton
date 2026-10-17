"""Projects resource contract, version 1.0.0.

This is the alignment surface for the app foundation client and frontend.
HTTP routes are specified here and are not mounted yet: there is no
Projects router on the engine or the backend. Clients must not call the
paths until a later charter lands the handlers.

Builds are engine executions. A project links to them by ``execution_id``,
the same identifier ``BuildsClient`` uses for
``/api/v1/engine/executions/{execution_id}``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping


PROJECTS_SCHEMA_VERSION = "1.0.0"
PROJECTS_SCHEMA_ID = "skeleton.projects.v1"

# Kept in lockstep with docs/architecture/contracts/projects.schema.json.
PROJECT_ROUTES: tuple[tuple[str, str], ...] = (
    ("POST", "/api/v1/projects"),
    ("GET", "/api/v1/projects"),
    ("GET", "/api/v1/projects/{project_id}"),
    ("POST", "/api/v1/projects/{project_id}/builds"),
)

PROJECT_ERROR_INVALID = "PROJECT.INVALID"
PROJECT_ERROR_NOT_FOUND = "PROJECT.NOT_FOUND"
PROJECT_ERROR_BUILD_CONFLICT = "PROJECT.BUILD_CONFLICT"

PROJECT_HTTP_STATUS = {
    PROJECT_ERROR_INVALID: 400,
    PROJECT_ERROR_NOT_FOUND: 404,
    PROJECT_ERROR_BUILD_CONFLICT: 409,
}

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_SUMMARY = 8_000
_MAX_TITLE = 200
_MAX_CONSTRAINTS = 32
_MAX_BUILDS = 64
_MAX_PAGE = 100


class ProjectContractError(ValueError):
    """A projects document violates schema skeleton.projects.v1."""


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


def project_error_envelope(
    code: str,
    message: str,
    *,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Skeleton API error envelope. Secret values do not belong in context."""

    if code not in PROJECT_HTTP_STATUS:
        raise ProjectContractError(f"unknown project error code {code!r}")
    if not isinstance(message, str) or not message or message != message.strip():
        raise ProjectContractError("error message must be non-empty normalized text")
    safe_context = dict(context or {})
    return {
        "error": {
            "type": "ProjectContractError",
            "code": code,
            "message": message,
            "context": safe_context,
        }
    }


def _id(value: object, field: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ProjectContractError(f"{field} must be a path-safe identifier")
    return value


def _text(value: object, field: str, *, max_length: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ProjectContractError(f"{field} must be text")
    if value != value.strip():
        raise ProjectContractError(f"{field} must be normalized")
    if not value and not allow_empty:
        raise ProjectContractError(f"{field} must be non-empty")
    if len(value) > max_length:
        raise ProjectContractError(f"{field} exceeds maximum length")
    return value


def _timestamp(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProjectContractError(f"{field} must be RFC3339 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ProjectContractError(f"{field} is invalid RFC3339 UTC") from exc
    if parsed.tzinfo is None:
        raise ProjectContractError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _mapping(value: object, field: str, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProjectContractError(f"{field} must be an object")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ProjectContractError(f"{field} has unknown fields: {unknown}")
    return value


def _version(value: object) -> str:
    if value != PROJECTS_SCHEMA_VERSION:
        raise ProjectContractError(
            f"schema_version must be {PROJECTS_SCHEMA_VERSION}"
        )
    return PROJECTS_SCHEMA_VERSION


@dataclass(frozen=True)
class ProjectBrief:
    title: str
    summary: str = ""
    genre: str = ""
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _text(self.title, "title", max_length=_MAX_TITLE))
        object.__setattr__(
            self, "summary", _text(self.summary, "summary", max_length=_MAX_SUMMARY, allow_empty=True)
        )
        object.__setattr__(
            self, "genre", _text(self.genre, "genre", max_length=80, allow_empty=True)
        )
        if isinstance(self.constraints, (str, bytes)) or not isinstance(self.constraints, tuple):
            raise ProjectContractError("constraints must be a tuple of strings")
        if len(self.constraints) > _MAX_CONSTRAINTS:
            raise ProjectContractError("constraints exceed the maximum count")
        object.__setattr__(
            self,
            "constraints",
            tuple(_text(item, "constraints", max_length=_MAX_TITLE) for item in self.constraints),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "genre": self.genre,
            "constraints": list(self.constraints),
        }

    @classmethod
    def from_dict(cls, value: object) -> "ProjectBrief":
        data = _mapping(value, "brief", {"title", "summary", "genre", "constraints"})
        raw_constraints = data.get("constraints", [])
        if isinstance(raw_constraints, (str, bytes)) or not isinstance(raw_constraints, list):
            raise ProjectContractError("constraints must be a list")
        return cls(
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            genre=data.get("genre", ""),
            constraints=tuple(raw_constraints),
        )


def brief_digest(brief: ProjectBrief) -> str:
    """Stable digest of a brief for internal handoff. Not an HTTP field."""

    if not isinstance(brief, ProjectBrief):
        raise ProjectContractError("brief must be a ProjectBrief")
    raw = json.dumps(brief.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProjectCreateRequest:
    """POST /api/v1/projects body. Non-idempotent unless Idempotency-Key is sent."""

    actor_id: str
    tenant_id: str
    brief: ProjectBrief
    schema_version: str = PROJECTS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        object.__setattr__(self, "actor_id", _id(self.actor_id, "actor_id"))
        object.__setattr__(self, "tenant_id", _id(self.tenant_id, "tenant_id"))
        if not isinstance(self.brief, ProjectBrief):
            raise ProjectContractError("brief must be a ProjectBrief")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "actor_id": self.actor_id,
            "tenant_id": self.tenant_id,
            "brief": self.brief.as_dict(),
        }

    @classmethod
    def from_dict(cls, value: object) -> "ProjectCreateRequest":
        data = _mapping(
            value,
            "project_create",
            {"schema_version", "actor_id", "tenant_id", "brief"},
        )
        return cls(
            actor_id=data.get("actor_id", ""),
            tenant_id=data.get("tenant_id", ""),
            brief=ProjectBrief.from_dict(data.get("brief")),
            schema_version=data.get("schema_version", ""),
        )


@dataclass(frozen=True)
class Project:
    project_id: str
    actor_id: str
    tenant_id: str
    brief: ProjectBrief
    status: ProjectStatus
    build_ids: tuple[str, ...]
    created_at: str
    updated_at: str
    schema_version: str = PROJECTS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        object.__setattr__(self, "project_id", _id(self.project_id, "project_id"))
        object.__setattr__(self, "actor_id", _id(self.actor_id, "actor_id"))
        object.__setattr__(self, "tenant_id", _id(self.tenant_id, "tenant_id"))
        if not isinstance(self.brief, ProjectBrief):
            raise ProjectContractError("brief must be a ProjectBrief")
        if not isinstance(self.status, ProjectStatus):
            raise ProjectContractError("status must be a ProjectStatus")
        if isinstance(self.build_ids, (str, bytes)) or not isinstance(self.build_ids, tuple):
            raise ProjectContractError("build_ids must be a tuple")
        if len(self.build_ids) > _MAX_BUILDS:
            raise ProjectContractError("build_ids exceed the maximum count")
        if len(set(self.build_ids)) != len(self.build_ids):
            raise ProjectContractError("build_ids must be unique")
        object.__setattr__(
            self,
            "build_ids",
            tuple(_id(item, "build_ids") for item in self.build_ids),
        )
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _timestamp(self.updated_at, "updated_at"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "actor_id": self.actor_id,
            "tenant_id": self.tenant_id,
            "brief": self.brief.as_dict(),
            "status": self.status.value,
            "build_ids": list(self.build_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: object) -> "Project":
        data = _mapping(
            value,
            "project",
            {
                "schema_version",
                "project_id",
                "actor_id",
                "tenant_id",
                "brief",
                "status",
                "build_ids",
                "created_at",
                "updated_at",
            },
        )
        raw_builds = data.get("build_ids", [])
        if isinstance(raw_builds, (str, bytes)) or not isinstance(raw_builds, list):
            raise ProjectContractError("build_ids must be a list")
        try:
            status = ProjectStatus(data.get("status"))
        except ValueError as exc:
            raise ProjectContractError("status is not a known project status") from exc
        return cls(
            project_id=data.get("project_id", ""),
            actor_id=data.get("actor_id", ""),
            tenant_id=data.get("tenant_id", ""),
            brief=ProjectBrief.from_dict(data.get("brief")),
            status=status,
            build_ids=tuple(raw_builds),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            schema_version=data.get("schema_version", ""),
        )


@dataclass(frozen=True)
class ProjectListQuery:
    actor_id: str
    tenant_id: str
    limit: int = 50
    cursor: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "actor_id", _id(self.actor_id, "actor_id"))
        object.__setattr__(self, "tenant_id", _id(self.tenant_id, "tenant_id"))
        if isinstance(self.limit, bool) or not isinstance(self.limit, int):
            raise ProjectContractError("limit must be an integer")
        if not 1 <= self.limit <= _MAX_PAGE:
            raise ProjectContractError("limit must be from 1 to 100")
        if self.cursor is not None:
            object.__setattr__(
                self,
                "cursor",
                _text(self.cursor, "cursor", max_length=512),
            )


@dataclass(frozen=True)
class ProjectList:
    items: tuple[Project, ...]
    next_cursor: str | None = None
    schema_version: str = PROJECTS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        if isinstance(self.items, (str, bytes)) or not isinstance(self.items, tuple):
            raise ProjectContractError("items must be a tuple of projects")
        if any(not isinstance(item, Project) for item in self.items):
            raise ProjectContractError("items must be a tuple of projects")
        if self.next_cursor is not None:
            object.__setattr__(
                self,
                "next_cursor",
                _text(self.next_cursor, "next_cursor", max_length=512),
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "items": [item.as_dict() for item in self.items],
            "next_cursor": self.next_cursor,
        }

    @classmethod
    def from_dict(cls, value: object) -> "ProjectList":
        data = _mapping(value, "project_list", {"schema_version", "items", "next_cursor"})
        raw_items = data.get("items")
        if not isinstance(raw_items, list):
            raise ProjectContractError("items must be a list")
        cursor = data.get("next_cursor")
        if cursor is not None and not isinstance(cursor, str):
            raise ProjectContractError("next_cursor must be text or null")
        return cls(
            items=tuple(Project.from_dict(item) for item in raw_items),
            next_cursor=cursor,
            schema_version=data.get("schema_version", ""),
        )


@dataclass(frozen=True)
class ProjectBuildLinkRequest:
    """POST /api/v1/projects/{project_id}/builds body.

    Idempotent for the same project and execution. Does not submit a build;
    submit stays on POST /api/v1/engine/executions.
    """

    actor_id: str
    tenant_id: str
    execution_id: str
    schema_version: str = PROJECTS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        object.__setattr__(self, "actor_id", _id(self.actor_id, "actor_id"))
        object.__setattr__(self, "tenant_id", _id(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "execution_id", _id(self.execution_id, "execution_id"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "actor_id": self.actor_id,
            "tenant_id": self.tenant_id,
            "execution_id": self.execution_id,
        }

    @classmethod
    def from_dict(cls, value: object) -> "ProjectBuildLinkRequest":
        data = _mapping(
            value,
            "project_build_link",
            {"schema_version", "actor_id", "tenant_id", "execution_id"},
        )
        return cls(
            actor_id=data.get("actor_id", ""),
            tenant_id=data.get("tenant_id", ""),
            execution_id=data.get("execution_id", ""),
            schema_version=data.get("schema_version", ""),
        )


@dataclass(frozen=True)
class ProjectBuildLink:
    project_id: str
    execution_id: str
    linked_at: str
    replayed: bool = False
    schema_version: str = PROJECTS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        object.__setattr__(self, "project_id", _id(self.project_id, "project_id"))
        object.__setattr__(self, "execution_id", _id(self.execution_id, "execution_id"))
        object.__setattr__(self, "linked_at", _timestamp(self.linked_at, "linked_at"))
        if not isinstance(self.replayed, bool):
            raise ProjectContractError("replayed must be a boolean")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "execution_id": self.execution_id,
            "linked_at": self.linked_at,
            "replayed": self.replayed,
        }

    @classmethod
    def from_dict(cls, value: object) -> "ProjectBuildLink":
        data = _mapping(
            value,
            "project_build_link_result",
            {"schema_version", "project_id", "execution_id", "linked_at", "replayed"},
        )
        replayed = data.get("replayed", False)
        if not isinstance(replayed, bool):
            raise ProjectContractError("replayed must be a boolean")
        return cls(
            project_id=data.get("project_id", ""),
            execution_id=data.get("execution_id", ""),
            linked_at=data.get("linked_at", ""),
            replayed=replayed,
            schema_version=data.get("schema_version", ""),
        )


def link_build(project: Project, execution_id: str, *, linked_at: str) -> tuple[Project, ProjectBuildLink]:
    """Return the project with ``execution_id`` appended, or a replay if present."""

    execution = _id(execution_id, "execution_id")
    if execution in project.build_ids:
        return project, ProjectBuildLink(
            project_id=project.project_id,
            execution_id=execution,
            linked_at=linked_at,
            replayed=True,
        )
    updated = Project(
        project_id=project.project_id,
        actor_id=project.actor_id,
        tenant_id=project.tenant_id,
        brief=project.brief,
        status=ProjectStatus.ACTIVE if project.status is ProjectStatus.DRAFT else project.status,
        build_ids=project.build_ids + (execution,),
        created_at=project.created_at,
        updated_at=linked_at,
    )
    return updated, ProjectBuildLink(
        project_id=project.project_id,
        execution_id=execution,
        linked_at=linked_at,
        replayed=False,
    )


__all__ = [
    "PROJECTS_SCHEMA_ID",
    "PROJECTS_SCHEMA_VERSION",
    "PROJECT_ERROR_BUILD_CONFLICT",
    "PROJECT_ERROR_INVALID",
    "PROJECT_ERROR_NOT_FOUND",
    "PROJECT_HTTP_STATUS",
    "PROJECT_ROUTES",
    "Project",
    "ProjectBrief",
    "ProjectBuildLink",
    "ProjectBuildLinkRequest",
    "ProjectContractError",
    "ProjectCreateRequest",
    "ProjectList",
    "ProjectListQuery",
    "ProjectStatus",
    "brief_digest",
    "link_build",
    "project_error_envelope",
]
