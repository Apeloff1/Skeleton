from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from gameforge.enterprise.auth import Principal, get_principal
from gameforge.enterprise.tenancy import bootstrap_local_tenant, TENANT_REGISTRY
from gameforge.enterprise.audit import AUDIT, audit_now
from gameforge.personal.diaries.base import DiaryKind
from gameforge.personal.diaries.service import DiaryService

router = APIRouter(prefix="/diaries", tags=["diaries"])
_DIARY_SERVICES: Dict[str, DiaryService] = {}


async def _service(
    principal: Principal,
    tenant_id: Optional[str],
    workspace_id: Optional[str],
    action: str = "write",
) -> tuple[DiaryService, str, str]:
    if tenant_id:
        tenant = TENANT_REGISTRY.require_access(tenant_id, principal.user_id, "read" if action == "read" else "write")
    else:
        tenant = bootstrap_local_tenant(principal.user_id)
    ws = workspace_id or next(iter(tenant.workspaces.keys()))
    key = f"{tenant.tenant_id}:{ws}:{principal.user_id}"
    svc = _DIARY_SERVICES.get(key)
    if svc is None:
        svc = DiaryService(
            user_id=principal.user_id,
            tenant_id=tenant.tenant_id,
            workspace_id=ws,
        )
        await svc.initialize()
        _DIARY_SERVICES[key] = svc
    return svc, tenant.tenant_id, ws


class DiaryWriteRequest(BaseModel):
    kind: str = Field(description="memory|introspect|outrospect|retrospect")
    title: str
    body: str
    tags: List[str] = []
    mood: Optional[float] = None
    intensity: Optional[float] = None
    metadata: Dict[str, Any] = {}
    tenant_id: Optional[str] = None
    workspace_id: Optional[str] = None


def _kind(value: str) -> DiaryKind:
    try:
        return DiaryKind(value.lower())
    except Exception:
        raise HTTPException(status_code=400, detail="kind must be memory|introspect|outrospect|retrospect")


def _entry_json(e) -> Dict[str, Any]:
    return {
        "entry_id": e.entry_id,
        "kind": e.kind.value,
        "title": e.title,
        "body": e.body,
        "tags": e.tags,
        "mood": e.mood,
        "intensity": e.intensity,
        "metadata": e.metadata,
        "source": e.source,
        "created_at": e.created_at.isoformat(),
    }


@router.post("/entries")
async def write_entry(req: DiaryWriteRequest, principal: Principal = Depends(get_principal)):
    svc, tenant_id, ws = await _service(principal, req.tenant_id, req.workspace_id, "write")
    kind = _kind(req.kind)
    entry = await svc.add(
        kind,
        req.title,
        req.body,
        tags=req.tags,
        mood=req.mood,
        intensity=req.intensity,
        metadata=req.metadata,
        source="user",
    )
    await AUDIT.emit(
        audit_now(
            tenant_id=tenant_id,
            workspace_id=ws,
            actor_user_id=principal.user_id,
            action="diary.write",
            resource_type="diary_entry",
            resource_id=entry.entry_id,
            details={"kind": kind.value},
        )
    )
    return _entry_json(entry)


@router.get("/entries")
async def list_entries(
    kind: Optional[str] = None,
    limit: int = 50,
    tenant_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    principal: Principal = Depends(get_principal),
):
    svc, tid, ws = await _service(principal, tenant_id, workspace_id, "read")
    k = _kind(kind) if kind else None
    if svc.store is None:
        diary = svc.get(k) if k else svc.memory
        entries = diary.recent(limit)
    elif k:
        entries = await svc.store.list_entries(
            tenant_id=tid, user_id=principal.user_id, kind=k, limit=limit
        )
    else:
        entries = []
        for kk in DiaryKind:
            entries.extend(
                await svc.store.list_entries(
                    tenant_id=tid, user_id=principal.user_id, kind=kk, limit=limit
                )
            )
        entries.sort(key=lambda e: e.created_at, reverse=True)
        entries = entries[:limit]
    return {"tenant_id": tid, "workspace_id": ws, "entries": [_entry_json(e) for e in entries]}


@router.get("/context")
async def diary_context(
    n: int = 5,
    tenant_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    principal: Principal = Depends(get_principal),
):
    svc, tid, ws = await _service(principal, tenant_id, workspace_id, "read")
    return {
        "tenant_id": tid,
        "workspace_id": ws,
        "context": svc.export_all_context(n=n),
        "mood": svc.mood_dashboard(),
    }


@router.get("/mood")
async def mood_dashboard(
    tenant_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    principal: Principal = Depends(get_principal),
):
    svc, tid, ws = await _service(principal, tenant_id, workspace_id, "read")
    return {"tenant_id": tid, "workspace_id": ws, "mood": svc.mood_dashboard()}
