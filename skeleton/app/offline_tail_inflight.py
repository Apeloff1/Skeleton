"""App-facing in-flight pressure + latency capture boundary for local CPU AI.

This controller is deliberately cooperative. A model backend must honor every
HOLD/ABORT and independently enforce actual memory and cancellation limits.
No simulated sample authorizes production inference; no restart is replayed.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from skeleton.ai.model_runtime.execution_telemetry import ExecutionTiming
from skeleton.ai.model_runtime.tail_inflight_guard import (
    InFlightCPUResourceGuard, InFlightPressureDecision,
    InFlightPressureDenied,
)
from skeleton.ai.model_runtime.tail_live_capture import LiveTailCapture


class InFlightLifecycleQuarantined(RuntimeError):
    """A cross-component transition failed; no automatic retry is allowed."""


@dataclass(frozen=True, slots=True)
class OfflineInFlightStatus:
    schema: str
    request_id: str | None
    state: str
    reason: str
    generated_tokens: int
    generation: int
    continue_execution: bool
    telemetry_quarantined: bool
    gpu_device_qualified: bool = False
    authorized_quantum_tokens: int = 0


class OfflineTailInFlightSession:
    """Single-request app wiring for measured pressure and latency capture.

    The guard and tail profiler are not one atomic durable transaction. Any
    failure after a transition starts quarantines this in-process controller;
    the trusted execution owner must reconcile its independent journal.
    """

    def __init__(
        self, guard: InFlightCPUResourceGuard, capture: LiveTailCapture,
    ) -> None:
        if type(guard) is not InFlightCPUResourceGuard:
            raise ValueError("canonical in-flight pressure guard required")
        if type(capture) is not LiveTailCapture:
            raise ValueError("canonical local tail capture required")
        self._guard = guard
        self._capture = capture
        self._lock = RLock()
        self._request_id: str | None = None
        self._quarantined = False

    def _require_healthy(self) -> None:
        if self._quarantined:
            raise InFlightLifecycleQuarantined("execution requires journal reconciliation")

    def _status(self, decision: InFlightPressureDecision) -> OfflineInFlightStatus:
        return OfflineInFlightStatus(
            schema="skeleton.app.offline-tail-inflight.v1",
            request_id=self._request_id,
            state=decision.state,
            reason=decision.reason,
            generated_tokens=decision.generated_tokens,
            generation=decision.generation,
            continue_execution=decision.continue_execution and not self._quarantined,
            telemetry_quarantined=self._quarantined,
            authorized_quantum_tokens=decision.authorized_quantum_tokens,
        )

    def begin(
        self, *, request_id: str, prompt_tokens: int,
    ) -> OfflineInFlightStatus:
        with self._lock:
            self._require_healthy()
            if self._request_id is not None:
                raise InFlightPressureDenied("one in-flight request per controller")
            decision = self._guard.start()
            try:
                self._capture.begin(
                    request_id=request_id, prompt_tokens=prompt_tokens,
                )
            except BaseException as exc:
                self._quarantined = True
                try:
                    self._guard.abort()
                except BaseException:
                    pass
                raise InFlightLifecycleQuarantined(
                    "tail capture failed after pressure admission"
                ) from exc
            self._request_id = request_id
            return self._status(decision)

    def first_token(self) -> None:
        with self._lock:
            self._require_healthy()
            if self._request_id is None or self._guard.status().state != "running":
                raise InFlightPressureDenied("first token requires running request")
            try:
                self._capture.first_token(self._request_id)
            except BaseException as exc:
                self._quarantined = True
                raise InFlightLifecycleQuarantined(
                    "first-token telemetry failed"
                ) from exc

    def admit_quantum(self, *, requested_tokens: int) -> OfflineInFlightStatus:
        """Issue a fresh, measured, one-quantum CPU token authorization.

        Production backends must use the returned authorized_quantum_tokens
        and continue_execution together; simulated receipts never authorize
        hardware execution or GPU qualification.
        """
        with self._lock:
            self._require_healthy()
            if self._request_id is None:
                raise InFlightPressureDenied("no in-flight request")
            return self._status(
                self._guard.admit_quantum(requested_tokens=requested_tokens)
            )

    def checkpoint(self, *, generated_tokens: int) -> OfflineInFlightStatus:
        with self._lock:
            self._require_healthy()
            if self._request_id is None:
                raise InFlightPressureDenied("no in-flight request")
            return self._status(
                self._guard.checkpoint(generated_tokens=generated_tokens)
            )

    def resume(self) -> OfflineInFlightStatus:
        with self._lock:
            self._require_healthy()
            if self._request_id is None:
                raise InFlightPressureDenied("no in-flight request")
            return self._status(self._guard.resume())

    def complete(
        self, *, output_tokens: int, prefix_reused_tokens: int = 0,
    ) -> tuple[OfflineInFlightStatus, ExecutionTiming]:
        with self._lock:
            self._require_healthy()
            if self._request_id is None:
                raise InFlightPressureDenied("no in-flight request")
            before = self._guard.status()
            if before.state != "running":
                raise InFlightPressureDenied("completion requires running execution")
            if type(output_tokens) is not int or output_tokens != before.generated_tokens:
                self._quarantined = True
                try:
                    self._guard.abort()
                except BaseException:
                    pass
                raise InFlightLifecycleQuarantined(
                    "completion token accounting mismatch; journal reconciliation required"
                )
            decision = self._guard.complete()
            if decision.state != "completed":
                raise InFlightPressureDenied("fresh pressure probe holds completion")
            try:
                timing = self._capture.complete(
                    self._request_id, output_tokens=output_tokens,
                    prefix_reused_tokens=prefix_reused_tokens,
                )
            except BaseException as exc:
                self._quarantined = True
                raise InFlightLifecycleQuarantined(
                    "tail capture failed after guarded completion"
                ) from exc
            return self._status(decision), timing

    def abort(self) -> OfflineInFlightStatus:
        with self._lock:
            self._require_healthy()
            if self._request_id is None:
                raise InFlightPressureDenied("no in-flight request")
            try:
                self._capture.abort(self._request_id)
                decision = self._guard.abort()
            except BaseException as exc:
                self._quarantined = True
                raise InFlightLifecycleQuarantined(
                    "abort telemetry requires reconciliation"
                ) from exc
            return self._status(decision)

    def status(self) -> OfflineInFlightStatus:
        with self._lock:
            return self._status(self._guard.status())
