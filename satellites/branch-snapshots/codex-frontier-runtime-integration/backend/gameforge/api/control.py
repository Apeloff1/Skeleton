from __future__ import annotations
import os
from datetime import datetime
from typing import Any, Dict, Optional, List

from fastapi import FastAPI
from gameforge.api.security_middleware import ZaibatsuSecurityMiddleware
from gameforge.enterprise.zaibatsu_security import SECURITY
from gameforge.enterprise.zaibatsu_appwide import install_appwide_zaibatsu, appwide_status
from pydantic import BaseModel, Field

from gameforge.version import __version__, __codename__, __tracks__
from gameforge.enterprise.auth import Principal, get_principal
from gameforge.enterprise.tenancy import TENANT_REGISTRY, bootstrap_local_tenant, MemberRole
from gameforge.enterprise.quotas import QUOTAS
from gameforge.enterprise.alerts import ALERTS, METRICS
from gameforge.enterprise.slo import SLOS
from gameforge.enterprise.failover import MultiRegionFailoverRunbook
from gameforge.enterprise.oidc_config import load_oidc_settings
from gameforge.enterprise.audit import AUDIT, audit_now
from gameforge.runtime.agent_runtime import AgentRuntime, AgentContext, WorkItem
from gameforge.runtime.generation import StyleAwareGenerator, MockLLMProvider
from gameforge.runtime.room_handlers import RoomHandlerRegistry, ROOM_SPECIALTIES
from gameforge.agents.level_system import AgentLevelSystem
from pathlib import Path
from fastapi.responses import FileResponse, HTMLResponse
from gameforge.api.diaries import router as diaries_router
from gameforge.api.scim import router as scim_router
from gameforge.api.personal_logs import router as logs_router
from gameforge.api.calendar_api import router as calendar_router
from gameforge.api.neuro_api import router as neuro_router
from gameforge.api.decade_logs_api import router as decade_router
from gameforge.api.coherence_api import router as coherence_router
from gameforge.api.math_api import router as math_router
from gameforge.api.exocortex_api import router as exocortex_router
from gameforge.api.security_api import router as security_router
from gameforge.enterprise.queue import WORK_QUEUE

app = FastAPI(title="GameForge", version=__version__)
app.add_middleware(ZaibatsuSecurityMiddleware)
_ZAIBATSU_INSTALL = install_appwide_zaibatsu()
app.include_router(diaries_router)
app.include_router(scim_router)
app.include_router(logs_router)
app.include_router(calendar_router)
app.include_router(neuro_router)
app.include_router(decade_router)
app.include_router(coherence_router)
app.include_router(math_router)
app.include_router(exocortex_router)
app.include_router(security_router)

_COCKPIT = Path(__file__).with_name("cockpit.html")


@app.get("/", response_class=HTMLResponse)
@app.get("/cockpit", response_class=HTMLResponse)
async def cockpit():
    if _COCKPIT.exists():
        return FileResponse(_COCKPIT)
    return HTMLResponse("<h1>GameForge</h1><p>cockpit.html missing</p>")


@app.get("/system/queue")
async def system_queue(principal: Principal = Depends(get_principal)):
    stats = WORK_QUEUE.stats() if hasattr(WORK_QUEUE, "stats") else {}
    return {"queue": stats}


# process-local agent registry
_AGENTS: Dict[str, AgentRuntime] = {}
_LEVELS: Dict[str, AgentLevelSystem] = {}
_ROOMS = RoomHandlerRegistry()
_GENERATOR = StyleAwareGenerator(MockLLMProvider(), ROOM_SPECIALTIES)


def _get_or_spawn(agent_id: str) -> AgentRuntime:
    if agent_id not in _AGENTS:
        ctx = AgentContext(agent_id=agent_id)
        levels = AgentLevelSystem(agent_id)
        _LEVELS[agent_id] = levels

        async def _on_complete(work: WorkItem):
            levels.grant_work_exp(work.room_id, amount=12.0)
            METRICS.inc("work_completed_total")

        rt = AgentRuntime(
            ctx,
            generator=_GENERATOR,
            on_work_complete=_on_complete,
            level_system=levels,
        )
        _AGENTS[agent_id] = rt
    return _AGENTS[agent_id]



class SpawnRequest(BaseModel):
    agent_id: str
    tenant_id: Optional[str] = None


class WorkRequest(BaseModel):
    agent_id: str
    room_id: str
    prompt: str
    priority: int = 50
    tenant_id: Optional[str] = None


