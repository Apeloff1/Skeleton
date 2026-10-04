"""``ModelClient``: the one call surface over every registered provider.

For each request the client walks the registry's ordered candidates.  Each
candidate is guarded by its circuit breaker and called with retries
(backoff + jitter) where every attempt is bounded by a per-attempt timeout,
the caller's overall deadline and a cancellation token.  When a candidate
fails in a provider-health way the client moves on; the registry's fallback
(normally :class:`OfflineProvider`) comes last and is granted a short grace
period past the deadline so Skeleton still answers when everything remote is
down.  Caller errors (invalid request, cancellation, capability denial) stop
the walk immediately because no other provider would do better.

Streaming follows the same walk but may only fail over *before* the first
chunk reaches the caller; once output is visible, a mid-stream failure is
surfaced rather than silently replaying a different model's answer.
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from dataclasses import dataclass, replace
from typing import Any, AsyncIterator, Callable

from .circuit import BreakerBoard, CircuitBreakerConfig, CircuitState
from .deadline import CancellationToken, Clock, Deadline, MonotonicClock, run_with_deadline
from .errors import (
    CapabilityDeniedError,
    CircuitOpenError,
    DeadlineExceededError,
    IntegrationError,
    InvalidRequestError,
    NoProviderAvailableError,
    OperationCancelledError,
    classify_exception,
)
from .observe import ObserverHub
from .provider import CallContext, Provider
from .registry import ProviderRegistry, SelectionPolicy
from .retry import RetryEvent, RetryPolicy, retry_async
from .types import ChatRequest, ChatResponse, StreamAccumulator, StreamChunk

__all__ = ["ClientConfig", "ModelClient"]

_TERMINAL = (InvalidRequestError, OperationCancelledError, CapabilityDeniedError)


@dataclass(frozen=True)
class ClientConfig:
    attempt_timeout: float | None = 60.0
    total_timeout: float | None = 180.0
    stream_idle_timeout: float | None = 30.0
    fallback_grace: float = 2.0
    retry: RetryPolicy = RetryPolicy()
    breaker: CircuitBreakerConfig = CircuitBreakerConfig()
    selection: SelectionPolicy = SelectionPolicy()
    max_concurrency: int = 64

    def __post_init__(self) -> None:
        for name in ("attempt_timeout", "total_timeout", "stream_idle_timeout"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive or None")
        if self.fallback_grace < 0:
            raise ValueError("fallback_grace must be >= 0")
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")


class ModelClient:
    def __init__(
        self,
        registry: ProviderRegistry,
        config: ClientConfig | None = None,
        *,
        clock: Clock | None = None,
        observers: ObserverHub | None = None,
        rng: random.Random | None = None,
        breakers: BreakerBoard | None = None,
    ) -> None:
        self.registry = registry
        self.config = config or ClientConfig()
        self.clock = clock or MonotonicClock()
        self.observers = observers or ObserverHub()
        self._rng = rng or random.Random()
        self.breakers = breakers or BreakerBoard(
            self.config.breaker,
            clock=self.clock,
            on_transition=self._on_circuit_transition,
        )
        self._semaphore = asyncio.Semaphore(self.config.max_concurrency)

    def _on_circuit_transition(self, name: str, old: CircuitState, new: CircuitState) -> None:
        self.observers.emit("circuit_transition", provider=name, attributes={"from": old.value, "to": new.value})

    # -- planning ----------------------------------------------------------
    def _deadline(self, timeout: float | None, deadline: Deadline | None) -> Deadline:
        base = deadline or Deadline.after(self.config.total_timeout, self.clock)
        return base.tighten(timeout)

    def plan(
        self,
        request: ChatRequest,
        *,
        provider: str | None = None,
        policy: SelectionPolicy | None = None,
    ) -> list[str]:
        """Ordered provider names the client would try for ``request``."""

        pol = policy or self.config.selection
        if provider is not None:
            self.registry.info(provider)
            fb = self.registry.fallback_name
            names = [provider]
            if fb is not None and fb != provider:
                tail = self.registry.candidates(request, policy=pol, include_fallback=True)
                names.extend(i.name for i in tail if i.name == fb)
            return names
        return [i.name for i in self.registry.candidates(request, policy=pol)]

    def _attempt_deadline(self, overall: Deadline, is_fallback: bool) -> Deadline:
        if is_fallback and overall.expired() and self.config.fallback_grace > 0:
            return Deadline.after(self.config.fallback_grace, self.clock)
        return overall

    # -- complete ----------------------------------------------------------
    async def complete(
        self,
        request: ChatRequest,
        *,
        timeout: float | None = None,
        deadline: Deadline | None = None,
        token: CancellationToken | None = None,
        provider: str | None = None,
        policy: SelectionPolicy | None = None,
        retry: RetryPolicy | None = None,
    ) -> ChatResponse:
        overall = self._deadline(timeout, deadline)
        tok = token or CancellationToken()
        names = self.plan(request, provider=provider, policy=policy)
        if not names:
            raise NoProviderAvailableError(
                "no provider can serve capabilities "
                + ", ".join(sorted(c.value for c in request.required_capabilities))
            )
        trace_id = uuid.uuid4().hex[:16]
        failures: dict[str, BaseException] = {}
        fallback = self.registry.fallback_name
        started = time.perf_counter()
        async with self._semaphore:
            for position, name in enumerate(names):
                tok.check()
                is_fallback = name == fallback
                attempt_deadline = self._attempt_deadline(overall, is_fallback)
                if attempt_deadline.expired():
                    failures[name] = DeadlineExceededError("deadline exhausted before attempt", provider=name)
                    continue
                try:
                    response = await self._complete_one(
                        name, request, attempt_deadline, tok, trace_id, retry or self.config.retry
                    )
                except _TERMINAL:
                    raise
                except IntegrationError as exc:
                    failures[name] = exc
                    self.observers.emit("provider_failed", provider=name, code=exc.code)
                    continue
                latency = (time.perf_counter() - started) * 1000.0
                used_fallback = position > 0 or is_fallback
                if used_fallback:
                    self.observers.emit(
                        "fallback_served", provider=name, attributes={"skipped": list(failures)}
                    )
                return replace(
                    response,
                    latency_ms=latency,
                    fallback_used=used_fallback,
                    metadata={**dict(response.metadata), "trace_id": trace_id, "tried": names[: position + 1]},
                )
        raise NoProviderAvailableError(
            f"all {len(names)} candidate providers failed", failures=failures
        )

    async def _complete_one(
        self,
        name: str,
        request: ChatRequest,
        deadline: Deadline,
        token: CancellationToken,
        trace_id: str,
        policy: RetryPolicy,
    ) -> ChatResponse:
        provider = self.registry.get(name)
        breaker = self.breakers.get(name)
        info = provider.info
        routed = request if request.model and info.serves_model(request.model) else request.with_model(
            info.default_model or request.model
        )

        async def attempt(n: int) -> ChatResponse:
            breaker.acquire()
            ctx = CallContext(deadline=deadline, token=token, attempt=n, trace_id=trace_id)
            t0 = time.perf_counter()
            self.observers.emit("attempt_started", provider=name, attempt=n)
            try:
                result = await run_with_deadline(
                    lambda: provider.complete(routed, ctx),
                    timeout=self.config.attempt_timeout,
                    deadline=deadline,
                    token=token,
                    what=f"{name} completion",
                )
            except asyncio.CancelledError:
                breaker.release()
                raise
            except BaseException as raw:
                err = classify_exception(raw, provider=name)
                breaker.record_failure(err)
                self.observers.emit(
                    "attempt_failed",
                    provider=name,
                    attempt=n,
                    code=err.code,
                    latency_ms=(time.perf_counter() - t0) * 1000.0,
                )
                if err is raw:
                    raise
                raise err from raw
            breaker.record_success()
            self.observers.emit(
                "attempt_succeeded", provider=name, attempt=n, latency_ms=(time.perf_counter() - t0) * 1000.0
            )
            return result

        def on_retry(event: RetryEvent) -> None:
            if event.will_retry:
                self.observers.emit(
                    "retry_scheduled",
                    provider=name,
                    attempt=event.attempt,
                    code=event.error.code,
                    attributes={"delay": round(event.delay, 4)},
                )

        result, attempts = await retry_async(
            attempt,
            policy=policy,
            clock=self.clock,
            deadline=deadline,
            token=token,
            rng=self._rng,
            on_event=on_retry,
            provider=name,
        )
        return replace(result, attempts=attempts)

    # -- stream ------------------------------------------------------------
    async def stream(
        self,
        request: ChatRequest,
        *,
        timeout: float | None = None,
        deadline: Deadline | None = None,
        token: CancellationToken | None = None,
        provider: str | None = None,
        policy: SelectionPolicy | None = None,
        retry: RetryPolicy | None = None,
    ) -> AsyncIterator[StreamChunk]:
        overall = self._deadline(timeout, deadline)
        tok = token or CancellationToken()
        names = self.plan(request, provider=provider, policy=policy)
        if not names:
            raise NoProviderAvailableError("no provider can serve this streaming request")
        pol = retry or self.config.retry
        fallback = self.registry.fallback_name
        failures: dict[str, BaseException] = {}
        trace_id = uuid.uuid4().hex[:16]
        async with self._semaphore:
            for name in names:
                tok.check()
                is_fallback = name == fallback
                attempt_deadline = self._attempt_deadline(overall, is_fallback)
                if attempt_deadline.expired():
                    failures[name] = DeadlineExceededError("deadline exhausted before attempt", provider=name)
                    continue
                breaker = self.breakers.get(name)
                prov = self.registry.get(name)
                for attempt_no, delay in _attempt_schedule(pol, self._rng):
                    if delay:
                        if delay >= attempt_deadline.remaining():
                            break
                        await self.clock.sleep(delay)
                    tok.check()
                    try:
                        breaker.acquire()
                    except CircuitOpenError as exc:
                        failures[name] = exc
                        break
                    ctx = CallContext(deadline=attempt_deadline, token=tok, attempt=attempt_no, trace_id=trace_id)
                    routed = request if request.model and prov.info.serves_model(request.model) else (
                        request.with_model(prov.info.default_model or request.model)
                    )
                    iterator = prov.stream(routed, ctx).__aiter__()
                    emitted = 0
                    try:
                        first = await self._next_chunk(iterator, attempt_deadline, tok, name)
                    except asyncio.CancelledError:
                        breaker.release()
                        await _aclose(iterator)
                        raise
                    except BaseException as raw:
                        err = classify_exception(raw, provider=name)
                        breaker.record_failure(err)
                        await _aclose(iterator)
                        if isinstance(err, _TERMINAL):
                            _raise(err, raw)
                        failures[name] = err
                        self.observers.emit("stream_open_failed", provider=name, attempt=attempt_no, code=err.code)
                        if not pol.should_retry(err):
                            break
                        continue
                    if first is None:
                        breaker.record_success()
                        failures[name] = IntegrationError("provider produced an empty stream", provider=name)
                        break
                    if is_fallback or failures:
                        self.observers.emit("fallback_served", provider=name, attributes={"skipped": list(failures)})
                    try:
                        chunk: StreamChunk | None = first
                        while chunk is not None:
                            yield replace(chunk, index=emitted, provider=chunk.provider or name)
                            emitted += 1
                            chunk = await self._next_chunk(iterator, attempt_deadline, tok, name)
                    except (asyncio.CancelledError, GeneratorExit):
                        breaker.release()
                        raise
                    except BaseException as raw:
                        err = classify_exception(raw, provider=name)
                        if not isinstance(err, OperationCancelledError):
                            breaker.record_failure(err)
                        self.observers.emit("stream_broken", provider=name, code=err.code)
                        _raise(err, raw)
                    finally:
                        await _aclose(iterator)
                    breaker.record_success()
                    return
        raise NoProviderAvailableError("all streaming candidates failed", failures=failures)

    async def _next_chunk(
        self,
        iterator: AsyncIterator[StreamChunk],
        deadline: Deadline,
        token: CancellationToken,
        name: str,
    ) -> StreamChunk | None:
        async def step() -> StreamChunk | None:
            try:
                return await iterator.__anext__()
            except StopAsyncIteration:
                return None

        return await run_with_deadline(
            step,
            timeout=self.config.stream_idle_timeout,
            deadline=deadline,
            token=token,
            what=f"{name} stream",
        )

    async def stream_to_response(self, request: ChatRequest, **kwargs: Any) -> ChatResponse:
        """Consume :meth:`stream` and fold it into a response."""

        acc = StreamAccumulator()
        started = time.perf_counter()
        async for chunk in self.stream(request, **kwargs):
            acc.add(chunk)
        if not acc.finished:
            acc.add(StreamChunk.finish(acc.chunk_count))
        return acc.build(latency_ms=(time.perf_counter() - started) * 1000.0)

    # -- convenience -------------------------------------------------------
    async def ask(self, prompt: str, *, system: str | None = None, **kwargs: Any) -> str:
        response = await self.complete(ChatRequest.from_prompt(prompt, system=system), **kwargs)
        return response.text

    def snapshot(self) -> dict[str, Any]:
        return {"registry": self.registry.snapshot(), "breakers": self.breakers.snapshot()}

    async def health(self) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        for name in self.registry.names():
            provider: Provider = self.registry.get(name)
            try:
                status = await run_with_deadline(provider.health, timeout=5.0, what=f"{name} health")
                results[name] = status.as_dict()
            except BaseException as raw:  # noqa: BLE001
                err = classify_exception(raw, provider=name)
                results[name] = {"healthy": False, "detail": err.code, "latency_ms": 0.0}
            results[name]["circuit"] = self.breakers.get(name).state.value
        return results


def _raise(err: BaseException, raw: BaseException) -> None:
    if err is raw:
        raise err
    raise err from raw


def _attempt_schedule(policy: RetryPolicy, rng: random.Random) -> list[tuple[int, float]]:
    delays = list(policy.delays(rng))
    return [(1, 0.0)] + [(i + 2, d) for i, d in enumerate(delays)]


async def _aclose(iterator: Any) -> None:
    closer: Callable[[], Any] | None = getattr(iterator, "aclose", None)
    if closer is None:
        return
    try:
        await closer()
    except Exception:  # noqa: BLE001
        pass
