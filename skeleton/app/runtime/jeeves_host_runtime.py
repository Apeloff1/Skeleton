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


@dataclass(frozen=True, slots=True)
class JeevesDispatchAuthorization:
    """Exact host permission question; model/request bytes supply no authority."""

    context: JeevesHostContext
    action: str
    request_id: str
    arguments_json: bytes
    dispatcher_policy_sha256: str

    @property
    def digest(self) -> str:
        return sha256(json.dumps({
            "scope": [self.context.tenant_id, self.context.project_id,
                      self.context.principal_id, self.context.run_id, self.context.trace_id],
            "action": self.action, "request_id": self.request_id,
            "arguments_sha256": sha256(self.arguments_json).hexdigest(),
            "dispatcher_policy_sha256": self.dispatcher_policy_sha256,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


class JeevesDispatcherGateway:
    """Run-scoped application host client for the actual private dispatcher inbox.

    The enclosing host authenticates the context and supplies its real
    authorizer. This is neither a public HTTP route nor a model tool grant.
    Request IDs, task IDs, singleton scope and dependency IDs are derived
    from the exact authenticated tenant/project/principal/run, with separate
    domain tags. Global service stop, key access and policy mutation cannot
    be requested through this gateway.
    """

    _ACTIONS = frozenset({"submit", "cancel", "cancel-pending", "signal", "reconcile", "command", "result",
                          "workflow-submit", "workflow-status", "workflow-cancel"})

    def __init__(self, *, directory: str | Path, policy_sha256: str,
                 scope: JeevesHostContext,
                 authorize: Callable[[JeevesDispatchAuthorization], bool]) -> None:
        from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
        if (not isinstance(scope, JeevesHostContext) or not callable(authorize)
                or type(policy_sha256) is not str or len(policy_sha256) != 64
                or any(ch not in "0123456789abcdef" for ch in policy_sha256)):
            raise JeevesHostRuntimeError("dispatcher binding requires exact policy and authorization")
        self._directory = Path(directory)
        self._scope = scope
        self._policy_sha256 = policy_sha256
        self._authorize = authorize
        app = LocalDispatcherApplication(self._directory)
        if app.policy.digest != policy_sha256 or scope.tenant_id not in app.policy.tenants:
            raise JeevesHostRuntimeError("dispatcher policy or tenant not provisioned")
        info = app.store.path.stat()
        self._database_identity = (info.st_dev, info.st_ino)

    @staticmethod
    def _identifier(value: object) -> str:
        if (type(value) is not str or not 1 <= len(value) <= 192
                or value.strip() != value
                or any(ord(ch) < 33 or ord(ch) > 126 for ch in value)):
            raise JeevesHostRuntimeError("dispatcher client identifier must be bounded ASCII")
        return value

    @staticmethod
    def _namespace(context: JeevesHostContext) -> tuple[str, str, str, str]:
        return (context.tenant_id, context.project_id, context.principal_id, context.run_id)

    def _scoped(self, domain: str, value: object) -> str:
        value = self._identifier(value)
        material = json.dumps(
            ["skeleton.jeeves.dispatch.scope.v1", domain, *self._namespace(self._scope), value],
            ensure_ascii=True, separators=(",", ":"), allow_nan=False,
        ).encode("ascii")
        return "app-" + domain + "-" + sha256(material).hexdigest()

    def _app(self):
        from skeleton.automation.agents.swarm_dispatch_app import LocalDispatcherApplication
        app = LocalDispatcherApplication(self._directory)
        info = app.store.path.stat()
        if (app.policy.digest != self._policy_sha256
                or self._scope.tenant_id not in app.policy.tenants
                or (info.st_dev, info.st_ino) != self._database_identity):
            raise JeevesHostRuntimeError("dispatcher binding identity changed")
        return app

    def _submit_body(self, supplied: dict, tenant: str) -> dict:
        required = {"task_id", "operation", "input"}
        optional = {"priority", "dependencies", "singleton", "timer_ms", "event",
                    "bindings", "binding_deadline_ms"}
        if not required.issubset(supplied) or not set(supplied).issubset(required | optional):
            raise JeevesHostRuntimeError("invalid host submission properties")
        operation = self._identifier(supplied["operation"])
        priority = supplied.get("priority", 100)
        # Reserved urgent lanes belong to the dispatcher administrator,
        # never to an application caller or a generated task argument.
        if type(priority) is not int or not 50 <= priority <= 1000:
            raise JeevesHostRuntimeError("host priority outside granted background lanes")
        deps = supplied.get("dependencies", [])
        if (type(deps) is not list or len(deps) > 32
                or any(type(dep) is not str for dep in deps) or len(set(deps)) != len(deps)):
            raise JeevesHostRuntimeError("invalid host dependency set")
        body = {"kind": "submit", "tenant": tenant,
                "task_id": self._scoped("task", supplied["task_id"]),
                "operation": operation, "input": supplied["input"],
                "priority": priority,
                "dependencies": [self._scoped("task", dep) for dep in deps]}
        if "singleton" in supplied:
            body["singleton"] = self._scoped("singleton", supplied["singleton"])
        for field in ("timer_ms", "event", "binding_deadline_ms"):
            if field in supplied:
                body[field] = supplied[field]
        if "bindings" in supplied:
            from skeleton.automation.agents.swarm_dispatch_bindings import BindingError, parse_bindings
            try:
                bindings = parse_bindings(supplied["bindings"], supplied["input"],
                                          task_id=supplied["task_id"])
            except BindingError as exc:
                raise JeevesHostRuntimeError("invalid host result bindings") from exc
            body["bindings"] = [
                {**binding.record(),
                 "source_request_id": self._scoped("request", binding.source_request_id),
                 "source_task_id": self._scoped("task", binding.source_task_id)}
                for binding in bindings
            ]
        return body

    def execute(self, *, context: JeevesHostContext, action: str,
                request_id: str, arguments: Mapping[str, Any]) -> dict:
        from skeleton.automation.agents.swarm_dispatch_app import _canonical, _json_object
        if (not isinstance(context, JeevesHostContext)
                or self._namespace(context) != self._namespace(self._scope)):
            raise JeevesHostRuntimeError("dispatcher request crossed authenticated run scope")
        request_id = self._identifier(request_id)
        if (type(action) is not str or action not in self._ACTIONS
                or type(arguments) is not dict):
            raise JeevesHostRuntimeError("unsupported dispatcher host request")
        # Round-trip immutable exact bytes. The authorizer receives those
        # bytes, never a mutable dictionary it can accidentally rewrite.
        canonical = _canonical(arguments)
        supplied = _json_object(canonical)
        body: dict[str, Any] = {}
        tenant = self._scope.tenant_id
        if action == "submit":
            body = self._submit_body(supplied, tenant)
        elif action == "workflow-submit":
            if set(supplied) != {"deadline_ms", "jobs"} or type(supplied["jobs"]) is not list or not 1 <= len(supplied["jobs"]) <= 32:
                raise JeevesHostRuntimeError("invalid host workflow graph")
            scoped_jobs = []
            child_authorizations = []
            for node in supplied["jobs"]:
                if type(node) is not dict or "request_id" not in node or "binding_deadline_ms" in node:
                    raise JeevesHostRuntimeError("invalid host workflow node")
                client_request = self._identifier(node["request_id"])
                original = {key: value for key, value in node.items() if key != "request_id"}
                scoped = self._submit_body(original, tenant)
                scoped.pop("kind")
                scoped.pop("tenant")
                scoped["request_id"] = self._scoped("request", client_request)
                scoped_jobs.append(scoped)
                child_authorizations.append((client_request, _canonical(original)))
            body = {"deadline_ms": supplied["deadline_ms"], "jobs": scoped_jobs}
        elif action in ("workflow-status", "workflow-cancel"):
            if set(supplied) != {"workflow_id"}:
                raise JeevesHostRuntimeError("exact client workflow identity required")
            body = {"workflow_id": self._scoped("workflow", supplied["workflow_id"])}
            if action == "workflow-cancel":
                body.update({"kind": action, "tenant": tenant})
        elif action == "cancel-pending":
            if set(supplied) != {"request_id"}:
                raise JeevesHostRuntimeError("exact pending client request identity required")
            body = {"kind": action, "tenant": tenant,
                    "request_id": self._scoped("request", supplied["request_id"])}
        elif action == "command":
            if set(supplied) != {"request_id"}:
                raise JeevesHostRuntimeError("exact client request identity required")
            self._identifier(supplied["request_id"])
        elif action == "signal":
            if set(supplied) != {"task_id", "event_id", "selector", "evidence"}:
                raise JeevesHostRuntimeError("invalid host event request")
            body = {"kind": "signal", "tenant": tenant,
                    "task_id": self._scoped("task", supplied["task_id"]),
                    "event_id": self._scoped("event", supplied["event_id"]),
                    "selector": self._identifier(supplied["selector"]),
                    "evidence": supplied["evidence"]}
        else:
            if set(supplied) != {"task_id"}:
                raise JeevesHostRuntimeError("exact client task identity required")
            body = {"kind": action, "tenant": tenant,
                    "task_id": self._scoped("task", supplied["task_id"])}
        authorization = JeevesDispatchAuthorization(
            context, action, request_id, canonical, self._policy_sha256,
        )
        try:
            permitted = self._authorize(authorization)
        except Exception:
            raise JeevesHostRuntimeError("dispatcher host authorization unavailable") from None
        if permitted is not True:
            raise JeevesHostRuntimeError("dispatcher host authorization denied")
        # Re-open the same provisioned policy and inode before every
        # authorized operation. Authentication never opens a new service.
        if action == "workflow-submit":
            # The graph grant does not waive per-operation host grants.
            for child_id, child_bytes in child_authorizations:
                try:
                    permitted = self._authorize(JeevesDispatchAuthorization(
                        context, "submit", child_id, child_bytes, self._policy_sha256,
                    ))
                except Exception:
                    raise JeevesHostRuntimeError("workflow child authorization unavailable") from None
                if permitted is not True:
                    raise JeevesHostRuntimeError("workflow child authorization denied")
        app = self._app()
        if action == "workflow-submit":
            return app.enqueue_workflow(tenant, self._scoped("workflow", request_id), body)
        if action == "workflow-status":
            return app.workflow_status(tenant, body["workflow_id"])
        if action == "command":
            found = app.inbox.command(self._scoped("request", supplied["request_id"]))
            return {"found": found is not None, "command": found}
        if action == "result":
            return app.result(tenant, body["task_id"])
        if action == "submit" and body["operation"] not in app.policy.operations:
            raise JeevesHostRuntimeError("operation not provisioned by dispatcher")
        return app.enqueue(self._scoped("request", request_id), body)


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
        idle_handlers: Mapping[Any, Callable[..., Any]] | None = None,
        idle_authorize: Callable[..., bool] | None = None,
        idle_verify_result: Callable[..., bool] | None = None,
        idle_telemetry_probe: Callable[..., Any] | None = None,
        idle_policy: Any = None,
        dispatcher_directory: str | Path | None = None,
        dispatcher_policy_sha256: str | None = None,
        dispatcher_authorize: Callable[[JeevesDispatchAuthorization], bool] | None = None,
    ) -> None:
        if not isinstance(scope, JeevesHostContext):
            raise JeevesHostRuntimeError("authenticated JeevesHostContext required")
        self.scope = scope
        self._lock = RLock()
        self._closed = False
        flags = (dispatcher_directory is not None, dispatcher_policy_sha256 is not None,
                 dispatcher_authorize is not None)
        if any(flags) and not all(flags):
            raise JeevesHostRuntimeError("dispatcher binding requires all three host provisions")
        self._dispatch_gateway = None if not all(flags) else JeevesDispatcherGateway(
            directory=dispatcher_directory, policy_sha256=dispatcher_policy_sha256,
            scope=scope, authorize=dispatcher_authorize,
        )
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
            idle_handlers=idle_handlers,
            idle_authorize=idle_authorize,
            idle_verify_result=idle_verify_result,
            idle_telemetry_probe=idle_telemetry_probe,
            idle_policy=idle_policy,
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

    def dispatch_request(
        self, *, context: JeevesHostContext, action: str, request_id: str,
        arguments: Mapping[str, Any],
    ) -> dict:
        """Send one exact, host-authorized request to the installed dispatcher."""
        with self._lock:
            self._require_live()
            self._context(context)
            if self._dispatch_gateway is None:
                raise JeevesHostRuntimeError("dispatcher not bound to this application runtime")
            return self._dispatch_gateway.execute(
                context=context, action=action, request_id=request_id, arguments=arguments,
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
                "idle_learning": {
                    "worker_enabled": self.workbench.idle_executor is not None,
                    "status": "host-invoked; cooperative worker preemption on live telemetry",
                    "custody": self.workbench.idle_executor.history_head()
                    if self.workbench.idle_executor is not None else None,
                    "auto_replay": False,
                },
                "runtime_availability": "requires host readiness and execution grants",
                "weights_loaded_by_jeeves": False,
                **({"dispatcher": {"bound": True, "scope": "authenticated-run",
                                   "execution": "external-local-service"}}
                   if self._dispatch_gateway is not None else {}),
            }

    def stage_candidate_model_release(
        self, proposal, *, context: JeevesHostContext, observed_at_ns: int,
    ):
        """Host-only staging of verified, consumed candidate weights.

        This records a proposal, not a model deployment or a promotion permit.
        """
        with self._lock:
            self._require_live()
            self._context(context, observed_at_ns=observed_at_ns)
            return self.workbench.stage_model_release(
                proposal, actor_id=context.principal_id,
                at_ns=observed_at_ns,
            )

    def record_external_model_release(
        self, proposal_digest: str, receipt, *,
        context: JeevesHostContext,
        expected_version: int,
        runtime_admission=None, rollback_proof=None,
    ):
        """Bind host-confirmed external model admission or rollback receipts."""
        with self._lock:
            self._require_live()
            self._context(context)
            if receipt.actor_id != context.principal_id:
                raise JeevesHostRuntimeError("external model release actor differs from host")
            return self.workbench.observe_model_release(
                proposal_digest, receipt, expected_version=expected_version,
                runtime_admission=runtime_admission,
                rollback_proof=rollback_proof,
            )

    def propose_idle_shadow_work(
        self, *, context: JeevesHostContext,
        telemetry, host_now_ns: int,
        active_work_ids: tuple[str, ...] = (),
    ):
        """Host-only scheduling proposal based on live machine telemetry."""
        with self._lock:
            self._require_live()
            self._context(context)
            return self.workbench.propose_idle_shadow_work(
                telemetry, host_now_ns=host_now_ns,
                active_work_ids=active_work_ids,
            )

    def invoke_idle_shadow_work(
        self, *, context: JeevesHostContext,
        intake_id: str, plan, assignment, telemetry, host_now_ns: int,
    ):
        """Dispatch exactly one externally permitted idle job with durable custody."""
        with self._lock:
            self._require_live()
            live = self._context(context)
            return self.workbench.invoke_idle_shadow_work(
                intake_id=intake_id, plan=plan,
                assignment=assignment, telemetry=telemetry,
                host_now_ns=host_now_ns, context=live,
            )

    def pending_idle_effects(self, *, context: JeevesHostContext,
                             limit: int = 100):
        """Observe uncertain idle effects without retriggering them."""
        with self._lock:
            self._require_live()
            self._context(context)
            return self.workbench.pending_idle_effects(limit=limit)

    def reconcile_idle_effect(
        self, *, context: JeevesHostContext,
        intent_digest: str, external_event_digest: str,
        confirmed_completed: bool, observed_at_ns: int,
        verify_external: Callable[[str, str, JeevesHostContext], bool],
    ):
        """Host-only external reconciliation for an interrupted idle worker."""
        if not callable(verify_external):
            raise JeevesHostRuntimeError("independent host recovery verifier required")
        with self._lock:
            self._require_live()
            self._context(context, observed_at_ns=observed_at_ns)
            if self.workbench.idle_executor is None:
                raise JeevesHostRuntimeError("idle worker has not been enabled")
            return self.workbench.idle_executor.reconcile(
                intent_digest,
                external_event_digest=external_event_digest,
                confirmed_completed=confirmed_completed,
                observed_at_ns=observed_at_ns,
                verify_external=lambda intent, proof: (
                    verify_external(intent, proof, context) is True
                ),
            )

    def pending_source_edits(self, *, context: JeevesHostContext,
                             limit: int = 100):
        """Host operator view of unresolved local source commits."""
        with self._lock:
            self._require_live()
            self._context(context)
            return self.workbench.pending_source_edits(limit=limit)

    def reconcile_source_edit(self, plan_digest: str, *,
                              context: JeevesHostContext,
                              observed_at_ns: int):
        """Resolve an interrupted local edit without executing it again."""
        with self._lock:
            self._require_live()
            self._context(context, observed_at_ns=observed_at_ns)
            return self.workbench.reconcile_source_edit(
                plan_digest, observed_at_ns=observed_at_ns,
            )

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
    "JeevesDispatchAuthorization", "JeevesDispatcherGateway",
]
