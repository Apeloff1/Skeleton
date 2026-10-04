"""Engine-side coordinator that owns provider execution for submitted commands."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from skeleton.api.engine_service import (
    EngineExecutionCommand,
    EngineExecutionService,
    EngineServiceError,
)
from skeleton.contracts.ai_execution import (
    AIExecutionResult,
    ExecutionState,
    execution_payload_digest,
)
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.intelligence.execution_runtime import (
    CognitiveExecutionRuntime,
    FinalizationBindingHook,
    VerificationHook,
)
from skeleton.provider_runtime import (
    AIMessage,
    ProviderRegistry,
    ProviderUnavailableError,
)
from skeleton.skills.tool_receipt_store import SQLiteToolReceiptStore
from skeleton.skills.tool_runtime import AsyncToolRuntime


def build_engine_tool_runtime(
    *,
    admission_runtime: AdmissionRuntime,
    receipt_store: SQLiteToolReceiptStore,
) -> AsyncToolRuntime:
    """Construct the engine-owned canonical tool runtime at its owner boundary."""

    if not isinstance(admission_runtime, AdmissionRuntime):
        raise TypeError("admission_runtime must be AdmissionRuntime")
    if not isinstance(receipt_store, SQLiteToolReceiptStore):
        raise TypeError("receipt_store must be SQLiteToolReceiptStore")
    return AsyncToolRuntime(
        admission_runtime=admission_runtime,
        receipt_store=receipt_store,
    )


class EngineExecutionCoordinatorError(RuntimeError):
    """Engine execution could not be scheduled or reconciled safely."""


class _LocalProviderBindingError(EngineExecutionCoordinatorError):
    """A local recovery identity cannot authorize further model dispatch."""


class EngineExecutionCoordinator:
    """Single-process launcher over durable execution state.

    Durable execution/checkpoint/result authority remains in the repository.
    This coordinator only ensures one local task is driving a given execution
    at a time. Restart recovery rehydrates commands from the durable submission
    store and resumes from canonical checkpoints.
    """

    def __init__(
        self,
        service: EngineExecutionService,
        *,
        provider_registry: ProviderRegistry | None = None,
        tool_runtime: AsyncToolRuntime | None = None,
        verification_hook: VerificationHook | None = None,
        finalization_binding_hook: FinalizationBindingHook | None = None,
    ) -> None:
        if not isinstance(service, EngineExecutionService):
            raise TypeError("service must be EngineExecutionService")
        self.service = service
        self.provider_registry = provider_registry or ProviderRegistry.from_env()
        self.tool_runtime = tool_runtime or AsyncToolRuntime()
        self.verification_hook = verification_hook
        self.finalization_binding_hook = finalization_binding_hook
        self._lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._closed = False

    async def ensure_started(
        self,
        command: EngineExecutionCommand,
    ) -> None:
        if not isinstance(command, EngineExecutionCommand):
            raise TypeError("command must be EngineExecutionCommand")
        if self._closed:
            raise EngineExecutionCoordinatorError("engine execution coordinator is closed")
        execution_id = command.execution_request.execution_id
        if self.service.repository.result(execution_id) is not None:
            return

        async with self._lock:
            existing = self._tasks.get(execution_id)
            if existing is not None and not existing.done():
                return
            task = asyncio.create_task(
                self._drive(command),
                name="engine-execution:" + execution_id,
            )
            self._tasks[execution_id] = task
            task.add_done_callback(
                lambda completed, eid=execution_id: self._task_done(
                    eid,
                    completed,
                )
            )

    def _task_done(
        self,
        execution_id: str,
        task: asyncio.Task[None],
    ) -> None:
        current = self._tasks.get(execution_id)
        if current is task:
            self._tasks.pop(execution_id, None)
        if task.cancelled():
            return
        # Retrieve the exception so the event loop never reports an unobserved
        # background task. _drive normally converts failures into durable state.
        try:
            task.exception()
        except asyncio.CancelledError:
            pass

    async def ensure_execution(self, execution_id: str) -> None:
        stored = self.service.submissions.get_by_execution_id(
            str(execution_id),
        )
        if stored is None:
            raise EngineExecutionCoordinatorError("engine submission is unavailable for execution")
        await self.ensure_started(stored.command)

    async def interrupt_cancelled_execution(self, execution_id: str) -> None:
        """Drain an execution after its authorized cancellation was committed.

        The cognitive runtime interrupts cooperative provider work and fences
        late noncooperative responses, including their actual usage. Cancelling
        its driver task here would bypass that durable finalization. Shield the
        driver so cancellation of this waiter cannot revoke execution authority.
        """

        if not isinstance(execution_id, str) or not execution_id.strip():
            raise ValueError("execution_id must be a nonempty string")
        while True:
            execution = self.service.repository.get(execution_id)
            if execution.terminal:
                return
            if not execution.cancellation_requested:
                raise EngineExecutionCoordinatorError("execution cancellation has not been durably requested")

            await self.ensure_execution(execution_id)
            async with self._lock:
                task = self._tasks.get(execution_id)
            if task is not None:
                await asyncio.shield(task)
            # A driver may have stopped at an approval checkpoint just as the
            # durable flag was committed. Resume that checkpoint until the
            # canonical runtime records a terminal result, without dispatching
            # another provider turn after observing cancellation.

    async def recover(self) -> tuple[str, ...]:
        recovered: list[str] = []
        for execution in self.service.repository.recoverable():
            stored = self.service.submissions.get_by_execution_id(execution.execution_id)
            if stored is None:
                await self._finalize_failure(
                    execution.execution_id,
                    "submission_command_missing",
                )
                continue
            await self.ensure_started(stored.command)
            recovered.append(execution.execution_id)
        return tuple(recovered)

    async def shutdown(self) -> None:
        self._closed = True
        async with self._lock:
            tasks = tuple(self._tasks.values())
            self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _drive(
        self,
        command: EngineExecutionCommand,
    ) -> None:
        execution_id = command.execution_request.execution_id
        try:
            self.service.ensure_execution_admission(command)
        except EngineServiceError:
            await self._finalize_failure(
                execution_id,
                "execution_admission_denied",
            )
            return
        try:
            provider = self.provider_registry.require_active()
        except ProviderUnavailableError:
            await self._finalize_failure(
                execution_id,
                "provider_unavailable",
            )
            return

        handoff = command.compiled_context
        allowed_tool_ids = tuple(
            str(item)
            for item in command.execution_request.tool_policy.get(
                "allowed_tool_ids",
                [],
            )
        )
        # Exposing a tool schema without an executable engine-side handler is
        # worse than failing closed: the model could request an effect that the
        # owning runtime cannot safely perform.
        for tool_id in allowed_tool_ids:
            try:
                await self.tool_runtime.manifest(tool_id)
            except Exception:  # noqa: BLE001 - Fail closed at the tool owner boundary.
                await self._finalize_failure(
                    execution_id,
                    "tool_handler_unavailable",
                )
                return

        verifier_selector = getattr(
            self.provider_registry,
            "verification_adapter_for",
            None,
        )
        semantic_verification_adapter = verifier_selector(provider) if callable(verifier_selector) else None

        runtime = CognitiveExecutionRuntime(
            self.service.repository,
            provider,
            self.tool_runtime,
            verification_hook=self.verification_hook,
            semantic_verification_adapter=semantic_verification_adapter,
            finalization_binding_hook=self.finalization_binding_hook,
            storage_meter=(
                lambda resource_id, write_id, payload, meter_now=None: (
                    self.service.meter_execution_storage(
                        command,
                        resource_id,
                        write_id,
                        payload,
                        now=meter_now,
                    )
                )
            ),
        )
        history = tuple(AIMessage(role=role, content=content) for role, content in handoff.history)

        try:
            checkpoint = self.service.repository.latest_checkpoint(execution_id)
            checkpoint = self._pin_local_provider(command, runtime, provider, checkpoint, history)
            approval_refs = self.service.active_approval_refs(
                execution_id,
            )
            if checkpoint is None:
                await runtime.start(
                    command.execution_request,
                    instructions=handoff.instructions,
                    prompt=handoff.prompt,
                    history=history,
                    context_digest=handoff.context_digest,
                    approval_refs=approval_refs,
                )
            else:
                await runtime.resume(
                    execution_id,
                    approval_refs=approval_refs,
                )
            if self.service.repository.result(execution_id) is not None:
                self.service.complete_execution_admission(execution_id)
        except asyncio.CancelledError:
            raise
        except _LocalProviderBindingError as exc:
            await self._finalize_failure(execution_id, str(exc))
        except Exception:  # noqa: BLE001 - Finalize any driver or hook failure.
            await self._finalize_failure(
                execution_id,
                "engine_execution_exception",
            )

    def _pin_local_provider(self, command, runtime, provider, checkpoint, history):
        """Commit or verify a local pin before the canonical runtime dispatches."""

        field = "local_provider_binding"
        prior = None if checkpoint is None else checkpoint.payload.get(field)
        is_local = getattr(provider, "provider_id", None) == "local"
        if not is_local and prior is None:
            return checkpoint
        descriptor = getattr(provider, "execution_identity", None)
        if not is_local or not callable(descriptor):
            raise _LocalProviderBindingError("local_provider_binding_mismatch")
        try:
            identity = descriptor()
            if (
                not isinstance(identity, dict)
                or identity.get("schema_version") != "skeleton.local_provider_execution_identity.v1"
                or identity.get("provider_id") != "local"
                or identity.get("model_id") != getattr(provider, "model", None)
            ):
                raise ValueError("invalid local execution identity")
            binding = {"identity": identity, "binding_digest": execution_payload_digest(identity)}
            if prior is not None:
                if (
                    not isinstance(prior, dict)
                    or set(prior) != {"identity", "binding_digest"}
                    or execution_payload_digest(prior["identity"]) != prior["binding_digest"]
                    or prior != binding
                ):
                    raise ValueError("local binding drift")
                return checkpoint
        except (ValueError, TypeError, KeyError, ProviderUnavailableError) as exc:
            raise _LocalProviderBindingError("local_provider_binding_mismatch") from exc
        handoff = command.compiled_context
        initial = runtime._initial_payload(
            command.execution_request,
            instructions=handoff.instructions,
            prompt=handoff.prompt,
            context_digest=handoff.context_digest,
            history=history,
        )
        current = self.service.repository.get(command.execution_request.execution_id)
        observed_checkpoint_version = 0 if checkpoint is None else checkpoint.checkpoint_version
        if current.checkpoint_version != observed_checkpoint_version:
            authoritative = self.service.repository.latest_checkpoint(current.execution_id)
            if authoritative is None:
                raise _LocalProviderBindingError("local_provider_binding_missing")
            return self._pin_local_provider(command, runtime, provider, authoritative, history)
        if current.state is not ExecutionState.CREATED:
            raise _LocalProviderBindingError("local_provider_binding_missing")
        if checkpoint is not None and (checkpoint.payload != initial):
            raise _LocalProviderBindingError("local_provider_binding_missing")
        initial[field] = binding
        return self.service.repository.checkpoint(
            current.execution_id,
            initial,
            expected_execution_version=current.version,
            expected_checkpoint_version=current.checkpoint_version,
        )

    async def _finalize_failure(
        self,
        execution_id: str,
        error_code: str,
    ) -> None:
        repository = self.service.repository
        existing = repository.result(execution_id)
        if existing is not None:
            return
        try:
            current = repository.get(execution_id)
        except Exception:  # noqa: BLE001 - Reconciliation needs a readable snapshot.
            return
        if current.terminal:
            return
        now = datetime.now(UTC)
        payload = {}
        try:
            checkpoint = repository.latest_checkpoint(execution_id)
            if checkpoint is not None:
                payload = dict(checkpoint.payload)
            if any(
                type(payload.get(key, 0)) is not int or payload.get(key, 0) < 0
                for key in ("model_turns", "tool_calls")
            ) or any(
                not isinstance(payload.get(key, []), list)
                or any(not isinstance(item, str) or not item.strip() for item in payload.get(key, []))
                for key in ("provider_receipts", "tool_receipts")
            ):
                raise ValueError("checkpoint usage identity is malformed")
            if not isinstance(payload.get("usage_events", []), list) or any(
                not isinstance(item, dict) for item in payload.get("usage_events", [])
            ):
                raise ValueError("checkpoint usage events are malformed")
        except Exception:  # noqa: BLE001 - Corrupt checkpoints cannot supply usage evidence.
            payload = {"usage_evidence_unavailable": True}
        result = AIExecutionResult(
            operation_id=current.operation_id,
            execution_id=current.execution_id,
            status="failed",
            usage={
                "error_code": str(error_code),
                "model_turns": int(payload.get("model_turns", 0)),
                "tool_calls": int(payload.get("tool_calls", 0)),
                "provider_usage": list(payload.get("usage_events", [])),
                **({"usage_evidence_unavailable": True} if payload.get("usage_evidence_unavailable") else {}),
            },
            provider_receipts=tuple(payload.get("provider_receipts", ())),
            tool_receipts=tuple(payload.get("tool_receipts", ())),
            stream_terminal_event=("stream-terminal:" + current.execution_id + ":failed:" + str(error_code)),
            completed_at=now,
        )
        try:
            repository.finalize(
                result,
                expected_execution_version=current.version,
                now=now,
            )
            self.service.complete_execution_admission(
                execution_id,
                now=now,
            )
        except Exception:
            # A concurrent driver may have completed or advanced the execution.
            # Re-read and leave durable reconciliation to the canonical state.
            if repository.result(execution_id) is None:
                raise


__all__ = [
    "EngineExecutionCoordinator",
    "EngineExecutionCoordinatorError",
]
