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
  • llm_chat            — retired compatibility alias; provider I/O is engine-owned
  • package_build       — produce a ZIP/APK from a Galaxy build_id
  • mongo_query         — read a knowledge collection
  • web_search          — placeholder (returns "feature gated", non-blocking)

This registry is consumed by agents.py (each agent step can declare a list
of tool calls to run before producing its output).
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import os, asyncio, json, sqlite3, subprocess, tempfile
from typing import Any, Callable, Coroutine
from uuid import uuid4
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
from core.exec_guard import code_execution_enabled, execution_disabled_response, execution_disabled_message
from skeleton.skills import (
    AsyncToolRuntime,
    SQLiteToolReceiptStore,
    ToolEffect,
    ToolExecutionRequest,
    ToolExecutionStatus,
    ToolManifest,
)
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
    max_output_bytes = scoped["max_output_bytes"]
    max_memory_mb = scoped["max_memory_mb"]

    suffix_map = {"c": ".c", "cpp": ".cpp", "cxx": ".cpp", "go": ".go", "rust": ".rs"}
    cmd_map = {
        "c": lambda src, out: ["gcc", src, "-o", out],
        "cpp": lambda src, out: ["g++", src, "-o", out],
        "cxx": lambda src, out: ["g++", src, "-o", out],
        "go": lambda src, out: ["go", "build", "-o", out, src],
        "rust": lambda src, out: ["rustc", src, "-o", out],
    }

    def _run_compile() -> dict:
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, f"src{suffix_map[lang]}")
            outp = os.path.join(td, "a.out")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(code)

            preexec_fn = None
            if os.name == "posix":
                def _limits():
                    import resource
                    memory_bytes = int(max_memory_mb) * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
                    cpu_seconds = max(1, int(float(timeout_seconds)) + 1)
                    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
                preexec_fn = _limits

            try:
                with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
                    proc = subprocess.Popen(
                        cmd_map[lang](src, outp),
                        stdout=stdout_file,
                        stderr=stderr_file,
                        preexec_fn=preexec_fn,
                    )
                    try:
                        exit_code = proc.wait(timeout=timeout_seconds)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                        return {"ok": False, "error": "compile timed out"}

                    def _tail(file_obj):
                        size = file_obj.seek(0, os.SEEK_END)
                        file_obj.seek(max(0, size - max_output_bytes), os.SEEK_SET)
                        return file_obj.read().decode("utf-8", errors="replace")

                    return {
                        "ok": exit_code == 0,
                        "stdout": _tail(stdout_file),
                        "stderr": _tail(stderr_file),
                        "exit_code": exit_code,
                    }
            except FileNotFoundError:
                return {"ok": False, "error": "toolchain_missing"}

    return await asyncio.to_thread(_run_compile)


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

    out = await binary_builder.package_build(doc, kinds=scoped["kinds"])
    oversized = []
    for artifact in out.get("artifacts", []):
        size_bytes = int(artifact.get("size_bytes") or 0)
        if size_bytes > scoped["max_output_bytes"]:
            oversized.append(str(artifact.get("artifact_id") or "unknown"))
            artifact_path = artifact.get("path")
            if isinstance(artifact_path, str):
                try:
                    os.remove(artifact_path)
                except (FileNotFoundError, OSError):
                    pass
        else:
            artifact["retention_days"] = scoped["retention_days"]

    if oversized:
        return {
            "ok": False,
            "error": "artifact_too_large",
            "artifacts_rejected": oversized,
        }

    try:
        for art in out.get("artifacts", []):
            await db.build_artifacts.update_one(
                {"artifact_id": art["artifact_id"]},
                {"$set": art},
                upsert=True,
            )
    except Exception:
        pass
    return {"ok": True, **out}


async def _tool_mongo_query(params: dict) -> dict:
    scoped = _DATABASE_POLICY.query_request(params)
    db = _db()
    coll = scoped["collection"]
    rows = await db[coll].find(
        scoped["filter"],
        scoped["project"],
    ).limit(scoped["limit"]).to_list(length=scoped["limit"])
    return {"ok": True, "collection": coll, "rows": rows, "count": len(rows)}


