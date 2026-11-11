"""
build_pipeline.py — Unified API surface for the new binary/vault/tool/interpreter
infrastructure.

Endpoints:
  POST   /api/binary/package         — package a galaxy build into ZIP/APK
  GET    /api/binary/download/{build_id}/{kind}  — streaming download
  GET    /api/binary/artifacts/{build_id}        — list artifacts for a build
  GET    /api/vault/collections                  — list available vault collections
  POST   /api/vault/query                        — query a vault collection / topic
  GET    /api/vault/stats                        — vault statistics
  POST   /api/tools/invoke                       — single tool call
  POST   /api/tools/invoke_many                  — parallel multi-call
  GET    /api/tools/describe                     — schema of available tools
  POST   /api/interpreter/run                    — interpreter run (multi-lang dispatch)
  GET    /api/interpreter/state/{session_id}     — fetch persisted REPL state
  POST   /api/jeeves/consult                     — direct in-process Jeeves query
"""
from __future__ import annotations

from core.public_exception_route import PublicExceptionRoute
import hashlib
import os
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT

from services import binary_builder, vault_loader, tool_registry, jeeves_consultant
from routes import gameforge_auth as auth
from core.exec_guard import code_execution_enabled, execution_disabled_response

router = APIRouter(route_class=PublicExceptionRoute, )

_MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
_DB_NAME = os.environ.get("DB_NAME", "test_database")
_client: AsyncIOMotorClient | None = None


def _db():
    global _client
    if _client is None:
        _client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
    return _client[_DB_NAME]


# ───────────────────────────── BINARY ─────────────────────────────
class PackageReq(BaseModel):
    build_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    kinds: list[Literal["zip", "apk"]] = Field(
        default_factory=lambda: ["zip", "apk"], min_length=1, max_length=2
    )


def _storage_build_id(build_id: str, identity: dict[str, str]) -> str:
    """Bind disk names to an authenticated owner without exposing identities.

    All physically stored packages use this deterministic cryptographic
    namespace, so two tenants using the same build_id cannot share bytes.
    """
    binary_builder._safe_build_id(build_id)
    if not all(identity.get(k) for k in ("tenant_id", "owner_id")):
        raise HTTPException(401, "Authentication required")
    scope = "\x00".join((identity["tenant_id"], identity["owner_id"], build_id))
    return hashlib.sha256(("binary-artifact-v2\x00" + scope).encode("utf-8")).hexdigest()


def _private_build_identity(user: dict, *, mutate: bool = False) -> dict[str, str]:
    identity = auth.require_authenticated_identity(user)
    if mutate and user.get("role") not in {"editor", "admin"}:
        raise HTTPException(403, "Editor authority required")
    return identity


async def _owned_binary_build(build_id: str, identity: dict[str, str]) -> dict:
    """Never treat an unscoped build_id as authorization for its sources."""
    binary_builder._safe_build_id(build_id)
    row = await _db().galaxy_builds.find_one(
        {"build_id": build_id, **identity}, {"_id": 0}
    )
    if (
        not isinstance(row, dict)
        or row.get("build_id") != build_id
        or any(row.get(key) != value for key, value in identity.items())
        or row.get("deleted") is True
        or row.get("revoked") is True
        or row.get("rights_revoked") is True
        or row.get("state") in {"deleted", "revoked", "archived", "withdrawn"}
    ):
        raise HTTPException(404, "Build not found")
    return row


def _public_artifact(artifact: dict, build_id: str) -> dict:
    """Only expose non-sensitive metadata; never return filesystem paths."""
    fields = ("artifact_id", "kind", "size_bytes", "file_count", "sha256",
              "is_installable", "created_at")
    result = {key: artifact[key] for key in fields if key in artifact}
    result["build_id"] = build_id
    if result.get("kind") in {"zip", "apk"}:
        result["download_url"] = f"/api/binary/download/{build_id}/{result['kind']}"
    return result


