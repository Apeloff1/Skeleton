"""Projects resource contract, schema skeleton.projects.v1 version 1.1.0.

This module describes the Projects HTTP implementation on PR #4097
(``is/app-foundation-persistence`` @ 7065e555), which Internal Systems is
moving from ``/api/app/projects`` onto ``/api/v1/projects`` inside
``create_app`` and behind ``install_gate``.

The checked router returns ``ProjectOut`` and ``BuildOut``. Version 1.1.0
keeps those fields and applies the mount ruling on top:

- ``brief`` is a plain string or the structured object
- ``POST /builds`` starts a server-side build and returns a Build that
  carries ``execution_id``; sending ``execution_id`` links that execution
  and does not start another job
- errors use the Skeleton envelope with ``PROJECT.*`` codes
- ``actor_id`` and ``tenant_id`` come from the bearer session, never from
  the body; the stored owner is the session user (``owner_id``)
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

PROJECTS_SCHEMA_VERSION = "1.1.0"
PROJECTS_SCHEMA_ID = "skeleton.projects.v1"

# Commit re-checked before this version was written. The prefix there is still
# /api/app/projects; PROJECT_ROUTES is the /api/v1/projects mount target.
PROJECTS_IMPLEMENTATION = {
    "pull_request": 4097,
    "branch": "is/app-foundation-persistence",
    "commit": "7065e555f9fff380a85ae479a79d3c34966ca097",
    "module": "skeleton/app_services/projects_api.py",
    "observed_prefix": "/api/app/projects",
}

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
PROJECT_ERROR_BUILD_NOT_FOUND = "PROJECT.BUILD_NOT_FOUND"
PROJECT_ERROR_CONFLICT = "PROJECT.CONFLICT"
PROJECT_ERROR_BUILD_CONFLICT = "PROJECT.BUILD_CONFLICT"

PROJECT_HTTP_STATUS = {
    PROJECT_ERROR_INVALID: 422,
    PROJECT_ERROR_UNAUTHENTICATED: 401,
    PROJECT_ERROR_NOT_FOUND: 404,
    PROJECT_ERROR_BUILD_NOT_FOUND: 404,
    PROJECT_ERROR_CONFLICT: 409,
    PROJECT_ERROR_BUILD_CONFLICT: 409,
}

BUILD_STATUSES = (
    "pending",
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
)

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_BRIEF = 20_000
_MAX_NAME = 200
_MAX_DERIVED_NAME = 80
_MAX_TITLE = 200
_MAX_SUMMARY = 8_000
_MAX_GENRE = 80
_MAX_CONSTRAINTS = 32
_MAX_TARGET = 64
_MAX_IDEMPOTENCY_KEY = 128
_MAX_ERROR = 4_000
_MAX_BUILD_LIST = 50
_MAX_JSON_DEPTH = 8
_DEFAULT_NAME = "Untitled project"
_REQUEST_FIELDS = {
    "project_create": {"brief", "name", "settings"},
    "build_create": {"target", "options", "idempotency_key", "execution_id"},
}


class ProjectContractError(ValueError):
    """A projects document violates schema skeleton.projects.v1."""


class BuildStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BuildRequestMode(str, Enum):
    """``execution_id`` links an existing execution. Otherwise the server starts one."""

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
    safe = context or {}
    if not isinstance(safe, Mapping):
        raise ProjectContractError("error context must be an object")
    return {
        "error": {
            "type": "ProjectContractError",
            "code": code,
            "message": message,
            "context": dict(safe),
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


def _raw_text(value: object, field: str, *, max_length: int, allow_empty: bool = False) -> str:
    """Length check without strip. Matches the checked pydantic string fields."""

    if not isinstance(value, str):
        raise ProjectContractError(f"{field} must be text")
    if not value and not allow_empty:
        raise ProjectContractError(f"{field} must be non-empty")
    if len(value) > max_length:
        raise ProjectContractError(f"{field} exceeds maximum length")
    return value


def _epoch(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProjectContractError(f"{field} must be epoch seconds")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ProjectContractError(f"{field} must be a finite epoch timestamp")
    return number


def _object(value: object, field: str, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProjectContractError(f"{field} must be an object")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ProjectContractError(f"{field} has unknown fields: {unknown}")
    return value


def _json_value(value: object, field: str, *, depth: int = 0) -> Any:
    if depth > _MAX_JSON_DEPTH:
        raise ProjectContractError(f"{field} is nested too deeply")
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProjectContractError(f"{field} must be finite")
        return value
    if isinstance(value, list):
        return [_json_value(item, field, depth=depth + 1) for item in value]
    if isinstance(value, Mapping):
        value = dict(value)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProjectContractError(f"{field} keys must be strings")
            out[key] = _json_value(item, field, depth=depth + 1)
        return out
    raise ProjectContractError(f"{field} must be JSON data")


def _json_object(value: object, field: str) -> dict[str, Any]:
    parsed = _json_value(value, field)
    if not isinstance(parsed, dict):
        raise ProjectContractError(f"{field} must be an object")
    return parsed


def _proxy(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class ProjectCaller:
    """Bearer-session identity. Handlers derive this; requests must not send it.

    ``owner_id`` is ``actor_id``, the session user id from #4097
    ``SessionPrincipal.user_id``. ``tenant_id`` is session scope when the
    session has one. The project row does not store a tenant column.
    """

    actor_id: str
    tenant_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "actor_id", _id(self.actor_id, "actor_id"))
        if self.tenant_id:
            object.__setattr__(self, "tenant_id", _id(self.tenant_id, "tenant_id"))

    @property
    def owner_id(self) -> str:
        return self.actor_id


@dataclass(frozen=True)
class ProjectBrief:
    title: str
    summary: str = ""
    genre: str = ""
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _text(self.title, "title", max_length=_MAX_TITLE))
        object.__setattr__(
            self,
            "summary",
            _text(self.summary, "summary", max_length=_MAX_SUMMARY, allow_empty=True),
        )
        object.__setattr__(
            self,
            "genre",
            _text(self.genre, "genre", max_length=_MAX_GENRE, allow_empty=True),
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
        data = _object(value, "brief", {"title", "summary", "genre", "constraints"})
        raw_constraints = data.get("constraints", [])
        if isinstance(raw_constraints, (str, bytes)) or not isinstance(raw_constraints, list):
            raise ProjectContractError("constraints must be a list")
        return cls(
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            genre=data.get("genre", ""),
            constraints=tuple(raw_constraints),
        )


def parse_brief(value: object) -> str | ProjectBrief:
    """Accept the string brief #4097 stores, or the structured object."""

    if isinstance(value, ProjectBrief):
        return value
    if isinstance(value, str):
        return _raw_text(value, "brief", max_length=_MAX_BRIEF)
    if isinstance(value, dict):
        return ProjectBrief.from_dict(value)
    raise ProjectContractError("brief must be a string or an object")


