"""Projects HTTP router (app foundation).  Fixed v1 route shapes.

Prefix ``/api/app/projects``.  Caller identity: ``Authorization: Bearer
<session token>`` resolved through the ``SessionResolver`` port
(``AuthService.resolve_session``).  The x-gf-seal gate (``install_gate``) still
applies in front of this router.  No secrets or tokens are ever returned.

  POST /api/app/projects                     201 ProjectOut   (create from brief)
  GET  /api/app/projects                     200 {"projects":[ProjectOut]}
  GET  /api/app/projects/{project_id}        200 ProjectOut   | 404
  POST /api/app/projects/{project_id}/builds 202 BuildOut     | 404
  GET  /api/app/projects/{project_id}/builds 200 {"builds":[BuildOut]} | 404
  GET  /api/app/projects/{project_id}/builds/{build_id} 200 BuildOut | 404
Errors: 401 {"detail":"invalid_session"}, 404 {"detail":"project_not_found"|"build_not_found"},
422 validation.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from skeleton.app_services.container import AppServices
from skeleton.app_services.ports import Build, Project, SessionPrincipal

PREFIX = "/api/app/projects"


class ProjectCreate(BaseModel):
    brief: str = Field(..., min_length=1, max_length=20000)
    name: Optional[str] = Field(default=None, max_length=200)
    settings: Dict[str, Any] = Field(default_factory=dict)


class BuildCreate(BaseModel):
    target: str = Field(default="", max_length=64)
    options: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class ProjectOut(BaseModel):
    project_id: str
    owner_id: str
    name: str
    brief: str
    settings: Dict[str, Any]
    created_at: float
    updated_at: float


class BuildOut(BaseModel):
    build_id: str
    project_id: str
    status: str
    target: str
    job_id: Optional[str]
    result: Dict[str, Any]
    error: str
    created_at: float
    updated_at: float


class ProjectList(BaseModel):
    projects: List[ProjectOut]


class BuildList(BaseModel):
    builds: List[BuildOut]


_lock = threading.Lock()
_services: Optional[AppServices] = None


def default_services() -> AppServices:
    """Lazily opened singleton (no lifespan hook)."""
    global _services
    with _lock:
        if _services is None:
            _services = AppServices.open(os.environ.get("APP_SERVICES_DATA_DIR", "data/app_services"))
        return _services


def _project_out(p: Project) -> ProjectOut:
    return ProjectOut(project_id=p.project_id, owner_id=p.owner_id, name=p.name, brief=p.brief,
                      settings=dict(p.settings), created_at=p.created_at, updated_at=p.updated_at)


def _build_out(b: Build) -> BuildOut:
    return BuildOut(build_id=b.build_id, project_id=b.project_id, status=b.status, target=b.target,
                    job_id=b.job_id, result=dict(b.result), error=b.error,
                    created_at=b.created_at, updated_at=b.updated_at)


def _name_from_brief(brief: str) -> str:
    first = brief.strip().splitlines()[0].strip()
    return (first[:80] or "Untitled project")


def build_router(services: Callable[[], AppServices] = default_services) -> APIRouter:
    router = APIRouter(prefix=PREFIX, tags=["app-projects"])

    def principal(authorization: Optional[str] = Header(default=None)) -> SessionPrincipal:
        token = ""
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        p = services().auth.resolve_session(token)
        if p is None:
            raise HTTPException(status_code=401, detail="invalid_session")
        return p

    def owned(project_id: str, who: SessionPrincipal) -> Project:
        p = services().projects.get_project(project_id)
        if p is None or p.owner_id != who.user_id:
            raise HTTPException(status_code=404, detail="project_not_found")
        return p

    @router.post("", status_code=201, response_model=ProjectOut)
    def create_project(body: ProjectCreate, who: SessionPrincipal = Depends(principal)) -> ProjectOut:
        name = (body.name or "").strip() or _name_from_brief(body.brief)
        try:
            p = services().projects.create_project(who.user_id, name, body.settings, brief=body.brief)
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail="project_name_conflict")
            raise
        return _project_out(p)

    @router.get("", response_model=ProjectList)
    def list_projects(who: SessionPrincipal = Depends(principal)) -> ProjectList:
        return ProjectList(projects=[_project_out(p) for p in services().projects.list_projects(who.user_id)])

    @router.get("/{project_id}", response_model=ProjectOut)
    def get_project(project_id: str, who: SessionPrincipal = Depends(principal)) -> ProjectOut:
        return _project_out(owned(project_id, who))

    @router.post("/{project_id}/builds", status_code=202, response_model=BuildOut)
    def create_build(project_id: str, body: BuildCreate, request: Request,
                     who: SessionPrincipal = Depends(principal)) -> BuildOut:
        owned(project_id, who)
        b = services().build_service.submit(
            project_id, target=body.target, options=body.options,
            correlation_id=request.headers.get("x-request-id", ""),
            idempotency_key=f"{project_id}:{body.idempotency_key}" if body.idempotency_key else None)
        return _build_out(b)

    @router.get("/{project_id}/builds", response_model=BuildList)
    def list_builds(project_id: str, who: SessionPrincipal = Depends(principal)) -> BuildList:
        owned(project_id, who)
        return BuildList(builds=[_build_out(b) for b in services().builds.list_builds(project_id)])

    @router.get("/{project_id}/builds/{build_id}", response_model=BuildOut)
    def get_build(project_id: str, build_id: str, who: SessionPrincipal = Depends(principal)) -> BuildOut:
        owned(project_id, who)
        b = services().builds.get_build(build_id)
        if b is None or b.project_id != project_id:
            raise HTTPException(status_code=404, detail="build_not_found")
        return _build_out(b)

    return router


router = build_router()
