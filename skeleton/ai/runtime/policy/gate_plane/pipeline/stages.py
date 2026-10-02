"""Built-in Pack F pipeline stages: deadline, retry, breaker, attempt timeout.

See :mod:`skeleton.gate_plane.pipeline.core` for the canonical ordering and
why it matters. All stages read time and sleep through ``ctx.clock`` so the
chaos suite can run them on a :class:`ManualClock` with zero real sleeps.
"""

from __future__ import annotations

import concurrent.futures
import random
from typing import Any, Dict, Optional

from skeleton.gate_plane.pipeline.breaker import CircuitBreaker
from skeleton.gate_plane.pipeline.budget import RetryBudget
from skeleton.gate_plane.pipeline.core import CallContext, Handler, PipelineRequest, PipelineResponse, StageCounter
from skeleton.gate_plane.pipeline.errors import (
    AttemptTimeout,
    BreakerOpenError,
    DeadlineExceeded,
    PipelineError,
)
from skeleton.gate_plane.pipeline.retry import RetrySpec, Verdict


class DeadlineStage:
    """Applies one total time budget (``timeout_s``) to the whole call.

    The deadline only ever shrinks: an inherited, earlier ``ctx.deadline``
    (e.g. propagated from the caller) wins. If the deadline has already
    passed when a response comes back, idempotent requests fail with
    :class:`DeadlineExceeded`; non-idempotent ones keep the response (the
    write happened — reporting a timeout would invite a duplicate) and a
    ``deadline_overrun`` event is recorded.
    """

    kind = "deadline"

    def __init__(self, timeout_s: float, *, name: str = "deadline") -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be > 0")
        self.name = name
        self.timeout_s = float(timeout_s)
        self.counter = StageCounter()

    def invoke(self, request: PipelineRequest, ctx: CallContext, nxt: Handler) -> PipelineResponse:
        ctx.deadline = ctx.deadline.child(self.timeout_s)
        if ctx.deadline.expired():
            self.counter.inc("expired_on_entry")
            ctx.event("deadline_exceeded", phase="entry")
            raise DeadlineExceeded("deadline already expired on entry")
        response = nxt(request, ctx)
        if ctx.deadline.expired():
            if request.idempotent:
                self.counter.inc("expired")
                ctx.event("deadline_exceeded", phase="exit")
                raise DeadlineExceeded(f"call exceeded {self.timeout_s:.3f}s budget")
            self.counter.inc("overrun_kept")
            ctx.event("deadline_overrun", status=response.status)
        return response

    def stats(self) -> Dict[str, Any]:
        return {"timeout_s": self.timeout_s, **self.counter.snapshot()}


class AttemptTimeoutStage:
    """Caps a single attempt at ``attempt_timeout_s`` (never past ``ctx.deadline``).

    *Cooperative* mode (default) checks the attempt deadline once the
    handler returns and raises :class:`AttemptTimeout` for a late result —
    this is what deterministic tests use. Pass ``executor`` for *enforced*
    mode, where the handler runs on a worker thread and the caller stops
    waiting at the deadline (the worker cannot be killed; handlers should
    honour ``ctx.attrs['attempt_deadline'].remaining()`` as their socket
    timeout).
    """

    kind = "attempt_timeout"

    def __init__(
        self,
        attempt_timeout_s: float,
        *,
        executor: Optional[concurrent.futures.Executor] = None,
        name: str = "attempt_timeout",
    ) -> None:
        if attempt_timeout_s <= 0:
            raise ValueError("attempt_timeout_s must be > 0")
        self.name = name
        self.attempt_timeout_s = float(attempt_timeout_s)
        self.executor = executor
        self.counter = StageCounter()

    def invoke(self, request: PipelineRequest, ctx: CallContext, nxt: Handler) -> PipelineResponse:
        attempt_deadline = ctx.deadline.child(self.attempt_timeout_s)
        ctx.attrs["attempt_deadline"] = attempt_deadline
        if attempt_deadline.expired():
            self.counter.inc("expired_on_entry")
            raise AttemptTimeout("no time left for another attempt")
        if self.executor is not None:
            future = self.executor.submit(nxt, request, ctx)
            try:
                response = future.result(timeout=attempt_deadline.remaining())
            except concurrent.futures.TimeoutError:
                future.cancel()
                self.counter.inc("timeout")
                ctx.event("attempt_timeout", mode="enforced")
                raise AttemptTimeout(f"attempt exceeded {self.attempt_timeout_s:.3f}s") from None
        else:
            response = nxt(request, ctx)
            if attempt_deadline.expired():
                self.counter.inc("timeout")
                ctx.event("attempt_timeout", mode="cooperative", status=response.status)
                raise AttemptTimeout(f"attempt exceeded {self.attempt_timeout_s:.3f}s")
        self.counter.inc("ok")
        return response

    def stats(self) -> Dict[str, Any]:
        return {"attempt_timeout_s": self.attempt_timeout_s, **self.counter.snapshot()}


