"""Pipeline retries — wrap stage callables with bounded retry predicates.

Not every failure should fail-fast: transient scrapes or model timeouts
can succeed on attempt 2. RetryStage wraps a Stage and retries per the
configured predicate/limit.

- :class:`RetryStage` — bounded retry wrapper honoring predicates
"""

from __future__ import annotations

from typing import Any, Tuple

from skeleton.kernel.errors import PipelineError
from skeleton.pipelines.core import PipelineContext, Stage


class RetryError(PipelineError):
    code = "PPL.RETRY"


class RetryStage:
    """Wrap a Stage with bounded retries; usable like a Stage."""

    def __init__(
        self,
        stage: Stage,
        *,
        max_attempts: int = 3,
        retryable: Tuple[type, ...] = (Exception,),
    ) -> None:
        if max_attempts <= 0:
            raise PipelineError("max_attempts must be positive")
        self._stage = stage
        self._attempts = max_attempts
        self._retryable = retryable

    def run(self, context: PipelineContext) -> Any:
        last_exc: Exception = RuntimeError("no attempts")
        for _ in range(1, self._attempts + 1):
            try:
                return self._stage.run(context)
            except Exception as exc:
                if not isinstance(exc, self._retryable):
                    raise
                last_exc = exc
        raise RetryError(
            "retry attempts exhausted",
            context={"stage": self._stage.name, "attempts": self._attempts},
        ) from last_exc

    def name(self) -> str:
        return self._stage.name

    def depends_on(self) -> Tuple[str, ...]:
        return self._stage.depends_on
