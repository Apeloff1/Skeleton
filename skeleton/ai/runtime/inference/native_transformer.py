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
from skeleton.ai.model_runtime.tokenization import TokenSequence

from .local import (
    LocalInferenceCancelled,
    LocalInputBudget,
    LocalInputBudgetError,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
    LocalPreparedInput,
)

from .native_runtime import _NativeStreamAudit

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
        self._preparation_issuer = object()

    @property
    def model_digest(self) -> str:
        return self._model_digest

    @property
    def runtime_digest(self) -> str:
        self._assert_identity()
        return self._runtime_digest

    def assert_identity(self) -> None:
        self._assert_identity()

    def check_readiness(self) -> None:
        """Inspect admitted identity/device metadata; workers verify weights."""
        device = self.runtime.device
        if (
            self.model_id != self._admitted_model_id
            or self.runtime.model_digest != self._model_digest
            or self.runtime.tokenizer.digest != self._tokenizer_digest
            or self._compute_runtime_digest() != self._runtime_digest
            or str(getattr(self.runtime.model, "device", "cpu") or "cpu") != device.actual
            or bool(getattr(self.runtime.model, "resident", False)) != device.resident
        ):
            raise RuntimeContractError("native transformer is no longer admitted on its execution device")

    def count_input_tokens(self, request: LocalInferenceRequest) -> int:
        return self.prepare_input(request).input_tokens

    def prepare_input(
        self,
        request: LocalInferenceRequest,
        *,
        scope_digest: str | None = None,
    ) -> LocalPreparedInput:
        if not isinstance(request, LocalInferenceRequest):
            raise TypeError("request must be LocalInferenceRequest")
        if request.tools:
            raise ValueError("native transformer backend does not synthesize governed tool calls")
        if request.structured_output_schema is not None:
            raise ValueError("native transformer backend does not claim structured-output conformance")
        limits = self.generation_limits()
        rendered = request.rendered_input
        try:
            budget = LocalInputBudget.from_limits(limits)
            budget.validate_request(request, 0, rendered=rendered)
        except LocalInputBudgetError as exc:
            raise RuntimeContractError(str(exc)) from exc
        sequence = self.runtime.encode(rendered)
        count = len(sequence.token_ids)
        try:
            budget.validate_tokens(count, request.max_output_tokens)
        except LocalInputBudgetError as exc:
            raise RuntimeContractError(str(exc)) from exc
        return LocalPreparedInput(
            request_digest=request.digest,
            model_digest=self._model_digest,
            runtime_digest=self._runtime_digest,
            execution_profile_digest=None,
            tokenizer_digest=self._tokenizer_digest,
            source_digest=hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            sequence_digest=sequence.digest,
            input_tokens=count,
            scope_digest=scope_digest,
            token_sequence=sequence,
            issuer=self._preparation_issuer,
        )

    def validate_prepared_input(self, request: LocalInferenceRequest, prepared: LocalPreparedInput) -> None:
        self._assert_identity()
        if not isinstance(prepared, LocalPreparedInput):
            raise RuntimeContractError("native prepared input contract is invalid")
        source_digest = hashlib.sha256(request.rendered_input.encode("utf-8")).hexdigest()
        prepared.assert_binding(
            request,
            issuer=self._preparation_issuer,
            model_digest=self._model_digest,
            runtime_digest=self._runtime_digest,
            execution_profile_digest=None,
            tokenizer_digest=self._tokenizer_digest,
            source_digest=source_digest,
        )
        sequence = prepared.token_sequence
        if (
            not isinstance(sequence, TokenSequence)
            or type(sequence.token_ids) is not tuple
            or sequence.tokenizer_digest != self._tokenizer_digest
            or sequence.source_text_digest != source_digest
            or len(sequence.token_ids) != prepared.input_tokens
            or sequence.digest != prepared.sequence_digest
            or any(
                type(token) is not int or not 0 <= token < self.runtime.tokenizer.vocab_size
                for token in sequence.token_ids
            )
        ):
            raise RuntimeContractError("native prepared token sequence changed after admission")
        try:
            LocalInputBudget.from_limits(self._declared_generation_limits()).validate_tokens(
                prepared.input_tokens,
                request.max_output_tokens,
            )
        except LocalInputBudgetError as exc:
            raise RuntimeContractError(str(exc)) from exc

    def generation_limits(self) -> dict[str, Any]:
        """Publish limits from the admitted decoder and its actual tokenizer."""

        self._assert_identity()
        return self._declared_generation_limits()

    def _declared_generation_limits(self) -> dict[str, Any]:
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
        if not isinstance(cancel, threading.Event):
            raise TypeError("cancel must be threading.Event")
        if cancel.is_set():
            raise LocalInferenceCancelled("local generation cancelled")
        return self.infer_prepared(request, cancel, self.prepare_input(request))

    def infer_prepared(
        self,
        request: LocalInferenceRequest,
        cancel: threading.Event,
        prepared: LocalPreparedInput,
    ) -> LocalInferenceResult:
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

        self.validate_prepared_input(request, prepared)
        limits = self._declared_generation_limits()
        if request.max_output_tokens > limits["max_output_tokens"]:
            raise RuntimeContractError("native request exceeds the admitted output-token budget")
        prompt_sequence = prepared.token_sequence
        if len(prompt_sequence.token_ids) > limits["context_window"]:
            raise RuntimeContractError("native request exceeds the admitted context budget")
        if len(prompt_sequence.token_ids) + request.max_output_tokens > limits["max_total_tokens"]:
            raise RuntimeContractError("native request exceeds the admitted total-token budget")
        started = time.perf_counter()

        def interrupt() -> None:
            if cancel.is_set():
                raise LocalInferenceCancelled("local generation cancelled")

        eos_id = self.runtime.tokenizer.special_token_id("eos")
        config = GenerationConfig(
            max_new_tokens=request.max_output_tokens,
            seed=request.seed,
            temperature=0.0,
            use_cache=True,
            stop_token_ids=() if eos_id is None else (eos_id,),
            stop_strings=request.stop,
            include_stop_tokens=False,
        )
        audit = _NativeStreamAudit(self.runtime, prompt_sequence, config)
        stream = self.runtime.stream_sequence(prompt_sequence, config, interrupt=interrupt)
        with stream:
            # The native decoder stops internally and still produces its real
            # terminal result, usage and receipt. Closing at a token event
            # would discard that terminal result rather than complete it.
            for event in stream:
                interrupt()
                audit.observe(event)
        result = stream.result
        if result is None:
            raise RuntimeError("native transformer completed without a terminal result")
        audit.validate(result)
        self._assert_identity()
        interrupt()

        text = result.text
        _bounded_utf8_size(text, _MAX_OUTPUT_BYTES)
        output_tokens = len(result.generated_ids)
        if (
            result.prompt_sequence != prompt_sequence
            or result.usage.prompt_tokens != len(prompt_sequence.token_ids)
            or result.usage.generated_tokens != output_tokens
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
    require_guarded_inference: bool = False,
    guarded_components: Any | None = None,
) -> LocalModelAdapter:
    """Build canonical transformer; protected mode requires trusted composition."""
    from skeleton.provider_runtime import ProviderPolicyError
    if type(require_guarded_inference) is not bool:
        raise ProviderPolicyError("protected transformer mode must be explicit")
    if require_guarded_inference:
        from .guarded_composition import ProtectedLocalComponents
        if not isinstance(guarded_components, ProtectedLocalComponents):
            raise ProviderPolicyError("protected transformer lacks trusted components")
    elif guarded_components is not None:
        raise ProviderPolicyError("protected components require enforced transformer mode")
    backend = NativeTransformerModel(runtime, model_id=model_id)
    engine = LocalInferenceEngine(
        backend, cache_size=cache_size, max_concurrency=max_concurrency,
        max_queue_size=max_queue_size, max_batch_size=max_batch_size,
        require_guarded_context=require_guarded_inference,
    )
    artifact_status = {
            "kind": "native_transformer",
            "model_digest": backend.model_digest,
            "runtime_digest": backend.runtime_digest,
            "tokenizer_digest": runtime.tokenizer.digest,
            "architecture_digest": runtime.architecture.digest,
            "device": runtime.device.to_dict(),
            "generation_limits": backend.generation_limits(),
    }
    if require_guarded_inference:
        from .guarded_composition import compose_protected_local_adapter
        return compose_protected_local_adapter(
            engine, components=guarded_components, default_seed=default_seed,
            artifact_status=artifact_status,
        )
    return LocalModelAdapter(
        engine, default_seed=default_seed, artifact_status=artifact_status,
    )


__all__ = ["NativeTransformerModel", "build_native_transformer_adapter"]
