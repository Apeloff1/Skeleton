"""
tool_registry.py — Unified "complex tools" registry that agents and the
build pipeline can call. Each tool is a coroutine that takes a dict of
parameters and returns a dict. The registry is invocation-flat: callers
specify (tool_name, params) and get a structured result back.

Available tools:
  • compile_code        — invoke the multi-language compiler
  • run_code            — execute code in the playground sandbox
  • analyze_code        — invoke the debugger / code intelligence analysis
  • vault_query         — fetch samples from the vault collections
  • jeeves_consult      — pull persona-flavoured guidance from Jeeves
  • llm_chat            — talk to GPT-4o via Emergent LLM key (if configured)
  • package_build       — produce a ZIP/APK from a Galaxy build_id
  • mongo_query         — read a knowledge collection
  • web_search          — placeholder (returns "feature gated", non-blocking)

This registry is consumed by agents.py (each agent step can declare a list
of tool calls to run before producing its output).
"""
from __future__ import annotations
import os, asyncio, json, subprocess, tempfile
from typing import Any, Callable, Coroutine
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
from core.exec_guard import code_execution_enabled, execution_disabled_response, execution_disabled_message
from skeleton.skills.tool_adapters import (
    ArtifactAdapterPolicy,
    DatabaseAdapterPolicy,
    NetworkEgressPolicy,
    SandboxAdapterPolicy,
    ToolAdapterDenied,
)

from . import vault_loader
from . import jeeves_consultant
from . import binary_builder

_MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
_DB_NAME = os.environ.get("DB_NAME", "test_database")
_client: AsyncIOMotorClient | None = None

_db_scope_raw = tuple(
    item.strip()
    for item in os.environ.get("TOOL_DB_ALLOWED_COLLECTIONS", "").split(",")
    if item.strip()
)
_SANDBOX_POLICY = SandboxAdapterPolicy()
_DATABASE_POLICY = DatabaseAdapterPolicy(
    allowed_collections=frozenset(_db_scope_raw) if _db_scope_raw else None
)
_NETWORK_POLICY = NetworkEgressPolicy()
_ARTIFACT_POLICY = ArtifactAdapterPolicy()


def _db():
    global _client
    if _client is None:
        _client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
    return _client[_DB_NAME]


# ─────────────────────────────────────────────────────────────────
# Tool implementations
# ─────────────────────────────────────────────────────────────────
async def _tool_vault_query(params: dict) -> dict:
    topic = params.get("topic") or params.get("collection") or ""
    limit = int(params.get("limit", 10))
    if params.get("collection"):
        rows = vault_loader.query_collection(params["collection"], limit=limit,
                                              contains=params.get("contains"))
        return {"collection": params["collection"], "rows": rows, "count": len(rows)}
    return {"topic": topic, "matches": vault_loader.query_topic(topic, limit=limit)}


async def _tool_jeeves_consult(params: dict) -> dict:
    return await jeeves_consultant.consult(
        params.get("context", "lesson"),
        topic=params.get("topic", ""),
        limit=int(params.get("limit", 1)),
    )


async def _tool_compile_code(params: dict) -> dict:
    if not code_execution_enabled():
        return execution_disabled_response("Tool compile execution")

    scoped = _SANDBOX_POLICY.compile_request(params)
    lang = scoped["language"]
    code = scoped["code"]
    timeout_seconds = scoped["timeout_seconds"]
    # Lightweight inline compile — defers to /api/compiler/compile semantics
    # by spawning a subprocess for compiled langs we can support locally.
    suffix_map = {"c": ".c", "cpp": ".cpp", "cxx": ".cpp", "go": ".go", "rust": ".rs"}
    cmd_map = {
        "c":    lambda src, out: ["gcc", src, "-o", out],
        "cpp":  lambda src, out: ["g++", src, "-o", out],
        "cxx":  lambda src, out: ["g++", src, "-o", out],
        "go":   lambda src, out: ["go", "build", "-o", out, src],
        "rust": lambda src, out: ["rustc", src, "-o", out],
    }
    if lang not in suffix_map:
        return {"ok": False, "error": f"language not supported for inline compile: {lang}"}
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, f"src{suffix_map[lang]}")
        outp = os.path.join(td, "a.out")
        with open(src, "w") as fh: fh.write(code)
        try:
            proc = subprocess.run(
                cmd_map[lang](src, outp),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            return {
                "ok": proc.returncode == 0,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-4000:],
                "exit_code": proc.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "compile timed out"}
        except FileNotFoundError:
            return {"ok": False, "error": "toolchain_missing"}


async def _tool_run_code(params: dict) -> dict:
    """Fail closed instead of evaluating agent-supplied Python in the backend.

    Executable snippets must go through the dedicated playground sandbox.  The
    registry previously used builtins.exec(), which bypassed that isolation and
    ran untrusted code inside the long-lived backend process.
    """
    if not code_execution_enabled():
        return {
            "ok": False,
            "disabled": True,
            "error": execution_disabled_message("Tool run execution"),
            "exit_code": 0,
        }

    code = params.get("code", "")
    lang = params.get("language", "python")
    if not code:
        return {"ok": False, "error": "empty code", "exit_code": 0}
    return {
        "ok": False,
        "disabled": True,
        "error": f"inline {lang} execution is disabled; use /api/playground/run",
        "exit_code": 0,
    }