def brief_as_json(brief: str | ProjectBrief) -> str | dict[str, Any]:
    if isinstance(brief, str):
        return brief
    if isinstance(brief, ProjectBrief):
        return brief.as_dict()
    raise ProjectContractError("brief must be a string or a ProjectBrief")


def brief_digest(brief: str | ProjectBrief) -> str:
    """Stable digest of a brief. Not an HTTP field."""

    raw = json.dumps(brief_as_json(brief), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def project_name(brief: str | ProjectBrief, name: str | None = None) -> str:
    """Default name used by the checked ``_name_from_brief`` path.

    An explicit name is stripped and kept up to 200 characters. A string
    brief contributes its first line, cut at 80 characters. A structured
    brief contributes its title.
    """

    if name is not None:
        if not isinstance(name, str):
            raise ProjectContractError("name must be text")
        if len(name) > _MAX_NAME:
            raise ProjectContractError("name exceeds maximum length")
        stripped = name.strip()
        if stripped:
            return stripped
    if isinstance(brief, str):
        first = brief.strip().splitlines()[0].strip() if brief.strip() else ""
        return (first[:_MAX_DERIVED_NAME] or _DEFAULT_NAME)
    if isinstance(brief, ProjectBrief):
        return brief.title or _DEFAULT_NAME
    raise ProjectContractError("brief must be a string or a ProjectBrief")


@dataclass(frozen=True)
class ProjectCreateRequest:
    """POST /api/v1/projects body. Identity is not a field of this body."""

    brief: str | ProjectBrief
    name: str | None = None
    settings: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        brief = parse_brief(self.brief)
        object.__setattr__(self, "brief", brief)
        if self.name is not None:
            object.__setattr__(self, "name", _raw_text(self.name, "name", max_length=_MAX_NAME, allow_empty=True))
        object.__setattr__(self, "settings", _proxy(_json_object(self.settings, "settings")))

    def as_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"brief": brief_as_json(self.brief), "settings": dict(self.settings)}
        if self.name is not None:
            body["name"] = self.name
        return body

    @classmethod
    def from_dict(cls, value: object) -> ProjectCreateRequest:
        data = _object(value, "project_create", _REQUEST_FIELDS["project_create"])
        if "brief" not in data:
            raise ProjectContractError("brief must be non-empty")
        name = data.get("name")
        return cls(
            brief=data["brief"],
            name=name if name is not None else None,
            settings=data.get("settings", {}),
        )