@app.get("/health")
async def health():
    return {"ok": True, "version": __version__}


@app.get("/ready")
async def ready():
    return {"ready": True}


@app.get("/system/version")
async def system_version():
    return {
        "version": __version__,
        "codename": __codename__,
        "freeze": True,
        "tracks": __tracks__,
    }


@app.get("/system/auth/config")
async def auth_config(principal: Principal = Depends(get_principal)):
    return load_oidc_settings().as_dict()


@app.get("/system/slos")
async def system_slos(principal: Principal = Depends(get_principal)):
    return {"slos": SLOS.evaluate()}


@app.get("/system/alerts")
async def system_alerts(principal: Principal = Depends(get_principal)):
    return {"alerts": [a.__dict__ for a in ALERTS.evaluate()]}


@app.get("/system/failover/runbook")
async def failover_runbook(principal: Principal = Depends(get_principal)):
    return MultiRegionFailoverRunbook().as_dict()


@app.post("/system/failover/precheck")
async def failover_precheck(principal: Principal = Depends(get_principal)):
    secondary = os.getenv("GAMEFORGE_SECONDARY_BASE_URL")
    result = {
        "primary_ready": True,
        "secondary": None,
        "ts": datetime.utcnow().isoformat(),
    }
    if secondary:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5) as client:
                h = await client.get(f"{secondary.rstrip('/')}/health")
                r = await client.get(f"{secondary.rstrip('/')}/ready")
                result["secondary"] = {
                    "health": h.status_code,
                    "ready": r.status_code,
                    "ok": h.status_code == 200 and r.status_code == 200,
                }
        except Exception as e:
            result["secondary"] = {"ok": False, "error": str(e)}
    return result


@app.get("/system/ops_overview")
async def ops_overview(principal: Principal = Depends(get_principal)):
    return {
        "slos": SLOS.evaluate(),
        "alerts": [a.__dict__ for a in ALERTS.evaluate()],
        "auth": load_oidc_settings().as_dict(),
        "agents": len(_AGENTS),
        "failover": {
            "primary": os.getenv("GAMEFORGE_REGION_PRIMARY", "eu-north-1"),
            "secondary": os.getenv("GAMEFORGE_REGION_SECONDARY", "eu-west-1"),
            "secondary_base": os.getenv("GAMEFORGE_SECONDARY_BASE_URL"),
        },
    }


@app.get("/rooms")
async def list_rooms(principal: Principal = Depends(get_principal)):
    return {"rooms": _ROOMS.list_rooms()}


@app.get("/coders")
async def list_coders_api(principal: Principal = Depends(get_principal)):
    from gameforge.rooms.coder_pool import list_coders as _list

    return {"coders": _list()}


@app.get("/rooms/assignments")
async def room_assignments_api(principal: Principal = Depends(get_principal)):
    from gameforge.rooms.room_assignments import ROOM_ASSIGNMENTS

    return {
        "assignments": {
            k: {
                "room_id": v.room_id,
                "room_name": v.room_name,
                "description": v.description,
                "tier_2": v.tier_2,
                "tier_3": v.tier_3,
                "tier_4": v.tier_4,
                "domain_tags": v.domain_tags,
            }
            for k, v in ROOM_ASSIGNMENTS.items()
        }
    }


from gameforge.enterprise.backup import BackupService
from gameforge.enterprise.backup_scheduler import BackupScheduler

_backup_service = BackupService()
_backup_scheduler = BackupScheduler(_backup_service)


@app.on_event("startup")
async def _startup_jobs():
    import asyncio

    asyncio.create_task(_backup_scheduler.start())


@app.get("/system/backup/status")
async def backup_status(principal: Principal = Depends(get_principal)):
    return _backup_scheduler.status()


@app.post("/system/backup/run")
async def backup_run_now(principal: Principal = Depends(get_principal)):
    result = await _backup_service.create_snapshot(
        label=f"manual-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
    )
    _backup_scheduler.last_result = result
    return result


@app.post("/agents/spawn")
async def spawn_agent(req: SpawnRequest, principal: Principal = Depends(get_principal)):
    if req.tenant_id:
        TENANT_REGISTRY.require_access(req.tenant_id, principal.user_id, "write")
    else:
        bootstrap_local_tenant(principal.user_id)
    rt = _get_or_spawn(req.agent_id)
    await rt.start()
    await AUDIT.emit(
        audit_now(
            tenant_id=req.tenant_id or "local",
            workspace_id="default",
            actor_user_id=principal.user_id,
            action="agent.spawn",
            resource_type="agent",
            resource_id=req.agent_id,
            details={},
        )
    )
    return {"agent_id": req.agent_id, "status": rt.status()}


