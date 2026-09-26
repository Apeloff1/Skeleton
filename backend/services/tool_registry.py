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
import os, asyncio, json, sqlite3
from typing import Any, Callable, Coroutine
from uuid import uuid4
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
from core.exec_guard import code_execution_enabled, execution_disabled_response, execution_disabled_message
from core.route_privacy import require_route_tool_transfer
from skeleton.skills import (
    AsyncToolRuntime,
    SQLiteToolReceiptStore,
    ToolApprovalPolicy,
    ToolAuthorityClass,
    ToolEffect,
    ToolIdempotencyMode,
    ToolRiskClass,
    ToolSideEffectClass,
    ToolExecutionRequest,
    ToolExecutionStatus,
    ToolManifest,
)
from skeleton.skills.tool_contract import validate_tool_arguments
from skeleton.vault.data_lifecycle import DataLifecycleRegistry, LifecycleState
from skeleton.vault.data_governance import DataGovernanceDenied
from skeleton.vault.governance_registry import GovernanceRegistry
from skeleton.skills.tool_adapters import (
    ArtifactAdapterPolicy,
    AsyncArtifactPackageAdapter,
    AsyncDatabaseQueryAdapter,
    AsyncJeevesConsultAdapter,
    AsyncNetworkSearchAdapter,
    AsyncSandboxCompileAdapter,
    AsyncVaultQueryAdapter,
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
_client: Any | None = None

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


_VAULT_OWNER = AsyncVaultQueryAdapter(vault_port=vault_loader)
_JEEVES_OWNER = AsyncJeevesConsultAdapter(
    consultant_port=jeeves_consultant
)
_SANDBOX_OWNER = AsyncSandboxCompileAdapter(
    policy=_SANDBOX_POLICY,
    execution_enabled=lambda: code_execution_enabled(),
    disabled_response=lambda name: execution_disabled_response(name),
)
_DATABASE_OWNER = AsyncDatabaseQueryAdapter(
    database_provider=lambda: _db(),
    policy=_DATABASE_POLICY,
)
_NETWORK_OWNER = AsyncNetworkSearchAdapter(policy=_NETWORK_POLICY)
_ARTIFACT_OWNER = AsyncArtifactPackageAdapter(
    database_provider=lambda: _db(),
    package_builder=binary_builder,
    policy=_ARTIFACT_POLICY,
    execution_enabled=lambda: code_execution_enabled(),
    disabled_response=lambda name: execution_disabled_response(name),
)


# ─────────────────────────────────────────────────────────────────
# Compatibility delegates
# ─────────────────────────────────────────────────────────────────
async def _tool_vault_query(params: dict) -> dict:
    return await _VAULT_OWNER.execute(params)


async def _tool_jeeves_consult(params: dict) -> dict:
    return await _JEEVES_OWNER.execute(params)


async def _tool_compile_code(params: dict) -> dict:
    return await _SANDBOX_OWNER.execute(params)


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
    return await _ARTIFACT_OWNER.execute(params)


async def _tool_mongo_query(params: dict) -> dict:
    return await _DATABASE_OWNER.execute(params)


async def _tool_web_search(params: dict) -> dict:
    return await _NETWORK_OWNER.execute(params)


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
        output_schema={"type": "object"},
        capabilities=("vault.read",),
        authority_class=ToolAuthorityClass.READ,
        risk_class=ToolRiskClass.LOW,
        side_effect_class=ToolSideEffectClass.NONE,
        idempotency_mode=ToolIdempotencyMode.INTRINSIC,
        approval_policy=ToolApprovalPolicy.NEVER,
        network_policy="none",
        data_policy="internal:bounded-vault",
        cost_model={"kind": "request", "estimated_units": 1},
        result_size_limit=1024 * 1024,
        max_concurrency=16,

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
        output_schema={"type": "object"},
        capabilities=("jeeves.read",),
        authority_class=ToolAuthorityClass.READ,
        risk_class=ToolRiskClass.LOW,
        side_effect_class=ToolSideEffectClass.NONE,
        idempotency_mode=ToolIdempotencyMode.INTRINSIC,
        approval_policy=ToolApprovalPolicy.NEVER,
        network_policy="none",
        data_policy="internal:persona-knowledge",
        cost_model={"kind": "request", "estimated_units": 1},
        result_size_limit=256 * 1024,
        max_concurrency=16,

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
        output_schema={"type": "object"},
        capabilities=("sandbox.compile",),
        authority_class=ToolAuthorityClass.PRIVILEGED,
        risk_class=ToolRiskClass.HIGH,
        side_effect_class=ToolSideEffectClass.LOCAL_REVERSIBLE,
        idempotency_mode=ToolIdempotencyMode.INTRINSIC,
        approval_policy=ToolApprovalPolicy.POLICY,
        network_policy="none",
        data_policy="ephemeral:sandbox-source",
        cost_model={"kind": "resource", "meter": "compile_seconds"},
        result_size_limit=128 * 1024,
        max_concurrency=4,

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
        output_schema={"type": "object"},
        capabilities=("sandbox.execute",),
        authority_class=ToolAuthorityClass.PRIVILEGED,
        risk_class=ToolRiskClass.HIGH,
        side_effect_class=ToolSideEffectClass.NONE,
        idempotency_mode=ToolIdempotencyMode.INTRINSIC,
        approval_policy=ToolApprovalPolicy.POLICY,
        network_policy="none",
        data_policy="ephemeral:sandbox-source",
        cost_model={"kind": "disabled"},
        result_size_limit=16 * 1024,
        max_concurrency=1,
        enabled=False,

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
        output_schema={"type": "object"},
        capabilities=("artifact.package", "artifact.persist"),
        authority_class=ToolAuthorityClass.WRITE,
        risk_class=ToolRiskClass.HIGH,
        side_effect_class=ToolSideEffectClass.LOCAL_REVERSIBLE,
        idempotency_mode=ToolIdempotencyMode.COMPENSATABLE,
        approval_policy=ToolApprovalPolicy.ALWAYS,
        network_policy="none",
        data_policy="internal:build-artifact",
        cost_model={"kind": "resource", "meter": "artifact_bytes"},
        result_size_limit=2 * 1024 * 1024,
        max_concurrency=2,

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
        output_schema={"type": "object"},
        capabilities=("repository.read",),
        authority_class=ToolAuthorityClass.READ,
        risk_class=ToolRiskClass.MEDIUM,
        side_effect_class=ToolSideEffectClass.NONE,
        idempotency_mode=ToolIdempotencyMode.INTRINSIC,
        approval_policy=ToolApprovalPolicy.NEVER,
        network_policy="database:scoped",
        data_policy="internal:collection-allowlist",
        cost_model={"kind": "request", "estimated_units": 1},
        result_size_limit=1024 * 1024,
        max_concurrency=16,

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
        output_schema={"type": "object"},
        capabilities=("network.search",),
        authority_class=ToolAuthorityClass.READ,
        risk_class=ToolRiskClass.MEDIUM,
        side_effect_class=ToolSideEffectClass.NONE,
        idempotency_mode=ToolIdempotencyMode.INTRINSIC,
        approval_policy=ToolApprovalPolicy.NEVER,
        network_policy="public-search:bounded-egress",
        data_policy="public:untrusted",
        cost_model={"kind": "request", "estimated_units": 1},
        result_size_limit=512 * 1024,
        max_concurrency=8,

    ),
}


