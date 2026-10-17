"""Projects client for the single contract ``skeleton.projects.v1``.

This follows the TD ruling: there is one contract, ``skeleton.projects.v1``
(PR #4112, being amended), served by Internal Systems' #4097 code under
``/api/v1/projects``. Until IS moves the routes, #4097 serves them at
``/api/app/projects``; pass ``base_path=`` to target that.

- Auth: ``Authorization: Bearer <session token>`` plus ``x-gf-seal`` when the
  gateway has a seal configured. ``actor_id`` and ``tenant_id`` are never sent;
  the server derives them from the session.
- Requests carry ``schema_version`` "1.0.0".
- Responses are parsed loosely so both the current #4097 shapes (``ProjectOut``,
  ``{"projects": [...]}``, ``BuildOut``) and the v1 shapes (``Project`` with
  status and build_ids, ``{"items": [...], "next_cursor": ...}``, Build plus
  ``execution_id``) are accepted.
- Errors: the v1 envelope ``{"error": {"type", "code": "PROJECT.*",
  "message"}}`` and the legacy ``{"detail": "<code>"}`` both surface as
  :class:`SkeletonHTTPError` with ``.code`` (and ``.message``) set.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence, Union
from urllib.parse import quote

import httpx

from skeleton.client.cancel import CancelToken
from skeleton.client.errors import (
    SkeletonHTTPError,
    SkeletonSessionConfigError,
    SkeletonTimeoutError,
)
from skeleton.client.gateway import GatewayClient, _safe_body

PROJECTS_BASE_PATH = "/api/v1/projects"
PROJECTS_SCHEMA_VERSION = "1.0.0"
PROJECTS_SCHEMA_ID = "skeleton.projects.v1"
SESSION_ENV = "SKELETON_SESSION_TOKEN"
PROJECT_STATUSES = frozenset({"draft", "active", "archived"})
BUILD_STATUSES = frozenset({"pending", "queued", "running", "succeeded", "failed", "cancelled"})
TERMINAL_BUILD_STATUSES = frozenset({"succeeded", "failed", "cancelled"})

SDK_ROUTES: tuple[tuple[str, str], ...] = (
    ("POST", PROJECTS_BASE_PATH),
    ("GET", PROJECTS_BASE_PATH),
    ("GET", PROJECTS_BASE_PATH + "/{project_id}"),
    ("POST", PROJECTS_BASE_PATH + "/{project_id}/builds"),
    ("GET", PROJECTS_BASE_PATH + "/{project_id}/builds"),
    ("GET", PROJECTS_BASE_PATH + "/{project_id}/builds/{build_id}"),
)

_MAX_BRIEF_TEXT = 20000
_MAX_TITLE = 200
_MAX_SUMMARY = 8000
_MAX_GENRE = 80
_MAX_CONSTRAINTS = 32


def _check_len(name: str, value: str | None, *, lo: int = 0, hi: int) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not (lo <= len(value) <= hi):
        raise ValueError(f"{name} must be a string of length {lo}..{hi}")


def _seg(value: str) -> str:
    if not value:
        raise ValueError("id must be non-empty")
    return quote(value, safe="")


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _ts(value: Any) -> float | str | None:
    """Timestamps: float epoch (#4097) or RFC 3339 string (v1); kept as given."""
    if value is None or isinstance(value, (int, float, str)) and not isinstance(value, bool):
        return value
    return str(value)


@dataclass(frozen=True, slots=True)
class ProjectBrief:
    """Structured brief (``skeleton.projects.v1`` ``ProjectBrief``)."""

    title: str
    summary: str = ""
    genre: str = ""
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _check_len("title", self.title, lo=1, hi=_MAX_TITLE)
        _check_len("summary", self.summary, hi=_MAX_SUMMARY)
        _check_len("genre", self.genre, hi=_MAX_GENRE)
        if isinstance(self.constraints, (str, bytes)):
            raise ValueError("constraints must be a sequence of strings")
        items = tuple(self.constraints)
        if len(items) > _MAX_CONSTRAINTS:
            raise ValueError(f"at most {_MAX_CONSTRAINTS} constraints")
        for item in items:
            _check_len("constraint", item, lo=1, hi=_MAX_TITLE)
        object.__setattr__(self, "constraints", items)

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "genre": self.genre,
            "constraints": list(self.constraints),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProjectBrief":
        return cls(
            title=str(data.get("title") or "Untitled"),
            summary=str(data.get("summary") or ""),
            genre=str(data.get("genre") or ""),
            constraints=tuple(str(c) for c in (data.get("constraints") or ())),
        )


BriefInput = Union[str, ProjectBrief]


@dataclass(frozen=True, slots=True)
class Project:
    """Union of #4097 ``ProjectOut`` and v1 ``Project`` (unknown keys ignored)."""

    project_id: str
    name: str = ""
    brief: str | ProjectBrief = ""
    settings: dict[str, Any] = field(default_factory=dict)
    status: str | None = None
    build_ids: tuple[str, ...] = ()
    owner_id: str | None = None
    actor_id: str | None = None
    tenant_id: str | None = None
    created_at: float | str | None = None
    updated_at: float | str | None = None
    schema_version: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Project":
        raw_brief = data.get("brief", "")
        brief: str | ProjectBrief
        if isinstance(raw_brief, Mapping):
            try:
                brief = ProjectBrief.from_dict(raw_brief)
            except ValueError:
                brief = str(raw_brief.get("title") or "")
        else:
            brief = str(raw_brief or "")
        name = data.get("name")
        if not name and isinstance(brief, ProjectBrief):
            name = brief.title
        return cls(
            project_id=str(data["project_id"]),
            name=str(name or ""),
            brief=brief,
            settings=dict(data.get("settings") or {}),
            status=_opt_str(data.get("status")),
            build_ids=tuple(str(b) for b in (data.get("build_ids") or ())),
            owner_id=_opt_str(data.get("owner_id")),
            actor_id=_opt_str(data.get("actor_id")),
            tenant_id=_opt_str(data.get("tenant_id")),
            created_at=_ts(data.get("created_at")),
            updated_at=_ts(data.get("updated_at")),
            schema_version=_opt_str(data.get("schema_version")),
        )


@dataclass(frozen=True, slots=True)
class ProjectPage:
    """``list()`` result: items plus ``next_cursor`` when the server pages."""

    items: tuple[Project, ...]
    next_cursor: str | None = None

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


@dataclass(frozen=True, slots=True)
class ProjectBuild:
    """#4097 ``BuildOut`` plus optional v1 ``execution_id`` / link fields."""

    build_id: str | None = None
    project_id: str = ""
    status: str | None = None
    execution_id: str | None = None
    target: str = ""
    job_id: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    created_at: float | str | None = None
    updated_at: float | str | None = None
    linked_at: str | None = None
    replayed: bool | None = None
    schema_version: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_BUILD_STATUSES

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProjectBuild":
        replayed = data.get("replayed")
        err = data.get("error")
        return cls(
            build_id=_opt_str(data.get("build_id")),
            project_id=str(data.get("project_id") or ""),
            status=_opt_str(data.get("status")),
            execution_id=_opt_str(data.get("execution_id")),
            target=str(data.get("target") or ""),
            job_id=_opt_str(data.get("job_id")),
            result=dict(data.get("result") or {}),
            error="" if err is None else (err if isinstance(err, str) else str(err)),
            created_at=_ts(data.get("created_at")),
            updated_at=_ts(data.get("updated_at")),
            linked_at=_opt_str(data.get("linked_at")),
            replayed=replayed if isinstance(replayed, bool) else None,
            schema_version=_opt_str(data.get("schema_version")),
        )


def _items(data: Any, *keys: str) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, Mapping):
        for key in keys:
            if isinstance(data.get(key), list):
                return data[key]
    return []


