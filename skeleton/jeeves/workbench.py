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
        source_read_authorize: Callable[..., bool] | None = None,
        shadow_write_authorize: Callable[..., bool] | None = None,
        shadow_review_verify: Callable[..., bool] | None = None,
        shadow_admission_verify: Callable[..., bool] | None = None,
        shadow_consume_verify: Callable[..., bool] | None = None,
        creator_handlers: Mapping[str, Callable[..., Any]] | None = None,
        creator_authorize: Callable[..., bool] | None = None,
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
        self._core = Jeeves()
        self._read_authorize = read_authorize
        self._orchestration_authorize = orchestration_authorize
        self._source_read_authorize = source_read_authorize
        self._shadow_write_authorize = shadow_write_authorize
        self._shadow_review_verify = shadow_review_verify
        self._shadow_admission_verify = shadow_admission_verify
        self._shadow_consume_verify = shadow_consume_verify
        self._creator_handlers = creator_handlers
        self._creator_authorize = creator_authorize
        self._open_runbooks: list[CreatorRunbookStore] = []
        self.atlas: JeevesRepositoryFileAtlas | None = None
        self.shadow: DurableShadowWeightPipeline | None = None
        self.orchestration: DurableOrchestrLedger | None = None
        try:
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
        return self._core.app_tool_registry(
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
