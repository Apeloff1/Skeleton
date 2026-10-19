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

    def __init__(
        self,
        runtime: NativeLLMRuntime,
        *,
        model_id: str = "skeleton-native-transformer",
        backup_runtime: NativeLLMRuntime | None = None,
    ) -> None:
        if not isinstance(runtime, NativeLLMRuntime):
            raise TypeError("runtime must be NativeLLMRuntime")
        if backup_runtime is not None and not isinstance(backup_runtime, NativeLLMRuntime):
            raise TypeError("backup_runtime must be NativeLLMRuntime or None")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("model_id must be non-empty")
        self.runtime = runtime
        self.backup_runtime = backup_runtime
        self.model_id = model_id.strip()
        self._model_digest = runtime.model_digest
        self._tokenizer_digest = runtime.tokenizer.digest
        self._runtime_digest = self._compute_runtime_digest()
        self._backup_failover_count = 0

    @property
    def model_digest(self) -> str:
        return self._model_digest

    @property
    def runtime_digest(self) -> str:
        return self._runtime_digest

    @property
    def backup_failover_count(self) -> int:
        return self._backup_failover_count

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

        started = time.perf_counter()
        default_policy = (
            request.temperature == 1.0
            and request.top_k == 0
            and request.top_p == 1.0
            and request.min_p == 0.0
            and request.repetition_penalty == 1.0
        )
        config = (
            GenerationConfig(
                max_new_tokens=request.max_output_tokens,
                seed=request.seed,
                temperature=0.0,
                use_cache=True,
            )
            if default_policy
            else GenerationConfig(
                max_new_tokens=request.max_output_tokens,
                seed=request.seed,
                temperature=request.temperature,
                top_k=request.top_k,
                top_p=request.top_p,
                min_p=request.min_p,
                repetition_penalty=request.repetition_penalty,
                use_cache=True,
            )
        )
        prompt = request.rendered_input
        prompt_sequence: tuple[int, ...] = ()
        stream = None
        result = None
        active_runtime = self.runtime
        try:
            self._assert_identity()
            prompt_sequence = self.runtime.encode(prompt)
            stream = self.runtime.stream(
                prompt,
                config,
            )
            for _event in stream:
                if cancel.is_set():
                    raise LocalInferenceCancelled("local generation cancelled")
            result = stream.result
            if result is None:
                raise RuntimeError("native transformer completed without a terminal result")
            self._assert_identity()
        except LocalInferenceCancelled:
            raise
        except Exception:
            if self.backup_runtime is None:
                raise
            self.backup_runtime.tokenizer.assert_unchanged()
            self.backup_runtime.assert_model_unchanged()
            active_runtime = self.backup_runtime
            prompt_sequence = self.backup_runtime.encode(prompt)
            b_stream = self.backup_runtime.stream(prompt, config)
            for _event in b_stream:
                if cancel.is_set():
                    raise LocalInferenceCancelled("local generation cancelled")
            result = b_stream.result
            if result is None:
                raise RuntimeError("backup native transformer completed without a terminal result")
            self._backup_failover_count += 1

        text = result.text
        output_tokens = len(result.generated_ids)
        finish_reason = (
            result.finish_reason
            if result.finish_reason in {"completed", "length"}
            else "completed"
        )
        stop_index = self._first_stop_index(text, request.stop)
        if stop_index is not None:
            text = text[:stop_index]
            # String stops are a compatibility surface above token generation.
            # Re-tokenize the published prefix so usage and response identity
            # describe exactly the content returned to the caller.
            output_tokens = 0 if not text else len(active_runtime.tokenizer.encode_ids(text))
            finish_reason = "completed"

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
    backup_runtime: NativeLLMRuntime | None = None,
) -> LocalModelAdapter:
    """Build the canonical provider-neutral adapter for the owned transformer."""
    backend = NativeTransformerModel(runtime, model_id=model_id, backup_runtime=backup_runtime)
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
            "has_backup_runtime": backup_runtime is not None,
        },
    )


__all__ = ["NativeTransformerModel", "build_native_transformer_adapter"]