async def _tool_package_build(params: dict) -> dict:
    if not code_execution_enabled():
        return execution_disabled_response("Tool binary packaging")

    scoped = _ARTIFACT_POLICY.package_request(params)
    build_id = scoped["build_id"]
    db = _db()
    doc = await db.galaxy_builds.find_one({"build_id": build_id}, {"_id": 0})
    if not doc:
        return {"ok": False, "error": f"build_id not found: {build_id}"}
    kinds = scoped["kinds"]
    out = await binary_builder.package_build(doc, kinds=kinds)
    # Persist artifact metadata
    try:
        for art in out["artifacts"]:
            await db.build_artifacts.update_one(
                {"artifact_id": art["artifact_id"]},
                {"$set": art}, upsert=True,
            )
    except Exception:
        pass
    return {"ok": True, **out}


async def _tool_mongo_query(params: dict) -> dict:
    scoped = _DATABASE_POLICY.query_request(params)
    coll = scoped["collection"]
    db = _db()
    q = scoped["filter"]
    proj = scoped["project"]
    limit = scoped["limit"]
    rows = await db[coll].find(q, proj).limit(limit).to_list(length=limit)
    return {"ok": True, "collection": coll, "rows": rows, "count": len(rows)}


async def _tool_llm_chat(params: dict) -> dict:
    """Call the Emergent LLM key via the same path the rest of the app uses."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        key = os.environ.get("EMERGENT_LLM_KEY", "")
        if not key:
            return {"ok": False, "error": "EMERGENT_LLM_KEY not set"}
        model = params.get("model", "gpt-4o")
        chat = LlmChat(api_key=key, session_id=params.get("session_id", "tool"), system_message=params.get("system", "You are a helpful assistant.")).with_model("openai", model)
        msg = await chat.send_message(UserMessage(text=params.get("prompt", "")))
        return {"ok": True, "response": str(msg)[:8000], "model": model}
    except Exception:
        return {"ok": False, "error": "llm_request_failed"}


async def _tool_web_search(params: dict) -> dict:
    """Live web search through a bounded egress/result policy."""
    scoped = _NETWORK_POLICY.search_request(params)
    query = scoped["query"]
    max_results = scoped["max_results"]
    kind = scoped["kind"]
    try:
        from ddgs import DDGS
    except Exception:
        return {"ok": False, "error": "ddgs_not_installed"}
    try:
        loop = asyncio.get_running_loop()

        def _search():
            with DDGS() as d:
                if kind == "news":
                    return list(d.news(query, max_results=max_results))
                if kind == "images":
                    return list(d.images(query, max_results=max_results))
                return list(d.text(query, max_results=max_results))

        results = await loop.run_in_executor(None, _search)
        clean: list[dict[str, str]] = []
        for raw in results:
            if not isinstance(raw, dict):
                continue
            normalized = _NETWORK_POLICY.sanitize_result(raw)
            if normalized is not None:
                clean.append(normalized)
            if len(clean) >= max_results:
                break
        return {
            "ok": True,
            "query": query,
            "kind": kind,
            "results": clean,
            "count": len(clean),
        }
    except ToolAdapterDenied:
        raise
    except Exception:
        return {"ok": False, "error": "web_search_failed"}


# ─────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────
ToolFn = Callable[[dict], Coroutine[Any, Any, dict]]
TOOLS: dict[str, ToolFn] = {
    "vault_query":    _tool_vault_query,
    "jeeves_consult": _tool_jeeves_consult,
    "compile_code":   _tool_compile_code,
    "run_code":       _tool_run_code,
    "package_build":  _tool_package_build,
    "mongo_query":    _tool_mongo_query,
    "llm_chat":       _tool_llm_chat,
    "web_search":     _tool_web_search,
}


async def invoke(tool: str, params: dict) -> dict:
    """Single-entry dispatch."""
    fn = TOOLS.get(tool)
    if fn is None:
        return {"ok": False, "error": f"unknown tool: {tool}", "available": list(TOOLS.keys())}
    try:
        return await fn(params or {})
    except ToolAdapterDenied:
        return {"ok": False, "error": "tool_denied"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}


async def invoke_many(calls: list[dict]) -> list[dict]:
    """Parallel multi-call. Each call: {tool, params}."""
    coros = [invoke(c.get("tool"), c.get("params", {})) for c in calls]
    return await asyncio.gather(*coros, return_exceptions=False)


def describe() -> dict:
    return {
        "tools": [
            {"name": "vault_query",    "params": ["topic|collection", "limit", "contains?"]},
            {"name": "jeeves_consult", "params": ["context", "topic?"]},
            {"name": "compile_code",   "params": ["language", "code"]},
            {"name": "run_code",       "params": ["language=python", "code"]},
            {"name": "package_build",  "params": ["build_id", "kinds=[zip,apk]"]},
            {"name": "mongo_query",    "params": ["collection", "filter", "limit"]},
            {"name": "llm_chat",       "params": ["prompt", "model?", "system?"]},
            {"name": "web_search",     "params": ["query"]},
        ],
        "count": len(TOOLS),
    }
