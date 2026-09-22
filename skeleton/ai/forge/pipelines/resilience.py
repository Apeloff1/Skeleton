"""Pipeline resilience — wrap parallel/sequential runners with a breaker.

Generational pipelines sometimes collapse under backpressure: sprinkle
kernel breaker policy around ``PipelineRunner.run()`` so failing runs
trip the circuit before the queue fills.

- :class:`ResilientRunner` — PipelineRunner + CircuitBreaker decor

Fix (2026-08-30): the original constructor passed ``policy=...`` to
``CircuitBreaker`` — a kwarg the kernel breaker does not accept — so the
wrapper raised ``TypeError`` at construction, and ``run()`` never engaged
the breaker anyway. The wrapper now builds the breaker correctly
(name + thresholds) and actually routes every run through
``before_call`` / ``on_success`` / ``on_failure``.
"""

from __future__ import annotations

from typing import Any, Tuple

from skeleton.kernel.breaker import CircuitBreaker, CircuitOpenError, CircuitState
from skeleton.pipelines.core import PipelineRunner, StageResult


class ResilientRunner:
    """PipelineRunner wrapped by kernel CircuitBreaker.

    A run counts as a breaker failure when any stage errored (the runner
    records stage errors on StageResult rather than raising, in non-
    fail-fast mode). OPEN circuits fail fast with CircuitOpenError
    before any stage executes.
    """

    def __init__(
        self,
        runner: PipelineRunner,
        *,
        name: str = "pipeline",
        failure_threshold: int = 5,
        window_s: float = 30.0,
        cooldown_s: float = 10.0,
        half_open_probes: int = 2,
    ) -> None:
        self._runner = runner
        self._breaker = CircuitBreaker(
            name,
            failure_threshold=failure_threshold,
            window_s=window_s,
            cooldown_s=cooldown_s,
            half_open_probes=half_open_probes,
        )

    def run(self, **inputs: Any) -> Tuple[StageResult, ...]:
        self._breaker.before_call()  # raises CircuitOpenError while OPEN
        try:
            results = self._runner.run(**inputs)
        except Exception:
            self._breaker.on_failure()
            raise
        if any(r.error is not None for r in results):
            self._breaker.on_failure()
        else:
            self._breaker.on_success()
        return results

    def breaker_state(self) -> CircuitState:
        return self._breaker.state

    def report(self) -> dict:
        return self._breaker.report()

    def reset_breaker(self) -> None:
        # Test hook: reconstruct the breaker with identical settings.
        self._breaker = CircuitBreaker(
            self._breaker.name,
            failure_threshold=self._breaker.failure_threshold,
            window_s=self._breaker.window_s,
            cooldown_s=self._breaker.cooldown_s,
            half_open_probes=self._breaker.half_open_probes,
        )
