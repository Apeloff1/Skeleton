"""Adapter from Skeleton's repository-owned transformer to local inference."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any

from skeleton.ai.model_runtime import (
    GenerationConfig,
    NativeLLMRuntime,
    RuntimeContractError,
)

from .local import (
    LocalInferenceCancelled,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
)

_MAX_OUTPUT_BYTES = 4 * 1024 * 1024


def _bounded_utf8_size(text: str, maximum: int) -> int:
    """Count bounded chunks rather than allocating an oversized encoded copy."""

    size = 0
    for offset in range(0, len(text), 8192):
        size += len(text[offset : offset + 8192].encode("utf-8", errors="strict"))
        if size > maximum:
            raise RuntimeContractError("native generation exceeds the local output byte budget")
    return size


class NativeTransformerModel:
    """Expose NativeLLMRuntime through the canonical LocalModelBackend contract."""

    model_family = "native_transformer"
    protocol_capabilities = ("text-generation",)
    tokenizer_kind = "native_tokenizer"

    def __init__(self, runtime: NativeLLMRuntime, *, model_id: str = "skeleton-native-transformer") -> None:
        if not isinstance(runtime, NativeLLMRuntime):
            raise TypeError("runtime must be NativeLLMRuntime")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("model_id must be non-empty")
        self.runtime = runtime
        self.model_id = model_id.strip()
        self._admitted_model_id = self.model_id
        self._model_digest = runtime.model_digest
        self._tokenizer_digest = runtime.tokenizer.digest
        self._runtime_digest = self._compute_runtime_digest()

    @property
    def model_digest(self) -> str:
        return self._model_digest

    @property
    def runtime_digest(self) -> str:
        self._assert_identity()
        return self._runtime_digest

    def assert_identity(self) -> None:
        self._assert_identity()

    def count_input_tokens(self, request: LocalInferenceRequest) -> int:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        self._assert_identity()
        return len(self.runtime.encode(request.rendered_input).token_ids)

    def generation_limits(self) -> dict[str, Any]:
        """Publish limits from the admitted decoder and its actual tokenizer."""

        self._assert_identity()
        tokenizer_limits = self.runtime.tokenizer.limits
        return {
            "context_window": min(self.runtime.limits.max_context, tokenizer_limits.max_tokens),
            "max_output_tokens": min(8192, self.runtime.limits.max_new_tokens, tokenizer_limits.max_tokens),
            "max_total_tokens": self.runtime.limits.max_total_tokens,
            "shared_context": False,
            "tokenizer": self.tokenizer_kind,
            "tokenizer_max_chars": tokenizer_limits.max_chars,
            "tokenizer_max_tokens": tokenizer_limits.max_tokens,
            "max_output_utf8_bytes": _MAX_OUTPUT_BYTES,
            "limits_source": "activated_native_runtime",
        }

    def _compute_runtime_digest(self) -> str:
        payload = {
            "schema_version": "skeleton.native_transformer.runtime.v1",
            "model_digest": self.runtime.model_digest,
            "tokenizer_digest": self.runtime.tokenizer.digest,
            "architecture_digest": self.runtime.architecture.digest,
            "device": self.runtime.device.to_dict(),
            "device_policy": self.runtime.device_policy.to_dict(),
            "limits": self.runtime.limits.to_dict(),
            "tokenizer_limits": {
                name: getattr(self.runtime.tokenizer.limits, name)
                for name in ("max_chars", "max_tokens", "max_chunks", "max_chunk_chars")
            },
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _assert_identity(self) -> None:
        # Report tokenizer-identity violations at the tokenizer contract boundary
        # before the broader model snapshot catches the same vocabulary mutation.
        self.runtime.tokenizer.assert_unchanged()
        self.runtime.assert_model_unchanged()
        if self.model_id != self._admitted_model_id:
            raise RuntimeContractError("native transformer model identifier drift")
        if self.runtime.model_digest != self._model_digest:
            raise RuntimeContractError("native transformer model identity drift")
        if self.runtime.tokenizer.digest != self._tokenizer_digest:
            raise RuntimeContractError("native transformer tokenizer identity drift")
        if self._compute_runtime_digest() != self._runtime_digest:
            raise RuntimeContractError("native transformer runtime identity drift")

    @staticmethod
    def _first_stop_index(text: str, stops: tuple[str, ...]) -> int | None:
        """Use the first stop occurrence in generated text, not marker-list order."""
        indices = (text.find(marker) for marker in stops if marker)
        return min((index for index in indices if index >= 0), default=None)

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

        limits = self.generation_limits()
        if request.max_output_tokens > limits["max_output_tokens"]:
            raise RuntimeContractError("native request exceeds the admitted output-token budget")
        prompt = request.rendered_input
        prompt_sequence = self.runtime.encode(prompt)
        if len(prompt_sequence.token_ids) > limits["context_window"]:
            raise RuntimeContractError("native request exceeds the admitted context budget")
        if len(prompt_sequence.token_ids) + request.max_output_tokens > limits["max_total_tokens"]:
            raise RuntimeContractError("native request exceeds the admitted total-token budget")
        started = time.perf_counter()

        def interrupt() -> None:
            if cancel.is_set():
                raise LocalInferenceCancelled("local generation cancelled")

        eos_id = self.runtime.tokenizer.special_token_id("eos")
        stream = self.runtime.stream_sequence(
            prompt_sequence,
            GenerationConfig(
                max_new_tokens=request.max_output_tokens,
                seed=request.seed,
                temperature=0.0,
                use_cache=True,
                stop_token_ids=() if eos_id is None else (eos_id,),
                stop_strings=request.stop,
                include_stop_tokens=False,
            ),
            interrupt=interrupt,
        )
        generated_bytes = 0
        generated_count = 0
        with stream:
            # The native decoder stops internally and still produces its real
            # terminal result, usage and receipt. Closing at a token event
            # would discard that terminal result rather than complete it.
            for event in stream:
                interrupt()
                if event.kind == "token":
                    generated_count += 1
                    if generated_count > request.max_output_tokens:
                        raise RuntimeContractError("native decoder exceeded its output-token budget")
                    piece = self.runtime.tokenizer.token_text(event.token_id)
                    generated_bytes += _bounded_utf8_size(piece, _MAX_OUTPUT_BYTES) + int(generated_count > 1)
                    if generated_bytes > _MAX_OUTPUT_BYTES:
                        raise RuntimeContractError("native generation exceeds the local output byte budget")
        result = stream.result
        if result is None:
            raise RuntimeError("native transformer completed without a terminal result")
        self._assert_identity()
        interrupt()

        text = result.text
        _bounded_utf8_size(text, _MAX_OUTPUT_BYTES)
        output_tokens = len(result.generated_ids)
        if (
            result.prompt_sequence != prompt_sequence
            or result.usage.prompt_tokens != len(prompt_sequence.token_ids)
            or result.usage.generated_tokens != output_tokens
            or generated_count != output_tokens
            or output_tokens > request.max_output_tokens
        ):
            raise RuntimeContractError("native terminal result does not match admitted token accounting")
        if result.finish_reason not in {"completed", "length", "stop_token", "stop_string"}:
            raise RuntimeContractError("native decoder returned an unsupported terminal reason")
        finish_reason = "length" if result.finish_reason == "length" else "completed"
        stop_index = self._first_stop_index(text, request.stop)
        if stop_index is not None:
            text = text[:stop_index]
            # Usage accounts for actual generation work, including a stop
            # delimiter that is withheld from the published text.
            finish_reason = "completed"

        published_digest = hashlib.sha256(
            json.dumps(
                {
                    "request_digest": request.digest,
                    "model_digest": self.model_digest,
                    "runtime_digest": self._runtime_digest,
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
        interrupt()
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
    max_concurrency: int = 1,
    max_queue_size: int = 256,
    max_batch_size: int = 256,
) -> LocalModelAdapter:
    """Build the canonical provider-neutral adapter for the owned transformer."""
    backend = NativeTransformerModel(runtime, model_id=model_id)
    engine = LocalInferenceEngine(
        backend, cache_size=cache_size, max_concurrency=max_concurrency,
        max_queue_size=max_queue_size, max_batch_size=max_batch_size,
    )
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
            "generation_limits": backend.generation_limits(),
        },
    )


__all__ = ["NativeTransformerModel", "build_native_transformer_adapter"]
