"""Projects resource contract, schema skeleton.projects.v1 version 1.0.0.

This describes the router built on PR #4097 at commit 959eec134
(``skeleton/api/projects_routes.py``), mounted by ``create_app`` at
``/api/v1/projects`` behind ``install_gate``.

Every call needs ``x-gf-seal`` and ``Authorization: Bearer <session>``.
``actor_id`` is the session user. ``tenant_id`` is ``APP_TENANT_ID``
(default ``default``). A body value for either must equal that session
value. The job queue those builds enqueue is ``docs/contracts/job_queue.md``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from skeleton.compat.datetime_utc import UTC
from datetime import datetime
from enum import Enum
from typing import Any

PROJECTS_SCHEMA_VERSION = "1.0.0"
PROJECTS_SCHEMA_ID = "skeleton.projects.v1"
DEFAULT_TENANT_ID = "default"
GAME_BUILD_KIND = "game.build"

# Checked implementation. The contract version string is the one that router emits.
PROJECTS_IMPLEMENTATION = {
    "pull_request": 4097,
    "branch": "is/app-foundation-persistence",
    "commit": "959eec1345f767208fb4c5dda6e7bd25b07058c3",
    "module": "skeleton/api/projects_routes.py",
    "store": "skeleton/persistence/app_foundation/projects_v1.py",
    "job_api": "docs/contracts/job_queue.md",
}

# method, path, status when the call is not an idempotent replay.
# Create and link replays return 200. Build start stays 202 when replayed.
PROJECT_ROUTES: tuple[tuple[str, str, int], ...] = (
    ("POST", "/api/v1/projects", 201),
    ("GET", "/api/v1/projects", 200),
    ("GET", "/api/v1/projects/{project_id}", 200),
    ("POST", "/api/v1/projects/{project_id}/builds", 202),
    ("GET", "/api/v1/projects/{project_id}/builds", 200),
    ("GET", "/api/v1/projects/{project_id}/builds/{build_id}", 200),
)

PROJECT_ERROR_INVALID = "PROJECT.INVALID"
PROJECT_ERROR_UNAUTHENTICATED = "PROJECT.UNAUTHENTICATED"
PROJECT_ERROR_NOT_FOUND = "PROJECT.NOT_FOUND"
PROJECT_ERROR_BUILD_CONFLICT = "PROJECT.BUILD_CONFLICT"
PROJECT_ERROR_NAME_CONFLICT = "PROJECT.NAME_CONFLICT"
PROJECT_ERROR_IDEMPOTENCY_MISMATCH = "PROJECT.IDEMPOTENCY_MISMATCH"
PROJECT_ERROR_UNAVAILABLE = "PROJECT.UNAVAILABLE"

PROJECT_HTTP_STATUS = {
    PROJECT_ERROR_INVALID: 400,
    PROJECT_ERROR_UNAUTHENTICATED: 401,
    PROJECT_ERROR_NOT_FOUND: 404,
    PROJECT_ERROR_BUILD_CONFLICT: 409,
    PROJECT_ERROR_NAME_CONFLICT: 409,
    PROJECT_ERROR_IDEMPOTENCY_MISMATCH: 409,
    PROJECT_ERROR_UNAVAILABLE: 503,
}

BUILD_STATUSES = (
    "pending",
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
)
_PAGE_CURSOR = re.compile(r"^r:[0-9]+$")

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


class BuildStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BuildRequestMode(str, Enum):
    START = "start"
    LINK = "link"


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


def assert_session_scope(body: Mapping[str, Any], *, actor_id: str, tenant_id: str) -> None:
    """Body identity is optional. A value that disagrees with the session is invalid."""

    if "actor_id" in body and body["actor_id"] != actor_id:
        raise ProjectContractError("actor_id is derived from the session")
    if "tenant_id" in body and body["tenant_id"] != tenant_id:
        raise ProjectContractError("tenant_id is derived from the session")


def page_limit(raw: object) -> int:
    """Query ``limit``. The handler reads it as text: digits only, 1..100, default 50."""

    if isinstance(raw, str):
        if not raw.isdigit():
            raise ProjectContractError("limit must be from 1 to 100")
        raw = int(raw)
    if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= _MAX_PAGE:
        raise ProjectContractError("limit must be from 1 to 100")
    return raw


def page_cursor(value: object) -> str | None:
    """Store cursor ``r:<rowid>``. ``zzz`` and other spellings are PROJECT.INVALID."""

    if value is None:
        return None
    if not isinstance(value, str) or _PAGE_CURSOR.fullmatch(value) is None:
        raise ProjectContractError("cursor is invalid")
    return value


def create_idempotency_scope(tenant_id: str, actor_id: str, header_key: str) -> str:
    """``Idempotency-Key`` stored as ``{tenant}:{actor}:{key}``."""

    return f"{tenant_id}:{actor_id}:{header_key}"


def build_idempotency_scope(tenant_id: str, actor_id: str, project_id: str, body_key: str) -> str:
    """Start-build key after ``job_api`` scopes ``{tenant}:{actor}:game.build:{project_id}:{key}``."""

    return f"{tenant_id}:{actor_id}:{GAME_BUILD_KIND}:{project_id}:{body_key}"


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
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ProjectContractError(f"{field} is invalid RFC3339 UTC") from exc
    if parsed.tzinfo is None:
        raise ProjectContractError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


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
    def from_dict(cls, value: object) -> ProjectBrief:
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


def parse_brief(value: object) -> ProjectBrief:
    """Accept a string or a brief object. The stored brief is always the object.

    A string uses the first line as ``title`` (cut at 200) and the remaining
    lines as ``summary`` (cut at 8000). That is the handler's ``_brief_from``.
    """

    if isinstance(value, ProjectBrief):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ProjectContractError("brief must be non-empty")
        lines = text.splitlines()
        title = lines[0].strip()[:_MAX_TITLE].strip()
        summary = "\n".join(lines[1:]).strip()[:_MAX_SUMMARY].strip()
        return ProjectBrief(title=title, summary=summary)
    if isinstance(value, dict):
        return ProjectBrief.from_dict(value)
    raise ProjectContractError("brief must be a string or a brief object")


def brief_digest(brief: ProjectBrief) -> str:
    """Stable digest of a brief for internal handoff. Not an HTTP field."""

    if not isinstance(brief, ProjectBrief):
        raise ProjectContractError("brief must be a ProjectBrief")
    raw = json.dumps(brief.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _optional_version(value: object) -> str | None:
    if value is None:
        return None
    return _version(value)


def _optional_id(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _id(value, field)


@dataclass(frozen=True)
class ProjectCreateRequest:
    """POST /api/v1/projects body. Identity is not required and is not trusted."""

    brief: ProjectBrief
    schema_version: str | None = None
    actor_id: str | None = None
    tenant_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _optional_version(self.schema_version))
        object.__setattr__(self, "actor_id", _optional_id(self.actor_id, "actor_id"))
        object.__setattr__(self, "tenant_id", _optional_id(self.tenant_id, "tenant_id"))
        if not isinstance(self.brief, ProjectBrief):
            raise ProjectContractError("brief must be a ProjectBrief")

    def as_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"brief": self.brief.as_dict()}
        if self.schema_version is not None:
            body["schema_version"] = self.schema_version
        if self.actor_id is not None:
            body["actor_id"] = self.actor_id
        if self.tenant_id is not None:
            body["tenant_id"] = self.tenant_id
        return body

    @classmethod
    def from_dict(cls, value: object) -> ProjectCreateRequest:
        data = _mapping(
            value,
            "project_create",
            {"schema_version", "actor_id", "tenant_id", "brief"},
        )
        if "brief" not in data:
            raise ProjectContractError("missing fields: ['brief']")
        return cls(
            brief=parse_brief(data["brief"]),
            schema_version=data.get("schema_version"),
            actor_id=data.get("actor_id"),
            tenant_id=data.get("tenant_id"),
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
    def from_dict(cls, value: object) -> Project:
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
    def from_dict(cls, value: object) -> ProjectList:
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
    """POST /builds body that links ``execution_id``. Not combinable with start fields."""

    execution_id: str
    schema_version: str | None = None
    actor_id: str | None = None
    tenant_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _optional_version(self.schema_version))
        object.__setattr__(self, "actor_id", _optional_id(self.actor_id, "actor_id"))
        object.__setattr__(self, "tenant_id", _optional_id(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "execution_id", _id(self.execution_id, "execution_id"))

    def as_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"execution_id": self.execution_id}
        if self.schema_version is not None:
            body["schema_version"] = self.schema_version
        if self.actor_id is not None:
            body["actor_id"] = self.actor_id
        if self.tenant_id is not None:
            body["tenant_id"] = self.tenant_id
        return body

    @classmethod
    def from_dict(cls, value: object) -> ProjectBuildLinkRequest:
        data = _mapping(
            value,
            "project_build_link",
            {"schema_version", "actor_id", "tenant_id", "execution_id"},
        )
        if "execution_id" not in data:
            raise ProjectContractError("missing fields: ['execution_id']")
        return cls(
            execution_id=data.get("execution_id", ""),
            schema_version=data.get("schema_version"),
            actor_id=data.get("actor_id"),
            tenant_id=data.get("tenant_id"),
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
    def from_dict(cls, value: object) -> ProjectBuildLink:
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


_BUILD_BODY_FIELDS = {
    "schema_version",
    "target",
    "options",
    "idempotency_key",
    "execution_id",
    "actor_id",
    "tenant_id",
}
_START_FIELDS = {"target", "options", "idempotency_key"}


def _target(value: object) -> str:
    if not isinstance(value, str) or len(value) > 64:
        raise ProjectContractError("target must be text up to 64 chars")
    return value


def _options(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProjectContractError("options must be an object")
    return dict(value)


def _idempotency_key(value: object, *, header: bool = False) -> str | None:
    label = "Idempotency-Key" if header else "idempotency_key"
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ProjectContractError(f"{label} must be 1..128 chars")
    return value


@dataclass(frozen=True)
class BuildStartRequest:
    """POST /builds body that enqueues ``game.build``. Replay stays HTTP 202."""

    target: str = ""
    options: Mapping[str, Any] | None = None
    idempotency_key: str | None = None
    schema_version: str | None = None
    actor_id: str | None = None
    tenant_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", _target(self.target))
        object.__setattr__(self, "options", _options({} if self.options is None else self.options))
        object.__setattr__(self, "idempotency_key", _idempotency_key(self.idempotency_key))
        object.__setattr__(self, "schema_version", _optional_version(self.schema_version))
        object.__setattr__(self, "actor_id", _optional_id(self.actor_id, "actor_id"))
        object.__setattr__(self, "tenant_id", _optional_id(self.tenant_id, "tenant_id"))

    @property
    def mode(self) -> BuildRequestMode:
        return BuildRequestMode.START

    def as_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"target": self.target, "options": dict(self.options or {})}
        if self.idempotency_key is not None:
            body["idempotency_key"] = self.idempotency_key
        if self.schema_version is not None:
            body["schema_version"] = self.schema_version
        if self.actor_id is not None:
            body["actor_id"] = self.actor_id
        if self.tenant_id is not None:
            body["tenant_id"] = self.tenant_id
        return body

    @classmethod
    def from_dict(cls, value: object) -> BuildStartRequest:
        data = _mapping(value, "build_start", _BUILD_BODY_FIELDS - {"execution_id"})
        if "execution_id" in data:
            raise ProjectContractError("execution_id links; it cannot be combined with start fields")
        return cls(
            target=data.get("target", ""),
            options=data.get("options", {}),
            idempotency_key=data.get("idempotency_key"),
            schema_version=data.get("schema_version"),
            actor_id=data.get("actor_id"),
            tenant_id=data.get("tenant_id"),
        )


def parse_build_request(value: object) -> BuildStartRequest | ProjectBuildLinkRequest:
    """Start when ``execution_id`` is absent. Link when it is the only action field."""

    data = _mapping(value, "build_request", _BUILD_BODY_FIELDS)
    if "execution_id" in data:
        if set(data) & _START_FIELDS:
            raise ProjectContractError("execution_id links; it cannot be combined with start fields")
        return ProjectBuildLinkRequest.from_dict(data)
    return BuildStartRequest.from_dict(data)


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


@dataclass(frozen=True)
class Build:
    """Build JSON from ``build_out``. ``execution_id`` is ``build_id``."""

    build_id: str
    project_id: str
    status: BuildStatus
    target: str
    job_id: str | None
    result: Mapping[str, Any]
    error: str
    created_at: str
    updated_at: str
    execution_id: str
    replayed: bool = False
    schema_version: str = PROJECTS_SCHEMA_VERSION
    schema_id: str = PROJECTS_SCHEMA_ID

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        if self.schema_id != PROJECTS_SCHEMA_ID:
            raise ProjectContractError(f"schema_id must be {PROJECTS_SCHEMA_ID}")
        object.__setattr__(self, "build_id", _id(self.build_id, "build_id"))
        object.__setattr__(self, "execution_id", _id(self.execution_id, "execution_id"))
        if self.execution_id != self.build_id:
            raise ProjectContractError("execution_id must equal build_id")
        object.__setattr__(self, "project_id", _id(self.project_id, "project_id"))
        if not isinstance(self.status, BuildStatus):
            raise ProjectContractError("status must be a BuildStatus")
        object.__setattr__(self, "target", _target(self.target))
        if self.job_id is not None:
            object.__setattr__(self, "job_id", _id(self.job_id, "job_id"))
        if not isinstance(self.result, Mapping) or isinstance(self.result, (str, bytes)):
            raise ProjectContractError("result must be an object")
        object.__setattr__(self, "result", dict(self.result))
        if not isinstance(self.error, str):
            raise ProjectContractError("error must be text")
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _timestamp(self.updated_at, "updated_at"))
        if not isinstance(self.replayed, bool):
            raise ProjectContractError("replayed must be a boolean")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "schema_id": self.schema_id,
            "build_id": self.build_id,
            "execution_id": self.execution_id,
            "project_id": self.project_id,
            "status": self.status.value,
            "target": self.target,
            "job_id": self.job_id,
            "result": dict(self.result),
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "replayed": self.replayed,
        }

    @classmethod
    def from_dict(cls, value: object) -> Build:
        data = _mapping(
            value,
            "build",
            {
                "schema_version",
                "schema_id",
                "build_id",
                "execution_id",
                "project_id",
                "status",
                "target",
                "job_id",
                "result",
                "error",
                "created_at",
                "updated_at",
                "replayed",
            },
        )
        try:
            status = BuildStatus(data.get("status"))
        except ValueError as exc:
            raise ProjectContractError("status is not a known build status") from exc
        job_id = data.get("job_id")
        if job_id is not None and not isinstance(job_id, str):
            raise ProjectContractError("job_id must be text or null")
        replayed = data.get("replayed", False)
        if not isinstance(replayed, bool):
            raise ProjectContractError("replayed must be a boolean")
        return cls(
            build_id=data.get("build_id", ""),
            project_id=data.get("project_id", ""),
            status=status,
            target=data.get("target", ""),
            job_id=job_id,
            result=data.get("result", {}),
            error=data.get("error", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            execution_id=data.get("execution_id", ""),
            replayed=replayed,
            schema_version=data.get("schema_version", ""),
            schema_id=data.get("schema_id", ""),
        )


@dataclass(frozen=True)
class BuildList:
    """GET /builds. Newest build row first. Linked executions without a row are omitted."""

    items: tuple[Build, ...]
    next_cursor: str | None = None
    schema_version: str = PROJECTS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", _version(self.schema_version))
        if isinstance(self.items, (str, bytes)) or not isinstance(self.items, tuple):
            raise ProjectContractError("items must be a tuple of builds")
        if any(not isinstance(item, Build) for item in self.items):
            raise ProjectContractError("items must be a tuple of builds")
        object.__setattr__(self, "next_cursor", page_cursor(self.next_cursor))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "items": [item.as_dict() for item in self.items],
            "next_cursor": self.next_cursor,
        }

    @classmethod
    def from_dict(cls, value: object) -> BuildList:
        data = _mapping(value, "build_list", {"schema_version", "items", "next_cursor"})
        raw = data.get("items")
        if not isinstance(raw, list):
            raise ProjectContractError("items must be a list")
        cursor = data.get("next_cursor")
        if cursor is not None and not isinstance(cursor, str):
            raise ProjectContractError("next_cursor must be text or null")
        return cls(
            items=tuple(Build.from_dict(item) for item in raw),
            next_cursor=cursor,
            schema_version=data.get("schema_version", ""),
        )


__all__ = [
    "BUILD_STATUSES",
    "DEFAULT_TENANT_ID",
    "GAME_BUILD_KIND",
    "PROJECTS_IMPLEMENTATION",
    "PROJECTS_SCHEMA_ID",
    "PROJECTS_SCHEMA_VERSION",
    "PROJECT_ERROR_BUILD_CONFLICT",
    "PROJECT_ERROR_IDEMPOTENCY_MISMATCH",
    "PROJECT_ERROR_INVALID",
    "PROJECT_ERROR_NAME_CONFLICT",
    "PROJECT_ERROR_NOT_FOUND",
    "PROJECT_ERROR_UNAUTHENTICATED",
    "PROJECT_ERROR_UNAVAILABLE",
    "PROJECT_HTTP_STATUS",
    "PROJECT_ROUTES",
    "Build",
    "BuildList",
    "BuildRequestMode",
    "BuildStartRequest",
    "BuildStatus",
    "Project",
    "ProjectBrief",
    "ProjectBuildLink",
    "ProjectBuildLinkRequest",
    "ProjectContractError",
    "ProjectCreateRequest",
    "ProjectList",
    "ProjectListQuery",
    "ProjectStatus",
    "assert_session_scope",
    "brief_digest",
    "build_idempotency_scope",
    "create_idempotency_scope",
    "link_build",
    "page_cursor",
    "page_limit",
    "parse_brief",
    "parse_build_request",
    "project_error_envelope",
]
