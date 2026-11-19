"""Opt-in local-native model admission facade over the canonical provider runtime.

No credentials, network calls, or provider selection live here. Jeeves' first
inference is admitted only for a model with matching revision-bound registration,
explicit local adapter identity, operator rights, weights custody, and hardware
capacity evidence. This is NOT a replacement for the native loader checks.
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from collections.abc import AsyncIterator, Callable
from typing import Any

from skeleton.provider_runtime import (
    ProviderAdapter, ProviderDelta, ProviderImageRequest, ProviderImageResponse,
    ProviderInvocationError, ProviderPolicyError, ProviderRequest, ProviderResponse,
    ProviderSpeechRequest, ProviderSpeechResponse,
)
from skeleton.shells.ai.model_registry import AIModelRegistry, ModelNotReadyError

LOCAL_NATIVE_PROVIDER_IDS = frozenset({"local", "native", "gguf", "llama_cpp"})


class LocalModelReadinessGate:
    """Check current model identity for every outbound invocation; fail closed."""

    def __init__(
        self, registry: AIModelRegistry, *, use: str = "model-inference",
        available_vram_mb: Callable[[], int | None] | None = None,
    ) -> None:
        self._registry = registry
        self._use = use
        self._probe = available_vram_mb or (lambda: None)

    def check(self, provider_id: str, model: str | None, *, use: str | None = None) -> None:
        if provider_id not in LOCAL_NATIVE_PROVIDER_IDS or not isinstance(model, str) or not model:
            raise ProviderPolicyError("first-model admission requires a local native provider identity")
        try:
            # Never implicitly substitute a remote advisory or fallback model.
            self._registry.require_ready(
                f"{provider_id}:{model}",
                use=use or self._use,
                available_vram_mb=self._probe(),
            )
        except (ModelNotReadyError, ValueError, KeyError, TypeError) as exc:
            raise ProviderPolicyError(f"local model admission denied: {exc}") from exc


class LocalReadyProviderAdapter(ProviderAdapter):
    """Wrap all provider methods; the inner adapter is deliberately not proxied."""

    def __init__(self, inner: ProviderAdapter, gate: LocalModelReadinessGate) -> None:
        self.__inner = inner
        self.__gate = gate
        self.provider_id = inner.provider_id
        self.model = inner.model
        if self.provider_id not in LOCAL_NATIVE_PROVIDER_IDS:
            raise ProviderPolicyError("remote/advisory adapters are not valid first-model providers")

    def _check(self, use: str, requested_model: str | None = None) -> None:
        if requested_model is not None and requested_model != self.model:
            raise ProviderPolicyError("requested model does not match the admitted adapter")
        self.__gate.check(self.provider_id, self.model, use=use)

    @property
    def available(self) -> bool:
        try:
            self._check("model-inference")
            return bool(self.__inner.available)
        except ProviderPolicyError:
            return False

    def status(self) -> dict[str, Any]:
        return {"id": self.provider_id, "model": self.model,
                "available": self.available, "local_ready_gate": True}

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self._check(request.purpose, request.model)
        return await self.__inner.generate(request)

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderDelta]:
        self._check(request.purpose, request.model)
        async for item in self.__inner.stream(request):
            yield item

    async def generate_image(self, request: ProviderImageRequest) -> ProviderImageResponse:
        self._check("image-generation")
        return await self.__inner.generate_image(request)

    async def create_image_variation(self, image: bytes, **kwargs: Any) -> ProviderImageResponse:
        self._check("image-generation")
        return await self.__inner.create_image_variation(image, **kwargs)

    async def edit_image(self, image: bytes, **kwargs: Any) -> ProviderImageResponse:
        self._check("image-generation")
        return await self.__inner.edit_image(image, **kwargs)

    async def synthesize_speech(self, request: ProviderSpeechRequest) -> ProviderSpeechResponse:
        self._check("speech-synthesis")
        return await self.__inner.synthesize_speech(request)


@dataclass(frozen=True, slots=True)
class ResourceEnvelope:
    """Explicit deadline and output-byte custody for opt-in local generation."""

    max_seconds: float = 60.0
    max_buffer_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        if not math.isfinite(self.max_seconds) or not 0 < self.max_seconds <= 3600:
            raise ValueError("max_seconds must be finite and in (0, 3600]")
        if type(self.max_buffer_bytes) is not int or not 0 < self.max_buffer_bytes <= 4 * 1024**3:
            raise ValueError("max_buffer_bytes must be a positive bounded integer")


class EnvelopedLocalReadyAdapter(LocalReadyProviderAdapter):
    """Apply admission checks and deadline/response custody without fallback."""

    def __init__(self, inner: ProviderAdapter, gate: LocalModelReadinessGate,
                 envelope: ResourceEnvelope) -> None:
        super().__init__(inner, gate)
        self._envelope = envelope

    async def _bound(self, awaitable: Any) -> Any:
        try:
            result = await asyncio.wait_for(awaitable, timeout=self._envelope.max_seconds)
        except TimeoutError as exc:
            raise ProviderInvocationError("local model deadline exceeded") from exc
        text = getattr(result, "text", None)
        if isinstance(text, str) and len(text.encode("utf-8")) > self._envelope.max_buffer_bytes:
            raise ProviderInvocationError("local model output byte budget exceeded")
        return result

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        return await self._bound(super().generate(request))

    async def generate_image(self, request: ProviderImageRequest) -> ProviderImageResponse:
        return await self._bound(super().generate_image(request))

    async def synthesize_speech(self, request: ProviderSpeechRequest) -> ProviderSpeechResponse:
        return await self._bound(super().synthesize_speech(request))

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderDelta]:
        budget = self._envelope.max_buffer_bytes
        try:
            async with asyncio.timeout(self._envelope.max_seconds):
                async for item in super().stream(request):
                    # Bound all text deltas, not merely the final assembled answer.
                    text = getattr(item, "text", None)
                    if isinstance(text, str):
                        budget -= len(text.encode("utf-8"))
                    if budget < 0:
                        raise ProviderInvocationError("local model streamed byte budget exceeded")
                    yield item
        except TimeoutError as exc:
            raise ProviderInvocationError("local model stream deadline exceeded") from exc


class ResourceEnvelopeExhausted(ProviderInvocationError):
    """A byte or step budget was exceeded. The invocation has no result."""

    def __init__(self, kind: str) -> None:
        if kind not in {"bytes", "steps"}:
            raise ValueError("envelope failure kind must be bytes or steps")
        super().__init__(f"resource envelope {kind} budget exhausted")
        self.kind = kind


class InvocationBudget:
    """Remainder of one invocation. Nested budgets share the parent counters.

    ``byte_budget`` and ``step_budget`` are the arguments of the call that
    created this frame. They are not process globals. A charge that would
    exceed this frame or the shared remainder is rejected before either
    counter moves.
    """

    def __init__(
        self,
        byte_budget: int,
        step_budget: int,
        *,
        shared: dict[str, int] | None = None,
    ) -> None:
        _budget_int(byte_budget, "byte_budget")
        _budget_int(step_budget, "step_budget")
        self._frame_bytes = byte_budget
        self._frame_steps = step_budget
        self._shared = shared if shared is not None else {
            "bytes": byte_budget,
            "steps": step_budget,
        }

    @property
    def remaining_bytes(self) -> int:
        return min(self._frame_bytes, self._shared["bytes"])

    @property
    def remaining_steps(self) -> int:
        return min(self._frame_steps, self._shared["steps"])

    def charge(self, *, nbytes: int, steps: int) -> None:
        _budget_int(nbytes, "nbytes")
        _budget_int(steps, "steps")
        if nbytes > self._frame_bytes or nbytes > self._shared["bytes"]:
            raise ResourceEnvelopeExhausted("bytes")
        if steps > self._frame_steps or steps > self._shared["steps"]:
            raise ResourceEnvelopeExhausted("steps")
        self._frame_bytes -= nbytes
        self._frame_steps -= steps
        self._shared["bytes"] -= nbytes
        self._shared["steps"] -= steps


def _budget_int(value: int, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def invoke_bounded(
    work: Callable[[InvocationBudget], Any],
    *,
    byte_budget: int,
    step_budget: int,
    parent: InvocationBudget | None = None,
) -> Any:
    """Run ``work`` under explicit budgets.

    On exhaustion the exception propagates and this function does not return
    the work's value. A nested call passes ``parent`` and spends that
    remainder; its own budgets are additional caps, not a new pool.
    """

    if not callable(work):
        raise TypeError("work must be callable")
    _budget_int(byte_budget, "byte_budget")
    _budget_int(step_budget, "step_budget")
    if parent is not None and type(parent) is not InvocationBudget:
        raise TypeError("parent budget must be an InvocationBudget")
    shared = None if parent is None else parent._shared
    budget = InvocationBudget(byte_budget, step_budget, shared=shared)
    return work(budget)


def run_bounded_loop(
    count: int,
    *,
    byte_budget: int,
    step_budget: int,
    nbytes: int,
    steps: int,
    parent: InvocationBudget | None = None,
) -> tuple[int, ...]:
    """Charge once per iteration and return only if every iteration fits."""

    if type(count) is not int or not 0 <= count <= 1_000_000:
        raise ValueError("count must be a bounded non-negative integer")

    def work(budget: InvocationBudget) -> tuple[int, ...]:
        produced: list[int] = []
        for index in range(count):
            budget.charge(nbytes=nbytes, steps=steps)
            produced.append(index)
        return tuple(produced)

    return invoke_bounded(
        work,
        byte_budget=byte_budget,
        step_budget=step_budget,
        parent=parent,
    )
