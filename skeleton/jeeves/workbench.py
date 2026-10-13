"""Tenant-scoped Jeeves workbench for the unified Skeleton application.

This is a concrete assembly adapter over existing owners, not another AI
service. The host supplies the repository, private state location and all
permissions. The workbench constructs one coherent Jeeves tool/runtime surface:

  * canonical feature + editor catalog and source atlas;
  * tenant-scoped shadow knowledge queue;
  * durable Supervisor/Secretary/Worker journal;
  * optional host-registered B014 creator handlers;
  * the existing ToolRegistry, ToolExecutor and exact host-grant routing.

No initial file scan, research crawl, learning admission, model training or
external app operation is triggered in the constructor. A model request cannot
invent an authorization callback or turn a declaration into a live handler.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
import os
from pathlib import Path
from threading import RLock
from typing import Any

from skeleton.jeeves.ai.creator_runbook_runtime import (
    CreatorRunbook, CreatorRunbookRunner,
)
from skeleton.jeeves.ai.creator_runbook_store import CreatorRunbookStore
from skeleton.jeeves.ai.orchestration_store import DurableOrchestrLedger
from skeleton.jeeves.agent.capability_dispatch import (
    HostCapabilityBinding, JeevesCapabilityDispatcher,
)
from skeleton.jeeves.agent.orchestrated_capability_runtime import (
    JeevesOrchestratedCapabilityRuntime,
)
from skeleton.jeeves.agent.tools import ToolExecutor, ToolRegistry
from skeleton.ai.training.shadow_weight_store import DurableShadowWeightPipeline
from skeleton.jeeves.repository_file_atlas import JeevesRepositoryFileAtlas
from skeleton.jeeves.core import Jeeves

MAX_WORKBENCH_ID = 192


class JeevesWorkbenchError(ValueError):
    """Invalid workbench scope, filesystem owner or host wiring."""


def _identity(value: str, name: str) -> str:
    if (not isinstance(value, str) or not value
            or value != value.strip() or len(value) > MAX_WORKBENCH_ID
            or any(ord(char) < 33 or char in "/\\\x00" for char in value)):
        raise JeevesWorkbenchError(f"{name} must be a bounded identity")
    return value


def _private_directory(base: Path, tenant: str, project: str) -> Path:
    """Create one opaque namespace without ever placing user IDs in paths."""
    namespace = sha256((tenant + "\x00" + project).encode("utf-8")).hexdigest()
    output = base / "jeeves" / namespace
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (output.is_symlink() or not output.resolve().is_relative_to(base)
            or (base / "jeeves").is_symlink()):
        raise JeevesWorkbenchError("workbench namespace must remain under host state")
    try:
        output.chmod(0o700)
    except OSError as exc:
        raise JeevesWorkbenchError("cannot enforce private workbench directory mode") from exc
    return output


class JeevesWorkbench:
    """Host-owned concrete Jeeves runtime workbench for one tenant/project.

    The workbench holds all stateful references so each tool registry uses
    consistent scopes, and the host can close the SQLite-backed journals when
    its project/session lifecycle ends.
    """

    def __init__(
        self, *,
        root: str | Path,
        state_directory: str | Path,
        tenant_id: str,
        project_id: str,
        principal_id: str,
        read_authorize: Callable[..., bool],
        orchestration_authorize: Callable[..., bool],
        core: Jeeves | None = None,
        source_read_authorize: Callable[..., bool] | None = None,
        shadow_write_authorize: Callable[..., bool] | None = None,
        shadow_review_verify: Callable[..., bool] | None = None,
        shadow_admission_verify: Callable[..., bool] | None = None,
        shadow_consume_verify: Callable[..., bool] | None = None,
        creator_handlers: Mapping[str, Callable[..., Any]] | None = None,
        creator_authorize: Callable[..., bool] | None = None,
        source_edit_authorize: Callable[..., bool] | None = None,
        source_edit_handler: Callable[..., Any] | None = None,
        source_edit_allowlist: Sequence[str] | None = None,
        release_verify_external: Callable[..., bool] | None = None,
        idle_handlers: Mapping[Any, Callable[..., Any]] | None = None,
        idle_authorize: Callable[..., bool] | None = None,
        idle_verify_result: Callable[..., bool] | None = None,
        idle_policy: Any = None,
    ) -> None:
        from skeleton.jeeves.app_capability_bridge import _root
        self.root = _root(root)
        self.tenant_id = _identity(tenant_id, "tenant_id")
        self.project_id = _identity(project_id, "project_id")
        self.principal_id = _identity(principal_id, "principal_id")
        if not callable(read_authorize) or not callable(orchestration_authorize):
            raise JeevesWorkbenchError("independent host read/orchestration authorizers required")
        if (creator_handlers is None) != (creator_authorize is None):
            raise JeevesWorkbenchError("creator handlers require a paired host authorizer")
        if source_edit_handler is not None and source_edit_allowlist is not None:
            raise JeevesWorkbenchError("choose injected editor or opt-in local editor, not both")
        if (source_edit_authorize is None) != (source_edit_handler is None and source_edit_allowlist is None):
            raise JeevesWorkbenchError("source editing requires a host authorizer and an explicit handler or allowlist")
        if source_edit_authorize is not None and not callable(source_edit_authorize):
            raise JeevesWorkbenchError("source edit authorization must be callable")
        if source_edit_handler is not None and not callable(source_edit_handler):
            raise JeevesWorkbenchError("source edit handler must be callable")
        if creator_handlers is not None and not isinstance(creator_handlers, Mapping):
            raise JeevesWorkbenchError("creator handlers must be an explicit mapping")
        if shadow_write_authorize is not None and any(
            not callable(f) for f in (
                shadow_review_verify, shadow_admission_verify, shadow_consume_verify,
            )
        ):
            raise JeevesWorkbenchError("writable shadow queues require independent verifiers")
        base = Path(state_directory)
        if not base.is_absolute():
            raise JeevesWorkbenchError("host state directory must be absolute")
        base = base.resolve()
        if base == self.root or base.is_relative_to(self.root):
            raise JeevesWorkbenchError("Jeeves runtime databases must be outside repository")
        self._scope = _private_directory(base, self.tenant_id, self.project_id)
        self._lock = RLock()
        self._closed = False
        if core is not None and not isinstance(core, Jeeves):
            raise JeevesWorkbenchError("core must be an existing Jeeves instance")
        self._core = core if core is not None else Jeeves()
        self._read_authorize = read_authorize
        self._orchestration_authorize = orchestration_authorize
        self._source_read_authorize = source_read_authorize
        self._shadow_write_authorize = shadow_write_authorize
        self._shadow_review_verify = shadow_review_verify
        self._shadow_admission_verify = shadow_admission_verify
        self._shadow_consume_verify = shadow_consume_verify
        self._creator_handlers = creator_handlers
        self._creator_authorize = creator_authorize
        self._source_edit_authorize = source_edit_authorize
        self._source_edit_handler = source_edit_handler
        self._local_source_editor = None
        self._source_edit_allowlist = source_edit_allowlist
        if release_verify_external is not None and not callable(release_verify_external):
            raise JeevesWorkbenchError("model release verification requires host callback")
        self._release_verify_external = release_verify_external
        provided_idle = (idle_handlers, idle_authorize, idle_verify_result)
        if any(value is not None for value in provided_idle) and not all(
            value is not None for value in provided_idle
        ):
            raise JeevesWorkbenchError("idle execution needs handlers, authorizer and verifier together")
        if idle_policy is not None and idle_handlers is None:
            raise JeevesWorkbenchError("idle policy requires a real host worker")
        self._idle_handlers = idle_handlers
        self._idle_authorize = idle_authorize
        self._idle_verify_result = idle_verify_result
        self._idle_policy = idle_policy
        self._open_runbooks: list[CreatorRunbookStore] = []
        self.atlas: JeevesRepositoryFileAtlas | None = None
        self.shadow: DurableShadowWeightPipeline | None = None
        self.orchestration: DurableOrchestrLedger | None = None
        self.model_releases = None
        self.idle_executor = None
        try:
            if self._source_edit_allowlist is not None:
                from skeleton.jeeves.source_edit_host import JeevesAtomicSourceEditor
                self._local_source_editor = JeevesAtomicSourceEditor(
                    repo_root=self.root,
                    journal_path=self._scope / "source_edits.sqlite",
                    allowed_roots=self._source_edit_allowlist,
                )
                self._source_edit_handler = self._local_source_editor
            self.atlas = JeevesRepositoryFileAtlas(
                self.root, self._scope / "source_atlas.sqlite",
            )
            self.shadow = DurableShadowWeightPipeline(
                self._scope / "shadow_evidence.sqlite",
            )
            self.orchestration = DurableOrchestrLedger(
                self._scope / "orchestration.sqlite",
                authorize=self._authorize_orchestration,
            )
            if self._release_verify_external is not None:
                from skeleton.ai.training.model_release_journal import ModelReleaseJournal
                self.model_releases = ModelReleaseJournal(
                    self._scope / "model_release_evidence.sqlite",
                    verify_external=self._scoped_release_verify,
                )
            if self._idle_handlers is not None:
                from skeleton.jeeves.ai.idle_learning_scheduler import IdleLearningPolicy
                from skeleton.jeeves.ai.idle_learning_runtime import JeevesIdleWorkExecutor
                if self._idle_policy is not None and not isinstance(self._idle_policy, IdleLearningPolicy):
                    raise JeevesWorkbenchError("idle policy must be a typed host policy")
                self.idle_executor = JeevesIdleWorkExecutor(
                    store_path=self._scope / "idle_effects.sqlite",
                    policy=self._idle_policy or IdleLearningPolicy(),
                    host_authorize=self._scoped_idle_authorize,
                    handlers={
                        kind: self._scoped_idle_handler(handler)
                        for kind, handler in self._idle_handlers.items()
                    },
                    verify_result=self._scoped_idle_verify,
                )
            self.tools = self._build_tools()
            self.executor = ToolExecutor(self.tools)
        except BaseException:
            self.close()
            raise

    def _ensure_open(self) -> None:
        if self._closed:
            raise JeevesWorkbenchError("Jeeves workbench is closed")

    def _authorize_orchestration(self, actor: str, authority: Any,
                                 action: str, digest: str) -> bool:
        return self._orchestration_authorize(
            self.tenant_id, self.project_id, self.principal_id,
            actor, authority, action, digest,
        ) is True

    def _scoped_read(self, tool: str, digest: str, context: Any) -> bool:
        if not self._context_scoped(context):
            return False
        return self._read_authorize(
            self.tenant_id, self.project_id, self.principal_id,
            tool, digest, context,
        ) is True

    def _scoped_source(self, tool: str, digest: str, context: Any) -> bool:
        return (
            self._context_scoped(context)
            and self._source_read_authorize is not None
            and self._source_read_authorize(
                self.tenant_id, self.project_id, self.principal_id,
                tool, digest, context,
            ) is True
        )

    def _scoped_shadow_write(self, tool: str, digest: str, context: Any) -> bool:
        return (
            self._context_scoped(context)
            and self._shadow_write_authorize is not None
            and self._shadow_write_authorize(
                self.tenant_id, self.project_id, self.principal_id,
                tool, digest, context,
            ) is True
        )

    def _context_scoped(self, context: Any) -> bool:
        return (
            getattr(context, "user_id", None) == self.principal_id
            and getattr(context, "metadata", {}).get("tenant_id") == self.tenant_id
            and getattr(context, "metadata", {}).get("project_id") == self.project_id
        )

    def _scoped_review(self, record: Any, review: Any, context: Any) -> bool:
        return (
            self._context_scoped(context)
            and self._shadow_review_verify is not None
            and self._shadow_review_verify(record, review, context) is True
        )

    def _scoped_training(self, record: Any, manifest: str, evidence: str,
                         context: Any) -> bool:
        return (
            self._context_scoped(context)
            and self._shadow_admission_verify is not None
            and self._shadow_admission_verify(
                record, manifest, evidence, context,
            ) is True
        )

    def _scoped_candidate(self, record: Any, candidate: str,
                          context: Any) -> bool:
        return (
            self._context_scoped(context)
            and self._shadow_consume_verify is not None
            and self._shadow_consume_verify(record, candidate, context) is True
        )

    def _scoped_release_verify(self, proposal: Any, receipt: Any) -> bool:
        return (
            self._release_verify_external is not None
            and self._release_verify_external(
                self.tenant_id, self.project_id, self.principal_id,
                proposal, receipt,
            ) is True
        )

    def stage_model_release(self, proposal: Any, *,
                            actor_id: str, at_ns: int):
        """Stage a qualified release proposal; never deploy model weights."""
        from skeleton.ai.training.shadow_candidate_gate import CandidateReleaseProposal
        with self._lock:
            self._ensure_open()
            if self.model_releases is None:
                raise JeevesWorkbenchError("model release owner was not enabled by host")
            if not isinstance(proposal, CandidateReleaseProposal):
                raise JeevesWorkbenchError("only independently qualified release proposals allowed")
            return self.model_releases.propose(
                proposal, actor_id=actor_id, at_ns=at_ns,
            )

    def observe_model_release(self, proposal_digest: str, receipt: Any, *,
                              expected_version: int,
                              runtime_admission=None, rollback_proof=None):
        """Record external model-serving admission/rollback evidence."""
        with self._lock:
            self._ensure_open()
            if self.model_releases is None:
                raise JeevesWorkbenchError("model release owner was not enabled by host")
            return self.model_releases.transition(
                proposal_digest, receipt, expected_version=expected_version,
                runtime_admission=runtime_admission,
                rollback_proof=rollback_proof,
            )

    def _scoped_creator(self, command: Any, context: Any) -> bool:
        if not self._context_scoped(context) or self._creator_authorize is None:
            return False
        if getattr(command, "project_id", None) != self.project_id:
            return False
        # Existing creator tool requires a host decision over the exact typed
        # command, tenant and authenticated principal on EVERY dispatch.
        return self._creator_authorize(command, context) is True

    def _build_tools(self) -> ToolRegistry:
        if self.atlas is None or self.shadow is None:
            raise JeevesWorkbenchError("workbench state owners are unavailable")
        registry = self._core.app_tool_registry(
            root=self.root,
            file_atlas=self.atlas,
            file_atlas_read_authorize=self._scoped_read,
            source_read_authorize=self._scoped_source
            if self._source_read_authorize is not None else None,
            shadow_pipeline=self.shadow,
            shadow_read_authorize=self._scoped_read,
            shadow_write_authorize=self._scoped_shadow_write
            if self._shadow_write_authorize is not None else None,
            shadow_review_verify=self._scoped_review,
            shadow_admission_verify=self._scoped_training,
            shadow_consume_verify=self._scoped_candidate,
            creator_handlers=self._creator_handlers,
            creator_authorize=self._scoped_creator
            if self._creator_authorize is not None else None,
        )
        if self._source_edit_handler is not None:
            from skeleton.jeeves.source_edit_gateway import register_source_edit_tools
            register_source_edit_tools(
                registry, atlas=self.atlas,
                authorize=self._scoped_source_edit,
                edit=self._host_source_edit,
                read_authorize=self._scoped_read,
            )
        return registry

    def _scoped_source_edit(self, plan: Any, context: Any) -> bool:
        return (
            self._context_scoped(context)
            and plan.project_id == self.project_id
            and self._source_edit_authorize is not None
            and self._source_edit_authorize(plan, context) is True
        )

    def _host_source_edit(self, plan: Any, context: Any):
        if not self._scoped_source_edit(plan, context):
            raise JeevesWorkbenchError("host denied source edit scope")
        return self._source_edit_handler(plan, context)

    def pending_source_edits(self, *, limit: int = 100):
        """List unresolved local editing effects for host/operator recovery."""
        with self._lock:
            self._ensure_open()
            if self._local_source_editor is None:
                raise JeevesWorkbenchError("local editor was not explicitly enabled")
            return self._local_source_editor.pending_edits(limit=limit)

    def reconcile_source_edit(self, plan_digest: str, *, observed_at_ns: int):
        """Reconcile a crash without replaying any file mutation."""
        with self._lock:
            self._ensure_open()
            if self._local_source_editor is None:
                raise JeevesWorkbenchError("local editor was not explicitly enabled")
            outcome = self._local_source_editor.reconcile_pending(
                plan_digest, observed_at_ns=observed_at_ns,
            )
            return {
                "schema": "jeeves.source_edit_reconciliation.v1",
                "plan_digest": plan_digest, "outcome": outcome,
                "external_effect_replayed": False,
            }

    def refresh_source_atlas(self, *, observed_at_ns: int,
                             hash_contents: bool = False):
        """Host-invoked full source observation; never model-triggered."""
        with self._lock:
            self._ensure_open()
            return self.atlas.refresh(
                observed_at_ns=observed_at_ns, hash_contents=hash_contents,
            )

    def apply_source_changes(self, changed_paths: list[str], *,
                             observed_at_ns: int, hash_contents: bool = False):
        """Host-invoked incremental atlas refresh."""
        with self._lock:
            self._ensure_open()
            return self.atlas.apply_changes(
                changed_paths, observed_at_ns=observed_at_ns,
                hash_contents=hash_contents,
            )

    def capability_dispatcher(self, bindings: Sequence[HostCapabilityBinding], *,
                              readiness: Callable[..., Any],
                              authorize: Callable[..., bool]) -> JeevesCapabilityDispatcher:
        if not callable(readiness) or not callable(authorize):
            raise JeevesWorkbenchError("capability host proofs must be injected")
        with self._lock:
            self._ensure_open()

            def scoped_readiness(feature: str, owner: str, context: Any):
                if not self._context_scoped(context):
                    raise JeevesWorkbenchError("capability readiness crosses active workbench")
                return readiness(feature, owner, context)

            def scoped_authorize(intent: Any, context: Any) -> bool:
                return (
                    self._context_scoped(context)
                    and intent.tenant_id == self.tenant_id
                    and intent.project_id == self.project_id
                    and authorize(intent, context) is True
                )

            return JeevesCapabilityDispatcher(
                registry=self.tools, executor=self.executor,
                bindings=bindings, readiness=scoped_readiness,
                authorize=scoped_authorize, root=self.root,
            )

    def orchestrated_runtime(
        self, dispatcher: JeevesCapabilityDispatcher, *,
        verify_result: Callable[..., str | None],
    ) -> JeevesOrchestratedCapabilityRuntime:
        if not callable(verify_result):
            raise JeevesWorkbenchError("host completion verifier required")
        with self._lock:
            self._ensure_open()
            return JeevesOrchestratedCapabilityRuntime(
                ledger=self.orchestration, dispatcher=dispatcher,
                verify_result=verify_result,
            )

    def compile_creator_runbook(self, project_id: str, steps: list[Mapping[str, Any]]):
        from skeleton.jeeves.app_capability_bridge import creator_plan
        if project_id != self.project_id:
            raise JeevesWorkbenchError("creator workflow crosses active workbench project")
        with self._lock:
            self._ensure_open()
            return creator_plan(project_id, steps)

    def open_creator_runbook(self, compiled_plan: Mapping[str, Any]) -> CreatorRunbookRunner:
        """Resume exact-plan state; caller must provide grants for each effect."""
        with self._lock:
            self._ensure_open()
            plan = CreatorRunbook(compiled_plan)
            if plan.project_id != self.project_id:
                raise JeevesWorkbenchError("creator runbook belongs to another project")
            path = self._scope / ("creator_" + plan.plan_sha256 + ".sqlite")
            store = CreatorRunbookStore(path, plan_sha256=plan.plan_sha256)
            try:
                runner = CreatorRunbookRunner(
                    plan, executor=self.executor,
                    persist=store.persist, restored=store.load(),
                )
            except BaseException:
                store.close()
                raise
            self._open_runbooks.append(store)
            return runner

    def _scoped_idle_authorize(self, assignment, intent: str, context) -> bool:
        return (
            self._context_scoped(context)
            and self._idle_authorize is not None
            and self._idle_authorize(
                self.tenant_id, self.project_id, self.principal_id,
                assignment, intent, context,
            ) is True
        )

    def _scoped_idle_handler(self, handler):
        def invoke(assignment, context):
            if not self._context_scoped(context):
                raise JeevesWorkbenchError("idle worker crossed tenant/project scope")
            return handler(assignment, context)
        return invoke

    def _scoped_idle_verify(self, assignment, receipt, context) -> bool:
        return (
            self._context_scoped(context)
            and self._idle_verify_result is not None
            and self._idle_verify_result(
                self.tenant_id, self.project_id, self.principal_id,
                assignment, receipt, context,
            ) is True
        )

    @staticmethod
    def _idle_candidate(record):
        """Derive a work item exclusively from current verified shadow custody."""
        from skeleton.jeeves.ai.idle_learning_scheduler import (
            IdleWorkCandidate, IdleWorkKind,
        )
        intake = record.intake
        kind = {
            "inbox": IdleWorkKind.EVIDENCE_CORROBORATION,
            "quarantined": IdleWorkKind.SOURCE_RESEARCH,
            "corroborated": IdleWorkKind.CANDIDATE_PREPARATION,
        }.get(record.state.value)
        if kind is None:
            raise JeevesWorkbenchError("shadow intake is not eligible for idle work")
        scope = intake.target_scope
        return IdleWorkCandidate(
            work_id="shadow-" + sha256(intake.intake_id.encode("utf-8")).hexdigest()[:48],
            scope_id=scope if len(scope) <= 192 else "scope-" + sha256(scope.encode("utf-8")).hexdigest(),
            source_digest=intake.digest,
            kind=kind,
            relevance_ppm=intake.relevance_ppm,
            novelty_ppm=intake.novelty_ppm,
            evidence_confidence_ppm=intake.confidence_ppm,
            created_at_ns=intake.observed_at_ns,
            cost_units=2 if kind is IdleWorkKind.SOURCE_RESEARCH else 1,
            requires_network=kind is IdleWorkKind.SOURCE_RESEARCH,
        )

    def invoke_idle_shadow_work(
        self, *, intake_id: str, plan, assignment, telemetry,
        host_now_ns: int, context,
    ):
        """Execute one host-approved idle task from fresh durable shadow state.

        The caller cannot substitute model-authored work parameters: every
        candidate field is recomputed from the tenant's current shadow record.
        The idle executor persists the intent before entering a worker handler.
        """
        from skeleton.jeeves.ai.idle_learning_scheduler import (
            HostIdleTelemetry, IdleWorkPlan, IdleWorkAssignment,
        )
        from skeleton.jeeves.agent.tools import ToolExecutionContext
        if not isinstance(context, ToolExecutionContext) or not self._context_scoped(context):
            raise JeevesWorkbenchError("host idle request has wrong tenant/project")
        if not isinstance(plan, IdleWorkPlan) or not isinstance(assignment, IdleWorkAssignment):
            raise JeevesWorkbenchError("idle dispatch requires typed plan and assignment")
        if not isinstance(telemetry, HostIdleTelemetry):
            raise JeevesWorkbenchError("host telemetry is required for actual work")
        with self._lock:
            self._ensure_open()
            if self.idle_executor is None:
                raise JeevesWorkbenchError("no host idle worker handlers configured")
            record = self.shadow.get(intake_id)
            if record is None:
                raise JeevesWorkbenchError("idle work refers to unknown shadow intake")
            candidate = self._idle_candidate(record)
            return self.idle_executor.invoke_one(
                plan=plan, assignment=assignment, candidate=candidate,
                telemetry=telemetry, host_now_ns=host_now_ns,
                context=context,
            )

    def pending_idle_effects(self, *, limit: int = 100):
        """List unresolved idle work for host-only, no-retry reconciliation."""
        with self._lock:
            self._ensure_open()
            if self.idle_executor is None:
                raise JeevesWorkbenchError("idle worker is not configured")
            return self.idle_executor.pending(limit=limit)

    def propose_idle_shadow_work(
        self, telemetry, *,
        host_now_ns: int,
        active_work_ids: tuple[str, ...] = (),
        policy=None,
    ):
        """Propose non-executing idle jobs using actual shadow custody only."""
        from skeleton.jeeves.ai.idle_learning_scheduler import (
            HostIdleTelemetry, JeevesIdleLearningScheduler,
        )
        if not isinstance(telemetry, HostIdleTelemetry):
            raise JeevesWorkbenchError("trusted host idle telemetry required")
        with self._lock:
            self._ensure_open()
            if self.idle_executor is not None:
                current_policy = self.idle_executor.policy
                if policy is not None and policy != current_policy:
                    raise JeevesWorkbenchError("proposal policy must equal host execution policy")
            else:
                current_policy = policy
            records = [
                record for record in self.shadow.entries(limit=1000)
                if record.state.value in ("inbox", "quarantined", "corroborated")
            ]
            candidates = tuple(self._idle_candidate(record) for record in records)
            return JeevesIdleLearningScheduler(policy=current_policy).propose(
                candidates, telemetry, host_now_ns=host_now_ns,
                active_work_ids=active_work_ids,
            )

    def source_context(self, objective: str, **kwargs: Any):
        with self._lock:
            self._ensure_open()
            return self._core.app_source_context(objective, atlas=self.atlas, **kwargs)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for store in getattr(self, "_open_runbooks", ()):
                store.close()
            for owner in (
                getattr(self, "_local_source_editor", None),
                getattr(self, "model_releases", None),
                getattr(self, "idle_executor", None),
                getattr(self, "orchestration", None),
                getattr(self, "shadow", None),
                getattr(self, "atlas", None),
            ):
                if owner is not None:
                    owner.close()

    def __enter__(self) -> "JeevesWorkbench":
        self._ensure_open()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = ["JeevesWorkbenchError", "JeevesWorkbench"]