@router.post("/binary/package")
async def binary_package(req: PackageReq, user=Depends(auth.get_current_user)):
    identity = _private_build_identity(user, mutate=True)
    if not code_execution_enabled():
        return execution_disabled_response("Binary packaging")

    db = _db()
    build = await _owned_binary_build(req.build_id, identity)
    storage_id = _storage_build_id(req.build_id, identity)
    # The owner-specific namespace is the only build ID that reaches the disk.
    out = await binary_builder.package_build(
        {**build, "build_id": storage_id}, kinds=list(dict.fromkeys(req.kinds))
    )
    published = []
    for artifact in out["artifacts"]:
        if artifact.get("kind") not in {"zip", "apk"}:
            continue
        row = {
            **artifact,
            **identity,
            "build_id": req.build_id,
            "storage_build_id": storage_id,
        }
        await db.build_artifacts.update_one(
            {"artifact_id": row["artifact_id"], **identity},
            {"$set": row},
            upsert=True,
        )
        published.append(_public_artifact(row, req.build_id))
    return {"build_id": req.build_id, "artifacts": published, "errors": out["errors"]}


@router.get("/binary/download/{build_id}/{kind}")
async def binary_download(build_id: str, kind: str, user=Depends(auth.get_current_user)):
    identity = _private_build_identity(user)
    if kind not in {"zip", "apk"}:
        raise HTTPException(400, "Invalid artifact kind")
    if (
        not build_id
        or len(build_id) > 128
        or any(not (ch.isascii() and (ch.isalnum() or ch in {"-", "_"})) for ch in build_id)
    ):
        raise HTTPException(400, "Invalid build ID")
    await _owned_binary_build(build_id, identity)
    storage_id = _storage_build_id(build_id, identity)
    document = await _db().build_artifacts.find_one({
        "build_id": build_id, "storage_build_id": storage_id,
        "kind": kind, **identity,
    }, {"_id": 0, "artifact_id": 1})
    if not document:
        raise HTTPException(404, "Artifact not found")
    opened = binary_builder.open_artifact_for_download(storage_id, kind)
    if opened is None:
        raise HTTPException(404, "Artifact not found")
    media = "application/zip" if kind == "zip" else "application/vnd.android.package-archive"

    def _chunks():
        # Byte stream remains pinned to the already-authorized file descriptor.
        try:
            while True:
                chunk = opened.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            opened.close()

    return StreamingResponse(
        _chunks(),
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="galaxy_{build_id}.{kind}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/binary/artifacts/{build_id}")
async def binary_artifacts(build_id: str, user=Depends(auth.get_current_user)):
    identity = _private_build_identity(user)
    await _owned_binary_build(build_id, identity)
    storage_id = _storage_build_id(build_id, identity)
    rows = await _db().build_artifacts.find(
        {"build_id": build_id, "storage_build_id": storage_id, **identity},
        {"_id": 0, "path": 0},
    ).to_list(length=50)
    artifacts = [_public_artifact(row, build_id) for row in rows]
    return {"build_id": build_id, "artifacts": artifacts, "count": len(artifacts)}


# ───────────────────────────── VAULT ─────────────────────────────
@router.get("/vault/collections", dependencies=[Depends(auth.require_authenticated_identity)])
async def vault_collections():
    cols = vault_loader.list_collections()
    return {"collections": cols, "count": len(cols)}


class VaultQueryReq(BaseModel):
    collection: Optional[str] = None
    topic: Optional[str] = None
    limit: int = 10
    contains: Optional[str] = None


@router.post("/vault/query", dependencies=[Depends(auth.require_authenticated_identity)])
async def vault_query(req: VaultQueryReq):
    if req.collection:
        rows = vault_loader.query_collection(req.collection, limit=req.limit, contains=req.contains)
        return {"collection": req.collection, "rows": rows, "count": len(rows)}
    if req.topic:
        matches = vault_loader.query_topic(req.topic, limit=req.limit)
        return {"topic": req.topic, "matches": matches, "collection_count": len(matches)}
    raise HTTPException(400, "specify either 'collection' or 'topic'")


