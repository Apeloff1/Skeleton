"""routes/orchestrator.py — AUTONOMOUS ORCHESTRATOR API (Segment 3).

Plan & Execute: turn a natural-language or explicit-step directive into a
BuildPlan DAG, execute it (async), and re-plan from any node.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from routes.galaxy_studio_access import private_build_access
from pydantic import BaseModel

from core import autonomous_orchestrator as orch

router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"], dependencies=[Depends(private_build_access)])


class PlanReq(BaseModel):
    directive: str = ""
    steps: list[dict] | None = None     # explicit JSON/YAML-parsed steps win over NL


@router.post("/{build_id}/plan")
def plan(build_id: str, req: PlanReq):
    return orch.plan_from_directive(build_id, req.directive, steps=req.steps)


@router.get("/plan/{plan_id}")
def get_plan(plan_id: str):
    return orch.get_plan(plan_id) or {"error": "plan_not_found"}


@router.get("/{build_id}/plans")
def list_plans(build_id: str, limit: int = 20):
    return orch.list_plans(build_id, limit=limit)


@router.post("/plan/{plan_id}/execute/async")
def execute_async(plan_id: str):
    return {"job_id": orch.start_execute_job(plan_id), "status": "running"}


@router.post("/job/{job_id}/cancel")
def cancel_job(job_id: str):
    """Cancel only an authenticated, owned orchestration job."""
    return orch.cancel_job(job_id)


@router.get("/job/{job_id}")
def job(job_id: str):
    return orch.get_job(job_id)


class ReplanReq(BaseModel):
    node_id: str


@router.post("/plan/{plan_id}/replan")
def replan(plan_id: str, req: ReplanReq):
    return orch.replan_from(plan_id, req.node_id)