class _CompatibilityResultStore:
    """Durable governed projection of canonical tool outputs for legacy callers."""

    _SOURCE_PREFIX = "tool-result://"
    _DELETION_TARGET = "tool-result"

    def __init__(
        self,
        path: str = ":memory:",
        max_entries: int = 4096,
        *,
        governance: GovernanceRegistry | None = None,
        retention_seconds: int = 7 * 24 * 60 * 60,
    ) -> None:
        if (
            isinstance(max_entries, bool)
            or not isinstance(max_entries, int)
            or max_entries < 1
        ):
            raise ValueError("max_entries must be a positive integer")
        if (
            isinstance(retention_seconds, bool)
            or not isinstance(retention_seconds, int)
            or retention_seconds < 60
            or retention_seconds > 365 * 24 * 60 * 60
        ):
            raise ValueError(
                "retention_seconds must be within [60, 31536000]"
            )
        self.max_entries = max_entries
        self.retention_seconds = retention_seconds
        self._lock = asyncio.Lock()
        self._path = str(path)
        self._owns_governance = governance is None
        if governance is None:
            lifecycle_path = (
                None
                if self._path == ":memory:"
                else self._path + ".governance.sqlite3"
            )
            governance = GovernanceRegistry(
                DataLifecycleRegistry(lifecycle_path)
            )
        self.governance = governance
        self._connection = sqlite3.connect(
            self._path,
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
                created_at TEXT NOT NULL,
                tenant_id TEXT,
                operation_id TEXT,
                tool_id TEXT,
                created_at_epoch REAL,
                retention_until REAL
            )
            """
        )
        existing_columns = {
            str(row["name"])
            for row in self._connection.execute(
                "PRAGMA table_info(legacy_tool_result)"
            ).fetchall()
        }
        for column, ddl in (
            ("tenant_id", "TEXT"),
            ("operation_id", "TEXT"),
            ("tool_id", "TEXT"),
            ("created_at_epoch", "REAL"),
            ("retention_until", "REAL"),
        ):
            if column not in existing_columns:
                self._connection.execute(
                    f"ALTER TABLE legacy_tool_result ADD COLUMN {column} {ddl}"
                )

    @classmethod
    def source_ref(cls, result_ref: str) -> str:
        value = str(result_ref).strip()
        if not value:
            raise ValueError("result_ref is required")
        return cls._SOURCE_PREFIX + value

    @classmethod
    def _parse_source_ref(cls, source_ref: object) -> str:
        raw = str(source_ref).strip()
        if not raw.startswith(cls._SOURCE_PREFIX):
            raise ValueError("tool result source_ref is invalid")
        result_ref = raw[len(cls._SOURCE_PREFIX):]
        if not result_ref:
            raise ValueError("tool result source_ref is invalid")
        return result_ref

    @staticmethod
    def _data_class(manifest: ToolManifest | None) -> str:
        if manifest is None:
            return "internal"
        prefix = str(manifest.data_policy).split(":", 1)[0].strip().lower()
        if prefix in {"public", "internal", "confidential", "restricted"}:
            return prefix
        return "internal"

    @staticmethod
    def _created_epoch(row: sqlite3.Row) -> float:
        raw = row["created_at_epoch"]
        if raw is not None:
            return float(raw)
        parsed = datetime.fromisoformat(str(row["created_at"]))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).timestamp()

    def _govern_result(
        self,
        *,
        result_ref: str,
        request: ToolExecutionRequest,
        manifest: ToolManifest | None,
        created_at: float,
        retention_until: float,
    ) -> None:
        self.governance.register_canonical_write(
            "artifact",
            record_id=result_ref,
            tenant_id=request.tenant_id,
            source_ref=self.source_ref(result_ref),
            data_class=self._data_class(manifest),
            purposes=("model-inference",),
            deletion_targets=(self._DELETION_TARGET,),
            created_at=created_at,
            retention_until=retention_until,
            exportable=False,
        )

    def _capacity_plan(
        self,
        rows: list[sqlite3.Row],
        *,
        now: float,
    ) -> list[tuple[str, str, str]]:
        plans: list[tuple[str, str, str]] = []
        for row in rows:
            tenant_id = row["tenant_id"]
            result_ref = row["result_ref"]
            if tenant_id is None:
                # Pre-governance legacy rows are retained until they are
                # replayed/backfilled with tenant identity.
                continue
            plan = self.governance.request_deletion(
                str(tenant_id),
                record_ids=(str(result_ref),),
                reason="tool-result-capacity",
                now=now,
            )
            plans.append(
                (plan.plan_id, str(result_ref), str(tenant_id))
            )
        return plans

    async def put(
        self,
        request: ToolExecutionRequest,
        result: dict,
        *,
        manifest: ToolManifest | None = None,
    ) -> str:
        if not isinstance(result, dict):
            raise TypeError("legacy tool result must be an object")
        if manifest is not None:
            if manifest.tool_id != request.tool_id:
                raise ValueError("tool result manifest does not match request")
            validate_tool_arguments(manifest.output_schema or {}, result)

        encoded_text = json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
        encoded = encoded_text.encode("utf-8")
        if manifest is not None and len(encoded) > manifest.result_size_limit:
            raise ValueError("tool result exceeds manifest result_size_limit")

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
            existing = self._connection.execute(
                "SELECT * FROM legacy_tool_result WHERE result_ref = ?",
                (ref,),
            ).fetchone()
            if existing is not None and existing["result_json"] != encoded_text:
                raise RuntimeError("legacy tool result digest collision")
            if existing is not None:
                for column, expected in (
                    ("tenant_id", request.tenant_id),
                    ("operation_id", request.operation_id),
                    ("tool_id", request.tool_id),
                ):
                    current = existing[column]
                    if current is not None and str(current) != str(expected):
                        raise RuntimeError(
                            "legacy tool result governance identity conflict"
                        )
                created_epoch = self._created_epoch(existing)
                retention_until = (
                    float(existing["retention_until"])
                    if existing["retention_until"] is not None
                    else created_epoch + self.retention_seconds
                )
            else:
                created_epoch = datetime.now(timezone.utc).timestamp()
                retention_until = created_epoch + self.retention_seconds

            # Governance is registered before payload mutation. A crash may
            # therefore leave metadata for an absent payload, but never a
            # durable payload without lifecycle authority.
            self._govern_result(
                result_ref=ref,
                request=request,
                manifest=manifest,
                created_at=created_epoch,
                retention_until=retention_until,
            )

            self._connection.execute("BEGIN IMMEDIATE")
            plans: list[tuple[str, str, str]] = []
            try:
                self._connection.execute(
                    """
                    INSERT INTO legacy_tool_result(
                        result_ref, result_json, created_at, tenant_id,
                        operation_id, tool_id, created_at_epoch,
                        retention_until
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(result_ref) DO UPDATE SET
                        tenant_id = COALESCE(
                            legacy_tool_result.tenant_id,
                            excluded.tenant_id
                        ),
                        operation_id = COALESCE(
                            legacy_tool_result.operation_id,
                            excluded.operation_id
                        ),
                        tool_id = COALESCE(
                            legacy_tool_result.tool_id,
                            excluded.tool_id
                        ),
                        created_at_epoch = COALESCE(
                            legacy_tool_result.created_at_epoch,
                            excluded.created_at_epoch
                        ),
                        retention_until = COALESCE(
                            legacy_tool_result.retention_until,
                            excluded.retention_until
                        )
                    """,
                    (
                        ref,
                        encoded_text,
                        datetime.fromtimestamp(
                            created_epoch,
                            timezone.utc,
                        ).isoformat(),
                        request.tenant_id,
                        request.operation_id,
                        request.tool_id,
                        created_epoch,
                        retention_until,
                    ),
                )
                overflow = self._connection.execute(
                    """
                    SELECT *
                    FROM legacy_tool_result
                    ORDER BY created_at_epoch DESC, created_at DESC, result_ref DESC
                    LIMIT -1 OFFSET ?
                    """,
                    (self.max_entries,),
                ).fetchall()
                governed_overflow = [
                    row for row in overflow if row["tenant_id"] is not None
                ]
                plans = self._capacity_plan(
                    governed_overflow,
                    now=datetime.now(timezone.utc).timestamp(),
                )
                for _, result_ref, _ in plans:
                    self._connection.execute(
                        "DELETE FROM legacy_tool_result WHERE result_ref = ?",
                        (result_ref,),
                    )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

            for plan_id, result_ref, _tenant_id in plans:
                self.governance.acknowledge_deletion(
                    plan_id,
                    result_ref,
                    self._DELETION_TARGET,
                    now=datetime.now(timezone.utc).timestamp(),
                )
        return ref

    async def get(self, ref: str) -> dict | None:
        async with self._lock:
            row = self._connection.execute(
                "SELECT * FROM legacy_tool_result WHERE result_ref = ?",
                (str(ref),),
            ).fetchone()
            if row is None or row["tenant_id"] is None:
                return None
            lifecycle = self.governance.lifecycle.get(str(ref))
            if lifecycle["state"] != LifecycleState.ACTIVE.value:
                return None
            retention_until = lifecycle.get("retention_until")
            if (
                retention_until is not None
                and float(retention_until)
                <= datetime.now(timezone.utc).timestamp()
            ):
                return None
            if lifecycle["tenant_id"] != str(row["tenant_id"]):
                raise RuntimeError("tool result governance tenant mismatch")
            value = json.loads(row["result_json"])
        if not isinstance(value, dict):
            raise RuntimeError("durable legacy tool result is not an object")
        return value

    async def delete(self, action) -> None:
        result_ref = self._parse_source_ref(action.source_ref)
        if result_ref != str(action.record_id):
            raise RuntimeError("tool result lifecycle identity mismatch")
        async with self._lock:
            self._connection.execute(
                """
                DELETE FROM legacy_tool_result
                WHERE result_ref = ? AND tenant_id = ?
                """,
                (result_ref, str(action.tenant_id)),
            )

    async def execute_retention_expiry(
        self,
        *,
        now: float | None = None,
    ) -> tuple[str, ...]:
        timestamp = (
            datetime.now(timezone.utc).timestamp()
            if now is None
            else float(now)
        )
        deleted: list[str] = []
        plans = self.governance.plan_retention_expiry(now=timestamp)
        for plan in plans:
            for action in plan.actions:
                if action.target != self._DELETION_TARGET:
                    raise RuntimeError(
                        "unexpected tool result deletion target"
                    )
                await self.delete(action)
                self.governance.acknowledge_deletion(
                    plan.plan_id,
                    action.record_id,
                    action.target,
                    now=timestamp,
                )
                deleted.append(action.record_id)
        return tuple(deleted)

    def close(self) -> None:
        self._connection.close()
        if self._owns_governance:
            self.governance.lifecycle.close()



def _canonical_receipt_path() -> str:
    return os.environ.get("BACKEND_TOOL_RECEIPT_PATH", ":memory:")


def _canonical_result_path() -> str:
    return os.environ.get("BACKEND_TOOL_RESULT_PATH", ":memory:")


def _canonical_result_retention_seconds() -> int:
    raw = os.environ.get("BACKEND_TOOL_RESULT_RETENTION_SECONDS", "604800")
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(
            "BACKEND_TOOL_RESULT_RETENTION_SECONDS must be an integer"
        ) from exc
    if value < 60 or value > 365 * 24 * 60 * 60:
        raise RuntimeError(
            "BACKEND_TOOL_RESULT_RETENTION_SECONDS is outside safe bounds"
        )
    return value


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
            _ARTIFACT_OWNER.compensate_result(result)
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
                _canonical_result_path(),
                retention_seconds=_canonical_result_retention_seconds(),
            )
        runtime = _CANONICAL_RUNTIME
        store = _CANONICAL_RESULT_STORE
        for name, fn in TOOLS.items():
            manifest = _TOOL_MANIFESTS[name]

            async def handler(
                request: ToolExecutionRequest,
                *,
                _fn=fn,
                _manifest=manifest,
            ) -> str:
                try:
                    result = await _fn(dict(request.arguments))
                except ToolAdapterDenied:
                    result = {"ok": False, "error": "tool_denied"}
                except Exception:
                    result = {"ok": False, "error": "tool_failed"}
                return await store.put(
                    request,
                    result,
                    manifest=_manifest,
                )

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
    data_class: str = "internal",
    transfer_purpose: str = "tool-execution",
) -> dict:
    """Execute through canonical request/receipt authority."""

    if tool not in TOOLS:
        return {
            "ok": False,
            "error": f"unknown tool: {tool}",
            "available": list(TOOLS.keys()),
        }
    manifest = _TOOL_MANIFESTS[tool]
    try:
        require_route_tool_transfer(
            tool_id=tool,
            data_policy=manifest.data_policy,
            network_policy=manifest.network_policy,
            data_class=data_class,
            purpose=transfer_purpose,
            tenant_id=tenant_id,
            source="backend.tool_registry",
        )
    except DataGovernanceDenied:
        return {
            "ok": False,
            "error": "route_privacy_denied",
            "tool": tool,
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
        data_class=data_class,
        transfer_purpose=transfer_purpose,
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
    data_class: str = "internal",
    transfer_purpose: str = "tool-execution",
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
        data_class=data_class,
        transfer_purpose=transfer_purpose,
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
            data_class=call.get("data_class") or "internal",
            transfer_purpose=(
                call.get("transfer_purpose")
                or "tool-execution"
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
                "data_policy": manifest.data_policy,
                "network_policy": manifest.network_policy,
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
