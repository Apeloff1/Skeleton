"""Identity-preserving bridge from native transformer to local inference."""
from __future__ import annotations
import threading
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig, RuntimeContractError
from skeleton.ai.runtime.inference.local import LocalInferenceCancelled, LocalInferenceRequest, LocalInferenceResult

class NativeRuntimeBackend:
    """Expose NativeLLMRuntime through LocalModelBackend without duplicating inference."""
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

    @property
    def tokenizer_digest(self) -> str:
        return self._tokenizer_digest

    def _assert_identity(self) -> None:
        self.runtime.assert_model_unchanged()
        self.runtime.tokenizer.assert_unchanged()
        if self.runtime.model_digest != self._model_digest:
            raise RuntimeContractError("native backend model identity drift")
        if self.runtime.tokenizer.digest != self._tokenizer_digest:
            raise RuntimeContractError("native backend tokenizer identity drift")

    def infer(self, request: LocalInferenceRequest, cancel: threading.Event) -> LocalInferenceResult:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        if cancel.is_set():
            raise LocalInferenceCancelled("native generation cancelled before admission")
        if request.tools:
            raise RuntimeContractError("native backend does not admit tool calls")
        if request.structured_output_schema is not None:
            raise RuntimeContractError("native backend does not admit structured output")
        self._assert_identity()
        result = self.runtime.generate(
            request.rendered_input,
            GenerationConfig(
                max_new_tokens=request.max_output_tokens,
                seed=request.seed,
                temperature=0.0,
                top_k=1,
                top_p=1.0,
                use_cache=True,
            ),
        )
        if cancel.is_set():
            raise LocalInferenceCancelled("native generation cancelled")
        self._assert_identity()
        return LocalInferenceResult(
            text=result.text,
            model_id=self.model_id,
            model_digest=self.model_digest,
            input_tokens=result.usage.prompt_tokens,
            output_tokens=result.usage.generated_tokens,
            finish_reason="length" if result.finish_reason == "length" else "completed",
            response_id="native:" + result.replay_receipt.digest[:32],
        )

__all__ = ["NativeRuntimeBackend"]
