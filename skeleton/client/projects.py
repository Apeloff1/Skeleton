"""App-foundation Projects client: ``/api/app/projects`` (NOT under ``/api/v1``).

Contract frozen by Internal Systems in PR #4097
(``skeleton/app_services/projects_api.py``). Every route needs
``Authorization: Bearer <session token>``. Errors are ``{"detail": "<code>"}``
and surface as :class:`SkeletonHTTPError` with ``.code`` set.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from urllib.parse import quote

import httpx

from skeleton.client.cancel import CancelToken
from skeleton.client.errors import (
    SkeletonHTTPError,
    SkeletonSessionConfigError,
    SkeletonTimeoutError,
)
from skeleton.client.gateway import GatewayClient, _safe_body

PREFIX = "/api/app/projects"
SESSION_ENV = "SKELETON_SESSION_TOKEN"
BUILD_STATUSES = frozenset({"pending", "queued", "running", "succeeded", "failed", "cancelled"})
TERMINAL_BUILD_STATUSES = frozenset({"succeeded", "failed", "cancelled"})

SDK_ROUTES: tuple[tuple[str, str], ...] = (
    ("POST", "/api/app/projects"),
    ("GET", "/api/app/projects"),
    ("GET", "/api/app/projects/{project_id}"),
    ("POST", "/api/app/projects/{project_id}/builds"),
    ("GET", "/api/app/projects/{project_id}/builds"),
    ("GET", "/api/app/projects/{project_id}/builds/{build_id}"),
)


@dataclass(frozen=True, slots=True)
class Project:
    project_id: str
    owner_id: str
    name: str
    brief: str
    settings: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Project":
        return cls(
            project_id=str(data["project_id"]),
            owner_id=str(data.get("owner_id", "")),
            name=str(data.get("name", "")),
            brief=str(data.get("brief", "")),
            settings=dict(data.get("settings") or {}),
            created_at=float(data.get("created_at") or 0.0),
            updated_at=float(data.get("updated_at") or 0.0),
        )


@dataclass(frozen=True, slots=True)
class ProjectBuild:
    build_id: str
    project_id: str
    status: str
    target: str = ""
    job_id: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_BUILD_STATUSES

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProjectBuild":
        job = data.get("job_id")
        return cls(
            build_id=str(data["build_id"]),
            project_id=str(data.get("project_id", "")),
            status=str(data.get("status", "")),
            target=str(data.get("target") or ""),
            job_id=None if job is None else str(job),
            result=dict(data.get("result") or {}),
            error=str(data.get("error") or ""),
            created_at=float(data.get("created_at") or 0.0),
            updated_at=float(data.get("updated_at") or 0.0),
        )


def _seg(value: str) -> str:
    if not value:
        raise ValueError("id must be non-empty")
    return quote(value, safe="")


def _check_len(name: str, value: str | None, *, lo: int = 0, hi: int) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not (lo <= len(value) <= hi):
        raise ValueError(f"{name} must be a string of length {lo}..{hi}")


class ProjectsClient:
    """Typed client for ``/api/app/projects`` (session-bearer auth)."""

    __slots__ = ("_gw", "_token")

    def __init__(self, gateway: GatewayClient, *, session_token: str | None = None) -> None:
        token = session_token if session_token is not None else os.environ.get(SESSION_ENV, "")
        if not token:
            raise SkeletonSessionConfigError(
                f"no session token: pass session_token= or set {SESSION_ENV}"
            )
        self._gw = gateway
        self._token = token

    def __repr__(self) -> str:  # never expose the token
        return "ProjectsClient(session_token=<redacted>)"

    # transport: own call so the per-call Authorization header is attached
    def _call(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
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
            try:
                response = gw._client.request(method, path, json=json, headers=headers)
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
        brief: str,
        *,
        name: str | None = None,
        settings: Mapping[str, Any] | None = None,
    ) -> Project:
        """POST /api/app/projects (201). Never retried. 409 ``project_name_conflict``."""
        _check_len("brief", brief, lo=1, hi=20000)
        _check_len("name", name, hi=200)
        body: dict[str, Any] = {"brief": brief}
        if name is not None:
            body["name"] = name
        if settings is not None:
            body["settings"] = dict(settings)
        return Project.from_dict(self._call("POST", PREFIX, json=body))

    def list(self) -> list[Project]:
        data = self._call("GET", PREFIX, idempotent=True)
        return [Project.from_dict(p) for p in (data or {}).get("projects", [])]

    def get(self, project_id: str) -> Project:
        return Project.from_dict(self._call("GET", f"{PREFIX}/{_seg(project_id)}", idempotent=True))

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
        """POST .../builds (202). Safe to retry: server dedups on ``idempotency_key``.

        A uuid4 key is generated when none is given and reused across retries.
        """
        _check_len("target", target, hi=64)
        key = idempotency_key or uuid.uuid4().hex
        _check_len("idempotency_key", key, lo=1, hi=128)
        body: dict[str, Any] = {"idempotency_key": key}
        if target is not None:
            body["target"] = target
        if options is not None:
            body["options"] = dict(options)
        return ProjectBuild.from_dict(
            self._call(
                "POST", f"{PREFIX}/{_seg(project_id)}/builds",
                json=body, idempotent=True, cancel=cancel,
            )
        )

    def list_builds(self, project_id: str) -> list[ProjectBuild]:
        """Newest 50 builds (server limit)."""
        data = self._call("GET", f"{PREFIX}/{_seg(project_id)}/builds", idempotent=True)
        return [ProjectBuild.from_dict(b) for b in (data or {}).get("builds", [])]

    def get_build(
        self, project_id: str, build_id: str, *, cancel: CancelToken | None = None
    ) -> ProjectBuild:
        return ProjectBuild.from_dict(
            self._call(
                "GET", f"{PREFIX}/{_seg(project_id)}/builds/{_seg(build_id)}",
                idempotent=True, cancel=cancel,
            )
        )

    def wait_build(
        self,
        project_id: str,
        build_id: str,
        *,
        poll_seconds: float = 1.0,
        timeout_seconds: float | None = None,
        cancel: CancelToken | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> ProjectBuild:
        """Poll until ``succeeded|failed|cancelled``; raises on timeout/cancel."""
        nap = sleep or self._gw._sleep
        deadline = None if timeout_seconds is None else clock() + timeout_seconds
        while True:
            if cancel is not None:
                cancel.raise_if_cancelled()
            build = self.get_build(project_id, build_id, cancel=cancel)
            if build.is_terminal:
                return build
            if deadline is not None and clock() >= deadline:
                raise SkeletonTimeoutError(
                    f"build {build_id} not terminal (status={build.status})"
                )
            if cancel is not None and nap is time.sleep:
                cancel.wait(poll_seconds)
            else:
                nap(poll_seconds)
