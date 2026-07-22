from __future__ import annotations
import os
from typing import Optional, Any, Dict

from fastapi import APIRouter, Header, HTTPException, Depends

from gameforge.enterprise.scim_webhook import ScimWebhookProcessor
from gameforge.enterprise.scim_users import ScimUserDirectory
from gameforge.enterprise.tenancy import TENANT_REGISTRY
from gameforge.enterprise.auth import Principal, get_principal

router = APIRouter(prefix="/scim", tags=["scim"])
processor = ScimWebhookProcessor()
directory = ScimUserDirectory(TENANT_REGISTRY)


def _secret_ok(x_scim_secret: Optional[str]) -> bool:
    expected = os.getenv("GAMEFORGE_SCIM_WEBHOOK_SECRET")
    if not expected:
        return False
    if x_scim_secret != expected:
        raise HTTPException(status_code=401, detail="Invalid SCIM webhook secret")
    return True


def _authorize_scim_write(x_scim_secret, principal, tenant_id) -> str:
    try:
        if _secret_ok(x_scim_secret):
            return "scim-webhook"
    except HTTPException:
        if x_scim_secret is not None:
            raise
    if tenant_id:
        TENANT_REGISTRY.require_access(tenant_id, principal.user_id, "admin")
    else:
        if not any(t.can(principal.user_id, "admin") for t in TENANT_REGISTRY.tenants.values()):
            # allow in dev when local tenant
            from gameforge.enterprise.tenancy import bootstrap_local_tenant

            bootstrap_local_tenant(principal.user_id)
    return principal.user_id


@router.post("/webhook")
async def scim_webhook(
    payload: Dict[str, Any],
    x_scim_secret: Optional[str] = Header(default=None),
    principal: Principal = Depends(get_principal),
):
    secret_mode = False
    try:
        secret_mode = _secret_ok(x_scim_secret)
    except HTTPException:
        if x_scim_secret is not None:
            raise
    try:
        events = processor.normalize_payload(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    results = []
    for event in events:
        if not secret_mode and event.tenant_id:
            TENANT_REGISTRY.require_access(event.tenant_id, principal.user_id, "admin")
        actor = "scim-webhook" if secret_mode else principal.user_id
        try:
            results.append(await processor.apply(event, actor_user_id=actor))
        except Exception as e:
            results.append(
                {"op": event.op.value, "user_id": event.user_id, "status": "error", "error": str(e)}
            )
    return {"processed": len(results), "results": results}


@router.get("/Users")
async def scim_list_users(
    startIndex: int = 1,
    count: int = 100,
    filter: Optional[str] = None,
    tenant_id: Optional[str] = None,
    x_scim_secret: Optional[str] = Header(default=None),
    principal: Principal = Depends(get_principal),
):
    _authorize_scim_write(x_scim_secret, principal, tenant_id)
    return directory.list_users(
        tenant_id=tenant_id, start_index=startIndex, count=count, filter_expr=filter
    )


@router.get("/Users/{user_id}")
async def scim_get_user(
    user_id: str,
    x_scim_secret: Optional[str] = Header(default=None),
    principal: Principal = Depends(get_principal),
):
    _authorize_scim_write(x_scim_secret, principal, None)
    user = directory.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/Users")
async def scim_create_user(
    payload: Dict[str, Any],
    x_scim_secret: Optional[str] = Header(default=None),
    principal: Principal = Depends(get_principal),
):
    actor = _authorize_scim_write(x_scim_secret, principal, payload.get("tenant_id"))
    try:
        return await directory.create_or_upsert_user(payload, actor=actor)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/Users/{user_id}")
async def scim_patch_user(
    user_id: str,
    payload: Dict[str, Any],
    x_scim_secret: Optional[str] = Header(default=None),
    principal: Principal = Depends(get_principal),
):
    actor = _authorize_scim_write(x_scim_secret, principal, payload.get("tenant_id"))
    try:
        return await directory.patch_user(user_id, payload, actor=actor)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
