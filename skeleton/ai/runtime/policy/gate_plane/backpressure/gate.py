"""Backpressure decisions and the ``backpressure`` pipeline stage.

Mapping from a :class:`PressureView` to an action (as agreed with Backend):

==========  ===============================================================
state       action
==========  ===============================================================
open        admit
throttle    delay ``retry_after_s`` then admit — if the delay fits both
            ``max_throttle_wait_s`` and the call deadline; otherwise shed
            with 429 and ``Retry-After``
shed        429 (load-shed) or 503 (queue full) with ``Retry-After``
            rounded up to whole seconds; priority-0 control-plane traffic
            is admitted anyway (mirrors ``AdaptiveGate`` overdraw)
==========  ===============================================================

When *no* source can produce a snapshot the gate admits by default
(``on_no_signal="admit"``): authentication and authorization stay
fail-closed elsewhere, and losing a load *signal* must not turn into a
self-inflicted outage. Set ``on_no_signal="shed"`` to fail closed instead.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from skeleton.gate_plane.backpressure.snapshot import (
    PressureState,
    PressureUnavailable,
    PressureView,
    retry_after_header,
    round_retry_after,
)
from skeleton.gate_plane.backpressure.sources import PressureSource
from skeleton.gate_plane.pipeline.core import CallContext, Handler, PipelineRequest, PipelineResponse
from skeleton.gate_plane.s2s.clock import Clock, system_clock

CONTROL_PRIORITY = 0
NO_SIGNAL_RETRY_AFTER_S = 1.0


class Action(str, Enum):
    ADMIT = "admit"
    DELAY = "delay"
    SHED = "shed"


@dataclass(frozen=True)
class BackpressureDecision:
    action: Action
    reason: str
    delay_s: float = 0.0
    status: int = 200
    retry_after_s: Optional[float] = None
    view: Optional[PressureView] = None

    @property
    def admitted(self) -> bool:
        return self.action is not Action.SHED

    @property
    def source(self) -> Optional[str]:
        return None if self.view is None else self.view.source

    def headers(self) -> List[tuple]:
        if self.retry_after_s is None:
            return []
        return [("retry-after", retry_after_header(self.retry_after_s))]

    def body(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"error": "overloaded" if self.status == 503 else "throttled", "reason": self.reason}
        if self.retry_after_s is not None:
            out["retry_after_s"] = self.retry_after_s
        return out

    def response(self) -> PipelineResponse:
        return PipelineResponse(self.status, self.body(), tuple(self.headers()))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "delay_s": self.delay_s,
            "status": self.status,
            "retry_after_s": self.retry_after_s,
            "source": self.source,
            "state": None if self.view is None else self.view.effective_state.value,
        }


DecisionListener = Callable[[PipelineRequest, BackpressureDecision], None]


class BackpressureGate:
    """Turns pressure snapshots into admit / delay / shed decisions."""

    def __init__(
        self,
        source: PressureSource,
        *,
        max_throttle_wait_s: float = 0.25,
        on_no_signal: str = "admit",
        exempt_priority: Optional[int] = CONTROL_PRIORITY,
        listeners: Optional[List[DecisionListener]] = None,
    ) -> None:
        if max_throttle_wait_s < 0:
            raise ValueError("max_throttle_wait_s must be >= 0")
        if on_no_signal not in ("admit", "shed"):
            raise ValueError("on_no_signal must be 'admit' or 'shed'")
        self.source = source
        self.max_throttle_wait_s = float(max_throttle_wait_s)
        self.on_no_signal = on_no_signal
        self.exempt_priority = exempt_priority
        self._listeners: List[DecisionListener] = list(listeners or [])
        self._lock = threading.Lock()
        self._counts: Dict[str, int] = {}

    def add_listener(self, listener: DecisionListener) -> None:
        self._listeners.append(listener)

    def _count(self, key: str) -> None:
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1

    def _emit(self, request: PipelineRequest, decision: BackpressureDecision) -> BackpressureDecision:
        self._count(f"{decision.action.value}:{decision.reason}")
        for listener in list(self._listeners):
            try:
                listener(request, decision)
            except Exception:  # noqa: BLE001 - observers never change verdicts
                pass
        return decision

    def decide(self, request: PipelineRequest, *, budget_s: Optional[float] = None) -> BackpressureDecision:
        """Decide for ``request``; ``budget_s`` is the remaining call deadline, if any."""
        try:
            view = self.source.read(request.tenant_id)
        except PressureUnavailable:
            if self.on_no_signal == "shed":
                return self._emit(
                    request,
                    BackpressureDecision(
                        Action.SHED, "no_signal", status=503, retry_after_s=NO_SIGNAL_RETRY_AFTER_S
                    ),
                )
            return self._emit(request, BackpressureDecision(Action.ADMIT, "no_signal"))

        state = view.effective_state
        exempt = self.exempt_priority is not None and request.priority <= self.exempt_priority
        if state is PressureState.OPEN:
            return self._emit(request, BackpressureDecision(Action.ADMIT, "open", view=view))
        if exempt:
            return self._emit(request, BackpressureDecision(Action.ADMIT, f"{state.value}_control_exempt", view=view))
        retry_after = round_retry_after(view.retry_after_s)
        if state is PressureState.THROTTLE:
            if retry_after <= 0:
                return self._emit(request, BackpressureDecision(Action.ADMIT, "throttle_no_wait", view=view))
            fits = retry_after <= self.max_throttle_wait_s and (budget_s is None or retry_after < budget_s)
            if fits:
                return self._emit(
                    request, BackpressureDecision(Action.DELAY, "throttle", delay_s=retry_after, view=view)
                )
            return self._emit(
                request,
                BackpressureDecision(
                    Action.SHED, "throttle_wait_too_long", status=429, retry_after_s=retry_after, view=view
                ),
            )
        # SHED
        status = 503 if view.queue_full else 429
        reason = "queue_full" if view.queue_full else "load_shed"
        return self._emit(
            request,
            BackpressureDecision(Action.SHED, reason, status=status, retry_after_s=max(retry_after, 1.0), view=view),
        )

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counts)


class BackpressureStage:
    """Pipeline stage (kind ``backpressure``) wrapping a :class:`BackpressureGate`.

    Sheds return a response (429/503 + ``Retry-After``) rather than raising so
    the telemetry stage outside it sees the status; they never reach the
    retry stage, so shed traffic cannot spend retry budget.
    """

    kind = "backpressure"

    def __init__(self, gate: BackpressureGate, *, name: str = "backpressure") -> None:
        self.name = name
        self.gate = gate

    def invoke(self, request: PipelineRequest, ctx: CallContext, nxt: Handler) -> PipelineResponse:
        budget = ctx.deadline.remaining() if ctx.deadline.bounded else None
        decision = self.gate.decide(request, budget_s=budget)
        ctx.attrs["backpressure"] = decision.as_dict()
        if decision.action is Action.SHED:
            ctx.event("backpressure_shed", reason=decision.reason, status=decision.status)
            return decision.response()
        if decision.action is Action.DELAY:
            ctx.event("backpressure_delay", delay_s=decision.delay_s)
            ctx.clock.sleep(decision.delay_s)
        return nxt(request, ctx)


def backpressure_stage_factory(gate: BackpressureGate) -> Callable[[Any], BackpressureStage]:
    """``PipelineRouter(stage_factories={"backpressure": backpressure_stage_factory(gate)})``."""

    def factory(_route: Any) -> BackpressureStage:
        return BackpressureStage(gate)

    return factory


def default_backpressure_gate(*, clock: Optional[Clock] = None, gate: Any = None, **kw: Any) -> BackpressureGate:
    from skeleton.gate_plane.backpressure.sources import default_pressure_source

    return BackpressureGate(default_pressure_source(clock=clock or system_clock(), gate=gate), **kw)


__all__ = [
    "Action",
    "BackpressureDecision",
    "BackpressureGate",
    "BackpressureStage",
    "CONTROL_PRIORITY",
    "backpressure_stage_factory",
    "default_backpressure_gate",
]