@dataclass(frozen=True)
class Project:
    """ProjectOut from the checked router, with brief as a string or object."""

    project_id: str
    owner_id: str
    name: str
    brief: str | ProjectBrief
    settings: Mapping[str, Any]
    created_at: float
    updated_at: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", _id(self.project_id, "project_id"))
        object.__setattr__(self, "owner_id", _id(self.owner_id, "owner_id"))
        object.__setattr__(self, "name", _text(self.name, "name", max_length=_MAX_NAME))
        object.__setattr__(self, "brief", parse_brief(self.brief))
        object.__setattr__(self, "settings", _proxy(_json_object(self.settings, "settings")))
        object.__setattr__(self, "created_at", _epoch(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _epoch(self.updated_at, "updated_at"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "owner_id": self.owner_id,
            "name": self.name,
            "brief": brief_as_json(self.brief),
            "settings": dict(self.settings),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: object) -> Project:
        data = _object(
            value,
            "project",
            {"project_id", "owner_id", "name", "brief", "settings", "created_at", "updated_at"},
        )
        return cls(
            project_id=data.get("project_id", ""),
            owner_id=data.get("owner_id", ""),
            name=data.get("name", ""),
            brief=data.get("brief", ""),
            settings=data.get("settings", {}),
            created_at=data.get("created_at", -1),
            updated_at=data.get("updated_at", -1),
        )


@dataclass(frozen=True)
class ProjectList:
    projects: tuple[Project, ...]

    def __post_init__(self) -> None:
        if isinstance(self.projects, (str, bytes)) or not isinstance(self.projects, tuple):
            raise ProjectContractError("projects must be a tuple of projects")
        if any(not isinstance(item, Project) for item in self.projects):
            raise ProjectContractError("projects must be a tuple of projects")

    def as_dict(self) -> dict[str, Any]:
        return {"projects": [item.as_dict() for item in self.projects]}

    @classmethod
    def from_dict(cls, value: object) -> ProjectList:
        data = _object(value, "project_list", {"projects"})
        raw = data.get("projects")
        if not isinstance(raw, list):
            raise ProjectContractError("projects must be a list")
        return cls(projects=tuple(Project.from_dict(item) for item in raw))


@dataclass(frozen=True)
class BuildCreateRequest:
    """POST /api/v1/projects/{project_id}/builds body.

    Omit ``execution_id`` to start a build (``BuildService.submit``: create
    the build row, enqueue ``game.build``, return status ``queued``).
    Send ``execution_id`` to link that execution and skip the enqueue.
    """

    target: str = ""
    options: Mapping[str, Any] = MappingProxyType({})
    idempotency_key: str | None = None
    execution_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target",
            _raw_text(self.target, "target", max_length=_MAX_TARGET, allow_empty=True),
        )
        object.__setattr__(self, "options", _proxy(_json_object(self.options, "options")))
        if self.idempotency_key is not None:
            object.__setattr__(
                self,
                "idempotency_key",
                _raw_text(
                    self.idempotency_key,
                    "idempotency_key",
                    max_length=_MAX_IDEMPOTENCY_KEY,
                ),
            )
        if self.execution_id is not None:
            object.__setattr__(self, "execution_id", _id(self.execution_id, "execution_id"))

    @property
    def mode(self) -> BuildRequestMode:
        if self.execution_id:
            return BuildRequestMode.LINK
        return BuildRequestMode.START

    def as_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"target": self.target, "options": dict(self.options)}
        if self.idempotency_key is not None:
            body["idempotency_key"] = self.idempotency_key
        if self.execution_id is not None:
            body["execution_id"] = self.execution_id
        return body

    @classmethod
    def from_dict(cls, value: object) -> BuildCreateRequest:
        data = _object(value, "build_create", _REQUEST_FIELDS["build_create"])
        return cls(
            target=data.get("target", ""),
            options=data.get("options", {}),
            idempotency_key=data.get("idempotency_key"),
            execution_id=data.get("execution_id"),
        )


