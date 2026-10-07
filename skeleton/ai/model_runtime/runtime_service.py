"""Governed serving service for the native FLGB-02 language-model runtime.

This module binds the executable transformer runtime to the existing
LocalModelRequest/LocalModelReceipt contracts.  It deliberately grants no tool,
filesystem, network, or mutation authority: the only operation is bounded local
inference under a model identity, input digest, output-token budget, cancellation
state, and deadline.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from .flgb_model_runtime import (
    LocalModelReceipt,
    LocalModelRequest,
    ModelIdentity,
    digest_json,
)
from .native_llm_runtime import GenerationResult, NativeLLMRuntime
from .runtime_contracts import (
    GenerationConfig,
    RuntimeContractError,
    RuntimeEvent,
)


class NativeServiceError(RuntimeContractError):
    """Fail-closed native serving boundary violation."""


class CancellationToken:
    """Small explicit cancellation primitive with no hidden authority."""

    def __init__(self) -> None:
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True


@dataclass(frozen=True)
class NativeServiceResult:
    receipt: LocalModelReceipt
    generation: GenerationResult | None
    events: tuple[RuntimeEvent, ...]

    def __post_init__(self) -> None:
        if self.receipt.terminal_reason == "completed":
            if self.generation is None:
                raise NativeServiceError(
                    "completed service result requires generation"
                )
        elif self.generation is not None:
            raise NativeServiceError(
                "non-completed service result cannot publish generation"
            )


class NativeModelService:
    """Execute LocalModelRequest against one immutable native runtime identity."""

    def __init__(
        self,
        runtime: NativeLLMRuntime,
        *,
        identity: ModelIdentity | None = None,
        model_id: str = "native-transformer",
        revision: str = "runtime-v1",
        clock_ns: Callable[[], int] | None = None,
    ) -> None:
        if not isinstance(runtime, NativeLLMRuntime):
            raise NativeServiceError("NativeLLMRuntime required")
        self.runtime = runtime
        self._clock_ns = clock_ns or time.monotonic_ns
        if not callable(self._clock_ns):
            raise NativeServiceError("clock_ns must be callable")

        if identity is None:
            identity = ModelIdentity(
                model_id=model_id,
                revision=revision,
                architecture="tiny-transformer",
                config_digest=runtime.architecture.digest,
                tokenizer_digest=runtime.tokenizer.digest,
                weights_digest=runtime.model_digest,
            )
        if not isinstance(identity, ModelIdentity):
            raise NativeServiceError("ModelIdentity required")
        self._validate_identity(identity)
        self.identity = identity

    @property
    def identity_digest(self) -> str:
        return self.identity.identity_digest

    def _validate_identity(self, identity: ModelIdentity) -> None:
        if identity.config_digest != self.runtime.architecture.digest:
            raise NativeServiceError(
                "model identity config does not match runtime architecture"
            )
        if identity.tokenizer_digest != self.runtime.tokenizer.digest:
            raise NativeServiceError(
                "model identity tokenizer does not match runtime tokenizer"
            )
        if identity.weights_digest != self.runtime.model_digest:
            raise NativeServiceError(
                "model identity weights do not match runtime model"
            )

    @staticmethod
    def input_digest(prompt: str, config: GenerationConfig) -> str:
        if not isinstance(prompt, str):
            raise NativeServiceError("prompt must be a string")
        if not isinstance(config, GenerationConfig):
            raise NativeServiceError("GenerationConfig required")
        return digest_json(
            {
                "prompt": prompt,
                "generation_config": config.to_dict(),
            }
        )

    def request(
        self,
        operation_id: str,
        prompt: str,
        config: GenerationConfig,
        *,
        deadline_ms: int,
    ) -> LocalModelRequest:
        """Create a request already bound to this service's immutable identity."""
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
        prompt_sequence = self.runtime.encode(prompt)
        return digest_json(
            {
                "prompt_tokens": len(prompt_sequence.token_ids),
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
        receipt = LocalModelReceipt(
            operation_id=request.operation_id,
            model_identity_digest=self.identity_digest,
            terminal_reason=terminal_reason,
            output_digest=None,
            usage_digest=self._usage_digest(
                prompt=prompt,
                generated_events=sum(
                    1 for event in events if event.kind == "token"
                ),
                terminal_reason=terminal_reason,
            ),
        )
        return NativeServiceResult(receipt, None, tuple(events))

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
            raise NativeServiceError(
                "generation exceeds local request output-token budget"
            )
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

        Deadline/cancellation checks happen before execution and between emitted
        runtime events.  A transformer kernel invocation is an atomic bounded
        step; this service does not attempt unsafe thread interruption inside it.
        """
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

        start_ns = int(self._clock_ns())
        deadline_ns = start_ns + request.deadline_ms * 1_000_000
        if int(self._clock_ns()) >= deadline_ns:
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
                if int(self._clock_ns()) >= deadline_ns:
                    return self._terminal(
                        request,
                        prompt=prompt,
                        terminal_reason="deadline",
                        events=events,
                    )
            generation = stream.result
            if generation is None:
                raise NativeServiceError(
                    "native runtime completed without generation result"
                )
        except RuntimeContractError:
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
