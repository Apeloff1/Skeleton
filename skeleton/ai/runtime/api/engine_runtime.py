"""Engine-side coordinator that owns provider execution for submitted commands."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Iterable

from skeleton.api.engine_service import (
    EngineExecutionCommand,
    EngineExecutionService,
    EngineServiceError,
)
from skeleton.contracts.ai_execution import AIExecutionResult
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.intelligence.execution_runtime import (
    CognitiveExecutionRuntime,
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
    ) -> None:
        if not isinstance(service, EngineExecutionService):
            raise TypeError("service must be EngineExecutionService")
        self.service = service
        self.provider_registry = provider_registry or ProviderRegistry.from_env()
        self.tool_runtime = tool_runtime or AsyncToolRuntime()
        self.verification_hook = verification_hook
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
            raise EngineExecutionCoordinatorError(
                "engine execution coordinator is closed"
            )
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
            raise EngineExecutionCoordinatorError(
                "engine submission is unavailable for execution"
            )
        await self.ensure_started(stored.command)

    async def recover(self) -> tuple[str, ...]:
        recovered: list[str] = []
        for execution in self.service.repository.recoverable():
            stored = self.service.submissions.get_by_execution_id(
                execution.execution_id
            )
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
            except Exception:
                await self._finalize_failure(
                    execution_id,
                    "tool_handler_unavailable",
                )
                return

        runtime = CognitiveExecutionRuntime(
            self.service.repository,
            provider,
            self.tool_runtime,
            verification_hook=self.verification_hook,
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
        history = tuple(
            AIMessage(role=role, content=content)
            for role, content in handoff.history
        )

        try:
            checkpoint = self.service.repository.latest_checkpoint(
                execution_id
            )
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
                self.service.complete_execution_admission(
                    execution_id
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._finalize_failure(
                execution_id,
                "engine_execution_exception",
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
        except Exception:
            return
        if current.terminal:
            return
        now = datetime.now(timezone.utc)
        result = AIExecutionResult(
            operation_id=current.operation_id,
            execution_id=current.execution_id,
            status="failed",
            usage={
                "error_code": str(error_code),
                "model_turns": 0,
                "tool_calls": 0,
            },
            stream_terminal_event=(
                "stream-terminal:"
                + current.execution_id
                + ":failed:"
                + str(error_code)
            ),
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