@router.get("/vault/stats", dependencies=[Depends(auth.require_authenticated_identity)])
async def vault_stats():
    return vault_loader.stats()


# ───────────────────────────── TOOLS ─────────────────────────────
class ToolInvokeReq(BaseModel):
    tool: str = Field(min_length=1, max_length=64)
    params: dict = Field(default_factory=dict)


_DENIED_PUBLIC_TOOLS = frozenset({"mongo_query", "package_build"})


def _admit_http_tool(tool: str) -> None:
    # Privileged DB and packaging adapters are internal orchestrator services,
    # not public HTTP capabilities. They lack owner-scoped authority here.
    if tool in _DENIED_PUBLIC_TOOLS:
        raise HTTPException(403, "Tool is not available over HTTP")


@router.post("/tools/invoke", dependencies=[
    Depends(auth.require_authenticated_identity),
    Depends(auth.require_role("editor")),
])
async def tools_invoke(req: ToolInvokeReq):
    _admit_http_tool(req.tool)
    return await tool_registry.invoke(req.tool, req.params)


class ToolMultiReq(BaseModel):
    calls: list[ToolInvokeReq] = Field(min_length=1, max_length=10)


@router.post("/tools/invoke_many", dependencies=[
    Depends(auth.require_authenticated_identity),
    Depends(auth.require_role("editor")),
])
async def tools_invoke_many(req: ToolMultiReq):
    for call in req.calls:
        _admit_http_tool(call.tool)
    payload = [{"tool": c.tool, "params": c.params} for c in req.calls]
    return {"results": await tool_registry.invoke_many(payload)}


@router.get("/tools/describe", dependencies=[Depends(auth.require_authenticated_identity)])
async def tools_describe():
    described = tool_registry.describe()
    # Do not advertise internal-only adapters to public HTTP clients.
    if isinstance(described, dict):
        return {key: value for key, value in described.items()
                if key not in _DENIED_PUBLIC_TOOLS}
    return described


# ───────────────────────────── INTERPRETER ─────────────────────────────
# Persistent REPL state per session_id (Python only — multi-lang
# dispatches to the existing /api/playground/run for those.)
_REPL_STATE: dict[str, dict] = {}


class InterpReq(BaseModel):
    code: str = Field(min_length=1, max_length=200_000)
    language: str = Field(default="python", max_length=16)
    session_id: str = Field(default="default", max_length=128)


@router.post("/interpreter/run", dependencies=[
    Depends(auth.require_authenticated_identity),
    Depends(auth.require_role("editor")),
])
async def interpreter_run(req: InterpReq):
    """Refuse in-process Python execution; arbitrary request code must not reach exec()."""
    if not code_execution_enabled():
        return execution_disabled_response("Interpreter execution")
    if req.language == "python":
        return execution_disabled_response("In-process Python interpreter execution")
    if req.language in ("c", "cpp", "cxx", "go", "rust"):
        return await tool_registry.invoke("compile_code", {"language": req.language, "code": req.code})
    return await tool_registry.invoke("run_code", {"language": req.language, "code": req.code})


@router.get("/interpreter/state/{session_id}", dependencies=[
    Depends(auth.require_authenticated_identity),
])
async def interpreter_state(session_id: str):
    # Legacy REPL execution is disabled and the historical process-wide dict
    # has no per-owner custody. Never reveal another user's old state.
    return {"session_id": session_id[:128], "exists": False}


# ───────────────────────────── JEEVES CONSULT ─────────────────────────────
class ConsultReq(BaseModel):
    context: str = "lesson"
    topic: str = ""


@router.post("/jeeves/consult", dependencies=[Depends(auth.require_authenticated_identity)])
async def jeeves_consult_route(req: ConsultReq):
    return await jeeves_consultant.consult(req.context, topic=req.topic)
