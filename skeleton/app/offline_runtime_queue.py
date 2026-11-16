"""Stateful local request admission composed with the canonical KV scheduler.

Only logical cache reservations are owned here. A trusted synchronous
executor must implement real allocation and token execution itself. This
boundary intentionally never advertises retained physical KV or native
kernel qualification.
"""
from __future__ import annotations

from dataclasses import dataclass, replace, asdict
import threading
import time
from typing import Protocol, Any

from skeleton.ai.model_runtime.admission_scheduler import AdmissionLimits, RuntimeAdmissionScheduler
from skeleton.ai.model_runtime.flgb_model_runtime import BatchRequest
from skeleton.ai.model_runtime.iteration_scheduler import InferencePhase, IterationWork
from skeleton.app.offline_runtime_preflight import RuntimePolicy, digest, integer, require
from skeleton.app.offline_runtime_session import OfflineRuntimeSession
from skeleton.app.offline_runtime_control import parse_work

SCHEMA = "skeleton.offline.request-progress.v1"


@dataclass(frozen=True, slots=True)
class QueuePolicy:
    max_requests: int = 256
    max_active: int = 8
    max_request_tokens: int = 16384
    kv_capacity_bytes: int = 256 * 1024**2
    kv_bytes_per_token: int = 4096

    def __post_init__(self) -> None:
        integer(self.max_requests, 1, 4096, "queue size")
        integer(self.max_active, 1, min(256, self.max_requests), "active limit")
        integer(self.max_request_tokens, 1, 65536, "request token bound")
        integer(self.kv_capacity_bytes, 1, 1 << 40, "KV capacity")
        integer(self.kv_bytes_per_token, 1, 1 << 30, "KV token estimate")


def reserve_cache(policy: RuntimePolicy, queue: QueuePolicy) -> RuntimePolicy:
    """Reserve the whole logical cache ceiling outside worker/weight budgets."""
    require(policy.backend == "cpu", "host KV reservation supports CPU only")
    return replace(policy, host_reserve_bytes=policy.host_reserve_bytes + queue.kv_capacity_bytes)


@dataclass(frozen=True, slots=True)
class Progress:
    request_id: str
    phase: str
    processed_tokens: int
    terminal: bool = False

    def __post_init__(self) -> None:
        require(type(self.request_id) is str and bool(self.request_id), "request identity required")
        require(self.phase in ("prefill", "decode"), "invalid progress phase")
        integer(self.processed_tokens, 0, 65536, "processed token count")
        require(type(self.terminal) is bool, "invalid terminal marker")


class SliceExecutor(Protocol):
    """Trusted local cooperative owner; never supplied through JSON or RPC."""

    def run_slice(self, *, request_id: str, phase: str, tokens: int,
                  deadline_ns: int, cancel: threading.Event) -> Progress: ...

    def release(self, request_id: str) -> None: ...


@dataclass(slots=True)
class _Request:
    request: BatchRequest
    prompt_left: int
    decode_left: int
    deadline_ns: int
    cancel: threading.Event
    age: int = 0


