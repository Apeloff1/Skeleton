"""
routes/gameforge_workflow.py — Autonomous Game-Dev Workflow API
(/api/gameforge/workflow).

Surfaces the Cowabunga v4 autonomous pipeline:
  • run / resume the Prompt→…→Deployment workflow
  • long-horizon ProjectOrchestrator (multi-phase full-game creation)
  • JeevesVault delivery: list / search / stats / download / delete

Runs are synchronous and fast (deterministic scoring, no sleeps). All state
is Mongo-persisted so history + resume survive restarts and forks.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from core.exec_guard import code_execution_enabled, execution_disabled_response
from core.http_errors import internal_http_error
from gameforge.workflow.autonomous_workflow import autonomous_workflow
from gameforge.workflow.jeeves_vault import jeeves_vault
from gameforge.workflow.project_orchestrator import create_project_orchestrator
from gameforge.workflow.workflow_persistence import workflow_persistence
from gameforge.workflow.delivery_scope import scope_for_user, use_scope
from routes.gameforge_auth import get_current_user, require_role

router = APIRouter(prefix="/api/gameforge/workflow", tags=["gameforge-workflow"])
_viewer = require_role("viewer")
_editor = require_role("editor")


def _scope(user):
    scope = scope_for_user(user)
    if scope is None:
        raise HTTPException(401, "workflow_identity_required")
    return scope


# ── models ────────────────────────────────────────────────────────────
class RunRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=16384)
    project_name: str = Field("GameForgeProject", min_length=1, max_length=120)
    max_iterations: int = 4


class ResumeRequest(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=120)


class ProjectRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=16384)
    project_name: str = Field("GameForgeProject", min_length=1, max_length=120)
    time_budget_months: int = 6
    iterations_per_phase: int = 2


# ── autonomous workflow ────────────────────────────────────────────────
@router.post("/run")
def run_workflow(req: RunRequest, response: Response, user=Depends(_editor)):
    """Run the full autonomous pipeline and (when quality allows) deploy a
    packaged build to the JeevesVault."""
    if not code_execution_enabled():
        return execution_disabled_response("GameForge workflow execution")

    try:
        with use_scope(_scope(user)):
            result = autonomous_workflow.run(req.project_name, req.prompt, req.max_iterations)
        response.headers["Cache-Control"] = "no-store"
        return {"ok": True, **result}
    except Exception as e:  # noqa: BLE001
        raise internal_http_error("workflow_failed", e) from None


@router.post("/resume")
def resume_workflow(req: ResumeRequest, response: Response, user=Depends(_editor)):
    """Resume the latest in-flight workflow for a project (if any)."""
    if not code_execution_enabled():
        return execution_disabled_response("GameForge workflow execution")

    with use_scope(_scope(user)):
        result = autonomous_workflow.resume(req.project_name)
    response.headers["Cache-Control"] = "no-store"
    if result is None:
        raise HTTPException(status_code=404, detail="no_resumable_state")
    return {"ok": True, **result}


@router.post("/project")
def run_project(req: ProjectRequest, response: Response, user=Depends(_editor)):
    """Long-horizon full-game creation via the ProjectOrchestrator."""
    if not code_execution_enabled():
        return execution_disabled_response("GameForge project execution")

    try:
        with use_scope(_scope(user)):
            orch = create_project_orchestrator(req.project_name)
            result = orch.create_full_game(
                req.prompt, time_budget_months=req.time_budget_months,
                iterations_per_phase=req.iterations_per_phase,
            )
        response.headers["Cache-Control"] = "no-store"
        return {"ok": True, **result}
    except Exception as e:  # noqa: BLE001
        raise internal_http_error("project_failed", e) from None


# ── history + status ────────────────────────────────────────────────────
@router.get("/runs")
def list_runs(project_name: Optional[str] = None, limit: int = Query(25, ge=1, le=100), user=Depends(_viewer)):
    with use_scope(_scope(user)):
        return {"ok": True, "runs": workflow_persistence.list_runs(project_name, limit)}


@router.get("/runs/{run_id}")
def get_run(run_id: str, user=Depends(_viewer)):
    with use_scope(_scope(user)):
        run = workflow_persistence.get_run(run_id)
    if not run:
        raise HTTPException(404, "run_not_found")
    return {"ok": True, "run": run}


@router.get("/status")
def status(user=Depends(_viewer)):
    with use_scope(_scope(user)):
        runs = workflow_persistence.list_runs(limit=1)
        vault_stats = jeeves_vault.stats()
    last = runs[0] if runs else {}
    summary = {key: last.get(key) for key in (
        "run_id", "project_name", "final_quality", "deploy_ready",
        "iterations_run", "completed_at", "release_qualified"
    )} if last else None
    return {"ok": True, "last_run": summary, "vault": vault_stats}


@router.get("/vault")
def vault_list(project_name: Optional[str] = None, limit: int = Query(50, ge=1, le=200), user=Depends(_viewer)):
    with use_scope(_scope(user)):
        return {"ok": True, "packages": jeeves_vault.list_packages(project_name, limit)}


@router.get("/vault/search")
def vault_search(q: str = Query(..., min_length=1, max_length=256),
                 limit: int = Query(50, ge=1, le=200), user=Depends(_viewer)):
    with use_scope(_scope(user)):
        return {"ok": True, "packages": jeeves_vault.search(q, limit)}


@router.get("/vault/stats")
def vault_stats(user=Depends(_viewer)):
    with use_scope(_scope(user)):
        return {"ok": True, **jeeves_vault.stats()}


@router.get("/vault/{package_id}")
def vault_get(package_id: str, user=Depends(_viewer)):
    with use_scope(_scope(user)):
        pkg = jeeves_vault.get(package_id)
    if not pkg:
        raise HTTPException(404, "package_not_found")
    return {"ok": True, "package": pkg}


@router.get("/vault/{package_id}/download")
def vault_download(package_id: str, response: Response,
                   token: Optional[str] = Query(None, max_length=128),
                   share_token: Optional[str] = Header(None, alias="X-Jeeves-Download-Token"),
                   user=Depends(get_current_user)):
    """Authenticated owner or explicit bearer capability; no ambient global access."""
    if share_token is not None and token is not None and share_token != token:
        raise HTTPException(403, "package_unavailable")
    credential = share_token if share_token is not None else token
    result = jeeves_vault.get_download(package_id, credential, scope=scope_for_user(user))
    if not result.get("ok"):
        raise HTTPException(403, "package_unavailable", headers={"Cache-Control": "no-store"})
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return result


@router.post("/vault/{package_id}/rotate-token")
def vault_rotate_token(package_id: str, response: Response, user=Depends(_editor)):
    with use_scope(_scope(user)):
        token = jeeves_vault.rotate_token(package_id)
    if token is None:
        raise HTTPException(404, "package_not_found")
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True, "download_token": token}


@router.delete("/vault/{package_id}")
def vault_delete(package_id: str, user=Depends(_editor)):
    with use_scope(_scope(user)):
        deleted = jeeves_vault.delete(package_id)
    if not deleted:
        raise HTTPException(404, "package_not_found")
    return {"ok": True, "deleted": package_id}


@router.post("/vault/cleanup")
def vault_cleanup(user=Depends(_editor)):
    with use_scope(_scope(user)):
        return {"ok": True, "removed": jeeves_vault.cleanup_expired()}
