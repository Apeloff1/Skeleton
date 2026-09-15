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

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from gameforge.workflow.autonomous_workflow import autonomous_workflow
from gameforge.workflow.jeeves_vault import jeeves_vault
from gameforge.workflow.project_orchestrator import create_project_orchestrator
from gameforge.workflow.workflow_persistence import workflow_persistence

router = APIRouter(prefix="/api/gameforge/workflow", tags=["gameforge-workflow"])


# ── models ────────────────────────────────────────────────────────────
class RunRequest(BaseModel):
    prompt: str = Field(..., min_length=3)
    project_name: str = "GameForgeProject"
    max_iterations: int = 4


class ResumeRequest(BaseModel):
    project_name: str


class ProjectRequest(BaseModel):
    prompt: str = Field(..., min_length=3)
    project_name: str = "GameForgeProject"
    time_budget_months: int = 6
    iterations_per_phase: int = 2


# ── autonomous workflow ────────────────────────────────────────────────
@router.post("/run")
async def run_workflow(req: RunRequest):
    """Run the full autonomous pipeline and (when quality allows) deploy a
    packaged build to the JeevesVault."""
    try:
        result = autonomous_workflow.run(req.project_name, req.prompt, req.max_iterations)
        return {"ok": True, **result}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"workflow_failed: {type(e).__name__}: {e}")


@router.post("/resume")
async def resume_workflow(req: ResumeRequest):
    """Resume the latest in-flight workflow for a project (if any)."""
    result = autonomous_workflow.resume(req.project_name)
    if result is None:
        raise HTTPException(status_code=404, detail="no_resumable_state")
    return {"ok": True, **result}


@router.post("/project")
async def run_project(req: ProjectRequest):
    """Long-horizon full-game creation via the ProjectOrchestrator."""
    try:
        orch = create_project_orchestrator(req.project_name)
        result = orch.create_full_game(
            req.prompt,
            time_budget_months=req.time_budget_months,
            iterations_per_phase=req.iterations_per_phase,
        )
        return {"ok": True, **result}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"project_failed: {type(e).__name__}: {e}")


# ── history + status ────────────────────────────────────────────────────
@router.get("/runs")
async def list_runs(project_name: Optional[str] = None, limit: int = Query(25, ge=1, le=100)):
    return {"ok": True, "runs": workflow_persistence.list_runs(project_name, limit)}


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    run = workflow_persistence.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    return {"ok": True, "run": run}


@router.get("/status")
async def status():
    runs = workflow_persistence.list_runs(limit=1)
    last = runs[0] if runs else None
    summary = None
    if last:
        summary = {
            "run_id": last.get("run_id"),
            "project_name": last.get("project_name"),
            "final_quality": last.get("final_quality") or last.get("execution", {}).get("overall_quality"),
            "deploy_ready": last.get("deploy_ready"),
            "iterations_run": last.get("iterations_run"),
            "completed_at": last.get("completed_at"),
        }
    return {"ok": True, "last_run": summary, "vault": jeeves_vault.stats()}


# ── JeevesVault delivery ────────────────────────────────────────────────
@router.get("/vault")
async def vault_list(project_name: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    return {"ok": True, "packages": jeeves_vault.list_packages(project_name, limit)}


@router.get("/vault/search")
async def vault_search(q: str = Query(..., min_length=1), limit: int = Query(50, ge=1, le=200)):
    return {"ok": True, "packages": jeeves_vault.search(q, limit)}


@router.get("/vault/stats")
async def vault_stats():
    return {"ok": True, **jeeves_vault.stats()}


@router.get("/vault/{package_id}")
async def vault_get(package_id: str):
    pkg = jeeves_vault.get(package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="package_not_found")
    return {"ok": True, "package": pkg}


@router.get("/vault/{package_id}/download")
async def vault_download(package_id: str, token: Optional[str] = None):
    """Return the package bytes (base64) + install instructions. Increments the
    download counter and enforces expiry / download limits."""
    res = jeeves_vault.get_download(package_id, token)
    if not res.get("ok"):
        code = 404 if res.get("error") in ("package_not_found", "package_bytes_missing") else 403
        raise HTTPException(status_code=code, detail=res.get("error", "download_failed"))
    return res


@router.delete("/vault/{package_id}")
async def vault_delete(package_id: str):
    if not jeeves_vault.delete(package_id):
        raise HTTPException(status_code=404, detail="package_not_found")
    return {"ok": True, "deleted": package_id}


@router.post("/vault/cleanup")
async def vault_cleanup():
    return {"ok": True, "removed": jeeves_vault.cleanup_expired()}
