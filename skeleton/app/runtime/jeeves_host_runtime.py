"""Application-owned adapter for Jeeves' tenant/project workbench.

This is the entry point used by Skeleton's product/API layer. The host must
authenticate the caller, provide its trusted authorization and readiness
callbacks, supply private state storage, and resolve grants through its real
permission service. No default principal, public write endpoint, implicit
permission or model-supplied runtime callback is provided.

Construction assembles in-process capability and evidence owners; it does not
start a background task, source crawl, inference model, or external provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping, Sequence

from skeleton.jeeves.agent.tools import (
    ToolExecutionContext, ToolGrant, ToolObservation,
)
from skeleton.jeeves.agent.types import ToolCall
from skeleton.jeeves.workbench import JeevesWorkbench
from skeleton.jeeves.agent.capability_dispatch import HostCapabilityBinding


class JeevesHostRuntimeError(ValueError):
    """Untrusted application context, stale runtime or missing host scope."""


@dataclass(frozen=True, slots=True)
class JeevesHostContext:
    tenant_id: str
    project_id: str
    principal_id: str
    run_id: str
    trace_id: str

    def __post_init__(self) -> None:
        for name in ("tenant_id", "project_id", "principal_id", "run_id", "trace_id"):
            value = getattr(self, name)
            if (not isinstance(value, str) or not 1 <= len(value) <= 192
                    or value != value.strip() or any(ord(ch) < 33 for ch in value)):
                raise JeevesHostRuntimeError(f"{name} must be an authenticated identifier")

    def to_tool_context(self, *, observed_at_ns: int | None = None) -> ToolExecutionContext:
        metadata: dict[str, Any] = {
            "tenant_id": self.tenant_id, "project_id": self.project_id,
        }
        if observed_at_ns is not None:
            if type(observed_at_ns) is not int or observed_at_ns < 0:
                raise JeevesHostRuntimeError("host observed_at_ns must be non-negative")
            metadata["observed_at_ns"] = observed_at_ns
        return ToolExecutionContext(
            run_id=self.run_id, user_id=self.principal_id,
            trace_id=self.trace_id, metadata=metadata,
        )


class JeevesApplicationRuntime:
    """Host-facing interface: explicit grants, source awareness and durable state."""

    def __init__(
        self, *, root: str | Path, state_directory: str | Path,
        scope: JeevesHostContext,
        read_authorize: Callable[..., bool],
        orchestration_authorize: Callable[..., bool],
        source_read_authorize: Callable[..., bool] | None = None,
        source_edit_authorize: Callable[..., bool] | None = None,
        source_edit_allowlist: Sequence[str] | None = None,
        source_edit_handler: Callable[..., Any] | None = None,
        creator_handlers: Mapping[str, Callable[..., Any]] | None = None,
        creator_authorize: Callable[..., bool] | None = None,
        shadow_write_authorize: Callable[..., bool] | None = None,
        shadow_review_verify: Callable[..., bool] | None = None,
        shadow_admission_verify: Callable[..., bool] | None = None,
        shadow_consume_verify: Callable[..., bool] | None = None,
        release_verify_external: Callable[..., bool] | None = None,
    ) -> None:
        if not isinstance(scope, JeevesHostContext):
            raise JeevesHostRuntimeError("authenticated JeevesHostContext required")
        self.scope = scope
        self._lock = RLock()
        self._closed = False
        self.workbench = JeevesWorkbench(
            root=root, state_directory=state_directory,
            tenant_id=scope.tenant_id, project_id=scope.project_id,
            principal_id=scope.principal_id,
            read_authorize=read_authorize,
            orchestration_authorize=orchestration_authorize,
            source_read_authorize=source_read_authorize,
            source_edit_authorize=source_edit_authorize,
            source_edit_allowlist=source_edit_allowlist,
            source_edit_handler=source_edit_handler,
            creator_handlers=creator_handlers,
            creator_authorize=creator_authorize,
            shadow_write_authorize=shadow_write_authorize,
            shadow_review_verify=shadow_review_verify,
            shadow_admission_verify=shadow_admission_verify,
            shadow_consume_verify=shadow_consume_verify,
            release_verify_external=release_verify_external,
        )

    def _require_live(self) -> None:
        if self._closed:
            raise JeevesHostRuntimeError("Jeeves application runtime is closed")

    def _context(self, ctx: JeevesHostContext, *,
                 observed_at_ns: int | None = None) -> ToolExecutionContext:
        if not isinstance(ctx, JeevesHostContext):
            raise JeevesHostRuntimeError("typed authenticated host context required")
        if (ctx.tenant_id != self.scope.tenant_id
                or ctx.project_id != self.scope.project_id
                or ctx.principal_id != self.scope.principal_id):
            raise JeevesHostRuntimeError("request crossed Jeeves tenant/project/principal")
        return ctx.to_tool_context(observed_at_ns=observed_at_ns)

    def invoke(
        self, *, tool_name: str, arguments: Mapping[str, Any],
        request_id: str, context: JeevesHostContext,
        grants: Sequence[ToolGrant],
        observed_at_ns: int | None = None,
    ) -> ToolObservation:
        """Invoke one operation, requiring externally issued exact ToolGrants."""
        if (not isinstance(request_id, str) or not 1 <= len(request_id) <= 192
                or request_id.strip() != request_id):
            raise JeevesHostRuntimeError("host request id must be canonical")
        if not isinstance(arguments, Mapping) or not isinstance(grants, (tuple, list)):
            raise JeevesHostRuntimeError("typed tool arguments and grants required")
        if any(not isinstance(grant, ToolGrant) for grant in grants):
            raise JeevesHostRuntimeError("grants must be actual host ToolGrant values")
        with self._lock:
            self._require_live()
            tool_context = self._context(context, observed_at_ns=observed_at_ns)
            call_id = "app-" + sha256(json.dumps(
                {"run": context.run_id, "request_id": request_id,
                 "tool": tool_name, "arguments": dict(arguments)},
                sort_keys=True, separators=(",", ":"), allow_nan=False,
                ensure_ascii=True,
            ).encode("utf-8")).hexdigest()[:32]
            return self.workbench.executor.execute(
                ToolCall(
                    call_id=call_id, name=tool_name,
                    arguments=dict(arguments),
                    reason="explicit host-authorized Jeeves application operation",
                ),
                tool_context, grants=grants,
            )

    def status(self) -> dict[str, Any]:
        """Safe, bounded control-plane snapshot with no source or secret values."""
        with self._lock:
            self._require_live()
            atlas = self.workbench.atlas
            try:
                source = atlas.metadata()
            except Exception:
                source = {
                    "schema": "jeeves.repository_file_atlas.v1",
                    "state": "not_refreshed",
                    "file_count": 0,
                }
            shadow = self.workbench.shadow.snapshot()
            ledger, head, revision = self.workbench.orchestration.load()
            counts: dict[str, int] = {}
            for row in shadow["records"]:
                state = row["state"]
                counts[state] = counts.get(state, 0) + 1
            return {
                "schema": "skeleton.app.jeeves_runtime_status.v1",
                "tenant_scope": "current",
                "project_scope": "current",
                "source_index": source,
                "tool_names": [
                    spec.name for spec in self.workbench.tools.specs()
                ],
                "shadow": {
                    "record_count": shadow["record_count"],
                    "head_digest": shadow["head_digest"],
                    "states": dict(sorted(counts.items())),
                },
                "orchestration": {
                    "task_count": len(ledger.records),
                    "ready_count": len(ledger.ready_names()),
                    "revision_count": revision, "head_digest": head,
                },
                "model_release": {
                    "enabled": self.workbench.model_releases is not None,
                    "proposals": len(self.workbench.model_releases.list_status(limit=1000))
                    if self.workbench.model_releases is not None else 0,
                    "count_capped_at": 1000,
                    "production_status": "external_model_serving_plane_only",
                },
                "runtime_availability": "requires host readiness and execution grants",
                "weights_loaded_by_jeeves": False,
            }

    def refresh_sources(self, *, observed_at_ns: int,
                        hash_contents: bool = False):
        """Host-only rebuild; never exposed as a model-facing tool."""
        with self._lock:
            self._require_live()
            return self.workbench.refresh_source_atlas(
                observed_at_ns=observed_at_ns,
                hash_contents=hash_contents,
            )

    def apply_source_events(self, paths: list[str], *,
                            observed_at_ns: int, hash_contents: bool = False):
        """Host-only incremental source-index projection update."""
        with self._lock:
            self._require_live()
            return self.workbench.apply_source_changes(
                paths, observed_at_ns=observed_at_ns,
                hash_contents=hash_contents,
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self.workbench.close()

    def __enter__(self) -> "JeevesApplicationRuntime":
        self._require_live()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = [
    "JeevesHostRuntimeError", "JeevesHostContext", "JeevesApplicationRuntime",
]
