"""Provider-neutral inference routing for the Jeeves agent runtime.

The router keeps provider selection, retries, circuit breaking, request caching,
and deterministic test fixtures outside the reasoning loop.  Models are
replaceable proposal engines; the runtime owns control flow and safety.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Deque, Mapping, Protocol, Sequence

from .types import (
    AgentContractError,
    ModelRequest,
    ModelResponse,
    ToolCall,
    finite_number,
    json_safe,
    positive_int,
    require_id,
    stable_fingerprint,
    stable_id,
)


class ProviderError(RuntimeError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class ProviderExhausted(ProviderError):
    pass


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    system_prompt: bool = True
    tools: bool = False
    structured_output: bool = False
    streaming: bool = False
    max_context_tokens: int = 128_000
    max_output_tokens: int = 16_384

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_context_tokens", positive_int("max_context_tokens", self.max_context_tokens, maximum=10_000_000))
        object.__setattr__(self, "max_output_tokens", positive_int("max_output_tokens", self.max_output_tokens, maximum=10_000_000))


class AgentProvider(Protocol):
    name: str
    model: str
    capabilities: ModelCapabilities

    def available(self) -> bool: ...

    def complete(self, request: ModelRequest) -> ModelResponse: ...


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 2
    initial_delay_seconds: float = 0.05
    multiplier: float = 2.0
    max_delay_seconds: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_attempts", positive_int("max_attempts", self.max_attempts, maximum=10))
        initial = finite_number("initial_delay_seconds", self.initial_delay_seconds)
        multiplier = finite_number("multiplier", self.multiplier)
        maximum = finite_number("max_delay_seconds", self.max_delay_seconds)
        if initial < 0 or multiplier < 1 or maximum < 0 or initial > maximum:
            raise AgentContractError("invalid retry backoff configuration")
        object.__setattr__(self, "initial_delay_seconds", initial)
        object.__setattr__(self, "multiplier", multiplier)
        object.__setattr__(self, "max_delay_seconds", maximum)

    def delay_for(self, attempt: int) -> float:
        if attempt <= 0:
            return 0.0
        return min(self.max_delay_seconds, self.initial_delay_seconds * (self.multiplier ** (attempt - 1)))


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Small deterministic circuit breaker per provider."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_seconds: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.failure_threshold = positive_int("failure_threshold", failure_threshold, maximum=1000)
        recovery = finite_number("recovery_seconds", recovery_seconds)
        if recovery <= 0:
            raise AgentContractError("recovery_seconds must be positive")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.recovery_seconds = recovery
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        self._state = CircuitState.CLOSED
        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state is CircuitState.OPEN and self._opened_at is not None:
                if self._clock() - self._opened_at >= self.recovery_seconds:
                    self._state = CircuitState.HALF_OPEN
            return self._state

    def allow(self) -> bool:
        return self.state in {CircuitState.CLOSED, CircuitState.HALF_OPEN}

    def success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None
            self._state = CircuitState.CLOSED

    def failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._state is CircuitState.HALF_OPEN or self._failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()

    def snapshot(self) -> dict[str, Any]:
        return {"state": self.state.value, "failures": self._failures, "opened_at": self._opened_at}


@dataclass(slots=True)
class _CacheEntry:
    response: ModelResponse
    expires_at: float


@dataclass(slots=True)
class ProviderStats:
    calls: int = 0
    successes: int = 0
    failures: int = 0
    retries: int = 0
    cache_hits: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_latency_ms: float = 0.0

    def snapshot(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "successes": self.successes,
            "failures": self.failures,
            "retries": self.retries,
            "cache_hits": self.cache_hits,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "mean_latency_ms": self.total_latency_ms / self.successes if self.successes else 0.0,
        }


class ProviderRouter:
    def __init__(
        self,
        providers: Sequence[AgentProvider],
        *,
        retry_policy: RetryPolicy | None = None,
        cache_ttl_seconds: float | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        provider_tuple = tuple(providers)
        if not provider_tuple:
            raise ValueError("provider router requires at least one provider")
        names = [require_id("provider name", provider.name) for provider in provider_tuple]
        if len(set(names)) != len(names):
            raise ValueError("provider names must be unique")
        self._providers = provider_tuple
        self._retry = retry_policy or RetryPolicy()
        self._cache_ttl = None
        if cache_ttl_seconds is not None:
            ttl = finite_number("cache_ttl_seconds", cache_ttl_seconds)
            if ttl <= 0:
                raise ValueError("cache_ttl_seconds must be positive")
            self._cache_ttl = ttl
        self._sleep = sleep
        self._clock = clock
        self._circuits = {provider.name: CircuitBreaker(clock=clock) for provider in provider_tuple}
        self._stats = {provider.name: ProviderStats() for provider in provider_tuple}
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = threading.RLock()

    def complete(
        self,
        request: ModelRequest,
        *,
        preferred: str | None = None,
        require_tools: bool = False,
        require_structured_output: bool = False,
    ) -> ModelResponse:
        if not isinstance(request, ModelRequest):
            raise TypeError("request must be ModelRequest")
        cached = self._cache_get(request)
        if cached is not None:
            return cached
        providers = self._eligible(
            request,
            preferred=preferred,
            require_tools=require_tools,
            require_structured_output=require_structured_output,
        )
        errors: list[str] = []
        for provider in providers:
            circuit = self._circuits[provider.name]
            if not circuit.allow():
                errors.append(f"{provider.name}: circuit open")
                continue
            for attempt in range(1, self._retry.max_attempts + 1):
                stats = self._stats[provider.name]
                stats.calls += 1
                started = self._clock()
                try:
                    response = provider.complete(request)
                    self._validate_response(provider, request, response)
                    elapsed = max(0.0, self._clock() - started) * 1000.0
                    if response.latency_ms == 0.0:
                        response = replace(response, latency_ms=elapsed)
                    circuit.success()
                    stats.successes += 1
                    stats.prompt_tokens += response.prompt_tokens
                    stats.completion_tokens += response.completion_tokens
                    stats.total_latency_ms += response.latency_ms
                    self._cache_put(request, response)
                    return response
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as exc:
                    circuit.failure()
                    stats.failures += 1
                    errors.append(f"{provider.name} attempt {attempt}: {type(exc).__name__}: {str(exc)[:300]}")
                    if attempt < self._retry.max_attempts and circuit.allow():
                        stats.retries += 1
                        delay = self._retry.delay_for(attempt)
                        if delay:
                            self._sleep(delay)
                    else:
                        break
        raise ProviderExhausted("all eligible providers failed: " + " | ".join(errors[-8:]))

    def _eligible(
        self,
        request: ModelRequest,
        *,
        preferred: str | None,
        require_tools: bool,
        require_structured_output: bool,
    ) -> tuple[AgentProvider, ...]:
        providers = list(self._providers)
        if preferred is not None:
            preferred = require_id("preferred provider", preferred)
            providers.sort(key=lambda provider: 0 if provider.name == preferred else 1)
        eligible: list[AgentProvider] = []
        for provider in providers:
            try:
                if not provider.available():
                    continue
            except Exception:
                continue
            capabilities = provider.capabilities
            if request.max_tokens > capabilities.max_output_tokens:
                continue
            if require_tools and not capabilities.tools:
                continue
            if require_structured_output and not capabilities.structured_output:
                continue
            eligible.append(provider)
        if not eligible:
            raise ProviderUnavailable("no provider satisfies the request capabilities")
        return tuple(eligible)

    @staticmethod
    def _validate_response(provider: AgentProvider, request: ModelRequest, response: ModelResponse) -> None:
        if not isinstance(response, ModelResponse):
            raise ProviderError("provider returned non-ModelResponse")
        if response.request_id != request.request_id:
            raise ProviderError("provider response request_id mismatch")
        if response.provider != provider.name:
            raise ProviderError("provider response provider name mismatch")
        if response.total_tokens < 0:
            raise ProviderError("provider returned invalid usage")

    def _cache_get(self, request: ModelRequest) -> ModelResponse | None:
        if self._cache_ttl is None or request.temperature != 0.0:
            return None
        key = request.fingerprint
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if self._clock() >= entry.expires_at:
                self._cache.pop(key, None)
                return None
            self._stats[entry.response.provider].cache_hits += 1
            return replace(entry.response, request_id=request.request_id, cached=True, latency_ms=0.0)

    def _cache_put(self, request: ModelRequest, response: ModelResponse) -> None:
        if self._cache_ttl is None or request.temperature != 0.0 or response.tool_calls:
            return
        with self._lock:
            self._cache[request.fingerprint] = _CacheEntry(response, self._clock() + self._cache_ttl)

    def stats(self) -> dict[str, Any]:
        return {
            provider.name: {
                **self._stats[provider.name].snapshot(),
                "circuit": self._circuits[provider.name].snapshot(),
                "model": provider.model,
            }
            for provider in self._providers
        }

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()


class LegacyProviderAdapter:
    """Adapt existing ``skeleton.jeeves.providers`` backends to ModelRequest."""

    capabilities = ModelCapabilities(system_prompt=True, tools=False, structured_output=False)

    def __init__(self, provider: Any, *, model: str | None = None) -> None:
        if provider is None or not callable(getattr(provider, "complete", None)):
            raise TypeError("legacy provider must expose complete()")
        self._provider = provider
        self.name = require_id("provider name", str(getattr(provider, "name", "legacy")))
        inferred = model or getattr(provider, "model", None) or self.name
        self.model = str(inferred)
        supports_system = bool(getattr(provider, "supports_system_prompt", False))
        self.capabilities = replace(self.capabilities, system_prompt=supports_system)

    def available(self) -> bool:
        available = getattr(self._provider, "available", None)
        return bool(available()) if callable(available) else True

    def complete(self, request: ModelRequest) -> ModelResponse:
        system_parts: list[str] = []
        history: list[str] = []
        current = ""
        for message in request.messages:
            if message.role.value == "system":
                system_parts.append(message.content)
            elif message.role.value == "user":
                current = message.content
            else:
                history.append(f"{message.role.value}: {message.content}")
        if not current:
            current = request.messages[-1].content
        system = "\n\n".join(system_parts)
        started = time.monotonic()
        if self.capabilities.system_prompt:
            content = self._provider.complete(
                current,
                context=history[-12:],
                max_tokens=request.max_tokens,
                system=system or None,
            )
        else:
            prompt = f"{system}\n\n{current}" if system else current
            content = self._provider.complete(prompt, context=history[-12:], max_tokens=request.max_tokens)
        if not isinstance(content, str):
            raise ProviderError("legacy provider returned non-text output")
        return ModelResponse(
            request_id=request.request_id,
            provider=self.name,
            model=self.model,
            content=content,
            latency_ms=(time.monotonic() - started) * 1000.0,
        )


class DeterministicProvider:
    """Scripted provider for tests, replay, and offline evaluation."""

    def __init__(
        self,
        responses: Sequence[str | Mapping[str, Any] | Exception],
        *,
        name: str = "deterministic",
        model: str = "fixture-v1",
        capabilities: ModelCapabilities | None = None,
    ) -> None:
        self.name = require_id("provider name", name)
        self.model = str(model)
        self.capabilities = capabilities or ModelCapabilities(tools=True, structured_output=True)
        self._responses: Deque[str | Mapping[str, Any] | Exception] = deque(responses)
        self.requests: list[ModelRequest] = []
        self._lock = threading.RLock()

    def available(self) -> bool:
        return True

    def complete(self, request: ModelRequest) -> ModelResponse:
        with self._lock:
            self.requests.append(request)
            if not self._responses:
                raise ProviderError("deterministic response queue exhausted")
            raw = self._responses.popleft()
        if isinstance(raw, Exception):
            raise raw
        if isinstance(raw, str):
            return ModelResponse(
                request_id=request.request_id,
                provider=self.name,
                model=self.model,
                content=raw,
            )
        data = json_safe(dict(raw))
        calls: list[ToolCall] = []
        for index, item in enumerate(data.get("tool_calls", []), start=1):
            if not isinstance(item, dict):
                raise ProviderError("fixture tool call must be an object")
            calls.append(
                ToolCall(
                    call_id=str(item.get("call_id") or stable_id("call", {"request": request.request_id, "index": index, "item": item})),
                    name=str(item["name"]),
                    arguments=item.get("arguments", {}),
                    reason=str(item.get("reason", "")),
                )
            )
        return ModelResponse(
            request_id=request.request_id,
            provider=self.name,
            model=self.model,
            content=str(data.get("content", "")),
            tool_calls=tuple(calls),
            prompt_tokens=int(data.get("prompt_tokens", 0)),
            completion_tokens=int(data.get("completion_tokens", 0)),
            finish_reason=str(data.get("finish_reason", "stop")),
            metadata=data.get("metadata", {}),
        )

    @property
    def remaining(self) -> int:
        with self._lock:
            return len(self._responses)


class RecordingProvider:
    """Decorator that records request/response fingerprints without prompt text."""

    def __init__(self, inner: AgentProvider, *, clock: Callable[[], float] = time.time) -> None:
        self._inner = inner
        self.name = inner.name
        self.model = inner.model
        self.capabilities = inner.capabilities
        self._clock = clock
        self.records: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def available(self) -> bool:
        return self._inner.available()

    def complete(self, request: ModelRequest) -> ModelResponse:
        started = self._clock()
        try:
            response = self._inner.complete(request)
        except BaseException as exc:
            with self._lock:
                self.records.append(
                    {
                        "at": started,
                        "request_id": request.request_id,
                        "request_fingerprint": request.fingerprint,
                        "ok": False,
                        "error_type": type(exc).__name__,
                    }
                )
            raise
        with self._lock:
            self.records.append(
                {
                    "at": started,
                    "request_id": request.request_id,
                    "request_fingerprint": request.fingerprint,
                    "ok": True,
                    "response_fingerprint": stable_fingerprint(
                        {
                            "content": response.content,
                            "tool_calls": [(call.name, call.arguments) for call in response.tool_calls],
                            "finish_reason": response.finish_reason,
                        }
                    ),
                    "prompt_tokens": response.prompt_tokens,
                    "completion_tokens": response.completion_tokens,
                }
            )
        return response
