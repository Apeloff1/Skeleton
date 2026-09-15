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
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Any, Optional
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT

from services import binary_builder, vault_loader, tool_registry, jeeves_consultant

router = APIRouter()

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
    build_id: str
    kinds: list[str] = ["zip", "apk"]


@router.post("/binary/package")
async def binary_package(req: PackageReq):
    db = _db()
    build = await db.galaxy_builds.find_one({"build_id": req.build_id}, {"_id": 0})
    if not build:
        raise HTTPException(404, f"build_id not found: {req.build_id}")
    out = await binary_builder.package_build(build, kinds=req.kinds)
    # Persist
    for art in out["artifacts"]:
        await db.build_artifacts.update_one(
            {"artifact_id": art["artifact_id"]}, {"$set": art}, upsert=True,
        )
    return {"build_id": req.build_id, **out}


@router.get("/binary/download/{build_id}/{kind}")
async def binary_download(build_id: str, kind: str):
    if kind not in ("zip", "apk"):
        raise HTTPException(400, "kind must be 'zip' or 'apk'")
    path = binary_builder.find_artifact_path(build_id, kind)
    if not path:
        raise HTTPException(404, f"artifact not found — call /api/binary/package first")
    media = "application/zip" if kind == "zip" else "application/vnd.android.package-archive"
    return FileResponse(str(path), media_type=media, filename=f"galaxy_{build_id}.{kind}")


@router.get("/binary/artifacts/{build_id}")
async def binary_artifacts(build_id: str):
    db = _db()
    arts = await db.build_artifacts.find({"build_id": build_id}, {"_id": 0}).to_list(length=50)
    return {"build_id": build_id, "artifacts": arts, "count": len(arts)}


# ───────────────────────────── VAULT ─────────────────────────────
@router.get("/vault/collections")
async def vault_collections():
    cols = vault_loader.list_collections()
    return {"collections": cols, "count": len(cols)}


class VaultQueryReq(BaseModel):
    collection: Optional[str] = None
    topic: Optional[str] = None
    limit: int = 10
    contains: Optional[str] = None


@router.post("/vault/query")
async def vault_query(req: VaultQueryReq):
    if req.collection:
        rows = vault_loader.query_collection(req.collection, limit=req.limit, contains=req.contains)
        return {"collection": req.collection, "rows": rows, "count": len(rows)}
    if req.topic:
        matches = vault_loader.query_topic(req.topic, limit=req.limit)
        return {"topic": req.topic, "matches": matches, "collection_count": len(matches)}
    raise HTTPException(400, "specify either 'collection' or 'topic'")


@router.get("/vault/stats")
async def vault_stats():
    return vault_loader.stats()


# ───────────────────────────── TOOLS ─────────────────────────────
class ToolInvokeReq(BaseModel):
    tool: str
    params: dict = {}


@router.post("/tools/invoke")
async def tools_invoke(req: ToolInvokeReq):
    return await tool_registry.invoke(req.tool, req.params)


class ToolMultiReq(BaseModel):
    calls: list[ToolInvokeReq]


@router.post("/tools/invoke_many")
async def tools_invoke_many(req: ToolMultiReq):
    payload = [{"tool": c.tool, "params": c.params} for c in req.calls]
    return {"results": await tool_registry.invoke_many(payload)}


@router.get("/tools/describe")
async def tools_describe():
    return tool_registry.describe()


# ───────────────────────────── INTERPRETER ─────────────────────────────
# Persistent REPL state per session_id (Python only — multi-lang
# dispatches to the existing /api/playground/run for those.)
_REPL_STATE: dict[str, dict] = {}


class InterpReq(BaseModel):
    code: str
    language: str = "python"
    session_id: str = "default"


@router.post("/interpreter/run")
async def interpreter_run(req: InterpReq):
    if req.language != "python":
        # Forward via the tool registry (which spawns subprocesses for compiled
        # langs and uses the playground for the rest).
        if req.language in ("c", "cpp", "cxx", "go", "rust"):
            return await tool_registry.invoke("compile_code", {"language": req.language, "code": req.code})
        return await tool_registry.invoke("run_code", {"language": req.language, "code": req.code})

    # Python — persistent globals/locals per session
    import io, contextlib
    state = _REPL_STATE.setdefault(req.session_id, {"globals": {"__name__": "__interp__"}, "history": []})
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            exec(compile(req.code, "<interp>", "exec"), state["globals"])
        state["history"].append({"code": req.code, "ok": True})
        return {
            "ok": True,
            "stdout": buf_out.getvalue()[-8000:],
            "stderr": buf_err.getvalue()[-8000:],
            "session_id": req.session_id,
            "history_length": len(state["history"]),
        }
    except Exception as e:
        state["history"].append({"code": req.code, "ok": False, "error": str(e)})
        return {
            "ok": False,
            "stdout": buf_out.getvalue()[-8000:],
            "stderr": f"{buf_err.getvalue()}\n{type(e).__name__}: {e}"[-8000:],
            "session_id": req.session_id,
            "history_length": len(state["history"]),
        }


@router.get("/interpreter/state/{session_id}")
async def interpreter_state(session_id: str):
    s = _REPL_STATE.get(session_id)
    if not s:
        return {"session_id": session_id, "exists": False}
    return {
        "session_id":    session_id,
        "exists":        True,
        "var_names":     [k for k in s["globals"] if not k.startswith("__")],
        "history_count": len(s["history"]),
        "recent":        s["history"][-5:],
    }


# ───────────────────────────── JEEVES CONSULT ─────────────────────────────
class ConsultReq(BaseModel):
    context: str = "lesson"
    topic: str = ""


@router.post("/jeeves/consult")
async def jeeves_consult_route(req: ConsultReq):
    return await jeeves_consultant.consult(req.context, topic=req.topic)