@dataclass(frozen=True)
class Build:
    """BuildOut from the checked router, plus the execution this build runs or links."""

    build_id: str
    project_id: str
    status: BuildStatus
    target: str
    job_id: str | None
    result: Mapping[str, Any]
    error: str
    created_at: float
    updated_at: float
    execution_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "build_id", _id(self.build_id, "build_id"))
        object.__setattr__(self, "project_id", _id(self.project_id, "project_id"))
        if not isinstance(self.status, BuildStatus):
            raise ProjectContractError("status must be a BuildStatus")
        object.__setattr__(
            self,
            "target",
            _raw_text(self.target, "target", max_length=_MAX_TARGET, allow_empty=True),
        )
        if self.job_id is not None:
            object.__setattr__(self, "job_id", _id(self.job_id, "job_id"))
        object.__setattr__(self, "result", _proxy(_json_object(self.result, "result")))
        object.__setattr__(
            self,
            "error",
            _raw_text(self.error, "error", max_length=_MAX_ERROR, allow_empty=True),
        )
        object.__setattr__(self, "created_at", _epoch(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _epoch(self.updated_at, "updated_at"))
        object.__setattr__(self, "execution_id", _id(self.execution_id, "execution_id"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "build_id": self.build_id,
            "project_id": self.project_id,
            "status": self.status.value,
            "target": self.target,
            "job_id": self.job_id,
            "result": dict(self.result),
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "execution_id": self.execution_id,
        }

    @classmethod
    def from_dict(cls, value: object) -> Build:
        data = _object(
            value,
            "build",
            {
                "build_id",
                "project_id",
                "status",
                "target",
                "job_id",
                "result",
                "error",
                "created_at",
                "updated_at",
                "execution_id",
            },
        )
        raw_status = data.get("status")
        try:
            status = BuildStatus(raw_status)
        except ValueError as exc:
            raise ProjectContractError("status is not a known build status") from exc
        job_id = data.get("job_id")
        if job_id is not None and not isinstance(job_id, str):
            raise ProjectContractError("job_id must be text or null")
        return cls(
            build_id=data.get("build_id", ""),
            project_id=data.get("project_id", ""),
            status=status,
            target=data.get("target", ""),
            job_id=job_id,
            result=data.get("result", {}),
            error=data.get("error", ""),
            created_at=data.get("created_at", -1),
            updated_at=data.get("updated_at", -1),
            execution_id=data.get("execution_id", ""),
        )


@dataclass(frozen=True)
class BuildList:
    builds: tuple[Build, ...]

    def __post_init__(self) -> None:
        if isinstance(self.builds, (str, bytes)) or not isinstance(self.builds, tuple):
            raise ProjectContractError("builds must be a tuple of builds")
        if len(self.builds) > _MAX_BUILD_LIST:
            raise ProjectContractError("builds exceed the maximum count")
        if any(not isinstance(item, Build) for item in self.builds):
            raise ProjectContractError("builds must be a tuple of builds")

    def as_dict(self) -> dict[str, Any]:
        return {"builds": [item.as_dict() for item in self.builds]}

    @classmethod
    def from_dict(cls, value: object) -> BuildList:
        data = _object(value, "build_list", {"builds"})
        raw = data.get("builds")
        if not isinstance(raw, list):
            raise ProjectContractError("builds must be a list")
        return cls(builds=tuple(Build.from_dict(item) for item in raw))


def visible_to(project: Project, caller: ProjectCaller) -> bool:
    """Ownership check used by the checked router: same session user, or 404."""

    if not isinstance(project, Project) or not isinstance(caller, ProjectCaller):
        raise ProjectContractError("visibility requires a project and a session caller")
    return project.owner_id == caller.owner_id


__all__ = [
    "BUILD_STATUSES",
    "PROJECTS_IMPLEMENTATION",
    "PROJECTS_SCHEMA_ID",
    "PROJECTS_SCHEMA_VERSION",
    "PROJECT_ERROR_BUILD_CONFLICT",
    "PROJECT_ERROR_BUILD_NOT_FOUND",
    "PROJECT_ERROR_CONFLICT",
    "PROJECT_ERROR_INVALID",
    "PROJECT_ERROR_NOT_FOUND",
    "PROJECT_ERROR_UNAUTHENTICATED",
    "PROJECT_HTTP_STATUS",
    "PROJECT_ROUTES",
    "Build",
    "BuildCreateRequest",
    "BuildList",
    "BuildRequestMode",
    "BuildStatus",
    "Project",
    "ProjectBrief",
    "ProjectCaller",
    "ProjectContractError",
    "ProjectCreateRequest",
    "ProjectList",
    "brief_as_json",
    "brief_digest",
    "parse_brief",
    "project_error_envelope",
    "project_name",
    "visible_to",
]
