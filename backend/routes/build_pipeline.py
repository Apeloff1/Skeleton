"""
build_pipeline.py — Unified API surface for binary/vault/tool/interpreter
infrastructure.

Endpoints:
  POST   /api/binary/package         — package a galaxy build into ZIP/APK
  GET    /api/binary/download/{build_id}/{kind}  — streaming download
  GET    /api/binary/artifacts/{build_id}        — list artifacts for a build
  GET    /api/vault/collections                  — list available vault collections
  POST   /api/vault/query                        — query a vault collection / topic
  GET    /api/vault/loader-stats                 — static vault-loader statistics
  POST   /api/tools/invoke                       — single tool call
  POST   /api/tools/invoke_many                  — parallel multi-call
  GET    /api/tools/describe                     — schema of available tools
  POST   /api/interpreter/run                    — interpreter run (multi-lang dispatch)
  GET    /api/interpreter/state/{session_id}     — fetch persisted REPL state
  POST   /api/jeeves/consult                     — direct in-process Jeeves query

The canonical user-vault statistics endpoint is owned by ``routes.vault``.
The loader-specific statistics endpoint is intentionally distinct so FastAPI
registration order cannot shadow one implementation with another.
"""
from __future__ import annotations

import contextlib
import io
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

from core.databases import client as _SHARED_MONGO_CLIENT
from core.exec_guard import code_execution_enabled, execution_disabled_response
from services import binary_builder, jeeves_consultant, tool_registry, vault_loader

router = APIRouter()

_DB_NAME = os.environ.get("DB_NAME", "test_database")
_client: AsyncIOMotorClient | None = None


def _db():
    global _client
    if _client is None:
        _client = _SHARED_MONGO_CLIENT
    return _client[_DB_NAME]


# ───────────────────────────── BINARY ─────────────────────────────
class PackageReq(BaseModel):
    build_id: str
    kinds: list[str] = Field(default_factory=lambda: ["zip", "apk"])


@router.post("/binary/package")
async def binary_package(req: PackageReq):
    if not code_execution_enabled():
        return execution_disabled_response("Binary packaging")

    db = _db()
    build = await db.galaxy_builds.find_one({"build_id": req.build_id}, {"_id": 0})
    if not build:
        raise HTTPException(404, f"build_id not found: {req.build_id}")
    out = await binary_builder.package_build(build, kinds=req.kinds)
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
        raise HTTPException(404, "artifact not found — call /api/binary/package first")
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
    collection: str | None = None
    topic: str | None = None
    limit: int = 10
    contains: str | None = None


@router.post("/vault/query")
async def vault_query(req: VaultQueryReq):
    if req.collection:
        rows = vault_loader.query_collection(req.collection, limit=req.limit, contains=req.contains)
        return {"collection": req.collection, "rows": rows, "count": len(rows)}
    if req.topic:
        matches = vault_loader.query_topic(req.topic, limit=req.limit)
        return {"topic": req.topic, "matches": matches, "collection_count": len(matches)}
    raise HTTPException(400, "specify either 'collection' or 'topic'")


@router.get("/vault/loader-stats")
async def vault_loader_stats():
    """Return static loader/catalogue statistics, not user-vault statistics."""
    return vault_loader.stats()


# ───────────────────────────── TOOLS ─────────────────────────────
class ToolInvokeReq(BaseModel):
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/tools/invoke")
async def tools_invoke(req: ToolInvokeReq):
    return await tool_registry.invoke(req.tool, req.params)


class ToolMultiReq(BaseModel):
    calls: list[ToolInvokeReq]


@router.post("/tools/invoke_many")
async def tools_invoke_many(req: ToolMultiReq):
    payload = [{"tool": call.tool, "params": call.params} for call in req.calls]
    return {"results": await tool_registry.invoke_many(payload)}


@router.get("/tools/describe")
async def tools_describe():
    return tool_registry.describe()


# ───────────────────────────── INTERPRETER ─────────────────────────────
_REPL_STATE: dict[str, dict[str, Any]] = {}


class InterpReq(BaseModel):
    code: str
    language: str = "python"
    session_id: str = "default"


@router.post("/interpreter/run")
async def interpreter_run(req: InterpReq):
    if not code_execution_enabled():
        return execution_disabled_response("Interpreter execution")

    if req.language != "python":
        if req.language in ("c", "cpp", "cxx", "go", "rust"):
            return await tool_registry.invoke(
                "compile_code", {"language": req.language, "code": req.code}
            )
        return await tool_registry.invoke(
            "run_code", {"language": req.language, "code": req.code}
        )

    state = _REPL_STATE.setdefault(
        req.session_id, {"globals": {"__name__": "__interp__"}, "history": []}
    )
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        if not code_execution_enabled():
            return execution_disabled_response("Interpreter execution")
        import builtins

        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            builtins.exec(builtins.compile(req.code, "<interp>", "exec"), state["globals"])
        state["history"].append({"code": req.code, "ok": True})
        return {
            "ok": True,
            "stdout": buf_out.getvalue()[-8000:],
            "stderr": buf_err.getvalue()[-8000:],
            "session_id": req.session_id,
            "history_length": len(state["history"]),
        }
    except Exception as exc:  # noqa: BLE001
        state["history"].append({"code": req.code, "ok": False, "error": str(exc)})
        return {
            "ok": False,
            "stdout": buf_out.getvalue()[-8000:],
            "stderr": f"{buf_err.getvalue()}\n{type(exc).__name__}: {exc}"[-8000:],
            "session_id": req.session_id,
            "history_length": len(state["history"]),
        }


@router.get("/interpreter/state/{session_id}")
async def interpreter_state(session_id: str):
    state = _REPL_STATE.get(session_id)
    if not state:
        return {"session_id": session_id, "exists": False}
    return {
        "session_id": session_id,
        "exists": True,
        "var_names": [key for key in state["globals"] if not key.startswith("__")],
        "history_count": len(state["history"]),
        "recent": state["history"][-5:],
    }


# ───────────────────────────── JEEVES CONSULT ──────────────────────────
class ConsultReq(BaseModel):
    context: str = "lesson"
    topic: str = ""


@router.post("/jeeves/consult")
async def jeeves_consult_route(req: ConsultReq):
    return await jeeves_consultant.consult(req.context, topic=req.topic)