@app.post("/work")
async def submit_work(req: WorkRequest, principal: Principal = Depends(get_principal)):
    tenant_id = req.tenant_id or "local"
    if req.tenant_id:
        TENANT_REGISTRY.require_access(req.tenant_id, principal.user_id, "write")
    else:
        bootstrap_local_tenant(principal.user_id)

    ok, reason = QUOTAS.check_and_consume_submit(tenant_id)
    if not ok:
        METRICS.inc("quota_blocked_total")
        raise HTTPException(status_code=429, detail=reason)

    rt = _get_or_spawn(req.agent_id)
    await rt.start()
    work = WorkItem.create(req.agent_id, req.room_id, req.prompt, req.priority)
    rt.enqueue(work)
    METRICS.inc("work_submitted_total")
    await AUDIT.emit(
        audit_now(
            tenant_id=tenant_id,
            workspace_id="default",
            actor_user_id=principal.user_id,
            action="work.submit",
            resource_type="work",
            resource_id=work.work_id,
            details={"room_id": req.room_id, "agent_id": req.agent_id},
        )
    )
    return {"work_id": work.work_id, "status": work.status, "agent": rt.status()}


@app.get("/agents/{agent_id}/status")
async def agent_status(agent_id: str, principal: Principal = Depends(get_principal)):
    rt = _AGENTS.get(agent_id)
    if not rt:
        raise HTTPException(status_code=404, detail="agent not found")
    levels = _LEVELS.get(agent_id)
    return {
        "status": rt.status(),
        "levels": levels.snapshot() if levels else {},
        "recent": [
            {
                "work_id": w.work_id,
                "room_id": w.room_id,
                "status": w.status,
                "completed_at": w.completed_at,
            }
            for w in rt.history[-10:]
        ],
    }


@app.get("/metrics")
async def metrics_json(principal: Principal = Depends(get_principal)):
    return METRICS.snapshot()


from gameforge.enterprise.compliance import ComplianceExportService
from gameforge.enterprise.access_review import AccessReviewService
from pydantic import BaseModel as _BaseModel

_compliance = ComplianceExportService()
_access_review = AccessReviewService()


@app.get("/tenants/{tenant_id}/access-review")
async def access_review_report(
    tenant_id: str,
    lookback_days: int = 30,
    principal: Principal = Depends(get_principal),
):
    tenant = TENANT_REGISTRY.require_access(tenant_id, principal.user_id, "admin")
    return await _access_review.build_report(tenant, lookback_days=lookback_days)


class AccessReviewAttestation(_BaseModel):
    notes: str | None = None


@app.post("/tenants/{tenant_id}/access-review/attest")
async def attest_access_review(
    tenant_id: str,
    req: AccessReviewAttestation,
    principal: Principal = Depends(get_principal),
):
    tenant = TENANT_REGISTRY.require_access(tenant_id, principal.user_id, "admin")
    await AUDIT.emit(
        audit_now(
            tenant_id=tenant_id,
            workspace_id=next(iter(tenant.workspaces.keys())),
            actor_user_id=principal.user_id,
            action="access_review.attest",
            resource_type="tenant",
            resource_id=tenant_id,
            details={"notes": req.notes or ""},
        )
    )
    return {
        "tenant_id": tenant_id,
        "reviewer_user_id": principal.user_id,
        "reviewed_at": datetime.utcnow().isoformat(),
        "notes": req.notes,
        "status": "attested",
    }


@app.post("/tenants/{tenant_id}/compliance/export")
async def export_compliance_pack(
    tenant_id: str,
    principal: Principal = Depends(get_principal),
):
    tenant = TENANT_REGISTRY.require_access(tenant_id, principal.user_id, "admin")
    snapshot = {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "status": tenant.status.value,
        "members": {u: r.value for u, r in tenant.members.items()},
        "workspaces": list(tenant.workspaces.keys()),
    }
    pack = await _compliance.build_tenant_pack(
        tenant_id,
        tenant_snapshot=snapshot,
        tenant_obj=tenant,
    )
    await AUDIT.emit(
        audit_now(
            tenant_id=tenant_id,
            workspace_id="system",
            actor_user_id=principal.user_id,
            action="compliance.export",
            resource_type="tenant",
            resource_id=tenant_id,
            details={"path": pack.get("export_path"), "sha256": pack.get("meta", {}).get("sha256")},
        )
    )
    return pack

