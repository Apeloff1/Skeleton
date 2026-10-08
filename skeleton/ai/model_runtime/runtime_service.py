"""Governed serving service for the native FLGB-02 language-model runtime.

This module binds the executable transformer runtime to the existing
LocalModelRequest/LocalModelReceipt contracts. It grants no tool, filesystem,
network, or mutation authority: the only operation is bounded local inference
under an immutable model identity, exact input digest, output-token budget,
cancellation state, and deadline.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from threading import Event
import time
from typing import Callable

from .flgb_model_runtime import LocalModelReceipt, LocalModelRequest, ModelIdentity, digest_json
from .native_llm_runtime import GenerationResult, NativeLLMRuntime
from .runtime_contracts import GenerationConfig, RuntimeContractError, RuntimeEvent


class NativeServiceError(RuntimeContractError):
    """Fail-closed native serving boundary violation."""


class CancellationToken:
    """Thread-safe explicit cancellation primitive with no hidden authority."""

    def __init__(self) -> None:
        self._event = Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()


@dataclass(frozen=True)
class NativeServiceResult:
    receipt: LocalModelReceipt
    generation: GenerationResult | None
    events: tuple[RuntimeEvent, ...]

    def __post_init__(self) -> None:
        completed = self.receipt.terminal_reason == "completed"
        if completed:
            if self.generation is None:
                raise NativeServiceError("completed service result requires generation")
            if self.receipt.output_digest != self.generation.output_digest:
                raise NativeServiceError("service output receipt mismatch")
            if self.receipt.usage_digest != self.generation.usage.digest:
                raise NativeServiceError("service usage receipt mismatch")
            if not self.events or self.events[-1].kind != "completed":
                raise NativeServiceError("completed service result requires terminal event")
        else:
            if self.generation is not None:
                raise NativeServiceError("failed service result cannot publish generation")
            if self.receipt.output_digest is not None:
                raise NativeServiceError("failed service result cannot publish output digest")
            if any(event.kind in {"token", "stopped", "completed"} for event in self.events):
                raise NativeServiceError("failed service result leaked generated output events")


class NativeModelService:
    """Execute LocalModelRequest against one immutable native runtime identity."""

    def __init__(
        self,
        runtime: NativeLLMRuntime,
        *,
        identity: ModelIdentity | None = None,
        clock_ns: Callable[[], int] | None = None,
    ) -> None:
        if not isinstance(runtime, NativeLLMRuntime):
            raise NativeServiceError("NativeLLMRuntime required")
        self.runtime = runtime
        self._clock_ns = clock_ns or time.monotonic_ns
        if not callable(self._clock_ns):
            raise NativeServiceError("clock_ns must be callable")
        identity = identity or runtime.model_identity
        if not isinstance(identity, ModelIdentity):
            raise NativeServiceError("ModelIdentity required")
        self._validate_identity(identity)
        self.identity = identity

    @property
    def identity_digest(self) -> str:
        return self.identity.identity_digest

    def _now_ns(self) -> int:
        value = self._clock_ns()
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise NativeServiceError("clock_ns must return a non-negative integer")
        return value

    def _validate_identity(self, identity: ModelIdentity) -> None:
        canonical = self.runtime.model_identity
        if identity != canonical:
            raise NativeServiceError("service identity is not the runtime canonical identity")

    @staticmethod
    def input_digest(prompt: str, config: GenerationConfig) -> str:
        if not isinstance(prompt, str):
            raise NativeServiceError("prompt must be a string")
        if not isinstance(config, GenerationConfig):
            raise NativeServiceError("GenerationConfig required")
        try:
            prompt.encode("utf-8", errors="strict")
            return digest_json(
                {
                    "prompt": prompt,
                    "generation_config": config.to_dict(),
                }
            )
        except (TypeError, ValueError, UnicodeError) as exc:
            raise NativeServiceError("request input is not canonically encodable") from exc

    def request(
        self,
        operation_id: str,
        prompt: str,
        config: GenerationConfig,
        *,
        deadline_ms: int,
    ) -> LocalModelRequest:
        """Create a request already bound to this service's canonical identity."""
        return LocalModelRequest(
            operation_id=operation_id,
            model_identity_digest=self.identity_digest,
            input_digest=self.input_digest(prompt, config),
            max_output_tokens=max(1, config.max_new_tokens),
            deadline_ms=deadline_ms,
        )

    def _usage_digest(
        self,
        *,
        prompt: str,
        generated_events: int,
        terminal_reason: str,
    ) -> str:
        # Terminal accounting must not call model or tokenizer code again:
        # the original request may have failed because those contracts drifted.
        try:
            prompt_bytes = prompt.encode("utf-8", errors="strict")
        except (AttributeError, UnicodeEncodeError) as exc:
            raise NativeServiceError("prompt is not valid UTF-8 text") from exc
        return digest_json(
            {
                "schema": "skeleton.ai.native-failure-usage.v2",
                "prompt_bytes": len(prompt_bytes),
                "prompt_digest": sha256(prompt_bytes).hexdigest(),
                "generated_events": generated_events,
                "terminal_reason": terminal_reason,
                "model_identity_digest": self.identity_digest,
            }
        )

    def _terminal(
        self,
        request: LocalModelRequest,
        *,
        prompt: str,
        terminal_reason: str,
        events: list[RuntimeEvent],
    ) -> NativeServiceResult:
        generated_events = sum(1 for event in events if event.kind == "token")
        safe_events = tuple(
            event for event in events if event.kind in {"admitted", "prompt"}
        )
        receipt = LocalModelReceipt(
            operation_id=request.operation_id,
            model_identity_digest=self.identity_digest,
            terminal_reason=terminal_reason,
            output_digest=None,
            usage_digest=self._usage_digest(
                prompt=prompt,
                generated_events=generated_events,
                terminal_reason=terminal_reason,
            ),
        )
        return NativeServiceResult(receipt, None, safe_events)

    def _validate_request(
        self,
        request: LocalModelRequest,
        prompt: str,
        config: GenerationConfig,
    ) -> None:
        if not isinstance(request, LocalModelRequest):
            raise NativeServiceError("LocalModelRequest required")
        if request.model_identity_digest != self.identity_digest:
            raise NativeServiceError("local request model identity mismatch")
        if request.input_digest != self.input_digest(prompt, config):
            raise NativeServiceError("local request input digest mismatch")
        if config.max_new_tokens > request.max_output_tokens:
            raise NativeServiceError("generation exceeds local request output-token budget")
        self.runtime.assert_model_unchanged()
        self.runtime.tokenizer.assert_unchanged()
        self._validate_identity(self.identity)

    def execute(
        self,
        request: LocalModelRequest,
        prompt: str,
        config: GenerationConfig,
        *,
        cancellation: CancellationToken | None = None,
    ) -> NativeServiceResult:
        """Execute one bounded local inference operation.

        Cancellation/deadline checks run before execution and between emitted
        runtime events. A transformer kernel invocation remains one bounded
        atomic step; this service does not attempt unsafe thread interruption.
        """
        if not isinstance(request, LocalModelRequest):
            raise NativeServiceError("LocalModelRequest required")
        start_ns = self._now_ns()
        deadline_ns = start_ns + request.deadline_ms * 1_000_000
        self._validate_request(request, prompt, config)
        token = cancellation or CancellationToken()
        if not isinstance(token, CancellationToken):
            raise NativeServiceError("CancellationToken required")

        events: list[RuntimeEvent] = []
        if token.cancelled:
            return self._terminal(
                request,
                prompt=prompt,
                terminal_reason="cancelled",
                events=events,
            )

        if self._now_ns() >= deadline_ns:
            return self._terminal(
                request,
                prompt=prompt,
                terminal_reason="deadline",
                events=events,
            )

        try:
            stream = self.runtime.stream(prompt, config)
            for event in stream:
                events.append(event)
                if token.cancelled:
                    return self._terminal(
                        request,
                        prompt=prompt,
                        terminal_reason="cancelled",
                        events=events,
                    )
                if self._now_ns() >= deadline_ns:
                    return self._terminal(
                        request,
                        prompt=prompt,
                        terminal_reason="deadline",
                        events=events,
                    )
            generation = stream.result
            if generation is None:
                raise NativeServiceError("native runtime completed without generation result")
        except (RuntimeContractError, TokenizerContractError):
            return self._terminal(
                request,
                prompt=prompt,
                terminal_reason="model_error",
                events=events,
            )

        receipt = LocalModelReceipt(
            operation_id=request.operation_id,
            model_identity_digest=self.identity_digest,
            terminal_reason="completed",
            output_digest=generation.output_digest,
            usage_digest=generation.usage.digest,
        )
        return NativeServiceResult(receipt, generation, tuple(events))


__all__ = [
    "CancellationToken",
    "NativeModelService",
    "NativeServiceError",
    "NativeServiceResult",
]
