"""Engine-side coordinator that owns provider execution for submitted commands."""

from __future__ import annotations

import asyncio
import logging
import os
import stat
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from skeleton.api.engine_service import (
    EngineExecutionCommand,
    EngineExecutionService,
    EngineServiceError,
)
from skeleton.contracts.ai_execution import AIExecutionRequest, AIExecutionResult
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.intelligence.execution_runtime import (
    CognitiveExecutionError,
    CognitiveExecutionRuntime,
    FinalizationBindingHook,
    VerificationHook,
)
from skeleton.intelligence.runtime_control import RuntimeOptimizationControl
from skeleton.kernel.runtime_supervision import (
    RuntimeServiceLifecycle,
    RuntimeSupervisionError,
    WorkLease,
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


class _ExecutionDatabaseOwner:
    """Exclusive live coordinator custody over the existing database inode.

    SQLite transactions fence durable state; this OS lock prevents a second
    live coordinator from treating a peer's in-flight turn as crash recovery.
    It never proves an uncertain provider dispatch completed or permits replay.
    """

    def __init__(self, repository) -> None:
        self._descriptor: int | None = None
        self._path: Path | None = None
        self._identity: tuple[int, int] | None = None
        self._process_id = os.getpid()
        if str(repository.path) == ":memory:":
            return
        descriptor = None
        try:
            # Match sqlite3.connect's literal path; expanduser would select a
            # different file when an API caller passes a literal '~' directory.
            path = Path(repository.path).resolve(strict=True)
            descriptor = os.open(path, os.O_RDWR | getattr(os, "O_CLOEXEC", 0))
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise OSError("execution database must be a regular file")
            if os.name == "nt":
                import msvcrt

                # Windows byte locks are mandatory. Reserve a non-data byte
                # beyond SQLite's maximum database size (2**48 bytes), without
                # writing or extending the file; never lock its header/pages.
                os.lseek(descriptor, 1 << 50, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            current = path.stat()
            if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                raise OSError("execution database changed during owner acquisition")
            self._descriptor, self._path = descriptor, path
            self._identity = (info.st_dev, info.st_ino)
        except (OSError, ImportError, ValueError) as exc:
            if descriptor is not None:
                os.close(descriptor)
            raise EngineExecutionCoordinatorError(
                "execution database requires one live coordinator with supported file locking"
            ) from exc

    def require_current(self) -> None:
        if os.getpid() != self._process_id:
            raise EngineExecutionCoordinatorError(
                "execution coordinator ownership cannot be inherited across fork"
            )
        if self._path is None:
            return
        if self._descriptor is None:
            raise EngineExecutionCoordinatorError("execution database ownership is closed")
        try:
            info = self._path.stat()
            current = (info.st_dev, info.st_ino)
        except OSError as exc:
            raise EngineExecutionCoordinatorError("execution database ownership is unavailable") from exc
        if current != self._identity:
            raise EngineExecutionCoordinatorError("execution database changed behind its live coordinator")

    def close(self) -> None:
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is not None:
            os.close(descriptor)


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
        provider_registry_factory: Callable[[], ProviderRegistry] | None = None,
        tool_runtime: AsyncToolRuntime | None = None,
        verification_hook: VerificationHook | None = None,
        finalization_binding_hook: FinalizationBindingHook | None = None,
        lifecycle: RuntimeServiceLifecycle | None = None,
    ) -> None:
        if not isinstance(service, EngineExecutionService):
            raise TypeError("service must be EngineExecutionService")
        self.service = service
        self._database_owner = _ExecutionDatabaseOwner(service.repository)
        try:
            service.repository.claim_coordinator_namespace()
            if provider_registry is not None and provider_registry_factory is not None:
                raise ValueError("provide a provider registry or its factory, not both")
            if provider_registry_factory is not None and not callable(provider_registry_factory):
                raise TypeError("provider_registry_factory must be callable")
            self.provider_registry = (
                provider_registry_factory()
                if provider_registry_factory is not None
                else provider_registry if provider_registry is not None else ProviderRegistry.from_env()
            )
            self.tool_runtime = tool_runtime or AsyncToolRuntime()
            self.verification_hook = verification_hook
            self.finalization_binding_hook = finalization_binding_hook
            if lifecycle is not None and not isinstance(
                lifecycle,
                RuntimeServiceLifecycle,
            ):
                raise TypeError("lifecycle must be RuntimeServiceLifecycle")
            self.lifecycle = lifecycle
            self._lock = asyncio.Lock()
            self._tasks: dict[str, asyncio.Task[None]] = {}
            self._foreground_requests: dict[asyncio.Task[None], AIExecutionRequest] = {}
            self._lifecycle_leases: dict[asyncio.Task[None], WorkLease] = {}
            self._pending_lifecycle_leases: dict[str, WorkLease] = {}
            self._supervision_faults: list[str] = []
            self._closed = False
            self._physical_shutdown_complete = False
            self.runtime_control = RuntimeOptimizationControl(
                self.service.repository,
                self.provider_registry,
                supervision_probe=self.supervision_snapshot,
            )
            self._maintenance_stop = asyncio.Event()
            self._maintenance_task: asyncio.Task[None] | None = None
            self._shutdown_task: asyncio.Task[None] | None = None
            self._recovery_cursor: tuple[datetime, str] | None = None
            self._recovery_lock = asyncio.Lock()
            self._recovery_scanned = 0
            self._recovery_started = 0
            self._recovery_error: str | None = None
            self._driver_failures = 0
            self._driver_finalization_failures = 0
            self._last_driver_error: str | None = None
        except BaseException:
            self._database_owner.close()
            raise

    async def ensure_started(
        self,
        command: EngineExecutionCommand,
        *,
        allow_starting: bool = False,
    ) -> None:
        if not isinstance(command, EngineExecutionCommand):
            raise TypeError("command must be EngineExecutionCommand")
        if self._closed:
            raise EngineExecutionCoordinatorError("engine execution coordinator is closed")
        if self._supervision_faults:
            raise EngineExecutionCoordinatorError("engine execution coordinator supervision is faulted")
        self._require_database_owner()
        execution_id = command.execution_request.execution_id
        if self.service.repository.result(execution_id) is not None:
            return

        async with self._lock:
            if self._closed:
                raise EngineExecutionCoordinatorError("engine execution coordinator is closed")
            existing = self._tasks.get(execution_id)
            if existing is not None and not existing.done():
                return
            if existing is not None and existing.done():
                self._task_done(execution_id, existing)

            lease = None
            if self.lifecycle is not None:
                try:
                    lease = self.lifecycle.acquire_work(
                        "engine-execution:" + execution_id,
                        allow_starting=allow_starting,
                    )
                    self._pending_lifecycle_leases[lease.work_id] = lease
                except RuntimeSupervisionError as exc:
                    raise EngineExecutionCoordinatorError(
                        "engine lifecycle denied execution admission"
                    ) from exc

            try:
                self.runtime_control.foreground_started()
                task = asyncio.create_task(
                    self._drive(command),
                    name="engine-execution:" + execution_id,
                )
            except BaseException:
                self.runtime_control.foreground_finished(command.execution_request)
                if lease is not None:
                    self._release_pending_lifecycle_lease(lease)
                raise

            self._tasks[execution_id] = task
            self._foreground_requests[task] = command.execution_request
            if lease is not None:
                self._lifecycle_leases[task] = lease
                self._pending_lifecycle_leases.pop(lease.work_id, None)
            task.add_done_callback(
                lambda completed, eid=execution_id: self._task_done(
                    eid,
                    completed,
                )
            )

    def _record_supervision_fault(self, message: str) -> None:
        normalized = str(message).strip()[:1024]
        if normalized and normalized not in self._supervision_faults:
            self._supervision_faults.append(normalized)

    def _require_database_owner(self) -> None:
        try:
            self._database_owner.require_current()
        except EngineExecutionCoordinatorError:
            self._record_supervision_fault("execution database ownership unavailable")
            raise

    def _release_lifecycle_lease(
        self,
        task: asyncio.Task[None],
    ) -> None:
        lease = self._lifecycle_leases.get(task)
        if lease is None:
            return
        if self._acknowledge_lifecycle_release(lease):
            self._lifecycle_leases.pop(task, None)

    def _release_pending_lifecycle_lease(self, lease: WorkLease) -> None:
        if self._acknowledge_lifecycle_release(lease):
            if self._pending_lifecycle_leases.get(lease.work_id) is lease:
                self._pending_lifecycle_leases.pop(lease.work_id, None)

    def _acknowledge_lifecycle_release(self, lease: WorkLease) -> bool:
        if self.lifecycle is None:
            self._record_supervision_fault(
                "lifecycle owner unavailable for retained work lease: " + lease.work_id
            )
            return False
        try:
            released = self.lifecycle.release_work(lease)
        except RuntimeSupervisionError as exc:
            self._record_supervision_fault(
                "lifecycle lease release failed for " + lease.work_id + ": " + str(exc)
            )
            return False
        if released is not True:
            self._record_supervision_fault(
                "lifecycle lease disappeared before task retirement: " + lease.work_id
            )
            return False
        return True

    def _task_done(
        self,
        execution_id: str,
        task: asyncio.Task[None],
    ) -> None:
        current = self._tasks.get(execution_id)
        if current is task:
            self._tasks.pop(execution_id, None)
        self._release_lifecycle_lease(task)
        request = self._foreground_requests.pop(task, None)
        if request is not None:
            try:
                self.runtime_control.foreground_finished(request)
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "Runtime outcome upkeep deferred (%s)",
                    type(exc).__name__,
                )
        if task.cancelled():
            return
        # Retrieve the exception so the event loop never reports an unobserved
        # background task. _drive normally converts failures into durable state.
        try:
            task.exception()
        except asyncio.CancelledError:
            pass

    def supervision_snapshot(self) -> dict[str, object]:
        """Return identity-safe local supervision state for health/evidence."""

        tasks = tuple(sorted(execution_id for execution_id, task in self._tasks.items() if not task.done()))
        lease_ids = tuple(
            sorted(
                lease.work_id
                for lease in (*self._lifecycle_leases.values(), *self._pending_lifecycle_leases.values())
            )
        )
        return {
            "closed": self._closed,
            "active_execution_ids": tasks,
            "active_task_count": len(tasks),
            "active_lease_ids": lease_ids,
            "active_lease_count": len(lease_ids),
            "supervision_faults": tuple(self._supervision_faults),
            "faulted": bool(self._supervision_faults),
            "runtime_maintenance": {
                "owned": self._maintenance_task is not None,
                "running": self._maintenance_task is not None and not self._maintenance_task.done(),
                "stopping": self._maintenance_stop.is_set(),
            },
            "recovery": {
                "maximum_recovery_drivers": 32,
                "page_limit": 128,
                "scan_in_progress": self._recovery_cursor is not None,
                "scanned": self._recovery_scanned,
                "started": self._recovery_started,
                "last_error": self._recovery_error,
                "driver_failures": self._driver_failures,
                "driver_finalization_failures": self._driver_finalization_failures,
                "last_driver_error": self._last_driver_error,
            },
        }

    async def ensure_execution(self, execution_id: str) -> None:
        stored = self.service.submissions.get_by_execution_id(
            str(execution_id),
        )
        if stored is None:
            raise EngineExecutionCoordinatorError("engine submission is unavailable for execution")
        await self.ensure_started(stored.command)

    async def interrupt_cancelled_execution(self, execution_id: str) -> None:
        """Wake a running execution after durable cancellation is requested.

        Cooperative providers observe the repository cancellation bit from the
        canonical runtime. Cancelling the coordinator task would bypass that
        terminalization path, so this method waits for the running driver to
        consume the durable request and only restarts recovery when no driver
        is active.
        """
        execution_id = str(execution_id)
        try:
            execution = self.service.repository.get(execution_id)
        except Exception as exc:
            raise EngineExecutionCoordinatorError("engine execution is unavailable for cancellation") from exc
        if not execution.cancellation_requested:
            raise EngineExecutionCoordinatorError("execution cancellation has not been requested")
        if execution.terminal or self.service.repository.result(execution_id) is not None:
            return

        async with self._lock:
            task = self._tasks.get(execution_id)
        if task is None or task.done():
            await self.ensure_execution(execution_id)
            async with self._lock:
                task = self._tasks.get(execution_id)
        # Cancellation acknowledgement must not wait for the entire
        # execution driver.  It should, however, give cooperative providers a
        # short bounded window to observe the durable bit and persist the
        # terminal cancellation result.  This keeps local cancellation
        # deterministic without deadlocking providers whose response can only
        # arrive after the caller regains control.
        if task is not None:
            done, _ = await asyncio.wait({task}, timeout=0.15)
            if task in done:
                # _drive is fail-closed and normally consumes its own errors.
                # Observe the task result so an unexpected terminal exception
                # can never become an un-retrieved task warning.
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

    async def recover(self) -> tuple[str, ...]:
        recovered = await self._recover_pending(allow_starting=True, include_waiting=True)
        if self._maintenance_task is None and not self._closed:
            self._maintenance_task = asyncio.create_task(
                self._maintain_runtime(),
                name="engine-runtime-maintenance",
            )
        return recovered

    async def _recover_pending(
        self,
        *,
        allow_starting: bool = False,
        include_waiting: bool = False,
    ) -> tuple[str, ...]:
        async with self._recovery_lock:
            return await self._recover_page(
                allow_starting=allow_starting,
                include_waiting=include_waiting,
            )

    async def _recover_page(
        self,
        *,
        allow_starting: bool,
        include_waiting: bool,
    ) -> tuple[str, ...]:
        """Resume a bounded page without eagerly allocating every old driver.

        Interactive approval/input endpoints still resume waiting work directly.
        Periodic recovery never polls those unchanged checkpoints for input.
        Canonical turn/dispatch fencing remains responsible for effect replay.
        """
        if self._closed or self._supervision_faults:
            return ()
        self._require_database_owner()
        available = max(0, 32 - sum(not task.done() for task in self._tasks.values()))
        if not available:
            return ()
        cursor = self._recovery_cursor
        page = await asyncio.to_thread(
            self.service.repository.recoverable_page,
            limit=128,
            after_updated_at=None if cursor is None else cursor[0],
            after_execution_id=None if cursor is None else cursor[1],
            include_waiting=include_waiting,
        )
        recovered: list[str] = []
        scanned = 0
        for execution in page:
            if self._closed or len(recovered) >= available:
                break
            scanned += 1
            self._recovery_scanned += 1
            self._recovery_cursor = (execution.updated_at, execution.execution_id)
            existing = self._tasks.get(execution.execution_id)
            if existing is not None and not existing.done():
                continue
            stored = self.service.submissions.get_by_execution_id(execution.execution_id)
            if stored is None:
                await self._finalize_failure(
                    execution.execution_id,
                    "submission_command_missing",
                )
                continue
            await self.ensure_started(
                stored.command,
                allow_starting=allow_starting,
            )
            recovered.append(execution.execution_id)
            self._recovery_started += 1
        if scanned == len(page) and len(page) < 128:
            self._recovery_cursor = None
        self._recovery_error = None
        return tuple(recovered)

    async def shutdown(self) -> None:
        """Retain shutdown custody through repeated caller cancellation."""
        if self._shutdown_task is None or (
            self._shutdown_task.done() and not self._physical_shutdown_complete
        ):
            self._shutdown_task = asyncio.create_task(self._shutdown_owned())
        cancelled = False
        while not self._shutdown_task.done():
            try:
                await asyncio.shield(self._shutdown_task)
            except asyncio.CancelledError:
                cancelled = True
        self._shutdown_task.result()
        if cancelled:
            raise asyncio.CancelledError

    @property
    def shutdown_started(self) -> bool:
        return self._closed

    @property
    def physical_shutdown_complete(self) -> bool:
        """True only after all owned workers/leases and database custody drain."""
        return self._physical_shutdown_complete

    async def _shutdown_owned(self) -> None:
        self._closed = True
        self._maintenance_stop.set()
        async with self._lock:
            task_items = tuple(self._tasks.items())

        for _execution_id, task in task_items:
            task.cancel()
        if task_items:
            await asyncio.gather(
                *(task for _execution_id, task in task_items),
                return_exceptions=True,
            )

        # Done callbacks normally retire exact task leases. Reconcile
        # synchronously as well so shutdown correctness never depends on the
        # event loop scheduling callback delivery before lifecycle STOPPED.
        for execution_id, task in task_items:
            self._task_done(execution_id, task)

        # A maintenance callback is bounded and cooperative. Keep custody of
        # the worker until it physically drains before closing its database.
        if self._maintenance_task is not None:
            maintenance = await asyncio.gather(self._maintenance_task, return_exceptions=True)
            if isinstance(maintenance[0], BaseException):
                self._record_supervision_fault("runtime maintenance stopped with a shutdown error")
            self._maintenance_task = None

        # Done callbacks may have failed to discharge an exact lease. Retain
        # and retry those identities after physical completion; a failed
        # release must never disappear merely because its task was retired.
        for task in tuple(self._lifecycle_leases):
            if task.done():
                self._release_lifecycle_lease(task)
        for lease in tuple(self._pending_lifecycle_leases.values()):
            self._release_pending_lifecycle_lease(lease)

        # The registry is the existing activation owner and deduplicates
        # aliases/verifiers that share a serving engine. Close those owners
        # before releasing persistent execution custody, including physical
        # preflight or local work not represented by a coordinator driver.
        # A scheduler facade never closes an engine shared by other adapters.
        local_closers = [
            closer
            for engine in self.provider_registry.runtime_serving_engines()
            if callable(closer := getattr(engine, "close", None))
        ]
        local_drain_errors = []
        if local_closers:

            async def close_local_owner(closer) -> None:
                # Evaluate the callback inside a gathered task so one faulty
                # closer cannot detach another owner's physical drain.
                await closer()

            local_drains = await asyncio.gather(
                *(close_local_owner(closer) for closer in local_closers),
                return_exceptions=True,
            )
            local_drain_errors = [result for result in local_drains if isinstance(result, BaseException)]
            if local_drain_errors:
                self._record_supervision_fault("local serving shutdown did not establish physical drain")
        async with self._lock:
            stranded_tasks = tuple(
                execution_id for execution_id, task in self._tasks.items() if not task.done()
            )
            self._tasks = {
                execution_id: task for execution_id, task in self._tasks.items() if not task.done()
            }

        if stranded_tasks:
            self._record_supervision_fault("shutdown left active tasks: " + ",".join(sorted(stranded_tasks)))
        if self._lifecycle_leases or self._pending_lifecycle_leases:
            leaked = tuple(
                sorted(
                    lease.work_id
                    for lease in (*self._lifecycle_leases.values(), *self._pending_lifecycle_leases.values())
                )
            )
            self._record_supervision_fault("shutdown left lifecycle leases: " + ",".join(leaked))

        if (
            not stranded_tasks
            and not self._lifecycle_leases
            and not self._pending_lifecycle_leases
            and not local_drain_errors
        ):
            # Maintenance close publishes durable host-presence drain and
            # zero physical-task counts. Keep that owner live until serving
            # workers and retained lifecycle custody have actually drained.
            self.runtime_control.close()
            self._database_owner.close()
            self._physical_shutdown_complete = True

        if self._supervision_faults:
            raise EngineExecutionCoordinatorError(
                "engine execution coordinator shutdown supervision failed: "
                + "; ".join(self._supervision_faults)
            )

    async def _maintain_runtime(self) -> None:
        while not self._maintenance_stop.is_set():
            lease = None
            try:
                if self.lifecycle is not None:
                    lease = self.lifecycle.acquire_work("engine-maintenance:runtime")
                    self._pending_lifecycle_leases[lease.work_id] = lease
                worker = asyncio.create_task(asyncio.to_thread(self.runtime_control.tick))
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    while not worker.done():
                        try:
                            await asyncio.shield(worker)
                        except asyncio.CancelledError:
                            continue
                    worker.result()
                    raise
            except RuntimeSupervisionError:
                # STARTING/DRAINING never grants background work.
                pass
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "Runtime maintenance deferred (%s)",
                    type(exc).__name__,
                )
            finally:
                if lease is not None and self.lifecycle is not None:
                    self._release_pending_lifecycle_lease(lease)
                    if lease.work_id in self._pending_lifecycle_leases:
                        self._maintenance_stop.set()
            if not self._maintenance_stop.is_set():
                try:
                    await self._recover_pending()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._recovery_error = type(exc).__name__
                    logging.getLogger(__name__).warning(
                        "Engine pending recovery deferred (%s)",
                        type(exc).__name__,
                    )
            try:
                await asyncio.wait_for(self._maintenance_stop.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass

    async def _drive(self, command: EngineExecutionCommand) -> None:
        try:
            self.runtime_control.reconcile()
            await self._execute(command)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Setup (role selection, verifier binding, checkpoint lookup) can
            # fail before the model loop's own terminalization guard. An
            # accepted command must not disappear with an unobserved task.
            self._driver_failures += 1
            self._last_driver_error = type(exc).__name__
            # Retain only trusted source basenames and function locations;
            # untrusted exception values and absolute paths stay out of logs.
            frames = tuple(
                f"{Path(frame.filename).name}:{frame.name}:{frame.lineno}"
                for frame in traceback.extract_tb(exc.__traceback__)[-3:]
            )
            logging.getLogger(__name__).warning(
                "Engine driver setup failed (%s); frames=%s",
                type(exc).__name__,
                frames,
            )
            try:
                await self._finalize_failure(
                    command.execution_request.execution_id,
                    "engine_coordinator_exception",
                )
            except Exception:
                self._driver_finalization_failures += 1
                # Retain the durable nonterminal command for the next bounded
                # recovery pass if persistence is temporarily unavailable.
                raise

    async def _execute(
        self,
        command: EngineExecutionCommand,
    ) -> None:
        execution_id = command.execution_request.execution_id
        if self.service.repository.result(execution_id) is not None:
            self.service.complete_execution_admission(execution_id)
            return
        try:
            self.service.ensure_execution_admission(command)
        except EngineServiceError:
            await self._finalize_failure(
                execution_id,
                "execution_admission_denied",
            )
            return
        try:
            provider = self.provider_registry.require_for_context(
                command.execution_request.context_policy,
            )
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

        verifier_selector = getattr(
            self.provider_registry,
            "verification_adapter_for",
            None,
        )
        semantic_verification_adapter = verifier_selector(provider) if callable(verifier_selector) else None

        from skeleton.intelligence.cooperation import normalize_cooperation_policy

        cooperative_adapters = {}
        cooperation = normalize_cooperation_policy(
            command.execution_request.context_policy.get("cooperation")
        )
        if cooperation is not None:
            try:
                for role, selection in cooperation["roles"].items():
                    role_context = dict(command.execution_request.context_policy)
                    role_context["provider_selection"] = dict(selection)
                    role_context.pop("provider_model", None)
                    cooperative_adapters[role] = self.provider_registry.require_for_context(role_context)
            except ProviderUnavailableError:
                await self._finalize_failure(execution_id, "cooperative_provider_unavailable")
                return

        runtime = CognitiveExecutionRuntime(
            self.service.repository,
            provider,
            self.tool_runtime,
            verification_hook=self.verification_hook,
            semantic_verification_adapter=semantic_verification_adapter,
            cooperative_adapters=cooperative_adapters,
            runtime_pressure_probe=self.runtime_control.pressure,
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
                try:
                    await runtime.resume(
                        execution_id,
                        approval_refs=approval_refs,
                    )
                except CognitiveExecutionError:
                    # The runtime first handles committed results, cancellation,
                    # deadlines and passive approval observation. It fences all
                    # actual execution and staged-result publication on the
                    # pinned provider identity. Preserve a useful failure code
                    # without preempting those safe recovery paths.
                    try:
                        runtime._assert_provider_binding(
                            self.service.repository.get(execution_id), checkpoint.payload
                        )
                    except CognitiveExecutionError:
                        code = (
                            "provider_activation_binding_missing"
                            if "provider_execution_binding" not in checkpoint.payload
                            else "provider_activation_binding_mismatch"
                        )
                        await self._finalize_failure(execution_id, code)
                        return
                    raise
            if self.service.repository.result(execution_id) is not None:
                self.service.complete_execution_admission(execution_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Engine execution %s failed (%s); frames=%s",
                execution_id,
                type(exc).__name__,
                [f"{frame.name}:{frame.lineno}" for frame in traceback.extract_tb(exc.__traceback__)],
            )
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
        # A failed recovery may already own settled physical provider work.
        # Preserve its receipts and metered turns without writing another
        # checkpoint or claiming any lost/unobserved work was completed.
        checkpoint = repository.latest_checkpoint(execution_id)
        payload = checkpoint.payload if checkpoint is not None else {}
        model_turns = payload.get("model_turns", 0)
        tool_calls = payload.get("tool_calls", 0)
        usage_events = payload.get("usage_events", [])
        provider_receipts = payload.get("provider_receipts", [])
        tool_receipts = payload.get("tool_receipts", [])
        if (
            type(model_turns) is not int or model_turns < 0
            or type(tool_calls) is not int or tool_calls < 0
            or not isinstance(usage_events, list)
            or not isinstance(provider_receipts, list)
            or not isinstance(tool_receipts, list)
        ):
            raise EngineExecutionCoordinatorError("durable execution usage is corrupt")
        result = AIExecutionResult(
            operation_id=current.operation_id,
            execution_id=current.execution_id,
            status="failed",
            provider_receipts=tuple(provider_receipts),
            tool_receipts=tuple(tool_receipts),
            usage={
                "error_code": str(error_code),
                "model_turns": model_turns,
                "tool_calls": tool_calls,
                "provider_usage": list(usage_events),
            },
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
