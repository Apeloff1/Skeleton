"""Integrity diagnostics for swarm runtime invariants."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_invariants import audit
from skeleton.agents.swarm_runtime import SwarmRuntime

router = APIRouter(prefix="/swarm/integrity", tags=["swarm-integrity"])


def _runtime() -> SwarmRuntime:
    from skeleton.api.server import get_state
    state = get_state()
    if state.swarm is None:
        state.swarm = HardenedSwarmRuntime()
    return state.swarm


@router.get("/audit")
def audit_runtime(runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    return asdict(audit(runtime))


@router.get("/assert")
def assert_runtime(runtime: SwarmRuntime = Depends(_runtime)) -> dict[str, Any]:
    report = audit(runtime)
    if not report.ok:
        raise HTTPException(status_code=503, detail={"errors": list(report.errors)})
    return {"ok": True, "task_count": report.task_count, "worker_count": report.worker_count}
