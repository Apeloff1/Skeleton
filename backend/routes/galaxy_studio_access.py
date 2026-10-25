"""Request scoping for the existing Galaxy build and artifact owners.

Role decisions remain with gameforge_auth.require_role. The scope only binds
private Galaxy records to the authenticated tenant and account.
"""
from __future__ import annotations

from contextvars import ContextVar

from fastapi import Depends, HTTPException, Request

from routes.gameforge_auth import get_current_user, require_role


_request_user: ContextVar[dict | None] = ContextVar("galaxy_request_user", default=None)
_PUBLIC_READS = frozenset({
    "/manifest", "/genres", "/capabilities/catalog", "/pipeline/catalog",
    "/datasets/catalog", "/domains", "/agent-db-manifest",
    "/axes", "/axes/stats",
})
_ADMIN_READS = frozenset({"/admin-status", "/workers", "/watchdog/health"})
_INSTALLATION_PREFIXES = ("/admin/", "/eas/", "/swarm/cold/", "/swarm/micro-dbs/")


def record_identity() -> dict:
    user = _request_user.get()
    if user is None or user.get("dev_mode"):
        return {}
    owner = str(user.get("email") or user.get("user_id") or "").strip()
    tenant = str(user.get("tenant_id") or "default").strip()
    if not owner:
        raise HTTPException(401, "Authentication required")
    if not tenant:
        raise HTTPException(403, "Tenant identity is unavailable")
    return {"tenant_id": tenant, "owner_id": owner}


def record_visible(record: dict) -> bool:
    user = _request_user.get()
    scope = record_identity()
    if not scope:
        return True
    tenant = record.get("tenant_id")
    if not tenant:
        # Old unowned installation records remain inspectable only by the
        # installation administrator, never by newly registered consumers.
        return user.get("role") == "admin" and scope["tenant_id"] == "default" and not record.get("owner_id")
    if tenant != scope["tenant_id"]:
        return False
    return user.get("role") == "admin" or record.get("owner_id") == scope["owner_id"]


def record_query() -> dict:
    scope = record_identity()
    if not scope:
        return {}
    user = _request_user.get()
    if user.get("role") != "admin":
        return scope
    if scope["tenant_id"] != "default":
        return {"tenant_id": scope["tenant_id"]}
    return {"$or": [{"tenant_id": "default"}, {"tenant_id": {"$exists": False}, "owner_id": {"$exists": False}}]}


async def visible_build_rows(rows) -> list[dict]:
    """Filter derived mixed-build projections through canonical metadata."""
    from routes.galaxy_studio_state import load_build

    visible = []
    checked = {}
    for row in rows:
        build_id = row.get("build_id") if isinstance(row, dict) else None
        if not isinstance(build_id, str) or not build_id:
            continue
        if build_id not in checked:
            checked[build_id] = await load_build(build_id) is not None
        if checked[build_id]:
            visible.append(row)
    return visible


async def galaxy_request_access(request: Request, user=Depends(get_current_user)):
    relative = request.url.path.removeprefix("/api/galaxy-studio").rstrip("/") or "/"
    read = request.method in {"GET", "HEAD", "OPTIONS"}
    if read and relative in _PUBLIC_READS:
        yield
        return
    installation = relative.startswith(_INSTALLATION_PREFIXES) or relative in _ADMIN_READS
    prepares_artifact = relative.startswith(("/download/", "/download-apk/"))
    minimum = "admin" if installation else "editor" if not read or prepares_artifact else "viewer"
    authenticated = require_role(minimum)(user)
    token = _request_user.set(authenticated)
    try:
        identity = record_identity()
        if installation and identity and identity["tenant_id"] != "default":
            raise HTTPException(403, "Installation administrator authority required")
        build_ids = request.query_params.getlist("build_id")
        if "build_id" in request.path_params:
            build_ids.append(request.path_params["build_id"])
        media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
        is_json = not media_type or media_type == "application/json" or media_type.startswith("application/") and media_type.endswith("+json")
        if not read and relative != "/create" and is_json:
            try:
                body = await request.json()
            except ValueError:
                body = None  # FastAPI reports malformed request bodies.
            if isinstance(body, dict) and "build_id" in body:
                build_ids.append(body["build_id"])
        if build_ids:
            from routes.galaxy_studio_state import load_build

            for build_id in build_ids:
                if not isinstance(build_id, str) or not build_id or await load_build(build_id) is None:
                    raise HTTPException(404, "Build not found")
        vault_id = request.path_params.get("vault_id")
        if vault_id:
            from routes.galaxy_studio_state import get_all_vault_entries

            entries = await get_all_vault_entries()
            if vault_id not in entries or not record_visible(entries[vault_id]):
                raise HTTPException(404, "Vault entry not found")
        yield
    finally:
        _request_user.reset(token)


__all__ = ["galaxy_request_access", "record_identity", "record_query", "record_visible", "visible_build_rows"]
