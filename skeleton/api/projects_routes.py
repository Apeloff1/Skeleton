"""skeleton.projects.v1 HTTP handlers, mounted by ``create_app`` at /api/v1/projects.

Behind ``install_gate`` (x-gf-seal client/service attestation) AND an end-user
session (``Authorization: Bearer <session>``).  actor_id = session user,
tenant_id = APP_TENANT_ID (default ``default``); both are server-derived.
Every error uses the envelope
``{"error":{"type","code":"PROJECT.*","message","context":{}}}``.
See docs/architecture/contracts/projects.md and the #4097 PR body for the
route table and deviations from #4112.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from skeleton.app_services.container import AppServices
from skeleton.app_services.ports import Build, SessionPrincipal
from skeleton.app_services.runtime import get_app_services
from skeleton.contracts.projects import (
    PROJECT_ERROR_BUILD_CONFLICT,
    PROJECT_ERROR_INVALID,
    PROJECT_ERROR_NOT_FOUND,
    PROJECTS_SCHEMA_ID,
    PROJECTS_SCHEMA_VERSION,
    ProjectBrief,
    ProjectContractError,
    ProjectListQuery,
    _ID,
)
from skeleton.app_services.job_api import IdempotencyMismatch
from skeleton.persistence.app_foundation.projects_v1 import (
    BuildLinkConflict,
    CreateIdempotencyMismatch,
    ProjectNameConflict,
    ProjectsV1Store,
    _iso,
)

_log = logging.getLogger(__name__)

PROJECT_ERROR_UNAUTHENTICATED = "PROJECT.UNAUTHENTICATED"
PROJECT_ERROR_NAME_CONFLICT = "PROJECT.NAME_CONFLICT"
PROJECT_ERROR_UNAVAILABLE = "PROJECT.UNAVAILABLE"
PROJECT_ERROR_IDEMPOTENCY_MISMATCH = "PROJECT.IDEMPOTENCY_MISMATCH"
GAME_BUILD_KIND = "game.build"
ERROR_STATUS = {
    PROJECT_ERROR_INVALID: 400,
    PROJECT_ERROR_UNAUTHENTICATED: 401,
    PROJECT_ERROR_NOT_FOUND: 404,
    PROJECT_ERROR_BUILD_CONFLICT: 409,
    PROJECT_ERROR_NAME_CONFLICT: 409,
    PROJECT_ERROR_IDEMPOTENCY_MISMATCH: 409,
    PROJECT_ERROR_UNAVAILABLE: 503,
}
BuildStatus = Literal["pending", "queued", "running", "succeeded", "failed", "cancelled"]
_BUILD_STATUSES: tuple[str, ...] = BuildStatus.__args__  # type: ignore[attr-defined]


class ProjectHTTPError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def error_response(code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=ERROR_STATUS[code], content={"error": {
        "type": "ProjectContractError", "code": code, "message": message, "context": {}}})


def _limit(raw: str) -> int:
    if not raw.isdigit() or not 1 <= int(raw) <= 100:
        raise ProjectHTTPError(PROJECT_ERROR_INVALID, "limit must be from 1 to 100")
    return int(raw)


def _tenant() -> str:
    return os.environ.get("APP_TENANT_ID", "default")


def build_out(b: Build, *, replayed: bool = False) -> dict[str, Any]:
    status: BuildStatus = b.status if b.status in _BUILD_STATUSES else "pending"  # type: ignore[assignment]
    return {
        "schema_version": PROJECTS_SCHEMA_VERSION, "schema_id": PROJECTS_SCHEMA_ID,
        "build_id": b.build_id, "execution_id": b.build_id, "project_id": b.project_id,
        "status": status, "target": b.target, "job_id": b.job_id, "result": dict(b.result),
        "error": b.error, "created_at": _iso(b.created_at), "updated_at": _iso(b.updated_at),
        "replayed": replayed,
    }


def _brief_from(value: Any) -> ProjectBrief:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ProjectContractError("brief must be non-empty")
        lines = text.splitlines()
        title = lines[0].strip()[:200].strip()
        summary = "\n".join(lines[1:]).strip()[:8000].strip()
        return ProjectBrief(title=title, summary=summary)
    if isinstance(value, dict):
        return ProjectBrief.from_dict(value)
    raise ProjectContractError("brief must be a string or a brief object")


async def _json_body(request: Request, allowed: set[str], required: set[str] = frozenset()) -> dict:
    raw = await request.body()
    if not raw:
        data: Any = {}
    else:
        try:
            data = json.loads(raw)
        except ValueError:
            raise ProjectHTTPError(PROJECT_ERROR_INVALID, "body must be JSON")
    if not isinstance(data, dict):
        raise ProjectHTTPError(PROJECT_ERROR_INVALID, "body must be an object")
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ProjectHTTPError(PROJECT_ERROR_INVALID, f"unknown fields: {unknown}")
    missing = sorted(required - set(data))
    if missing:
        raise ProjectHTTPError(PROJECT_ERROR_INVALID, f"missing fields: {missing}")
    if "schema_version" in data and data["schema_version"] != PROJECTS_SCHEMA_VERSION:
        raise ProjectHTTPError(PROJECT_ERROR_INVALID, f"schema_version must be {PROJECTS_SCHEMA_VERSION}")
    return data


def _reject_scope_fields(data: dict, who: SessionPrincipal) -> None:
    # actor/tenant are server-derived; a body value that disagrees is rejected.
    if "actor_id" in data and data["actor_id"] != who.user_id:
        raise ProjectHTTPError(PROJECT_ERROR_INVALID, "actor_id is derived from the session")
    if "tenant_id" in data and data["tenant_id"] != _tenant():
        raise ProjectHTTPError(PROJECT_ERROR_INVALID, "tenant_id is derived from the session")


def build_router(services_dep=get_app_services) -> APIRouter:
    router = APIRouter(prefix="/projects", tags=["projects-v1"])

    def principal(authorization: Optional[str] = Header(default=None),
                  svc: AppServices = Depends(services_dep)) -> SessionPrincipal:
        token = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else ""
        p = svc.auth.resolve_session(token) if token else None
        if p is None:
            raise ProjectHTTPError(PROJECT_ERROR_UNAUTHENTICATED, "valid session required")
        return p

    def guarded(fn):
        async def wrapper(*a, **kw):
            try:
                return await fn(*a, **kw)
            except ProjectHTTPError as e:
                return error_response(e.code, e.message)
            except ProjectContractError as e:
                return error_response(PROJECT_ERROR_INVALID, str(e) or "invalid request")
            except sqlite3.Error:
                _log.exception("projects storage error")
                return error_response(PROJECT_ERROR_UNAVAILABLE, "project storage unavailable")
        wrapper.__name__ = fn.__name__
        wrapper.__signature__ = __import__("inspect").signature(fn)  # type: ignore[attr-defined]
        return wrapper

    def _project_or_404(svc: AppServices, who: SessionPrincipal, project_id: str):
        if _ID.fullmatch(project_id or "") is None:
            raise ProjectHTTPError(PROJECT_ERROR_NOT_FOUND, "project not found")
        p = ProjectsV1Store(svc.db).get(who.user_id, _tenant(), project_id)
        if p is None:
            raise ProjectHTTPError(PROJECT_ERROR_NOT_FOUND, "project not found")
        return p

    async def _auth(request: Request, svc: AppServices) -> SessionPrincipal:
        return principal(request.headers.get("authorization"), svc)

    @router.post("")
    @guarded
    async def create_project(request: Request, svc: AppServices = Depends(services_dep),
                             idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")):
        who = await _auth(request, svc)
        data = await _json_body(request, {"schema_version", "brief", "actor_id", "tenant_id"}, {"brief"})
        _reject_scope_fields(data, who)
        if idempotency_key is not None and (not idempotency_key or len(idempotency_key) > 128):
            raise ProjectHTTPError(PROJECT_ERROR_INVALID, "Idempotency-Key must be 1..128 chars")
        try:
            project, replayed = ProjectsV1Store(svc.db).create(
                who.user_id, _tenant(), _brief_from(data["brief"]), idempotency_key)
        except ProjectNameConflict:
            raise ProjectHTTPError(PROJECT_ERROR_NAME_CONFLICT, "a project with this title already exists")
        except CreateIdempotencyMismatch:
            raise ProjectHTTPError(PROJECT_ERROR_IDEMPOTENCY_MISMATCH,
                                   "Idempotency-Key was already used with a different body")
        return JSONResponse(status_code=200 if replayed else 201, content=project.as_dict())

    @router.get("")
    @guarded
    async def list_projects(request: Request, svc: AppServices = Depends(services_dep),
                            limit: str = "50", cursor: Optional[str] = None):
        who = await _auth(request, svc)
        q = ProjectListQuery(actor_id=who.user_id, tenant_id=_tenant(), limit=_limit(limit), cursor=cursor)
        items, nxt = ProjectsV1Store(svc.db).list(q.actor_id, q.tenant_id, q.limit, q.cursor)
        return JSONResponse({"schema_version": PROJECTS_SCHEMA_VERSION,
                             "items": [p.as_dict() for p in items], "next_cursor": nxt})

    @router.get("/{project_id}")
    @guarded
    async def get_project(project_id: str, request: Request, svc: AppServices = Depends(services_dep)):
        who = await _auth(request, svc)
        return JSONResponse(_project_or_404(svc, who, project_id).as_dict())

    @router.post("/{project_id}/builds")
    @guarded
    async def start_or_link_build(project_id: str, request: Request,
                                  svc: AppServices = Depends(services_dep)):
        who = await _auth(request, svc)
        _project_or_404(svc, who, project_id)
        data = await _json_body(request, {"schema_version", "target", "options", "idempotency_key",
                                          "execution_id", "actor_id", "tenant_id"})
        _reject_scope_fields(data, who)
        store = ProjectsV1Store(svc.db)
        if "execution_id" in data:
            if set(data) & {"target", "options", "idempotency_key"}:
                raise ProjectHTTPError(PROJECT_ERROR_INVALID, "execution_id links; it cannot be combined with start fields")
            if not isinstance(data["execution_id"], str) or _ID.fullmatch(data["execution_id"]) is None:
                raise ProjectHTTPError(PROJECT_ERROR_INVALID, "execution_id must be a path-safe identifier")
            try:
                link = store.link(who.user_id, _tenant(), project_id, data["execution_id"])
            except BuildLinkConflict:
                raise ProjectHTTPError(PROJECT_ERROR_BUILD_CONFLICT, "execution cannot be linked")
            if link is None:
                raise ProjectHTTPError(PROJECT_ERROR_NOT_FOUND, "project not found")
            return JSONResponse(status_code=200 if link.replayed else 201, content=link.as_dict())
        target, options, key = data.get("target", ""), data.get("options", {}), data.get("idempotency_key")
        if not isinstance(target, str) or len(target) > 64:
            raise ProjectHTTPError(PROJECT_ERROR_INVALID, "target must be text up to 64 chars")
        if not isinstance(options, dict):
            raise ProjectHTTPError(PROJECT_ERROR_INVALID, "options must be an object")
        if key is not None and (not isinstance(key, str) or not key or len(key) > 128):
            raise ProjectHTTPError(PROJECT_ERROR_INVALID, "idempotency_key must be 1..128 chars")
        try:
            handle = svc.jobs.enqueue(
                GAME_BUILD_KIND, {"target": target, "options": options},
                actor_id=who.user_id, tenant_id=_tenant(), project_id=project_id,
                idempotency_key=f"{project_id}:{key}" if key else None,
                correlation_id=request.headers.get("x-request-id") or None)
        except IdempotencyMismatch:
            raise ProjectHTTPError(PROJECT_ERROR_IDEMPOTENCY_MISMATCH,
                                   "idempotency_key was already used with a different target/options")
        b = svc.builds.get_build(handle.execution_id)
        if not handle.replayed:
            try:
                store.link(who.user_id, _tenant(), project_id, b.build_id)
            except BuildLinkConflict:
                svc.jobs.cancel(handle.job_id)
                raise ProjectHTTPError(PROJECT_ERROR_BUILD_CONFLICT, "project build limit reached")
            b = svc.builds.get_build(handle.execution_id)
        return JSONResponse(status_code=202, content=build_out(b, replayed=handle.replayed))

    @router.get("/{project_id}/builds")
    @guarded
    async def list_builds(project_id: str, request: Request, svc: AppServices = Depends(services_dep),
                          limit: str = "50", cursor: Optional[str] = None):
        who = await _auth(request, svc)
        _project_or_404(svc, who, project_id)
        ids, nxt = ProjectsV1Store(svc.db).list_build_rows(project_id, _limit(limit), cursor)
        items = [build_out(b) for b in (svc.builds.get_build(i) for i in ids) if b is not None]
        return JSONResponse({"schema_version": PROJECTS_SCHEMA_VERSION, "items": items, "next_cursor": nxt})

    @router.get("/{project_id}/builds/{build_id}")
    @guarded
    async def get_build(project_id: str, build_id: str, request: Request,
                        svc: AppServices = Depends(services_dep)):
        who = await _auth(request, svc)
        _project_or_404(svc, who, project_id)
        b = svc.builds.get_build(build_id)
        if b is None or b.project_id != project_id:
            raise ProjectHTTPError(PROJECT_ERROR_NOT_FOUND, "build not found")
        return JSONResponse(build_out(b))

    return router


router = build_router()