class OfflineRequestQueue:
    """Serialize one iteration at a time; enforce exact consumed scheduling slices.

    The trusted executor is synchronous. It may cooperate with the deadline
    and cancellation event; this supervisor cannot interrupt a blocked kernel.
    A failing executor poisons the queue instead of releasing a suspect logical
    reservation and pretending physical bytes were reclaimed.
    """

    def __init__(self, session: OfflineRuntimeSession, policy: QueuePolicy,
                 executor: SliceExecutor, *, base_policy: RuntimePolicy) -> None:
        require(isinstance(session, OfflineRuntimeSession), "trusted session required")
        require(isinstance(policy, QueuePolicy), "queue policy required")
        require(callable(getattr(executor, "run_slice", None)) and
                callable(getattr(executor, "release", None)), "trusted slice executor required")
        # The application session publishes its immutable policy through a
        # read-only property. Its host reserve must include the whole KV budget.
        require(isinstance(base_policy, RuntimePolicy) and session.policy == reserve_cache(base_policy, policy),
                "session lacks separately reserved CPU cache budget")
        self._session = session
        self._policy = policy
        self._executor = executor
        self._scheduler = RuntimeAdmissionScheduler(AdmissionLimits(
            max_active_requests=policy.max_active, max_queued_requests=policy.max_requests,
            max_batch_size=policy.max_active,
            max_tokens_per_batch=min(1_000_000, policy.max_request_tokens * policy.max_active),
            kv_capacity_bytes=policy.kv_capacity_bytes))
        self._requests: dict[str, _Request] = {}
        self._lock = threading.RLock()
        self._iteration_lock = threading.Lock()
        self._poisoned = False
        self._closed = False
        self._sequence = 0

    def _open(self) -> None:
        require(not self._closed and not self._poisoned, "request queue unavailable")

    def submit(self, request: BatchRequest, *, timeout_ms: int) -> None:
        require(isinstance(request, BatchRequest), "canonical batch request required")
        integer(timeout_ms, 1, 86_400_000, "request timeout")
        total = request.prompt_tokens + request.max_new_tokens
        require(total <= self._policy.max_request_tokens, "request exceeds token bound")
        # Reuse exactly the same public identity restrictions as iteration work.
        parse_work([{"request_id": request.request_id, "phase": "prefill" if request.prompt_tokens else "decode",
                     "remaining_tokens": request.prompt_tokens or request.max_new_tokens,
                     "priority": request.priority, "age": 0}])
        with self._lock:
            self._open()
            require(len(self._requests) < self._policy.max_requests, "request queue full")
            require(request.request_id not in self._requests, "duplicate request identity")
            self._scheduler.submit(request, kv_bytes=total * self._policy.kv_bytes_per_token)
            self._requests[request.request_id] = _Request(
                request, request.prompt_tokens, request.max_new_tokens,
                time.monotonic_ns() + timeout_ms * 1_000_000, threading.Event())

    def cancel(self, request_id: str) -> bool:
        """Signal cooperative cancellation even while a slice is running."""
        with self._lock:
            row = self._requests.get(request_id)
            if row is None:
                return False
            row.cancel.set()
            return True

    def _retire(self, request_id: str, *, completed: bool) -> None:
        """Release executor ownership before returning scheduler capacity."""
        if request_id in self._scheduler.active_ids:
            self._executor.release(request_id)
            if completed:
                self._scheduler.complete(request_id, retain_kv=False)
            else:
                self._scheduler.cancel(request_id)
        else:
            self._scheduler.cancel(request_id)
        self._requests.pop(request_id)

    def _sweep(self, now: int) -> list[dict]:
        retired = []
        for key, row in tuple(self._requests.items()):
            if row.cancel.is_set() or now >= row.deadline_ns:
                reason = "cancelled" if row.cancel.is_set() else "deadline"
                self._retire(key, completed=False)
                retired.append({"request_id": key, "terminal": reason})
        return retired

    def _work(self) -> tuple[IterationWork, ...]:
        rows = []
        for key in self._scheduler.active_ids:
            row = self._requests[key]
            phase = InferencePhase.PREFILL if row.prompt_left else InferencePhase.DECODE
            tokens = row.prompt_left if row.prompt_left else row.decode_left
            require(tokens > 0, "empty active request")
            rows.append(IterationWork(key, phase, tokens, row.request.priority, row.age))
        return tuple(rows)

    def tick(self) -> dict:
        """Execute only a fresh, consumed cooperative grant, with bounded progress."""
        with self._lock:
            self._open()
            require(self._iteration_lock.acquire(blocking=False), "another iteration is in progress")
        try:
            return self._tick()
        except BaseException:
            with self._lock:
                self._poisoned = True
                for row in self._requests.values():
                    row.cancel.set()
                self._session.close()
            raise
        finally:
            # Coordinate completion with close(): under the state lock, the
            # closing thread either observes this final cleanup or owns the
            # now-idle iteration lock itself. No unowned shutdown interval.
            with self._lock:
                try:
                    if self._closed and not self._poisoned:
                        self._sweep(time.monotonic_ns())
                except BaseException:
                    self._poisoned = True
                    raise
                finally:
                    self._iteration_lock.release()

    def _tick(self) -> dict:
        with self._lock:
            # close() may have won the interval after tick acquired custody.
            # No further observation or admission should occur in that case.
            if self._closed:
                retired = self._sweep(time.monotonic_ns())
                body = {"schema": SCHEMA, "sequence": self._sequence,
                        "admission_digest": None, "scheduler_digest": self._scheduler.snapshot()["digest"],
                        "progress": [], "retired": retired,
                        "capacity": self._scheduler.capacity(), "status": "closed",
                        "kv_accounting": "logical_reservation_only",
                        "executor": "trusted_cooperative_owner",
                        "native_qualified": False, "release_qualified": False}
                return {**body, "progress_digest": digest(body)}
            self._open()
            retired = self._sweep(time.monotonic_ns())
            decision = self._scheduler.admit()
            require(not decision.evicted_kv and not decision.rejected,
                    "unexpected cache eviction or rejected canonical request")
            work = self._work()
            observation = self._session.offer(work)
            grant = observation["admission"]
            slices = self._session.consume(grant) if grant["status"] == "candidate" else ()
            self._sequence += 1
        progressed = []
        for item in slices:
            key = item["request_id"]
            with self._lock:
                row = self._requests.get(key)
                require(row is not None and key in self._scheduler.active_ids, "grant request no longer active")
                now = time.monotonic_ns()
                if self._closed or row.cancel.is_set() or now >= row.deadline_ns:
                    continue
                if now > grant["expires_ns"]:
                    break
                phase = "prefill" if row.prompt_left else "decode"
                remaining = row.prompt_left if row.prompt_left else row.decode_left
                require(item["phase"] == phase and 1 <= item["tokens"] <= remaining,
                        "grant exceeds request phase budget")
                deadline = min(row.deadline_ns, grant["expires_ns"])
            result = self._executor.run_slice(request_id=key, phase=phase,
                                              tokens=item["tokens"], deadline_ns=deadline,
                                              cancel=row.cancel)
            with self._lock:
                require(isinstance(result, Progress) and result.request_id == key
                        and result.phase == phase and result.processed_tokens <= item["tokens"],
                        "executor progress exceeds exact grant")
                if phase == "prefill":
                    require(not result.terminal, "prefill cannot claim decoded completion")
                    row.prompt_left -= result.processed_tokens
                else:
                    row.decode_left -= result.processed_tokens
                now = time.monotonic_ns()
                # Never count a late or cancelled result as successful terminal output.
                if row.cancel.is_set() or now >= row.deadline_ns or now > deadline:
                    reason = "cancelled" if row.cancel.is_set() else "deadline"
                    self._retire(key, completed=False)
                    retired.append({"request_id": key, "terminal": reason})
                    continue
                progressed.append(asdict(result))
                if result.terminal or (row.prompt_left == 0 and row.decode_left == 0):
                    self._retire(key, completed=True)
                    retired.append({"request_id": key, "terminal": "completed"})
        with self._lock:
            retired.extend(self._sweep(time.monotonic_ns()))
            advanced = {item["request_id"] for item in progressed if item["processed_tokens"]}
            for key, row in self._requests.items():
                row.age = 0 if key in advanced else min(row.age + 1, 1 << 31)
            body = {"schema": SCHEMA, "sequence": self._sequence,
                    "admission_digest": grant["admission_digest"], "scheduler_digest": self._scheduler.snapshot()["digest"],
                    "progress": progressed, "retired": retired, "capacity": self._scheduler.capacity(),
                    "kv_accounting": "logical_reservation_only", "executor": "trusted_cooperative_owner",
                    "native_qualified": False, "release_qualified": False}
            return {**body, "progress_digest": digest(body)}

    def status(self) -> dict:
        with self._lock:
            return {"closed": self._closed, "poisoned": self._poisoned,
                    "sequence": self._sequence, "capacity": self._scheduler.capacity(),
                    "iteration_in_progress": self._iteration_lock.locked(),
                    "drain_complete": self._closed and not self._requests and not self._iteration_lock.locked(),
                    "requests": [{"request_id": key, "prompt_left": row.prompt_left,
                                  "decode_left": row.decode_left, "cancelled": row.cancel.is_set()}
                                 for key, row in sorted(self._requests.items())],
                    "native_qualified": False, "release_qualified": False}

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for row in self._requests.values():
                row.cancel.set()
            # If a tick holds the lock, let that owner finish draining.
            # A stuck executor retains its reservations and cancellation fence.
            owns_cleanup = self._iteration_lock.acquire(blocking=False)
            if not owns_cleanup:
                self._session.close()
                return
            try:
                for key in tuple(self._requests):
                    self._retire(key, completed=False)
            except BaseException:
                self._poisoned = True
                raise
            finally:
                self._session.close()
                self._iteration_lock.release()
