"""Adapter from Skeleton's repository-owned transformer to local inference."""
from __future__ import annotations

import threading
import time

from skeleton.ai.model_runtime import GenerationConfig, NativeLLMRuntime, RuntimeContractError

from .local import LocalInferenceCancelled, LocalInferenceRequest, LocalInferenceResult


class NativeTransformerModel:
    """Expose NativeLLMRuntime through the canonical LocalModelBackend contract."""

    def __init__(self, runtime: NativeLLMRuntime, *, model_id: str = "skeleton-native-transformer") -> None:
        if not isinstance(runtime, NativeLLMRuntime):
            raise TypeError("runtime must be NativeLLMRuntime")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("model_id must be non-empty")
        self.runtime = runtime
        self.model_id = model_id.strip()
        self._model_digest = runtime.model_digest
        self._tokenizer_digest = runtime.tokenizer.digest

    @property
    def model_digest(self) -> str:
        return self._model_digest

    def _assert_identity(self) -> None:
        self.runtime.assert_model_unchanged()
        self.runtime.tokenizer.assert_unchanged()
        if self.runtime.model_digest != self._model_digest:
            raise RuntimeContractError("native transformer model identity drift")
        if self.runtime.tokenizer.digest != self._tokenizer_digest:
            raise RuntimeContractError("native transformer tokenizer identity drift")

    def infer(self, request: LocalInferenceRequest, cancel: threading.Event) -> LocalInferenceResult:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        if not isinstance(cancel, threading.Event):
            raise TypeError("cancel must be threading.Event")
        if request.tools:
            raise ValueError("native transformer backend does not synthesize governed tool calls")
        if request.structured_output_schema is not None:
            raise ValueError("native transformer backend does not claim structured-output conformance")
        if cancel.is_set():
            raise LocalInferenceCancelled("local generation cancelled")

        self._assert_identity()
        prompt = request.rendered_input
        prompt_sequence = self.runtime.encode(prompt)
        started = time.perf_counter()
        stream = self.runtime.stream(
            prompt,
            GenerationConfig(
                max_new_tokens=request.max_output_tokens,
                seed=request.seed,
                temperature=0.0,
                use_cache=True,
            ),
        )
        for _event in stream:
            if cancel.is_set():
                raise LocalInferenceCancelled("local generation cancelled")
        result = stream.result
        if result is None:
            raise RuntimeError("native transformer completed without a terminal result")
        self._assert_identity()

        text = result.text
        for marker in request.stop:
            index = text.find(marker)
            if index >= 0:
                text = text[:index]
                break

        response_id = "local-native:" + result.output_digest[:32]
        return LocalInferenceResult(
            text=text,
            model_id=self.model_id,
            model_digest=self.model_digest,
            input_tokens=len(prompt_sequence.token_ids),
            output_tokens=len(result.generated_ids),
            finish_reason=result.finish_reason if result.finish_reason in {"completed", "length"} else "completed",
            response_id=response_id,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )


__all__ = ["NativeTransformerModel"]