async def _tool_web_search(params: dict) -> dict:
    """Live web search through bounded egress and result policy."""
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
# Registry and canonical compatibility delegation
# ─────────────────────────────────────────────────────────────────
ToolFn = Callable[[dict], Coroutine[Any, Any, dict]]
TOOLS: dict[str, ToolFn] = {
    "vault_query": _tool_vault_query,
    "jeeves_consult": _tool_jeeves_consult,
    "compile_code": _tool_compile_code,
    "run_code": _tool_run_code,
    "package_build": _tool_package_build,
    "mongo_query": _tool_mongo_query,
    "web_search": _tool_web_search,
}


def _object_schema(properties: dict, *, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


_TOOL_MANIFESTS: dict[str, ToolManifest] = {
    "vault_query": ToolManifest(
        tool_id="vault_query",
        version="1.0.0",
        description="Read bounded samples from approved vault collections.",
        input_schema=_object_schema(
            {
                "topic": {"type": "string", "maxLength": 512},
                "collection": {"type": "string", "maxLength": 128},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "contains": {"type": "string", "maxLength": 512},
            }
        ),
    ),
    "jeeves_consult": ToolManifest(
        tool_id="jeeves_consult",
        version="1.0.0",
        description="Read bounded Jeeves guidance.",
        input_schema=_object_schema(
            {
                "context": {"type": "string", "maxLength": 128},
                "topic": {"type": "string", "maxLength": 1024},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            }
        ),
    ),
    "compile_code": ToolManifest(
        tool_id="compile_code",
        version="1.0.0",
        description="Compile bounded source in an approved local toolchain.",
        input_schema=_object_schema(
            {
                "language": {
                    "type": "string",
                    "enum": ["c", "cpp", "cxx", "go", "rust"],
                },
                "code": {"type": "string", "minLength": 1, "maxLength": 200000},
            },
            required=["code"],
        ),
    ),
    "run_code": ToolManifest(
        tool_id="run_code",
        version="1.0.0",
        description="Compatibility surface for sandboxed code execution.",
        input_schema=_object_schema(
            {
                "language": {"type": "string", "maxLength": 64},
                "code": {"type": "string", "minLength": 1, "maxLength": 200000},
            },
            required=["code"],
        ),
    ),
    "package_build": ToolManifest(
        tool_id="package_build",
        version="1.0.0",
        description="Create bounded package artifacts for an existing build.",
        input_schema=_object_schema(
            {
                "build_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "kinds": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["zip", "apk"]},
                    "minItems": 1,
                    "maxItems": 2,
                },
                "max_output_bytes": {
                    "type": "integer",
                    "minimum": 1024,
                    "maximum": 536870912,
                },
                "retention_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 30,
                },
            },
            required=["build_id"],
        ),
        effect=ToolEffect.REVERSIBLE,
        approval_required=True,
    ),
    "mongo_query": ToolManifest(
        tool_id="mongo_query",
        version="1.0.0",
        description="Read bounded data from an approved database collection.",
        input_schema=_object_schema(
            {
                "collection": {"type": "string", "minLength": 1, "maxLength": 128},
                "filter": {"type": "object"},
                "project": {"type": "object"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            required=["collection"],
        ),
    ),
    "web_search": ToolManifest(
        tool_id="web_search",
        version="1.0.0",
        description="Bounded web search through approved egress policy.",
        input_schema=_object_schema(
            {
                "query": {"type": "string", "minLength": 1, "maxLength": 512},
                "q": {"type": "string", "minLength": 1, "maxLength": 512},
                "kind": {"type": "string", "enum": ["text", "news", "images"]},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
            }
        ),
    ),
}


class _CompatibilityResultStore:
    """Durable projection of canonical tool outputs for legacy callers."""

    def __init__(self, path: str = ":memory:", max_entries: int = 4096) -> None:
        self.max_entries = max_entries
        self._lock = asyncio.Lock()
        self._connection = sqlite3.connect(
            str(path),
            check_same_thread=False,
            isolation_level=None,
            timeout=5.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS legacy_tool_result (
                result_ref TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

    async def put(self, request: ToolExecutionRequest, result: dict) -> str:
        if not isinstance(result, dict):
            raise TypeError("legacy tool result must be an object")
        encoded_text = json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
        encoded = encoded_text.encode("utf-8")
        identity_parts = [request.operation_id]
        if request.execution_id is not None:
            identity_parts.extend(
                (request.execution_id, request.turn_id or "", request.call_id or "")
            )
        identity_parts.extend(
            (request.tool_id, request.idempotency_key, request.arguments_digest)
        )
        identity = "\x1f".join(identity_parts).encode("utf-8")
        ref = "legacy-tool-result:" + hashlib.sha256(
            identity + b"\x1f" + encoded
        ).hexdigest()
        async with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute(
                    "SELECT result_json FROM legacy_tool_result WHERE result_ref = ?",
                    (ref,),
                ).fetchone()
                if existing is not None and existing["result_json"] != encoded_text:
                    raise RuntimeError("legacy tool result digest collision")
                self._connection.execute(
                    """
                    INSERT OR IGNORE INTO legacy_tool_result(
                        result_ref, result_json, created_at
                    ) VALUES (?, ?, ?)
                    """,
                    (ref, encoded_text, datetime.now(timezone.utc).isoformat()),
                )
                self._connection.execute(
                    """
                    DELETE FROM legacy_tool_result
                    WHERE result_ref IN (
                        SELECT result_ref
                        FROM legacy_tool_result
                        ORDER BY created_at DESC, result_ref DESC
                        LIMIT -1 OFFSET ?
                    )
                    """,
                    (self.max_entries,),
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return ref

    async def get(self, ref: str) -> dict | None:
        async with self._lock:
            row = self._connection.execute(
                "SELECT result_json FROM legacy_tool_result WHERE result_ref = ?",
                (str(ref),),
            ).fetchone()
        if row is None:
            return None
        value = json.loads(row["result_json"])
        if not isinstance(value, dict):
            raise RuntimeError("durable legacy tool result is not an object")
        return value

    def close(self) -> None:
        self._connection.close()


def _canonical_receipt_path() -> str:
    return os.environ.get("BACKEND_TOOL_RECEIPT_PATH", ":memory:")


def _canonical_result_path() -> str:
    return os.environ.get("BACKEND_TOOL_RESULT_PATH", ":memory:")


_CANONICAL_RUNTIME: AsyncToolRuntime | None = None
_CANONICAL_RESULT_STORE: _CompatibilityResultStore | None = None
_CANONICAL_INIT_LOCK: asyncio.Lock | None = None
_CANONICAL_INIT_LOOP: asyncio.AbstractEventLoop | None = None
_CANONICAL_READY = False


def _get_canonical_init_lock() -> asyncio.Lock:
    """Create the initialization lock only inside the active event loop."""

    global _CANONICAL_INIT_LOCK, _CANONICAL_INIT_LOOP
    loop = asyncio.get_running_loop()
    if _CANONICAL_INIT_LOCK is None or _CANONICAL_INIT_LOOP is not loop:
        _CANONICAL_INIT_LOCK = asyncio.Lock()
        _CANONICAL_INIT_LOOP = loop
    return _CANONICAL_INIT_LOCK


async def _result_postcondition(
    request: ToolExecutionRequest,
    result_ref: str | None,
) -> bool:
    if result_ref is None:
        return False
    store = _CANONICAL_RESULT_STORE
    if store is None:
        return False
    result = await store.get(result_ref)
    return bool(result is not None and result.get("ok") is not False)


async def _package_compensator(
    request: ToolExecutionRequest,
    result_ref: str | None,
) -> str:
    if result_ref is not None:
        store = _CANONICAL_RESULT_STORE
        result = await store.get(result_ref) if store is not None else None
        if result is not None:
            for artifact in result.get("artifacts", []):
                if not isinstance(artifact, dict):
                    continue
                path = artifact.get("path")
                if isinstance(path, str):
                    try:
                        os.remove(path)
                    except (FileNotFoundError, OSError):
                        pass
    identity_parts = [request.operation_id]
    if request.execution_id is not None:
        identity_parts.extend(
            (request.execution_id, request.turn_id or "", request.call_id or "")
        )
    identity_parts.extend((request.tool_id, request.idempotency_key))
    material = "\x1f".join(identity_parts).encode("utf-8")
    return "compensation:" + hashlib.sha256(material).hexdigest()


async def _ensure_canonical_runtime() -> None:
    global _CANONICAL_RUNTIME, _CANONICAL_RESULT_STORE, _CANONICAL_READY
    if _CANONICAL_READY:
        return
    async with _get_canonical_init_lock():
        if _CANONICAL_READY:
            return
        if _CANONICAL_RUNTIME is None:
            _CANONICAL_RUNTIME = AsyncToolRuntime(
                receipt_store=SQLiteToolReceiptStore(_canonical_receipt_path())
            )
        if _CANONICAL_RESULT_STORE is None:
            _CANONICAL_RESULT_STORE = _CompatibilityResultStore(
                _canonical_result_path()
            )
        runtime = _CANONICAL_RUNTIME
        store = _CANONICAL_RESULT_STORE
        for name, fn in TOOLS.items():
            manifest = _TOOL_MANIFESTS[name]

            async def handler(
                request: ToolExecutionRequest,
                *,
                _fn=fn,
            ) -> str:
                try:
                    result = await _fn(dict(request.arguments))
                except ToolAdapterDenied:
                    result = {"ok": False, "error": "tool_denied"}
                except Exception:
                    result = {"ok": False, "error": "tool_failed"}
                return await store.put(request, result)

            await runtime.register(
                manifest,
                handler,
                postcondition=_result_postcondition,
                compensate=(
                    _package_compensator
                    if manifest.effect is ToolEffect.REVERSIBLE
                    else None
                ),
            )
        _CANONICAL_READY = True


async def invoke_canonical(
    tool: str,
    params: dict,
    *,
    operation_id: str,
    tenant_id: str,
    idempotency_key: str,
    execution_id: str | None = None,
    turn_id: str | None = None,
    call_id: str | None = None,
    request_id: str | None = None,
    approval_ref: str | None = None,
    delegated_authority_ref: str | None = None,
) -> dict:
    """Execute through canonical request/receipt authority."""

    if tool not in TOOLS:
        return {
            "ok": False,
            "error": f"unknown tool: {tool}",
            "available": list(TOOLS.keys()),
        }
    await _ensure_canonical_runtime()
    request = ToolExecutionRequest(
        request_id=request_id or str(uuid4()),
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        call_id=call_id,
        tenant_id=tenant_id,
        tool_id=tool,
        idempotency_key=idempotency_key,
        arguments=dict(params or {}),
        requested_at=datetime.now(timezone.utc),
        approval_ref=approval_ref,
        delegated_authority_ref=delegated_authority_ref,
    )
    runtime = _CANONICAL_RUNTIME
    if runtime is None:
        raise RuntimeError("canonical tool runtime failed to initialize")
    receipt = await runtime.execute(request)

    if receipt.status is ToolExecutionStatus.DENIED:
        return {
            "ok": False,
            "error": receipt.error_code or "tool_denied",
            "receipt": receipt.as_dict(),
        }
    if receipt.status is ToolExecutionStatus.FAILED:
        return {
            "ok": False,
            "error": receipt.error_code or "tool_failed",
            "receipt": receipt.as_dict(),
        }
    if receipt.result_ref is None:
        return {
            "ok": False,
            "error": "result_unavailable",
            "receipt": receipt.as_dict(),
        }
    result = await _CANONICAL_RESULT_STORE.get(receipt.result_ref)
    if result is None:
        return {
            "ok": False,
            "error": "result_unavailable",
            "receipt": receipt.as_dict(),
        }
    result["receipt"] = receipt.as_dict()
    return result


def _legacy_policy_preflight(tool: str, params: dict) -> dict | None:
    """Preserve deterministic adapter denials before any compatibility side effect."""

    try:
        if tool == "compile_code":
            _SANDBOX_POLICY.compile_request(params)
        elif tool == "package_build":
            _ARTIFACT_POLICY.package_request(params)
        elif tool == "mongo_query":
            _DATABASE_POLICY.query_request(params)
        elif tool == "web_search":
            _NETWORK_POLICY.search_request(params)
    except ToolAdapterDenied:
        return {"ok": False, "error": "tool_denied"}
    return None


async def invoke(
    tool: str,
    params: dict,
    *,
    operation_id: str | None = None,
    execution_id: str | None = None,
    turn_id: str | None = None,
    call_id: str | None = None,
    tenant_id: str = "legacy-backend",
    idempotency_key: str | None = None,
    request_id: str | None = None,
    approval_ref: str | None = None,
    delegated_authority_ref: str = "legacy:backend/services/tool_registry.invoke",
) -> dict:
    """Legacy-compatible entrypoint delegated through canonical authority."""

    if tool == "llm_chat":
        return {
            "ok": False,
            "error": "provider_tool_retired",
            "tool": "llm_chat",
            "delegate": "skeleton-engine-provider-boundary",
        }

    manifest = _TOOL_MANIFESTS.get(tool)
    if manifest is None:
        return {
            "ok": False,
            "error": f"unknown tool: {tool}",
            "available": list(TOOLS.keys()),
        }

    normalized_params = dict(params or {})
    denied = _legacy_policy_preflight(tool, normalized_params)
    if denied is not None:
        return denied

    rid = request_id or str(uuid4())
    op_id = operation_id or str(uuid4())
    if manifest.effect is not ToolEffect.READ_ONLY and not idempotency_key:
        return {
            "ok": False,
            "error": "idempotency_key_required",
            "tool": tool,
        }
    key = idempotency_key or rid
    return await invoke_canonical(
        tool,
        normalized_params,
        operation_id=op_id,
        execution_id=execution_id,
        turn_id=turn_id,
        call_id=call_id,
        tenant_id=tenant_id,
        idempotency_key=key,
        request_id=rid,
        approval_ref=approval_ref,
        delegated_authority_ref=delegated_authority_ref,
    )


async def invoke_many(calls: list[dict]) -> list[dict]:
    """Parallel compatibility calls delegated through canonical authority."""

    coros = [
        invoke(
            call.get("tool"),
            call.get("params", {}),
            operation_id=call.get("operation_id"),
            execution_id=call.get("execution_id"),
            turn_id=call.get("turn_id"),
            call_id=call.get("call_id"),
            tenant_id=call.get("tenant_id") or "legacy-backend",
            idempotency_key=call.get("idempotency_key"),
            request_id=call.get("request_id"),
            approval_ref=call.get("approval_ref"),
            delegated_authority_ref=(
                call.get("delegated_authority_ref")
                or "legacy:backend/services/tool_registry.invoke_many"
            ),
        )
        for call in calls
    ]
    return await asyncio.gather(*coros, return_exceptions=False)


def describe() -> dict:
    legacy_params = {
        "vault_query": ["topic|collection", "limit", "contains?"],
        "jeeves_consult": ["context", "topic?"],
        "compile_code": ["language", "code"],
        "run_code": ["language=python", "code"],
        "package_build": [
            "build_id",
            "kinds=[zip,apk]",
            "max_output_bytes?",
            "retention_days?",
        ],
        "mongo_query": ["collection", "filter", "limit"],
        "web_search": ["query"],
    }
    items = []
    for name, manifest in _TOOL_MANIFESTS.items():
        items.append(
            {
                "name": name,
                "params": legacy_params[name],
                "effect": manifest.effect.value,
                "approval_required": manifest.approval_required,
                "idempotency_required": manifest.effect is not ToolEffect.READ_ONLY,
                "canonical_version": manifest.version,
            }
        )
    return {
        "tools": items,
        "count": len(items),
        "authority": "canonical-tool-runtime",
        "retired_tools": {
            "llm_chat": {
                "reason": "provider execution is engine-owned",
                "delegate": "skeleton-engine-provider-boundary",
            }
        },
    }
