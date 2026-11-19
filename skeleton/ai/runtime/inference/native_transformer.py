"""Adapter from Skeleton's repository-owned transformer to local inference."""
from __future__ import annotations

import hashlib
import json
import threading
import time

from skeleton.ai.model_runtime import GenerationConfig, NativeLLMRuntime, RuntimeContractError

from .local import (
    LocalInferenceCancelled,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
)


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
        self._runtime_digest = self._compute_runtime_digest()

    @property
    def model_digest(self) -> str:
        return self._model_digest

    @property
    def runtime_digest(self) -> str:
        return self._runtime_digest

    def _compute_runtime_digest(self) -> str:
        payload = {
            "schema_version": "skeleton.native_transformer.runtime.v1",
            "model_digest": self.runtime.model_digest,
            "tokenizer_digest": self.runtime.tokenizer.digest,
            "architecture_digest": self.runtime.architecture.digest,
            "device": self.runtime.device.to_dict(),
            "limits": self.runtime.limits.to_dict(),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _assert_identity(self) -> None:
        # Report tokenizer-identity violations at the tokenizer contract boundary
        # before the broader model snapshot catches the same vocabulary mutation.
        self.runtime.tokenizer.assert_unchanged()
        self.runtime.assert_model_unchanged()
        if self.runtime.model_digest != self._model_digest:
            raise RuntimeContractError("native transformer model identity drift")
        if self.runtime.tokenizer.digest != self._tokenizer_digest:
            raise RuntimeContractError("native transformer tokenizer identity drift")
        if self._compute_runtime_digest() != self._runtime_digest:
            raise RuntimeContractError("native transformer runtime identity drift")

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
        output_tokens = len(result.generated_ids)
        finish_reason = (
            result.finish_reason
            if result.finish_reason in {"completed", "length"}
            else "completed"
        )
        for marker in request.stop:
            index = text.find(marker)
            if index >= 0:
                text = text[:index]
                # String stops are a compatibility surface above token generation.
                # Re-tokenize the published prefix so usage and response identity
                # describe exactly the content returned to the caller.
                output_tokens = 0 if not text else len(self.runtime.tokenizer.encode_ids(text))
                finish_reason = "completed"
                break

        published_digest = hashlib.sha256(
            json.dumps(
                {
                    "request_digest": request.digest,
                    "model_digest": self.model_digest,
                    "runtime_digest": self.runtime_digest,
                    "text": text,
                    "output_tokens": output_tokens,
                    "finish_reason": finish_reason,
                },
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        response_id = "local-native:" + published_digest[:32]
        execution_receipt_digest = hashlib.sha256(
            (result.replay_receipt.digest + ":" + published_digest).encode("ascii")
        ).hexdigest()
        return LocalInferenceResult(
            text=text,
            model_id=self.model_id,
            model_digest=self.model_digest,
            input_tokens=len(prompt_sequence.token_ids),
            output_tokens=output_tokens,
            finish_reason=finish_reason,
            response_id=response_id,
            execution_receipt_digest=execution_receipt_digest,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )


def build_native_transformer_adapter(
    runtime: NativeLLMRuntime,
    *,
    model_id: str = "skeleton-native-transformer",
    cache_size: int = 128,
    default_seed: int = 0,
) -> LocalModelAdapter:
    """Build the canonical provider-neutral adapter for the owned transformer."""
    backend = NativeTransformerModel(runtime, model_id=model_id)
    engine = LocalInferenceEngine(backend, cache_size=cache_size)
    return LocalModelAdapter(
        engine,
        default_seed=default_seed,
        artifact_status={
            "kind": "native_transformer",
            "model_digest": backend.model_digest,
            "runtime_digest": backend.runtime_digest,
            "tokenizer_digest": runtime.tokenizer.digest,
            "architecture_digest": runtime.architecture.digest,
            "device": runtime.device.to_dict(),
        },
    )


__all__ = ["NativeTransformerModel", "build_native_transformer_adapter"]