class ProjectsClient:
    """Typed client for ``skeleton.projects.v1`` (session-bearer auth)."""

    __slots__ = ("_gw", "_token", "base_path")

    def __init__(
        self,
        gateway: GatewayClient,
        *,
        session_token: str | None = None,
        base_path: str = PROJECTS_BASE_PATH,
    ) -> None:
        token = session_token if session_token is not None else os.environ.get(SESSION_ENV, "")
        if not token:
            raise SkeletonSessionConfigError(
                f"no session token: pass session_token= or set {SESSION_ENV}"
            )
        if not base_path.startswith("/"):
            raise ValueError("base_path must start with '/'")
        self._gw = gateway
        self._token = token
        self.base_path = base_path.rstrip("/")

    def __repr__(self) -> str:  # never expose the token
        return f"ProjectsClient(base_path={self.base_path!r}, session_token=<redacted>)"

    # transport: own call so the per-call Authorization header is attached
    def _call(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
        extra_headers: Mapping[str, str] | None = None,
        idempotent: bool = False,
        cancel: CancelToken | None = None,
    ) -> Any:
        gw = self._gw
        from skeleton.client.errors import SkeletonSealConfigError
        from skeleton.client.gateway import _invalid_seal, _seal_unavailable

        attempts = gw._retry.max_attempts if idempotent else 1
        resealed = False
        attempt = 0
        while attempt < attempts:
            if cancel is not None:
                cancel.raise_if_cancelled()
            headers = gw._call_headers()
            headers["Authorization"] = f"Bearer {self._token}"
            if extra_headers:
                headers.update(extra_headers)
            try:
                response = gw._client.request(
                    method, path, json=json, params=params, headers=headers
                )
            except httpx.TimeoutException as exc:
                raise SkeletonTimeoutError(str(exc)) from exc
            except httpx.TransportError as exc:
                from skeleton.client.errors import SkeletonTransportError

                raise SkeletonTransportError(str(exc)) from exc
            gw._note_response(response, headers["x-request-id"])
            if _seal_unavailable(response):  # never retried
                raise SkeletonSealConfigError(
                    "server has no seal secret configured (503 seal_unavailable)"
                )
            if gw._seal is not None and not resealed and _invalid_seal(response):
                resealed = True
                gw._seal.invalidate()
                continue
            if (
                idempotent
                and response.status_code in gw._retry.retry_status_codes
                and attempt + 1 < attempts
            ):
                gw._backoff(attempt, response, cancel)
                attempt += 1
                continue
            if response.status_code >= 400:
                raise SkeletonHTTPError(
                    response.status_code,
                    response.reason_phrase,
                    url=str(response.url),
                    body=_safe_body(response),
                )
            return response.json() if response.content else None
        raise AssertionError("unreachable")

    # projects
    def create(
        self,
        brief: BriefInput,
        *,
        name: str | None = None,
        settings: Mapping[str, Any] | None = None,
    ) -> Project:
        """POST {base}. Never retried.

        ``brief`` is plain text (1..20000) or a structured :class:`ProjectBrief`.
        """
        body: dict[str, Any] = {"schema_version": PROJECTS_SCHEMA_VERSION}
        if isinstance(brief, ProjectBrief):
            body["brief"] = brief.as_dict()
        else:
            _check_len("brief", brief, lo=1, hi=_MAX_BRIEF_TEXT)
            body["brief"] = brief
        _check_len("name", name, hi=200)
        if name is not None:
            body["name"] = name
        if settings is not None:
            body["settings"] = dict(settings)
        return Project.from_dict(self._call("POST", self.base_path, json=body))

    def list(self, *, limit: int | None = None, cursor: str | None = None) -> ProjectPage:
        params: dict[str, Any] = {}
        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
                raise ValueError("limit must be an int in 1..100")
            params["limit"] = limit
        if cursor is not None:
            _check_len("cursor", cursor, lo=1, hi=512)
            params["cursor"] = cursor
        data = self._call("GET", self.base_path, params=params or None, idempotent=True)
        items = tuple(Project.from_dict(p) for p in _items(data, "items", "projects"))
        nxt = data.get("next_cursor") if isinstance(data, Mapping) else None
        return ProjectPage(items=items, next_cursor=_opt_str(nxt))

    def get(self, project_id: str) -> Project:
        return Project.from_dict(
            self._call("GET", f"{self.base_path}/{_seg(project_id)}", idempotent=True)
        )

    # builds
    def start_build(
        self,
        project_id: str,
        *,
        target: str | None = None,
        options: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        execution_id: str | None = None,
        cancel: CancelToken | None = None,
    ) -> ProjectBuild:
        """POST {base}/{id}/builds: start a build, or link ``execution_id``.

        Safe to retry: a uuid4 ``idempotency_key`` is generated when none is
        given and reused across retries (sent in the body and as the
        ``Idempotency-Key`` header).
        """
        _check_len("target", target, hi=64)
        _check_len("execution_id", execution_id, lo=1, hi=128)
        key = idempotency_key or uuid.uuid4().hex
        _check_len("idempotency_key", key, lo=1, hi=128)
        body: dict[str, Any] = {"schema_version": PROJECTS_SCHEMA_VERSION, "idempotency_key": key}
        if target is not None:
            body["target"] = target
        if options is not None:
            body["options"] = dict(options)
        if execution_id is not None:
            body["execution_id"] = execution_id
        data = self._call(
            "POST", f"{self.base_path}/{_seg(project_id)}/builds",
            json=body, extra_headers={"Idempotency-Key": key},
            idempotent=True, cancel=cancel,
        )
        return ProjectBuild.from_dict(data or {})

    def link_execution(
        self, project_id: str, execution_id: str, *, idempotency_key: str | None = None
    ) -> ProjectBuild:
        """Link an existing engine execution (thin alias of ``start_build``)."""
        if not execution_id:
            raise ValueError("execution_id is required")
        return self.start_build(
            project_id, execution_id=execution_id, idempotency_key=idempotency_key
        )

    def list_builds(self, project_id: str) -> list[ProjectBuild]:
        data = self._call("GET", f"{self.base_path}/{_seg(project_id)}/builds", idempotent=True)
        return [ProjectBuild.from_dict(b) for b in _items(data, "builds", "items")]

    def get_build(
        self, project_id: str, build_id: str, *, cancel: CancelToken | None = None
    ) -> ProjectBuild:
        return ProjectBuild.from_dict(
            self._call(
                "GET", f"{self.base_path}/{_seg(project_id)}/builds/{_seg(build_id)}",
                idempotent=True, cancel=cancel,
            )
        )

    def wait_build(
        self,
        project_id: str,
        build_id: str,
        *,
        poll_seconds: float = 1.0,
        timeout_seconds: float = 600.0,
        cancel: CancelToken | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> ProjectBuild:
        """Poll until ``succeeded|failed|cancelled``; raises on timeout/cancel."""
        if timeout_seconds is None or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive number (default 600)")
        nap = sleep or self._gw._sleep
        deadline = clock() + timeout_seconds
        while True:
            if cancel is not None:
                cancel.raise_if_cancelled()
            build = self.get_build(project_id, build_id, cancel=cancel)
            if build.is_terminal:
                return build
            if clock() >= deadline:
                raise SkeletonTimeoutError(
                    f"build {build_id} not terminal (status={build.status})"
                )
            if cancel is not None and nap is time.sleep:
                cancel.wait(poll_seconds)
            else:
                nap(poll_seconds)
