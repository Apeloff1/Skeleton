"""Request scoping for the existing Galaxy build and artifact owners.

Role decisions remain with gameforge_auth.require_role. The scope only binds
private Galaxy records to the authenticated tenant and account.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

from fastapi import Depends, HTTPException, Request

from routes.gameforge_auth import get_current_user, require_role, require_authenticated_identity, ROLE_RANK


_request_user: ContextVar[dict | None] = ContextVar("galaxy_request_user", default=None)
_work_principal: ContextVar[dict | None] = ContextVar("galaxy_work_principal", default=None)
_work_cancelled: ContextVar[object | None] = ContextVar("galaxy_work_cancelled", default=None)
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


def private_identity(*, mutation: bool = False) -> dict:
    """Exact account scope for indirect build consumers, including local mode.

    Existing Galaxy administrator visibility remains unchanged. Churn and
    orchestration can dispatch private source and therefore require ownership.
    """
    user = _request_user.get()
    captured = _work_principal.get()
    if captured is not None:
        from routes.gameforge_auth import _users

        expected = require_authenticated_identity(captured)
        account = ({"email": captured["email"]} if captured.get("email")
                   else {"user_id": captured.get("user_id")})
        try:
            user = _users().find_one({**account, "disabled": {"$ne": True}},
                                     {"_id": 0, "password_hash": 0})
        except Exception:
            raise HTTPException(503, "Account authority unavailable") from None
        if not user or require_authenticated_identity(user) != expected:
            raise HTTPException(403, "Account authority changed")
        _request_user.set(user)
    identity = require_authenticated_identity(user)
    minimum = "editor" if mutation or captured is not None else "viewer"
    if ROLE_RANK.get(user.get("role"), -1) < ROLE_RANK[minimum]:
        raise HTTPException(403, f"Requires role >= {minimum}")
    check = _work_cancelled.get()
    if check is not None and check():
        raise HTTPException(409, "Work cancelled")
    return identity


def capture_private_principal() -> dict:
    private_identity(mutation=True)
    user = _request_user.get()
    return {key: user[key] for key in ("email", "user_id", "tenant_id", "role") if key in user}


@contextmanager
def private_work_scope(principal: dict, cancelled=None):
    """Carry server identity into a raw thread, revalidating before each access."""
    user_token = _request_user.set(dict(principal))
    work_token = _work_principal.set(dict(principal))
    cancel_token = _work_cancelled.set(cancelled)
    try:
        private_identity(mutation=True)
        yield
    finally:
        _work_cancelled.reset(cancel_token)
        _work_principal.reset(work_token)
        _request_user.reset(user_token)


def require_owned_build(build_id: str, *, mutation: bool = False) -> dict:
    """Read canonical Galaxy metadata through its existing cache/Mongo owner.

    Derived gamefiles, plans, runs, jobs and client-supplied ownership never
    establish authority. Missing or unowned historical metadata fails closed.
    """
    identity = private_identity(mutation=mutation)
    if not isinstance(build_id, str) or not build_id:
        raise HTTPException(404, "Build not found")
    from routes.galaxy_studio_state import _builds

    build = _builds.get(build_id)
    if build is None:
        from core.databases import get_sync_db

        try:
            build = get_sync_db()["galaxy_builds"].find_one(
                {"build_id": build_id, **identity}, {"_id": 0, "build_id": 1, "owner_id": 1, "tenant_id": 1})
        except Exception:
            raise HTTPException(503, "Build authority unavailable") from None
    if not build or build.get("build_id") != build_id or any(build.get(key) != value for key, value in identity.items()):
        raise HTTPException(404, "Build not found")
    return identity


async def private_build_access(request: Request, user=Depends(get_current_user)):
    """Admission shared by independently mounted churn/orchestrator routers."""
    if request.method in {"GET", "HEAD", "OPTIONS"} and request.url.path.rstrip("/") == "/api/churn/models":
        yield
        return
    require_authenticated_identity(user)
    token = _request_user.set(user)
    try:
        mutation = request.method not in {"GET", "HEAD", "OPTIONS"}
        private_identity(mutation=mutation)
        build_id = request.path_params.get("build_id")
        if build_id:
            # Synchronous metadata lookups stay off the ASGI event loop.
            from starlette.concurrency import run_in_threadpool

            await run_in_threadpool(require_owned_build, build_id, mutation=mutation)
        yield
    finally:
        _request_user.reset(token)


async def galaxy_request_access(request: Request, user=Depends(get_current_user)):
    relative = request.url.path.removeprefix("/api/galaxy-studio").rstrip("/") or "/"
    read = request.method in {"GET", "HEAD", "OPTIONS"}
    if read and relative in _PUBLIC_READS:
        yield
        return
    installation = relative.startswith(_INSTALLATION_PREFIXES) or relative in _ADMIN_READS
    prepares_artifact = relative.startswith(("/download/", "/download-apk/"))
    minimum = "admin" if installation else "editor" if not read or prepares_artifact else "viewer"
    # Private Galaxy routes require a real account even when the rest of the
    # developer installation has relaxed authentication. Never admit the
    # synthetic dev_mode administrator to private build or artifact data.
    require_authenticated_identity(user)
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


__all__ = ["galaxy_request_access", "record_identity", "record_query", "record_visible", "visible_build_rows",
           "private_build_access", "private_identity", "capture_private_principal", "private_work_scope", "require_owned_build"]
