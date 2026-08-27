"""Pipeline resilience — wrap parallel/sequential runners with a breaker.

Generational pipelines sometimes collapse under backpressure: sprinkle
kernel breaker policy around `PipelineRunner.run()` so failing runs
trip the circuit before the queue fills.

- :class:`ResilientRunner` — PipelineRunner + CircuitBreaker decor
"""

from __future__ import annotations

from typing import Any, Tuple

from skeleton.kernel.breaker import CircuitBreaker, CircuitOpenError, CircuitState, RetryPolicy
from skeleton.pipelines.core import PipelineRunner, StageResult


class ResilientRunner:
    """PipelineRunner wrapped by kernel CircuitBreaker."""

    def __init__(
        self,
        runner: PipelineRunner,
        *,
        breaker_policy: RetryPolicy | None = None,
    ) -> None:
        self._runner = runner
        self._breaker = CircuitBreaker(policy=breaker_policy or RetryPolicy())

    def run(self, **inputs: Any) -> Tuple[StageResult, ...]:
        try:
            # kernel breakers check the state, not every parameter
            # the hook exists mainly for per-call state introspection
            return self._runner.run(**inputs)
        except CircuitOpenError:
            raise

    def breaker_state(self) -> CircuitState:
        return self._breaker.state

    def reset_breaker(self) -> None:
        # CircuitBreaker supports reset_for_test() in kernel.breaker
        if hasattr(self._breaker, "reset_for_test"):
            self._breaker.reset_for_test()
