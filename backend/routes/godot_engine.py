"""
routes/godot_engine.py — HTTP surface for the in-repo Godot engine.

Mounted at ``/api/godot-engine`` via ``core.routes_registry.KNOWN_ROUTES``.

Endpoints
---------
GET  /api/godot-engine/status            — binary availability, version, integrity, pipeline stats
GET  /api/godot-engine/templates         — scaffold templates with their file lists
POST /api/godot-engine/projects          — scaffold a new Godot project (409 on slug conflict)
POST /api/godot-engine/jobs              — submit a headless job (import/check/export)
GET  /api/godot-engine/jobs              — recent jobs
GET  /api/godot-engine/jobs/{job_id}     — single job with stdout/stderr tails
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gameforge.godot_engine.binary import binary_status, get_binary
from gameforge.godot_engine.pipeline import get_pipeline
from gameforge.godot_engine.project import (
    ProjectExistsError,
    ProjectSpec,
    available_templates,
    scaffold_project,
)

router = APIRouter(prefix="/api/godot-engine", tags=["godot-engine"])

# Projects are scaffolded under the backend data dir (gitignored, volume-backed).
_PROJECTS_ROOT = Path(
    os.environ.get(
        "GODOT_PROJECTS_DIR",
        str(Path(__file__).resolve().parents[1] / "data" / "godot_projects"),
    )
)

_SLUG_RE = re.compile(r"^[a-z0-9_]{1,48}$")


def _project_dir_for(slug: str) -> Path:
    """Resolve a user-supplied slug to a project dir, or 404/422 out.

    The slug must be a simple directory name; the resolved path must stay
    inside the projects root. No traversal through to the pipeline.
    """
    if not _SLUG_RE.match(slug):
        raise HTTPException(422, f"invalid project slug: {slug!r}")
    project_dir = _PROJECTS_ROOT / slug
    if not project_dir.is_dir():
        raise HTTPException(404, f"no project named {slug!r}")
    return project_dir


# ── Models ────────────────────────────────────────────────────────────────

class ProjectCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    template: Literal["platformer2d", "topdown2d", "blank2d"] = "platformer2d"
    renderer: Literal["forward_plus", "mobile", "gl_compatibility"] = "gl_compatibility"
    window_width: int = Field(1280, ge=320, le=7680)
    window_height: int = Field(720, ge=240, le=4320)
    features: list[str] = Field(default_factory=lambda: ["4.2"])
    autoloads: dict[str, str] = Field(default_factory=dict)
    input_actions: dict[str, list[str]] = Field(default_factory=dict)
    overwrite: bool = False


class JobSubmitRequest(BaseModel):
    kind: Literal["import", "check", "export", "dump_gdextension"]
    project_slug: str | None = None
    preset: str | None = None          # export: preset name from export_presets.cfg
    output: str | None = None          # export: output path relative to project dir
    script: str | None = None          # check: path to .gd file relative to project dir
    timeout: int = Field(600, ge=10, le=3600)


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.get("/status")
async def godot_status() -> dict:
    """Report binary availability, engine profile, integrity, pipeline stats."""
    status = binary_status()
    if not status.get("available"):
        return status
    try:
        status["version"] = (await get_binary().probe()).version
    except Exception as e:
        status["probe_error"] = f"{type(e).__name__}: {e}"
    status["projects_root"] = str(_PROJECTS_ROOT)
    status["pipeline"] = get_pipeline().stats()
    return status


@router.get("/templates")
async def list_templates() -> list[dict]:
    """Scaffold templates with the files and controllers each one emits."""
    return available_templates()


@router.post("/projects", status_code=201)
async def create_project(req: ProjectCreateRequest) -> dict:
    """Scaffold a runnable Godot 4 project (project.godot, main scene, script)."""
    spec = ProjectSpec(
        title=req.title,
        description=req.description,
        template=req.template,
        renderer=req.renderer,
        window_width=req.window_width,
        window_height=req.window_height,
        features=req.features,
        autoloads=req.autoloads,
        input_actions=req.input_actions,
    )
    try:
        result = scaffold_project(spec, _PROJECTS_ROOT, overwrite=req.overwrite)
    except ProjectExistsError as e:
        raise HTTPException(
            409,
            f"project {e.slug!r} already exists — set overwrite=true to replace it",
        ) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return result.to_dict()


@router.post("/jobs", status_code=202)
async def submit_job(req: JobSubmitRequest) -> dict:
    """Submit a headless Godot job; returns immediately with a job id."""
    project_dir = _project_dir_for(req.project_slug) if req.project_slug else None
    kwargs: dict = {}
    if req.kind == "export":
        if not req.preset or not req.output:
            raise HTTPException(422, "export jobs need preset and output")
        kwargs["preset"] = req.preset
        kwargs["output"] = (project_dir or _PROJECTS_ROOT) / req.output
    if req.kind == "check":
        if not req.script:
            raise HTTPException(422, "check jobs need script")
        kwargs["script"] = (project_dir or _PROJECTS_ROOT) / req.script
    try:
        job = await get_pipeline().submit(
            req.kind, project_dir, timeout=req.timeout, **kwargs
        )
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(422, str(e)) from e
    return job.to_dict()


@router.get("/jobs")
async def list_jobs(limit: int = 50) -> list[dict]:
    return [j.to_dict() for j in get_pipeline().list(limit)]


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = get_pipeline().get(job_id)
    if job is None:
        raise HTTPException(404, f"no job {job_id!r}")
    return job.to_dict()
