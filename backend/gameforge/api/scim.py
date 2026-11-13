from __future__ import annotations
import hmac
import os
from typing import Annotated, Optional, Any, Dict

from core.public_exception_route import PublicExceptionRoute
from fastapi import APIRouter, Header, HTTPException, Depends, Path, Query

from gameforge.enterprise.scim_webhook import ScimWebhookProcessor
from gameforge.enterprise.scim_users import ScimUserDirectory
from gameforge.enterprise.tenancy import TENANT_REGISTRY
from gameforge.enterprise.auth import Principal, get_principal

router = APIRouter(route_class=PublicExceptionRoute, prefix="/scim", tags=["scim"])
processor = ScimWebhookProcessor()
directory = ScimUserDirectory(TENANT_REGISTRY)


def _secret_ok(x_scim_secret: Optional[str]) -> bool:
    expected = os.getenv("GAMEFORGE_SCIM_WEBHOOK_SECRET")
    if expected is None or not expected:
        if x_scim_secret is not None:
            raise HTTPException(status_code=401, detail="Invalid SCIM webhook secret")
        return False
    if x_scim_secret is None:
        return False
    if (
        type(x_scim_secret) is not str
        or len(x_scim_secret) > 512
        or len(expected) > 512
        or not hmac.compare_digest(x_scim_secret, expected)
    ):
        raise HTTPException(status_code=401, detail="Invalid SCIM webhook secret")
    return True


def _authorize_scim_write(x_scim_secret, principal, tenant_id) -> str:
    if _secret_ok(x_scim_secret):
        return "scim-webhook"
    # Only signed webhook integrations may operate across all tenants.
    # A generic admin from one tenant is NOT a superuser in all tenants.
    if not isinstance(tenant_id, str) or not 1 <= len(tenant_id) <= 200:
        raise HTTPException(status_code=403, detail="Explicit SCIM tenant required")
    if principal is None or not isinstance(principal.user_id, str) or not principal.user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        TENANT_REGISTRY.require_access(tenant_id, principal.user_id, "admin")
    except (KeyError, PermissionError):
        raise HTTPException(status_code=403, detail="SCIM tenant admin required") from None
    return principal.user_id

async def get_scim_webhook_principal(
    x_scim_secret: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> Principal:
    """Authenticate machine webhooks by configured secret, without a bearer.

    Other SCIM endpoints retain their standard get_principal dependency. A
    wrong provided secret never silently falls back to developer/user auth.
    """
    if _secret_ok(x_scim_secret):
        return Principal(
            user_id="scim-webhook", roles=["admin"], auth_method="scim_secret"
        )
    return await get_principal(authorization=authorization, x_user_id=x_user_id)


@router.post("/webhook")
async def scim_webhook(
    payload: Dict[str, Any],
    x_scim_secret: Optional[str] = Header(default=None),
    principal: Principal = Depends(get_scim_webhook_principal),
):
    secret_mode = False
    try:
        secret_mode = _secret_ok(x_scim_secret)
    except HTTPException:
        if x_scim_secret is not None:
            raise
    try:
        events = processor.normalize_payload(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid SCIM request") from None
    results = []
    for event in events:
        if not secret_mode:
            if not isinstance(event.tenant_id, str) or not event.tenant_id:
                raise HTTPException(status_code=403, detail="Explicit SCIM tenant required")
            _authorize_scim_write(None, principal, event.tenant_id)
        actor = "scim-webhook" if secret_mode else principal.user_id
        try:
            results.append(await processor.apply(event, actor_user_id=actor))
        except Exception:
            results.append(
                {"op": event.op.value, "user_id": event.user_id, "status": "error", "error": "scim_apply_failed"}
            )
    return {"processed": len(results), "results": results}


@router.get("/Users")
async def scim_list_users(
    startIndex: int = Query(1, ge=1, le=100000),
    count: int = Query(100, ge=1, le=1000),
    filter: Optional[str] = Query(None, max_length=1000),
    tenant_id: Optional[str] = Query(None, min_length=1, max_length=200),
    x_scim_secret: Optional[str] = Header(default=None),
    principal: Principal = Depends(get_principal),
):
    _authorize_scim_write(x_scim_secret, principal, tenant_id)
    return directory.list_users(
        tenant_id=tenant_id, start_index=startIndex, count=count, filter_expr=filter
    )


@router.get("/Users/{user_id}")
async def scim_get_user(
    user_id: Annotated[str, Path(min_length=1, max_length=200)],
    tenant_id: Optional[str] = Query(None, min_length=1, max_length=200),
    x_scim_secret: Optional[str] = Header(default=None),
    principal: Principal = Depends(get_principal),
):
    _authorize_scim_write(x_scim_secret, principal, tenant_id)
    user = directory.get_user(user_id, tenant_id=tenant_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/Users")
async def scim_create_user(
    payload: Dict[str, Any],
    x_scim_secret: Optional[str] = Header(default=None),
    principal: Principal = Depends(get_principal),
):
    if not isinstance(payload.get("tenant_id"), str) or not payload["tenant_id"]:
        raise HTTPException(status_code=422, detail="Explicit tenant_id required")
    actor = _authorize_scim_write(x_scim_secret, principal, payload["tenant_id"])
    try:
        return await directory.create_or_upsert_user(payload, actor=actor)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid SCIM request") from None


@router.patch("/Users/{user_id}")
async def scim_patch_user(
    user_id: Annotated[str, Path(min_length=1, max_length=200)],
    payload: Dict[str, Any],
    x_scim_secret: Optional[str] = Header(default=None),
    principal: Principal = Depends(get_principal),
):
    actor = _authorize_scim_write(x_scim_secret, principal, payload.get("tenant_id"))
    try:
        return await directory.patch_user(user_id, payload, actor=actor)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid SCIM request") from None
