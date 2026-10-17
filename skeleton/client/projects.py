"""Projects client for ``skeleton.projects.v1`` (base ``/api/v1/projects``).

Aligned to Internal Systems' #4097 at 6524b7c35 (``skeleton/api/projects_routes.py``;
its ``skeleton/contracts/projects.py`` is byte-identical to #4112's).

- Auth: every route needs ``x-gf-seal`` (configure a seal on the gateway) and
  ``Authorization: Bearer <session token>``. Seal failures come from the gate as
  ``{"error": "invalid_seal"}`` (re-minted once) or ``{"error":
  "seal_unavailable"}`` (never retried).
- ``actor_id`` and ``tenant_id`` are server-derived and never sent. Unknown body
  fields are rejected with 400, so the client sends only contract fields.
- Errors use ``{"error": {"type": "ProjectContractError", "code": "PROJECT.*",
  "message", "context"}}`` and surface as :class:`SkeletonHTTPError` with
  ``.code``, ``.message`` and ``.context`` set.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
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

PROJECT_ERROR_INVALID = "PROJECT.INVALID"  # 400
PROJECT_ERROR_UNAUTHENTICATED = "PROJECT.UNAUTHENTICATED"  # 401
PROJECT_ERROR_NOT_FOUND = "PROJECT.NOT_FOUND"  # 404
PROJECT_ERROR_BUILD_CONFLICT = "PROJECT.BUILD_CONFLICT"  # 409
PROJECT_ERROR_NAME_CONFLICT = "PROJECT.NAME_CONFLICT"  # 409
PROJECT_ERROR_UNAVAILABLE = "PROJECT.UNAVAILABLE"  # 503
PROJECT_ERROR_IDEMPOTENCY_MISMATCH = "PROJECT.IDEMPOTENCY_MISMATCH"  # 409
PROJECT_ERROR_STATUS: dict[str, int] = {
    PROJECT_ERROR_INVALID: 400,
    PROJECT_ERROR_UNAUTHENTICATED: 401,
    PROJECT_ERROR_NOT_FOUND: 404,
    PROJECT_ERROR_BUILD_CONFLICT: 409,
    PROJECT_ERROR_NAME_CONFLICT: 409,
    PROJECT_ERROR_UNAVAILABLE: 503,
    PROJECT_ERROR_IDEMPOTENCY_MISMATCH: 409,
}

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


@dataclass(frozen=True, slots=True)
class ProjectBrief:
    """``ProjectBrief``: title 1..200, summary <=8000, genre <=80, <=32 constraints."""

    title: str
    summary: str = ""
    genre: str = ""
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _check_len("title", self.title, lo=1, hi=_MAX_TITLE)
        _check_len("summary", self.summary, hi=_MAX_SUMMARY)
        _check_len("genre", self.genre, hi=_MAX_GENRE)
        if isinstance(self.constraints, (str, bytes)):
            raise TypeError("constraints must be a sequence of strings")
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
    def from_dict(cls, data: Mapping[str, Any]) -> ProjectBrief:
        """Lenient: server data is trusted, so no length re-validation."""
        obj = object.__new__(cls)
        object.__setattr__(obj, "title", str(data.get("title") or ""))
        object.__setattr__(obj, "summary", str(data.get("summary") or ""))
        object.__setattr__(obj, "genre", str(data.get("genre") or ""))
        object.__setattr__(
            obj, "constraints", tuple(str(c) for c in (data.get("constraints") or ()))
        )
        return obj


BriefInput = str | ProjectBrief


@dataclass(frozen=True, slots=True)
class Project:
    """``Project`` (unknown keys ignored)."""

    project_id: str
    brief: ProjectBrief
    status: str = "draft"
    build_ids: tuple[str, ...] = ()
    actor_id: str | None = None
    tenant_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    schema_version: str | None = None

    @property
    def title(self) -> str:
        return self.brief.title

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Project:
        raw = data.get("brief")
        if isinstance(raw, Mapping):
            brief = ProjectBrief.from_dict(raw)
        else:
            brief = ProjectBrief.from_dict({"title": str(raw or "")})
        return cls(
            project_id=str(data["project_id"]),
            brief=brief,
            status=str(data.get("status") or "draft"),
            build_ids=tuple(str(b) for b in (data.get("build_ids") or ())),
            actor_id=_opt_str(data.get("actor_id")),
            tenant_id=_opt_str(data.get("tenant_id")),
            created_at=_opt_str(data.get("created_at")),
            updated_at=_opt_str(data.get("updated_at")),
            schema_version=_opt_str(data.get("schema_version")),
        )


@dataclass(frozen=True, slots=True)
class ProjectPage:
    """``ProjectList``: items plus ``next_cursor``."""

    items: tuple[Project, ...]
    next_cursor: str | None = None

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


@dataclass(frozen=True, slots=True)
class ProjectBuildPage:
    """Build list page: items (newest first) plus ``next_cursor``.

    Iterable, sized and indexable so callers that treated ``list_builds()`` as a
    list keep working.
    """

    items: tuple[ProjectBuild, ...]
    next_cursor: str | None = None

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index):
        return self.items[index]


@dataclass(frozen=True, slots=True)
class ProjectBuild:
    """``Build`` (``execution_id`` == ``build_id``; ``replayed`` on idempotent replay)."""

    build_id: str
    project_id: str = ""
    status: str = "pending"
    execution_id: str | None = None
    target: str = ""
    job_id: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    replayed: bool = False
    schema_version: str | None = None
    schema_id: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_BUILD_STATUSES

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ProjectBuild:
        build_id = str(data["build_id"])
        err = data.get("error")
        return cls(
            build_id=build_id,
            project_id=str(data.get("project_id") or ""),
            status=str(data.get("status") or "pending"),
            execution_id=_opt_str(data.get("execution_id")) or build_id,
            target=str(data.get("target") or ""),
            job_id=_opt_str(data.get("job_id")),
            result=dict(data.get("result") or {}),
            error="" if err is None else str(err),
            created_at=_opt_str(data.get("created_at")),
            updated_at=_opt_str(data.get("updated_at")),
            replayed=data.get("replayed") is True,
            schema_version=_opt_str(data.get("schema_version")),
            schema_id=_opt_str(data.get("schema_id")),
        )


@dataclass(frozen=True, slots=True)
class ProjectBuildLink:
    """``ProjectBuildLink``: result of linking an existing engine execution."""

    project_id: str
    execution_id: str
    linked_at: str | None = None
    replayed: bool = False
    schema_version: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ProjectBuildLink:
        return cls(
            project_id=str(data.get("project_id") or ""),
            execution_id=str(data["execution_id"]),
            linked_at=_opt_str(data.get("linked_at")),
            replayed=data.get("replayed") is True,
            schema_version=_opt_str(data.get("schema_version")),
        )


def _items(data: Any) -> list[Any]:
    if isinstance(data, Mapping) and isinstance(data.get("items"), list):
        return data["items"]
    return []


def _page_params(limit: int | None, cursor: str | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an int in 1..100")
        params["limit"] = limit
    if cursor is not None:
        _check_len("cursor", cursor, lo=1, hi=512)
        params["cursor"] = cursor
    return params


class ProjectsClient:
    """Typed client for ``skeleton.projects.v1`` (seal + session-bearer auth)."""

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
        idempotency_key: str | None = None,
        name: Any = None,
        settings: Any = None,
    ) -> Project:
        """POST {base}: 201 Created, or 200 when replayed via ``Idempotency-Key``.

        ``brief`` is plain text (1..20000) or a :class:`ProjectBrief`. Retried
        only when ``idempotency_key`` is given (1..128); otherwise never.
        ``name``/``settings`` are not part of the contract and raise ValueError.
        """
        if name is not None or settings is not None:
            raise ValueError(
                "name/settings are not part of skeleton.projects.v1 (server rejects "
                "unknown fields); put the title in ProjectBrief.title"
            )
        body: dict[str, Any] = {"schema_version": PROJECTS_SCHEMA_VERSION}
        if isinstance(brief, ProjectBrief):
            body["brief"] = brief.as_dict()
        else:
            # skeleton.projects.v1 BriefInput: non-empty string, no upper bound (the
            # server derives title<=200 / summary<=8000 from it).
            if not isinstance(brief, str):
                raise TypeError("brief must be a str or ProjectBrief")
            if not brief.strip():
                raise ValueError("brief must be non-empty")
            body["brief"] = brief
        headers: dict[str, str] | None = None
        if idempotency_key is not None:
            _check_len("idempotency_key", idempotency_key, lo=1, hi=128)
            headers = {"Idempotency-Key": idempotency_key}
        return Project.from_dict(
            self._call(
                "POST", self.base_path, json=body, extra_headers=headers,
                idempotent=idempotency_key is not None,
            )
        )

    def list(self, *, limit: int | None = None, cursor: str | None = None) -> ProjectPage:
        """GET {base}?limit=1..100&cursor= -> items + next_cursor."""
        params = _page_params(limit, cursor)
        data = self._call("GET", self.base_path, params=params or None, idempotent=True)
        items = tuple(Project.from_dict(p) for p in _items(data))
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
        cancel: CancelToken | None = None,
    ) -> ProjectBuild:
        """POST {base}/{id}/builds (start): 202 Build, ``replayed`` on replay.

        A uuid4 ``idempotency_key`` is generated when none is given and reused
        across retries, so retrying is safe. To link an existing execution use
        :meth:`link_execution` (start and link fields are never mixed).
        """
        _check_len("target", target, hi=64)
        key = idempotency_key or uuid.uuid4().hex
        _check_len("idempotency_key", key, lo=1, hi=128)
        body: dict[str, Any] = {"schema_version": PROJECTS_SCHEMA_VERSION, "idempotency_key": key}
        if target is not None:
            body["target"] = target
        if options is not None:
            body["options"] = dict(options)
        return ProjectBuild.from_dict(
            self._call(
                "POST", f"{self.base_path}/{_seg(project_id)}/builds",
                json=body, idempotent=True, cancel=cancel,
            )
        )

    def link_execution(self, project_id: str, execution_id: str) -> ProjectBuildLink:
        """POST {base}/{id}/builds (link): 201 ProjectBuildLink, 200 on replay.

        Linking is idempotent per (project, execution), so it is safe to retry.
        """
        _check_len("execution_id", execution_id, lo=1, hi=128)
        body = {"schema_version": PROJECTS_SCHEMA_VERSION, "execution_id": execution_id}
        return ProjectBuildLink.from_dict(
            self._call(
                "POST", f"{self.base_path}/{_seg(project_id)}/builds",
                json=body, idempotent=True,
            )
        )

    def list_builds(
        self, project_id: str, *, limit: int | None = None, cursor: str | None = None
    ) -> ProjectBuildPage:
        """GET {base}/{id}/builds?limit=1..100&cursor= -> items (newest first) + next_cursor."""
        params = _page_params(limit, cursor)
        data = self._call(
            "GET", f"{self.base_path}/{_seg(project_id)}/builds",
            params=params or None, idempotent=True,
        )
        items = tuple(ProjectBuild.from_dict(b) for b in _items(data))
        nxt = data.get("next_cursor") if isinstance(data, Mapping) else None
        return ProjectBuildPage(items=items, next_cursor=_opt_str(nxt))

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