class BreakerStage:
    """Consults a :class:`CircuitBreaker` on every attempt.

    Accounting: 2xx/3xx and non-429 4xx are breaker *successes* (the
    upstream answered); 429 releases the permit without counting; 5xx,
    attempt timeouts and transport errors are *failures*.
    """

    kind = "breaker"

    def __init__(self, breaker: CircuitBreaker, *, spec: Optional[RetrySpec] = None, name: str = "breaker") -> None:
        self.name = name
        self.breaker = breaker
        self.spec = spec or RetrySpec()

    def invoke(self, request: PipelineRequest, ctx: CallContext, nxt: Handler) -> PipelineResponse:
        if not self.breaker.try_acquire():
            retry_after = self.breaker.retry_after_s()
            ctx.event("breaker_reject", breaker=self.breaker.name, retry_after_s=retry_after)
            raise BreakerOpenError(self.breaker.name, retry_after_s=retry_after)
        try:
            response = nxt(request, ctx)
        except Exception as exc:  # noqa: BLE001 - classified, then re-raised
            if isinstance(exc, AttemptTimeout) or not isinstance(exc, PipelineError):
                self.breaker.record_failure()
            else:
                self.breaker.record_ignored()
            raise
        except BaseException:
            self.breaker.record_ignored()
            raise
        verdict = self.spec.classify_response(response)
        if response.status == 429:
            self.breaker.record_ignored()
        elif verdict in (Verdict.SUCCESS, Verdict.CLIENT_ERROR):
            self.breaker.record_success()
        else:
            self.breaker.record_failure()
        return response


class RetryStage:
    """Re-issues retryable failures within attempts, deadline and budget.

    A retry happens only if *all* hold: the failure is retryable, attempts
    remain, the method is retry-safe (or carries an Idempotency-Key), the
    backoff fits inside the remaining deadline, and the shared
    :class:`RetryBudget` grants a token. The token is withdrawn last so a
    retry that would be refused anyway never spends one. Backoff honours a
    server ``Retry-After`` (capped by ``spec.max_retry_after_s``).
    """

    kind = "retry"

    def __init__(
        self,
        spec: RetrySpec,
        *,
        budget: Optional[RetryBudget] = None,
        rng: Optional[random.Random] = None,
        name: str = "retry",
    ) -> None:
        self.name = name
        self.spec = spec
        self.budget = budget
        self.rng = rng or random.Random()
        self.counter = StageCounter()

    def invoke(self, request: PipelineRequest, ctx: CallContext, nxt: Handler) -> PipelineResponse:
        if self.budget is not None:
            self.budget.deposit()
        attempts = 0
        while True:
            ctx.attempt = attempts + 1
            response: Optional[PipelineResponse] = None
            error: Optional[BaseException] = None
            try:
                response = nxt(request, ctx)
                verdict = self.spec.classify_response(response)
            except Exception as exc:  # noqa: BLE001 - classified below
                error = exc
                verdict = self.spec.classify_error(exc)
            attempts += 1
            ctx.attrs["attempts"] = attempts
            self.counter.inc("attempts")

            if verdict is not Verdict.RETRYABLE:
                return self._finish(response, error)

            stop: Optional[str] = None
            delay = 0.0
            if attempts >= self.spec.max_attempts:
                stop = "attempts_exhausted"
            elif not self.spec.method_allows_retry(request):
                stop = "unsafe_method"
            else:
                hint = self.spec.retry_after_hint(response) if response is not None else None
                delay = hint if hint is not None else self.spec.backoff(attempts, self.rng)
                if ctx.deadline.bounded and delay >= ctx.deadline.remaining():
                    stop = "deadline"
                elif self.budget is not None and not self.budget.try_withdraw():
                    stop = "budget_exhausted"
            if stop is not None:
                self.counter.inc(f"stop_{stop}")
                ctx.event("retry_stop", reason=stop)
                return self._finish(response, error)

            self.counter.inc("retries")
            cause = f"status_{response.status}" if response is not None else type(error).__name__
            ctx.event("retry", delay_s=delay, cause=cause)
            if delay > 0:
                ctx.clock.sleep(delay)

    @staticmethod
    def _finish(response: Optional[PipelineResponse], error: Optional[BaseException]) -> PipelineResponse:
        if error is not None:
            raise error
        assert response is not None
        return response

    def stats(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"spec": self.spec.as_dict(), **self.counter.snapshot()}
        if self.budget is not None:
            out["budget"] = self.budget.stats()
        return out


__all__ = ["AttemptTimeoutStage", "BreakerStage", "DeadlineStage", "RetryStage"]
