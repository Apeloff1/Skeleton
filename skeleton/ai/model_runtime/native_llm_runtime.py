"""Executable native LLM serving boundary over Skeleton's causal transformer."""
from __future__ import annotations
from dataclasses import dataclass
import math
import hmac
import random
import sys
from array import array
import threading
from weakref import WeakKeyDictionary
from typing import Any, Callable, Iterator, Mapping, Sequence

from skeleton.cortex.attn import sample_logits
from skeleton.cortex.transformer import KVCache, TinyTransformer

from .flgb_model_runtime import ModelIdentity, TokenSequence, digest_json
from .runtime_checkpoint import (
    checkpoint_json as encode_checkpoint_json,
    logical_bytes,
    make_checkpoint,
    parse_checkpoint_json,
    capture_validated_model,
    restore_components,
)
from .runtime_contracts import (
    BatchGenerationRequest,
    DevicePolicy,
    DeviceReceipt,
    GenerationConfig,
    ReplayMismatch,
    ReplayReceipt,
    RuntimeArchitecture,
    RuntimeContractError,
    RuntimeEvent,
    RuntimeLimits,
    RuntimeUsage,
)
from .tokenization import NativeTokenizer, StreamingTextFeed, TokenizerContractError
from .decode_acceleration import RollingPenaltyWindow, WordStopMatcher


@dataclass(frozen=True)
class GenerationResult:
    prompt_sequence: TokenSequence
    generated_ids: tuple[int, ...]
    generated_tokens: tuple[str, ...]
    text: str
    finish_reason: str
    usage: RuntimeUsage
    replay_receipt: ReplayReceipt
    events: tuple[RuntimeEvent, ...]
    checkpoint_digest: str

    @property
    def output_digest(self) -> str:
        return self.replay_receipt.output_digest

    def to_record(self) -> dict[str, Any]:
        receipt = self.replay_receipt
        return {
            "model_digest": receipt.model_digest,
            "tokenizer_digest": receipt.tokenizer_digest,
            "architecture_digest": receipt.architecture_digest,
            "request_digest": receipt.request_digest,
            "output_digest": receipt.output_digest,
            "config_digest": receipt.config_digest,
            "device_digest": receipt.device_digest,
            "prompt_token_ids": list(self.prompt_sequence.token_ids),
            "generated_token_ids": list(self.generated_ids),
            "finish_reason": self.finish_reason,
            "usage": self.usage.to_dict(),
            "checkpoint_digest": self.checkpoint_digest,
        }


@dataclass(frozen=True)
class InferenceResult:
    """Deterministic next-token graph output before sampling."""

    prompt_sequence: TokenSequence
    logits: tuple[float, ...]
    cache_tokens: int
    model_digest: str
    architecture_digest: str

    @property
    def argmax_token_id(self) -> int:
        if not self.logits:
            raise RuntimeContractError("inference result has no logits")
        return max(range(len(self.logits)), key=self.logits.__getitem__)

    @property
    def digest(self) -> str:
        return digest_json({
            "prompt_sequence_digest": self.prompt_sequence.digest,
            "logits": list(self.logits),
            "cache_tokens": self.cache_tokens,
            "model_digest": self.model_digest,
            "architecture_digest": self.architecture_digest,
        })


@dataclass(frozen=True)
class BatchGenerationResult:
    request_id: str
    result: GenerationResult


@dataclass(frozen=True)
class _FusedLogitsRequest:
    window: tuple[int, ...]


@dataclass(frozen=True)
class _PagedLogitsReply:
    values: Sequence[float]
    tokens: int
    bytes: int
    resets: int


class GenerationStream:
    """Streaming iterator whose terminal GenerationResult is retained."""

    def __init__(self, iterator: Iterator[RuntimeEvent]) -> None:
        self._iterator = iterator
        self.result: GenerationResult | None = None
        self._closed = False

    def __iter__(self) -> "GenerationStream":
        return self

    def __next__(self) -> RuntimeEvent:
        if self._closed:
            raise StopIteration
        try:
            return next(self._iterator)
        except StopIteration as exc:
            self._closed = True
            if exc.value is not None and not isinstance(exc.value, GenerationResult):
                raise RuntimeContractError("stream returned invalid terminal result")
            self.result = exc.value
            raise

    def close(self) -> None:
        """Cancel a partially consumed stream and release its generator state."""
        close = getattr(self._iterator, "close", None)
        if close is not None:
            close()
        self._closed = True

    def __enter__(self) -> "GenerationStream":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


class NativeLLMRuntime:
    """Bounded deterministic serving runtime for TinyTransformer.

    Embeddings, learned positional vectors, RoPE, multi-head attention, FFNs,
    output projection, and KV stepping remain owned by skeleton.cortex.
    This class owns admission, execution identity, decoding, replay, persistence,
    and serving-facing resource limits.
    """

    def __init__(
        self,
        model: TinyTransformer,
        *,
        limits: RuntimeLimits | None = None,
        device_policy: DevicePolicy | None = None,
    ) -> None:
        if not isinstance(model, TinyTransformer):
            raise RuntimeContractError("TinyTransformer required")
        self.model = model
        self.limits = limits or RuntimeLimits.for_model(model)
        # Idle session prefix caches are disposable, per-runtime, globally
        # bounded retention. Weak keys do not prolong session lifetimes.
        self._idle_prefix_lock = threading.Lock()
        self._idle_prefix_bytes = WeakKeyDictionary()
        if self.limits.max_context > model.ctx:
            raise RuntimeContractError("runtime context exceeds model context")
        self.device_policy = device_policy or DevicePolicy()

        # Admission captures a detached graph for validation once; retaining
        # it alongside live weights would permanently duplicate every row.
        snapshot, self._model_digest = capture_validated_model(model)
        self._model_bytes = logical_bytes(snapshot)
        del snapshot
        if self._model_bytes > self.limits.max_model_bytes:
            raise RuntimeContractError("model exceeds runtime memory budget")

        try:
            self.tokenizer = NativeTokenizer(model)
        except TokenizerContractError as exc:
            raise RuntimeContractError("native tokenizer admission failed") from exc
        self.architecture = self._architecture()
        if self.estimate_kv_bytes(self.limits.max_context) > self.limits.max_kv_bytes:
            raise RuntimeContractError("configured context exceeds KV memory budget")
        self.device = self._bind_device(self.device_policy)
        self.model._strict_device_request = (
            not self.device_policy.allow_fallback
            and self.device_policy.requested in {"torch", "torch-cpu", "cuda", "gpu", "mps"}
        )

    def _architecture(self) -> RuntimeArchitecture:
        return RuntimeArchitecture(
            vocab_size=len(self.model.itos),
            dim=self.model.dim,
            context=self.model.ctx,
            heads=self.model.n_heads,
            layers=self.model.n_layers,
            feed_forward=self.model.d_ff,
            norm=self.model.norm,
            ffn_kind=self.model.ffn_kind,
            positional=(
                "rope-only"
                if getattr(self.model, "position_mode", "learned_rope") == "rope"
                else "learned-position-embedding+rope-attention"
            ),
        )

    @property
    def model_digest(self) -> str:
        return self._model_digest

    @property
    def model_bytes(self) -> int:
        return self._model_bytes

    @property
    def model_identity(self) -> ModelIdentity:
        """Canonical immutable identity for the admitted native transformer."""
        return ModelIdentity(
            model_id="skeleton-native-transformer",
            revision=self.model_digest,
            architecture="skeleton.cortex.TinyTransformer",
            config_digest=self.architecture.digest,
            tokenizer_digest=self.tokenizer.digest,
            weights_digest=self.model_digest,
        )

    def spill_cpu_kv(self, cache: KVCache, store: object) -> str:
        """Persist an admitted CPU reference KV cache; no GPU tensor migration."""
        from .cpu_kv_spill import CpuKVSpillStore
        if not isinstance(store, CpuKVSpillStore):
            raise RuntimeContractError("CpuKVSpillStore required")
        return store.stage(self, cache)

    def restore_cpu_kv(self, digest: str, store: object) -> KVCache:
        """Restore exact native CPU KV state under the current model identity."""
        from .cpu_kv_spill import CpuKVSpillStore
        if not isinstance(store, CpuKVSpillStore):
            raise RuntimeContractError("CpuKVSpillStore required")
        return store.restore(self, digest)

    def _reserve_idle_cpu_prefix(self, session, size: int) -> bool:
        """Bound aggregate idle Python KV retention, not concurrent workers."""
        if type(size) is not int or size <= 0:
            return False
        with self._idle_prefix_lock:
            previous = self._idle_prefix_bytes.get(session, 0)
            total = sum(self._idle_prefix_bytes.values()) - previous
            cap = min(256 * 1024**2, self.limits.max_kv_bytes)
            if (total + size > cap
                    or (not previous and len(self._idle_prefix_bytes) >= 32)):
                return False
            self._idle_prefix_bytes[session] = size
            return True

    def _release_idle_cpu_prefix(self, session) -> None:
        with self._idle_prefix_lock:
            self._idle_prefix_bytes.pop(session, None)

    def estimate_kv_bytes(self, tokens: int) -> int:
        count = max(0, int(tokens))
        return count * self.model.n_layers * self.model.dim * 2 * 8 + count * 8

    def _bind_device(self, policy: DevicePolicy) -> DeviceReceipt:
        requested = policy.requested
        wants_kv_policy = (
            policy.kv_dtype != "fp32" or policy.kv_limit_bytes is not None
            or policy.prefill_query_chunk is not None
        )
        if policy.kv_limit_bytes is not None and (
            policy.kv_limit_bytes > self.limits.max_kv_bytes
        ):
            raise RuntimeContractError(
                "device KV allocation ceiling exceeds native runtime policy"
            )
        if requested == "cpu" and wants_kv_policy:
            raise RuntimeContractError(
                "KV compression/budget or chunked prefill requires a Torch execution device"
            )
        current = str(getattr(self.model, "device", "cpu") or "cpu")
        was_resident = bool(getattr(self.model, "resident", False))
        if requested == "cpu" and current == "cpu" and not was_resident:
            actual = "cpu"
            resident = False
        else:
            try:
                if wants_kv_policy:
                    self.model.to(
                        requested,
                        kv_dtype=policy.kv_dtype,
                        max_kv_bytes=policy.kv_limit_bytes,
                        prefill_query_chunk=policy.prefill_query_chunk,
                    )
                else:
                    # Preserve compatibility with legacy device binders and
                    # one-argument test doubles when optional compact-KV
                    # functionality has not been requested.
                    self.model.to(requested)
            except Exception as exc:
                raise RuntimeContractError("device binding failed") from exc
            actual = str(getattr(self.model, "device", "cpu") or "cpu")
            resident = bool(getattr(self.model, "resident", False))
        if requested in {"cuda", "gpu"}:
            degraded = actual != "cuda" or not resident
        elif requested == "mps":
            degraded = actual != "mps" or not resident
        elif requested in {"torch", "torch-cpu"}:
            degraded = not resident
        else:
            degraded = False
        # Explicitly configured compact caches must be implemented by the
        # selected execution backend, regardless of general fallback policy.
        if wants_kv_policy and not resident:
            raise RuntimeContractError(
                "requested KV precision/budget not admitted on this device"
            )
        if degraded and not policy.allow_fallback:
            raise RuntimeContractError(
                "requested device unavailable and fallback is disabled"
            )
        return DeviceReceipt(
            requested, actual, resident, degraded,
            policy.kv_dtype if resident else "fp32",
            policy.kv_limit_bytes if resident else None,
            policy.prefill_query_chunk if resident else None,
        )

    def bind_device(self, policy: DevicePolicy) -> DeviceReceipt:
        if not isinstance(policy, DevicePolicy):
            raise RuntimeContractError("DevicePolicy required")
        receipt = self._bind_device(policy)
        self.device_policy = policy
        self.device = receipt
        self.model._strict_device_request = (
            not policy.allow_fallback
            and policy.requested in {"torch", "torch-cpu", "cuda", "gpu", "mps"}
        )
        return receipt

    def _current_model_digest(self) -> str:
        _, digest = capture_validated_model(self.model)
        return digest

    def assert_model_unchanged(self) -> None:
        if not hmac.compare_digest(self._current_model_digest(), self.model_digest):
            raise RuntimeContractError(
                "model mutated after admission; call refresh_model_identity"
            )

    def _assert_execution_device(self) -> None:
        """Do not issue a single-device receipt for a mixed-device execution."""
        actual = str(getattr(self.model, "device", "cpu") or "cpu")
        resident = bool(getattr(self.model, "resident", False))
        if actual == self.device.actual and resident == self.device.resident:
            return
        if (actual == "cpu" and not resident and self.device_policy.allow_fallback
                and self.device_policy.kv_dtype == "fp32"
                and self.device_policy.kv_limit_bytes is None
                and self.device_policy.prefill_query_chunk is None):
            # The transformer has synchronized canonical weights before
            # dropping its accelerator. A subsequent whole request can use
            # this explicit degraded receipt; the in-flight request cannot.
            self.device = DeviceReceipt(self.device_policy.requested, "cpu", False, True)
        raise RuntimeContractError(
            "execution device changed; retry the whole request after explicit device admission"
        )

    def refresh_model_identity(self) -> str:
        snapshot, digest = capture_validated_model(self.model)
        size = logical_bytes(snapshot)
        if size > self.limits.max_model_bytes:
            raise RuntimeContractError("mutated model exceeds runtime memory budget")
        try:
            tokenizer = NativeTokenizer(self.model)
        except TokenizerContractError as exc:
            raise RuntimeContractError("native tokenizer re-admission failed") from exc
        architecture = self._architecture()
        if self.limits.max_context > self.model.ctx:
            raise RuntimeContractError("mutated model context below runtime limit")
        if self.estimate_kv_bytes(self.limits.max_context) > self.limits.max_kv_bytes:
            raise RuntimeContractError("mutated model exceeds KV memory budget")
        # Re-pin accelerator tensors and drop old KV state before a changed
        # model identity can be admitted; never serve mismatched weights.
        accelerator = getattr(self.model, "_accel", None)
        if accelerator is not None:
            try:
                accelerator.pin()
                _, refreshed_digest = capture_validated_model(self.model)
                if not hmac.compare_digest(refreshed_digest, digest):
                    raise RuntimeContractError(
                        "model changed while rebinding accelerator"
                    )
            except Exception as exc:
                # A failed refresh cannot publish a hybrid CPU/GPU model.
                self.model._accel = None
                self.model.resident = False
                self.model.device = "cpu"
                raise RuntimeContractError(
                    "accelerator rebind failed during model identity refresh"
                ) from exc
        # Never retain a detached graph after its identity was admitted.
        self._model_digest = digest
        self._model_bytes = size
        self.tokenizer = tokenizer
        self.architecture = architecture
        return self.model_digest

    def health_snapshot(self) -> Mapping[str, Any]:
        return {
            "model_digest": self.model_digest,
            "model_identity_digest": self.model_identity.identity_digest,
            "tokenizer_digest": self.tokenizer.digest,
            "architecture": self.architecture.to_dict(),
            "architecture_digest": self.architecture.digest,
            "model_bytes": self.model_bytes,
            "kv_bytes_per_token": self.estimate_kv_bytes(1),
            "device": {
                "requested": self.device.requested,
                "actual": self.device.actual,
                "resident": self.device.resident,
                "degraded": self.device.degraded,
                "digest": self.device.digest,
            },
            "limits": self.limits.to_dict(),
        }

    def encode(self, text: str) -> TokenSequence:
        try:
            return self.tokenizer.encode_sequence(text)
        except TokenizerContractError as exc:
            raise RuntimeContractError("native tokenizer encode failed") from exc

    def decode_ids(self, token_ids: Sequence[int]) -> str:
        try:
            return self.tokenizer.decode_ids(token_ids)
        except TokenizerContractError as exc:
            raise RuntimeContractError("native tokenizer decode failed") from exc

    def infer_sequence(
        self,
        sequence: TokenSequence,
        *,
        use_cache: bool = True,
        interrupt: Callable[[], None] | None = None,
        cache: KVCache | None = None,
    ) -> InferenceResult:
        """Run embeddings → position/RoPE → transformer blocks → LM head.

        This exposes the executable inference graph independently of decoding so
        loaders, portability checks, and samplers can validate identical model
        state against a canonical pre-tokenized input.
        """
        if not isinstance(sequence, TokenSequence):
            raise RuntimeContractError("TokenSequence required")
        if interrupt is not None:
            interrupt()
        if not isinstance(use_cache, bool):
            raise RuntimeContractError("use_cache must be boolean")
        if cache is not None:
            if not use_cache or not isinstance(cache, KVCache):
                raise RuntimeContractError("explicit KV cache requires cache-enabled inference")
            if cache.n_layers != self.model.n_layers or cache.ctx != self.limits.max_context:
                raise RuntimeContractError("explicit KV cache architecture mismatch")
            if (self.device.actual != "cpu" or self.model.resident
                    or getattr(self.model, "_accel", None) is not None):
                raise RuntimeContractError("external KV cache requires exact CPU execution")
            if cache.owner is not None and (
                cache.owner is not self.model or cache.revision != (
                    self.model.steps, self.model.fitted, self.model.tied,
                    self.model.device, self.model.resident,
                )
            ):
                raise RuntimeContractError("explicit KV cache has stale model ownership")
        self.assert_model_unchanged()
        self._assert_execution_device()
        try:
            self.tokenizer.assert_unchanged()
        except TokenizerContractError as exc:
            raise RuntimeContractError("tokenizer drift during inference") from exc
        if not hmac.compare_digest(sequence.tokenizer_digest, self.tokenizer.digest):
            raise RuntimeContractError("token sequence tokenizer identity mismatch")
        if not sequence.token_ids:
            raise RuntimeContractError("token sequence must not be empty")
        if len(sequence.token_ids) > self.limits.max_context:
            raise RuntimeContractError("prompt exceeds context budget")
        if any(token_id >= self.tokenizer.vocab_size for token_id in sequence.token_ids):
            raise RuntimeContractError("token sequence contains id outside vocabulary")
        self.assert_model_unchanged()
        try:
            self.tokenizer.assert_unchanged()
        except TokenizerContractError as exc:
            raise RuntimeContractError("tokenizer drift during inference") from exc
        if use_cache and self.estimate_kv_bytes(len(sequence.token_ids)) > self.limits.max_kv_bytes:
            raise RuntimeContractError("inference exceeds KV memory budget")
        window = sequence.token_ids[-self.limits.max_context:]
        binding = (self.model_digest, self.tokenizer.digest, self.architecture.digest,
                   self.device.digest, self.limits, self.device_policy)
        active_cache = (cache if cache is not None else
                        KVCache(self.model.n_layers, self.limits.max_context) if use_cache else None)
        raw_logits = (self.model._logits_window(window, active_cache) if interrupt is None
                      else self.model._logits_window(window, active_cache, interrupt=interrupt))
        if interrupt is not None:
            interrupt()
        logits = tuple(float(value) for value in raw_logits)
        self._assert_execution_device()
        if len(logits) != self.tokenizer.vocab_size:
            raise RuntimeContractError("inference graph emitted invalid logits shape")
        if any(value != value or value in (float("inf"), float("-inf")) for value in logits):
            raise RuntimeContractError("inference graph emitted non-finite logits")
        self.assert_model_unchanged()
        try:
            self.tokenizer.assert_unchanged()
        except TokenizerContractError as exc:
            raise RuntimeContractError("tokenizer drift during inference") from exc
        if binding != (self.model_digest, self.tokenizer.digest, self.architecture.digest,
                       self.device.digest, self.limits, self.device_policy):
            raise RuntimeContractError("runtime binding changed during inference")
        return InferenceResult(
            prompt_sequence=sequence,
            logits=logits,
            cache_tokens=len(active_cache.tokens) if active_cache is not None else 0,
            model_digest=self.model_digest,
            architecture_digest=self.architecture.digest,
        )

    def infer_text(self, text: str, *, use_cache: bool = True,
                   interrupt: Callable[[], None] | None = None) -> InferenceResult:
        """Tokenize text and execute one next-token inference graph pass."""
        if interrupt is not None:
            interrupt()
        return self.infer_sequence(self.encode(text), use_cache=use_cache, interrupt=interrupt)

    def _finalize_feed(self, feed: StreamingTextFeed) -> TokenSequence:
        """Admit a bounded text feed without leaking tokenizer-specific errors."""
        if not isinstance(feed, StreamingTextFeed):
            raise RuntimeContractError("StreamingTextFeed required")
        try:
            return feed.finalize(self.tokenizer)
        except TokenizerContractError as exc:
            raise RuntimeContractError("feed tokenization failed admission") from exc

    def infer_feed(
        self,
        feed: StreamingTextFeed,
        *,
        use_cache: bool = True,
        interrupt: Callable[[], None] | None = None,
    ) -> InferenceResult:
        """Execute next-token inference directly from a bounded text feed."""
        if interrupt is not None:
            interrupt()
        return self.infer_sequence(self._finalize_feed(feed), use_cache=use_cache,
                                   interrupt=interrupt)

    def _config_digest(self, config: GenerationConfig) -> str:
        return digest_json(config.to_dict())

    @staticmethod
    def _sampling_logits(
        logits: Sequence[float], history: Sequence[int], generated_count: int,
        config: GenerationConfig,
        *, repetition_counts: Mapping[int, int] | None = None,
    ) -> list[float]:
        """Apply request-bound policies without mutating model graph logits.

        Repetition uses both prompt and continuation, limited to the configured
        recent window. Multiplicative penalties move negative and positive
        logits in the same probability-reducing direction.
        """
        adjusted = list(logits)
        if (config.repetition_penalty != 1.0 or config.presence_penalty
                or config.frequency_penalty):
            if repetition_counts is None:
                counts: dict[int, int] = {}
                for token_id in history[-config.penalty_window:]:
                    counts[token_id] = counts.get(token_id, 0) + 1
            else:
                counts = repetition_counts
            for token_id, count in counts.items():
                value = adjusted[token_id]
                value = (value / config.repetition_penalty if value >= 0.0
                         else value * config.repetition_penalty)
                value -= config.presence_penalty + config.frequency_penalty * count
                if not math.isfinite(value):
                    raise RuntimeContractError("sampling penalty overflow")
                adjusted[token_id] = value
        blocked = set(config.suppress_token_ids)
        if generated_count < config.min_new_tokens:
            blocked.update(config.stop_token_ids)
        for token_id in blocked:
            adjusted[token_id] = float("-inf")
        if not any(math.isfinite(value) for value in adjusted):
            raise RuntimeContractError("sampling policy leaves no eligible token")
        return adjusted

    def _request_digest(
        self,
        prompt_sequence: TokenSequence,
        config: GenerationConfig,
    ) -> str:
        return digest_json(
            {
                "model_digest": self.model_digest,
                "tokenizer_digest": self.tokenizer.digest,
                "prompt_sequence_digest": prompt_sequence.digest,
                "config_digest": self._config_digest(config),
            }
        )

    def _admit_sequence(
        self,
        sequence: TokenSequence,
        config: GenerationConfig,
    ) -> int:
        """Validate a pre-tokenized request using the same admission as text."""
        if not isinstance(sequence, TokenSequence):
            raise RuntimeContractError("TokenSequence required")
        if not isinstance(config, GenerationConfig):
            raise RuntimeContractError("GenerationConfig required")
        config.validate(limits=self.limits, vocab_size=self.tokenizer.vocab_size)
        self.assert_model_unchanged()
        self._assert_execution_device()
        try:
            self.tokenizer.assert_unchanged()
        except TokenizerContractError as exc:
            raise RuntimeContractError("tokenizer mutated after admission") from exc
        if not hmac.compare_digest(sequence.tokenizer_digest, self.tokenizer.digest):
            raise RuntimeContractError("token sequence tokenizer identity mismatch")
        prompt_tokens = len(sequence.token_ids)
        if not prompt_tokens:
            raise RuntimeContractError("token sequence must not be empty")
        if any(token_id >= self.tokenizer.vocab_size for token_id in sequence.token_ids):
            raise RuntimeContractError("token sequence contains id outside vocabulary")
        if prompt_tokens > self.limits.max_context:
            raise RuntimeContractError("prompt exceeds context budget")
        if prompt_tokens + config.max_new_tokens > self.limits.max_total_tokens:
            raise RuntimeContractError("request exceeds total-token budget")
        projected = min(self.limits.max_context, prompt_tokens + config.max_new_tokens)
        projected_kv = self.estimate_kv_bytes(projected) if config.use_cache else 0
        if projected_kv > self.limits.max_kv_bytes:
            raise RuntimeContractError("request exceeds KV memory budget")
        return projected_kv

    def _admit(
        self,
        prompt: str,
        config: GenerationConfig,
    ) -> tuple[TokenSequence, int]:
        if not isinstance(config, GenerationConfig):
            raise RuntimeContractError("GenerationConfig required")
        sequence = self.encode(prompt)
        return sequence, self._admit_sequence(sequence, config)

    def stream(
        self,
        prompt: str,
        config: GenerationConfig | None = None,
        *, interrupt: Callable[[], None] | None = None,
    ) -> GenerationStream:
        cfg = config or GenerationConfig(
            max_new_tokens=min(32, self.limits.max_new_tokens)
        )
        return GenerationStream(self._stream_impl(prompt, cfg, interrupt=interrupt))

    def _stream_impl(
        self,
        prompt: str,
        config: GenerationConfig,
        *, interrupt: Callable[[], None] | None = None,
    ) -> Iterator[RuntimeEvent]:
        if interrupt is not None:
            interrupt()
        if not isinstance(config, GenerationConfig):
            raise RuntimeContractError("GenerationConfig required")
        try:
            sequence = self.encode(prompt)
        except TokenizerContractError as exc:
            raise RuntimeContractError("prompt tokenization failed admission") from exc
        except RuntimeContractError as exc:
            if isinstance(exc.__cause__, TokenizerContractError):
                raise RuntimeContractError("prompt tokenization failed admission") from exc.__cause__
            raise
        return (yield from self._stream_sequence_impl(sequence, config, interrupt=interrupt))

    def stream_sequence(
        self,
        sequence: TokenSequence,
        config: GenerationConfig | None = None,
        *, interrupt: Callable[[], None] | None = None,
        _private_cpu_cache: KVCache | None = None,
    ) -> GenerationStream:
        """Stream pre-tokenized inference through the canonical decoder.

        The private cache argument is for the trusted local prefill owner;
        the decoder still verifies compatibility and exact admitted tokens.
        """
        cfg = config or GenerationConfig(max_new_tokens=min(32, self.limits.max_new_tokens))
        if _private_cpu_cache is None:
            return GenerationStream(self._stream_sequence_impl(sequence, cfg, interrupt=interrupt))
        return GenerationStream(self._stream_sequence_impl(sequence, cfg, interrupt=interrupt,
                               _private_cpu_cache=_private_cpu_cache))

    def _stream_sequence_impl(
        self,
        prompt_sequence: TokenSequence,
        config: GenerationConfig,
        *, interrupt: Callable[[], None] | None = None,
        _private_cpu_cache: KVCache | None = None,
        fused: bool = False,
        paged: bool = False,
    ) -> Iterator[RuntimeEvent]:
        if interrupt is not None:
            interrupt()
        if paged and not (fused and config.use_cache):
            raise RuntimeContractError("paged generation requires cached fused requests")
        if fused and config.use_cache and not paged:
            raise RuntimeContractError("fused stateless batch requires explicit use_cache=False")
        self._admit_sequence(prompt_sequence, config)
        admitted_binding = (
            self.model_digest, self.tokenizer.digest, self.architecture.digest,
            self.device.digest, self.device_policy, self.limits,
        )

        def assert_binding() -> None:
            # Distinguish tokenizer identity drift before aggregate binding
            # checks. Keep the full (more costly) tokenizer integrity proof at
            # the existing post-inference checkpoint, not twice per token.
            if self.tokenizer.digest != admitted_binding[1]:
                raise RuntimeContractError("tokenizer mutated during generation")
            if admitted_binding != (
                self.model_digest, self.tokenizer.digest, self.architecture.digest,
                self.device.digest, self.device_policy, self.limits,
            ):
                raise RuntimeContractError("runtime binding changed during generation")

        config_digest = self._config_digest(config)
        request_digest = self._request_digest(prompt_sequence, config)
        events: list[RuntimeEvent] = []
        sequence = 0

        event = RuntimeEvent(sequence, "admitted", detail_digest=request_digest)
        events.append(event)
        yield event
        sequence += 1

        event = RuntimeEvent(
            sequence,
            "prompt",
            detail_digest=prompt_sequence.digest,
        )
        events.append(event)
        yield event
        sequence += 1

        rng = random.Random(int(config.seed) & 0xFFFFFFFF)
        cache = (
            KVCache(self.model.n_layers, self.limits.max_context)
            if config.use_cache and _private_cpu_cache is None
            else _private_cpu_cache
        )
        if _private_cpu_cache is not None:
            if (not config.use_cache or self.device.actual != "cpu"
                    or self.device.resident or self.model._accel is not None
                    or self.model.use_mod or type(cache) is not KVCache
                    or cache.n_layers != self.model.n_layers
                    or cache.ctx != self.limits.max_context
                    or cache.next_position != len(cache.tokens)
                    or tuple(cache.tokens) != prompt_sequence.token_ids[:len(cache.tokens)]
                    or (cache.tokens and cache.owner is not self.model)
                    or self.estimate_kv_bytes(len(cache.tokens)) > self.limits.max_kv_bytes):
                raise RuntimeContractError("private CPU prefix cache is not compatible with admitted prompt")
            # Usage counts resets for this generation, not the session lifetime.
            cache.reset_count = 0
        output = list(prompt_sequence.token_ids)
        generated: list[int] = []
        penalty = (RollingPenaltyWindow(output, config.penalty_window)
                   if config.repetition_penalty != 1.0 or config.presence_penalty or config.frequency_penalty
                   else None)
        # The canonical word tokenizer is append-only; BPE can revise the
        # entire rendering if an unknown piece appears, so stays on its
        # authoritative complete-decode path.
        stop_matcher = (WordStopMatcher(config.stop_strings)
                        if config.stop_strings and type(self.tokenizer) is NativeTokenizer
                        and getattr(self.model, "bpe", None) is None else None)
        stop_ids = set(config.stop_token_ids)
        finish_reason = "length"
        cache_resets = 0
        kv_peak = 0
        stopped_text: str | None = None

        for _ in range(config.max_new_tokens):
            assert_binding()
            if interrupt is not None:
                interrupt()
            window = output[-self.limits.max_context :]
            if fused:
                raw_logits = yield _FusedLogitsRequest(tuple(window or [self.model.unk]))
                if isinstance(raw_logits, _PagedLogitsReply) and paged and cache is not None:
                    cache.tokens = list(window or [self.model.unk])
                    if len(cache.tokens) != raw_logits.tokens:
                        raise RuntimeContractError("paged occupancy mismatch")
                    cache.reserved_bytes = raw_logits.bytes
                    cache.reset_count = raw_logits.resets
                    raw_logits = raw_logits.values
                elif raw_logits is None or paged:
                    raise RuntimeContractError("fused decode lacks admitted logits")
            elif interrupt is None:
                raw_logits = self.model._logits_window(window, cache)
            else:
                raw_logits = self.model._logits_window(window, cache, interrupt=interrupt)
                interrupt()
            logits = tuple(float(value) for value in raw_logits)
            self._assert_execution_device()
            assert_binding()
            if len(logits) != self.tokenizer.vocab_size:
                raise RuntimeContractError("generation graph emitted invalid logits shape")
            if any(not math.isfinite(value) for value in logits):
                raise RuntimeContractError("generation graph emitted non-finite logits")
            if cache is not None:
                cache_resets = cache.reset_count

            next_id = int(
                sample_logits(
                    self._sampling_logits(logits, output, len(generated), config,
                                          repetition_counts=penalty.counts if penalty is not None else None),
                    rng,
                    temperature=config.temperature,
                    top_k=config.top_k,
                    top_p=config.top_p,
                    min_p=config.min_p,
                )
            )
            if not 0 <= next_id < self.tokenizer.vocab_size:
                raise RuntimeContractError("sampler emitted token outside vocabulary")
            output.append(next_id)
            generated.append(next_id)
            if penalty is not None:
                penalty.append(next_id)
            token_text = self.tokenizer.token_text(next_id)
            stop_token_hit = next_id in stop_ids
            stop_string_hit = False
            if stop_matcher is not None:
                stop_matcher.append(token_text)
            if config.stop_strings and len(generated) >= config.min_new_tokens:
                # Preserve the decoder's token-budget rejection even when
                # no stop marker has yet matched the incremental scan.
                if len(generated) > self.tokenizer.limits.max_tokens:
                    raise TokenizerContractError("decode token budget exceeded")
                if stop_matcher is None or stop_matcher.first is not None:
                    decoded = self.tokenizer.decode_ids(generated)
                    if stop_matcher is not None:
                        try:
                            position = stop_matcher.verify(decoded)
                        except ValueError as exc:
                            raise RuntimeContractError("word stop matching drift") from exc
                        stopped_text = decoded[:position]
                        stop_string_hit = True
                    else:
                        matches = [decoded.find(marker) for marker in config.stop_strings]
                        matches = [position for position in matches if position >= 0]
                        if matches:
                            stopped_text = decoded[:min(matches)]
                            stop_string_hit = True
            cache_tokens = len(cache.tokens) if cache is not None else 0
            if cache is not None:
                kv_peak = max(kv_peak, self.estimate_kv_bytes(cache_tokens), cache.reserved_bytes)
                if kv_peak > self.limits.max_kv_bytes:
                    raise RuntimeContractError("generation exceeded KV memory budget")
            self.assert_model_unchanged()
            try:
                self.tokenizer.assert_unchanged()
            except TokenizerContractError as exc:
                raise RuntimeContractError("tokenizer mutated during generation") from exc

            event = RuntimeEvent(
                sequence,
                "token",
                token_id=next_id,
                # String-stop mode buffers visible text until completion.
                # BPE boundaries can revise a suffix; publishing raw pieces
                # would expose partial stop markers that cannot be recalled.
                text_delta=("" if config.stop_strings or (
                    stop_token_hit and not config.include_stop_tokens
                ) else token_text),
                cache_tokens=cache_tokens,
                detail_digest=digest_json(
                    {
                        "request_digest": request_digest,
                        "ordinal": len(generated),
                        "token_id": next_id,
                    }
                ),
            )
            events.append(event)
            yield event
            sequence += 1

            if stop_token_hit or stop_string_hit:
                finish_reason = "stop_string" if stop_string_hit else "stop_token"
                event = RuntimeEvent(
                    sequence,
                    "stopped",
                    token_id=next_id,
                    text_delta="",
                    cache_tokens=cache_tokens,
                    detail_digest=event.detail_digest,
                )
                events.append(event)
                yield event
                sequence += 1
                break

        if config.max_new_tokens == 0:
            finish_reason = "completed"

        assert_binding()

        generated_ids = tuple(generated)
        generated_tokens = tuple(
            self.tokenizer.token_text(token_id) for token_id in generated_ids
        )
        visible_ids = generated_ids
        if (finish_reason == "stop_token" and not config.include_stop_tokens
                and visible_ids):
            visible_ids = visible_ids[:-1]
        text = (stopped_text if stopped_text is not None
                else self.tokenizer.decode_ids(visible_ids))
        output_digest = digest_json(
            {
                "generated_ids": list(generated_ids),
                "text": text,
                "finish_reason": finish_reason,
            }
        )
        usage = RuntimeUsage(
            prompt_tokens=len(prompt_sequence.token_ids),
            generated_tokens=len(generated_ids),
            total_tokens=len(prompt_sequence.token_ids) + len(generated_ids),
            model_bytes=self.model_bytes,
            kv_peak_bytes=kv_peak,
            cache_resets=cache_resets,
        )
        receipt = ReplayReceipt(
            model_digest=self.model_digest,
            tokenizer_digest=self.tokenizer.digest,
            architecture_digest=self.architecture.digest,
            request_digest=request_digest,
            output_digest=output_digest,
            config_digest=config_digest,
            device_digest=self.device.digest,
            seed=config.seed,
        )
        # Construct and validate the durable checkpoint before announcing
        # completion. An invalidated model or tokenizer must never emit a
        # terminal success event whose final replay receipt is unavailable.
        if interrupt is not None:
            interrupt()
        checkpoint = self.checkpoint()
        assert_binding()
        if interrupt is not None:
            interrupt()
        event = RuntimeEvent(
            sequence,
            "completed",
            text_delta=text if config.stop_strings else "",
            cache_tokens=len(cache.tokens) if cache is not None else 0,
            detail_digest=receipt.digest,
        )
        events.append(event)
        yield event

        return GenerationResult(
            prompt_sequence=prompt_sequence,
            generated_ids=generated_ids,
            generated_tokens=generated_tokens,
            text=text,
            finish_reason=finish_reason,
            usage=usage,
            replay_receipt=receipt,
            events=tuple(events),
            checkpoint_digest=checkpoint["digest"],
        )

    def stream_paged_sequence(self, sequence: TokenSequence, config: GenerationConfig, *,
                              max_workspace_bytes: int, paged_kv_bytes: int, interrupt=None):
        """Preserve the canonical pre-tokenized stream and audit events."""
        from .paged_attention import PagedBatchSession
        self._admit_sequence(sequence, config)
        accel=getattr(self.model,"_accel",None)
        if accel is None or accel.device_name!="cuda" or not config.use_cache:
            raise RuntimeContractError("protected paged stream requires resident CUDA and cached config")

        def drive():
            with accel._inference_lock(interrupt):
                session=PagedBatchSession(accel,slots=1,context=self.limits.max_context,
                    max_kv_bytes=paged_kv_bytes,max_workspace_bytes=max_workspace_bytes,require_gpu=True)
                gen=self._stream_sequence_impl(sequence,config,interrupt=interrupt,fused=True,paged=True)
                try:
                    if session.page_bytes*session.pages_per_slot>self.limits.max_kv_bytes:
                        raise RuntimeContractError("paged stream allocation exceeds runtime KV ceiling")
                    reply=None
                    while True:
                        try:
                            event=gen.send(reply)
                        except StopIteration as terminal:
                            return terminal.value
                        reply=None
                        if isinstance(event,_FusedLogitsRequest):
                            reply=_PagedLogitsReply(*session.logits([0],[event.window],interrupt=interrupt)[0])
                        else:
                            yield event
                finally:
                    gen.close()
                    session.close()
        return GenerationStream(drive())

    def generate_reconstructed_context(self, spool, checkpoint_digest: str, question: str,
                                       config: GenerationConfig, policy, *, semantic_ranker=None, interrupt=None):
        """Explicit offline operator context reconstruction with exact source receipt."""
        from .context_reconstruction import reconstruct
        return reconstruct(self, spool, checkpoint_digest, question, config, policy, semantic_ranker=semantic_ranker, interrupt=interrupt)

    def generate_sequence(
        self,
        sequence: TokenSequence,
        config: GenerationConfig | None = None,
        *, interrupt: Callable[[], None] | None = None,
    ) -> GenerationResult:
        """Generate from token IDs without lossy decoding and retokenization."""
        with self.stream_sequence(sequence, config, interrupt=interrupt) as stream:
            for _event in stream:
                pass
        if stream.result is None:
            raise RuntimeContractError("generation terminated without result")
        return stream.result

    def stream_feed(
        self,
        feed: StreamingTextFeed,
        config: GenerationConfig | None = None,
        *, interrupt: Callable[[], None] | None = None,
    ) -> GenerationStream:
        """Execute a bounded text feed as a stream of real transformer tokens.

        The feed is finalized once; token IDs are forwarded without a lossy
        text round-trip, and generation uses the canonical decoder.
        """
        if interrupt is not None:
            interrupt()
        return self.stream_sequence(self._finalize_feed(feed), config, interrupt=interrupt)

    def generate_feed(
        self,
        feed: StreamingTextFeed,
        config: GenerationConfig | None = None,
        *, interrupt: Callable[[], None] | None = None,
    ) -> GenerationResult:
        """Finalize a StreamingTextFeed and execute it end-to-end."""
        if interrupt is not None:
            interrupt()
        return self.generate_sequence(self._finalize_feed(feed), config, interrupt=interrupt)

    def generate(
        self,
        prompt: str,
        config: GenerationConfig | None = None,
        *, interrupt: Callable[[], None] | None = None,
    ) -> GenerationResult:
        with self.stream(prompt, config, interrupt=interrupt) as stream:
            for _event in stream:
                pass
        if stream.result is None:
            raise RuntimeContractError("generation terminated without result")
        return stream.result

    def _admit_batch(
        self, requests: Sequence[BatchGenerationRequest],
        *, interrupt: Callable[[], None] | None = None,
        reuse_shared_prefix: bool = False,
        prefix_budget_bytes: int = 8 * 1024**2,
    ) -> tuple[BatchGenerationResult, ...]:
        """Execute a bounded batch with optional same-owner CPU prefix reuse.

        Explicit opt-in authorizes sharing prompt computation INSIDE this
        batch only. The optimized path may reorder physical execution, but
        results retain caller order. It never reuses generated continuation
        tokens, crosses calls, or changes a sampling configuration.
        """
        if type(reuse_shared_prefix) is not bool:
            raise RuntimeContractError("explicit shared prefix batch policy required")
        if type(prefix_budget_bytes) is not int or not 1 <= prefix_budget_bytes <= 64 * 1024**2:
            raise RuntimeContractError("invalid shared prefix batch budget")
        if not requests:
            return ()
        if len(requests) > self.limits.max_batch_size:
            raise RuntimeContractError("batch size budget exceeded")
        if any(not isinstance(request, BatchGenerationRequest) for request in requests):
            raise RuntimeContractError("BatchGenerationRequest required")
        ids = [request.request_id for request in requests]
        if len(set(ids)) != len(ids):
            raise RuntimeContractError("duplicate batch request id")

        aggregate = 0
        admitted: list[tuple[BatchGenerationRequest, TokenSequence]] = []
        for request in requests:
            if interrupt is not None:
                interrupt()
            sequence, _ = self._admit(request.prompt, request.config)
            aggregate += len(sequence.token_ids) + request.config.max_new_tokens
            if aggregate > self.limits.max_batch_tokens:
                raise RuntimeContractError("batch token budget exceeded")
            admitted.append((request, sequence))
        return tuple(admitted)

    def generate_batch(
        self, requests: Sequence[BatchGenerationRequest],
        *, interrupt: Callable[[], None] | None = None,
    ) -> tuple[BatchGenerationResult, ...]:
        admitted = self._admit_batch(requests, interrupt=interrupt)
        # Each admitted sequence is immutable and bound to the tokenizer
        # digest. Re-encoding a prompt here would create a second admission
        # boundary and allow a different token trajectory after preflight.
        budget = min(prefix_budget_bytes, self.limits.max_kv_bytes // 4)
        if (reuse_shared_prefix and budget > 0 and len(admitted) > 1
                and type(self) is NativeLLMRuntime and self.device.actual == "cpu"
                and not self.device.resident and self.model._accel is None
                and not self.model.use_mod
                and all(request.config.use_cache for request, _ in admitted)):
            return self._generate_shared_prefix_batch(admitted, budget, interrupt)
        return tuple(
            BatchGenerationResult(
                request.request_id,
                self.generate_sequence(sequence, request.config, interrupt=interrupt),
            )
            for request, sequence in admitted
        )

    def _generate_shared_prefix_batch(self, admitted, budget, interrupt):
        # Lexicographic order clusters exact token prefixes with one bank,
        # not an unbounded Python trie or a full bank per leaf. Stable index
        # ties preserve deterministic ordering for duplicate prompts.
        order = sorted(range(len(admitted)), key=lambda i: (admitted[i][1].token_ids, i))
        results = {}
        cache = None
        previous_prompt = ()
        previous_binding = None
        for i in order:
            if interrupt is not None:
                interrupt()
            request, sequence = admitted[i]
            ids = sequence.token_ids
            binding = (self.model_digest, self.tokenizer.digest, self.architecture.digest,
                       self.device.digest, self.device_policy, self.limits,
                       self.model.steps, self.model.fitted, self.model.tied)
            common = 0
            if (cache is not None and binding == previous_binding
                    and cache.owner is self.model
                    and cache.revision == (self.model.steps, self.model.fitted,
                                           self.model.tied, self.model.device, self.model.resident)
                    and cache.next_position == len(cache.tokens)
                    and tuple(cache.tokens) == previous_prompt[:len(cache.tokens)]):
                for old, new in zip(cache.tokens, ids):
                    if old != new:
                        break
                    common += 1
                # A trimmed bank has no final logits. Leave one token to
                # project in the canonical decoder, even for an exact match.
                common = min(common, len(ids) - 1)
            if common:
                for bank in (cache.K, cache.V):
                    for layer in bank:
                        del layer[common:]
                del cache.tokens[common:]
                cache.next_position = common
                cache.last_logits = None
                cache.reserved_bytes = 0
            else:
                cache = KVCache(self.model.n_layers, self.limits.max_context)
            with self.stream_sequence(sequence, request.config, interrupt=interrupt,
                                      _private_cpu_cache=cache) as stream:
                for _event in stream:
                    pass
            if stream.result is None:
                raise RuntimeContractError("batch generation terminated without result")
            results[i] = BatchGenerationResult(request.request_id, stream.result)
            # Retain ONLY tokens belonging to this input. A sliding bank or
            # changed device cannot contribute to subsequent prefill.
            if (cache.next_position != len(cache.tokens) or len(cache.tokens) < len(ids)
                    or tuple(cache.tokens[:len(ids)]) != ids
                    or len(ids) + len(stream.result.generated_ids) > self.limits.max_context):
                cache = None
            else:
                for bank in (cache.K, cache.V):
                    for layer in bank:
                        del layer[len(ids):]
                del cache.tokens[len(ids):]
                cache.next_position = len(ids)
                cache.last_logits = None
                cache.reserved_bytes = 0
                if (not NativeConversationSession._compact_retained_prefix(
                        cache, width=self.model.dim, budget=budget)
                        or NativeConversationSession._retained_prefix_size(cache) > budget):
                    cache = None
            previous_prompt = ids
            previous_binding = binding
        return tuple(results[i] for i in range(len(admitted)))

    def replay(
        self,
        receipt: ReplayReceipt,
        prompt: str,
        config: GenerationConfig,
        *,
        require_same_device: bool = True,
    ) -> GenerationResult:
        if not isinstance(receipt, ReplayReceipt):
            raise RuntimeContractError("ReplayReceipt required")
        if receipt.model_digest != self.model_digest:
            raise ReplayMismatch("model identity changed")
        if receipt.tokenizer_digest != self.tokenizer.digest:
            raise ReplayMismatch("tokenizer identity changed")
        if receipt.architecture_digest != self.architecture.digest:
            raise ReplayMismatch("architecture identity changed")
        if require_same_device and receipt.device_digest != self.device.digest:
            raise ReplayMismatch("device identity changed")

        result = self.generate(prompt, config)
        observed = result.replay_receipt
        for label, left, right in (
            ("request", observed.request_digest, receipt.request_digest),
            ("config", observed.config_digest, receipt.config_digest),
            ("output", observed.output_digest, receipt.output_digest),
        ):
            if not hmac.compare_digest(left, right):
                raise ReplayMismatch(f"{label} replay digest mismatch")
        return result

    def checkpoint(self) -> Mapping[str, Any]:
        self.assert_model_unchanged()
        try:
            self.tokenizer.assert_unchanged()
        except TokenizerContractError as exc:
            raise RuntimeContractError("tokenizer changed before checkpoint") from exc
        return make_checkpoint(
            model=self.model,
            model_digest=self.model_digest,
            tokenizer_checkpoint=self.tokenizer.checkpoint(),
            architecture=self.architecture.to_dict(),
            limits=self.limits,
            device_policy=self.device_policy,
        )

    def checkpoint_json(self) -> str:
        return encode_checkpoint_json(
            self.checkpoint(),
            max_bytes=self.limits.max_checkpoint_bytes,
        )

    @classmethod
    def restore(
        cls,
        checkpoint: Mapping[str, Any],
        *,
        device_policy: DevicePolicy | None = None,
    ) -> "NativeLLMRuntime":
        model, limits, policy, tokenizer_checkpoint, architecture = restore_components(
            checkpoint,
            device_policy=device_policy,
        )
        runtime = cls(model, limits=limits, device_policy=policy)
        if not hmac.compare_digest(runtime.model_digest, checkpoint["model_digest"]):
            raise RuntimeContractError("restored graph differs from admitted checkpoint weights")
        try:
            runtime.tokenizer.assert_checkpoint_matches(tokenizer_checkpoint)
        except TokenizerContractError as exc:
            raise RuntimeContractError("native tokenizer checkpoint identity mismatch") from exc
        if runtime.architecture.to_dict() != dict(architecture):
            raise RuntimeContractError("runtime checkpoint architecture mismatch")
        return runtime

    @classmethod
    def restore_json(
        cls,
        payload: str | bytes,
        *,
        device_policy: DevicePolicy | None = None,
    ) -> "NativeLLMRuntime":
        return cls.restore(
            parse_checkpoint_json(payload),
            device_policy=device_policy,
        )


class NativeConversationSession:
    """Stateful, bounded token-native conversation over an admitted runtime.

    A turn is committed only after successful generation. No generated text is
    decoded and re-encoded, preserving the exact token trajectory.
    """

    def __init__(self, runtime: NativeLLMRuntime, *, prefix_cache_bytes: int = 0) -> None:
        if not isinstance(runtime, NativeLLMRuntime):
            raise RuntimeContractError("NativeLLMRuntime required")
        if (type(prefix_cache_bytes) is not int
                or not 0 <= prefix_cache_bytes <= min(256 * 1024**2, runtime.limits.max_kv_bytes)):
            raise RuntimeContractError("private CPU prefix retention budget exceeds runtime ceiling")
        self._prefix_cache_bytes = prefix_cache_bytes
        self._prefix_cache: KVCache | None = None
        self._prefix_binding: tuple | None = None
        self._prefix_reused_tokens = 0
        self.runtime = runtime
        self._model_digest = runtime.model_digest
        self._tokenizer_digest = runtime.tokenizer.digest
        self._tokens: tuple[int, ...] = ()
        self.turns = 0
        self._revision = 0
        self._pending_streams: dict[int, tuple[int, str]] = {}

    @property
    def token_ids(self) -> tuple[int, ...]:
        return self._tokens

    def _clear_prefix_cache(self) -> None:
        self.runtime._release_idle_cpu_prefix(self)
        self._prefix_cache = None
        self._prefix_binding = None
        self._prefix_reused_tokens = 0

    def _cache_binding(self) -> tuple:
        runtime = self.runtime
        return (runtime.model_digest, runtime.tokenizer.digest,
                runtime.architecture.digest, runtime.device.digest,
                runtime.device_policy, runtime.limits)

    @staticmethod
    def _compact_retained_prefix(cache: KVCache, *, width: int, budget: int) -> bool:
        """Lossless packed native double rows for private idle CPU banks.

        Only a detached, successful owner-local bank is eligible. Active
        inference can read packed rows directly; newly appended rows may
        remain ordinary lists until publication. No quantization, re-encode
        of token IDs, disk write or accelerator claim. Reject invalid banks
        without granting idle-retention authority.
        """
        count = len(cache.tokens)
        if (not count or cache.next_position != count or cache.reserved_bytes
                or width < 1 or budget < 1 or array("d").itemsize != 8
                or count * cache.n_layers * width * 16 > budget):
            return False
        for bank in (cache.K, cache.V):
            if len(bank) != cache.n_layers:
                return False
            for layer in bank:
                if len(layer) != count:
                    return False
                for index, row in enumerate(layer):
                    if len(row) != width:
                        return False
                    if type(row) is array:
                        if row.typecode != "d" or any(not math.isfinite(x) for x in row):
                            return False
                        continue
                    if type(row) is not list or any(type(x) is not float or not math.isfinite(x) for x in row):
                        return False
                    # Convert one row at a time so the whole packed bank
                    # is never resident alongside a second unpacked bank.
                    packed = array("d", row)
                    if sys.getsizeof(packed) < sys.getsizeof(row) + sum(sys.getsizeof(x) for x in row):
                        layer[index] = packed
        return True

    @staticmethod
    def _retained_prefix_size(cache: KVCache) -> int:
        # Conservative Python object accounting (not process RSS or driver
        # allocation); count each occurrence even when objects alias.
        size = sys.getsizeof(cache) + sys.getsizeof(cache.__dict__)
        size += sys.getsizeof(cache.tokens) + sum(sys.getsizeof(x) for x in cache.tokens)
        if cache.last_logits is not None:
            size += sys.getsizeof(cache.last_logits) + sum(sys.getsizeof(x) for x in cache.last_logits)
        for bank in (cache.K, cache.V):
            size += sys.getsizeof(bank)
            for layer in bank:
                size += sys.getsizeof(layer)
                for row in layer:
                    # array owns its C double buffer, not individual
                    # Python float objects. getsizeof includes that buffer.
                    size += sys.getsizeof(row)
                    if type(row) is not array:
                        size += sum(sys.getsizeof(x) for x in row)
        return size

    @property
    def prefix_cache_status(self) -> Mapping[str, int]:
        cache = self._prefix_cache
        return {"retention_budget_bytes": self._prefix_cache_bytes,
                "retained_tokens": len(cache.tokens) if cache is not None else 0,
                "estimated_retained_python_bytes": self._retained_prefix_size(cache) if cache is not None else 0,
                "previous_turn_prefix_tokens": self._prefix_reused_tokens}

    def reset(self) -> None:
        self._clear_prefix_cache()
        self._tokens = ()
        self.turns = 0
        self._revision += 1
        self._pending_streams.clear()

    def _assert_identity(self) -> None:
        self.runtime.assert_model_unchanged()
        try:
            self.runtime.tokenizer.assert_unchanged()
        except TokenizerContractError as exc:
            raise RuntimeContractError("session tokenizer mutated") from exc
        if not hmac.compare_digest(self._model_digest, self.runtime.model_digest):
            raise RuntimeContractError("session model identity changed")
        if not hmac.compare_digest(self._tokenizer_digest, self.runtime.tokenizer.digest):
            raise RuntimeContractError("session tokenizer identity changed")

    def generate(
        self,
        text: str,
        config: GenerationConfig | None = None,
    ) -> GenerationResult:
        self._assert_identity()
        incoming = self.runtime.encode(text).token_ids
        if not incoming:
            raise RuntimeContractError("conversation turn must not be empty")
        if len(incoming) > self.runtime.limits.max_context:
            raise RuntimeContractError("conversation turn exceeds context budget")
        cfg = config or GenerationConfig(
            max_new_tokens=min(32, self.runtime.limits.max_new_tokens)
        )
        if not isinstance(cfg, GenerationConfig):
            raise RuntimeContractError("GenerationConfig required")
        available = self.runtime.limits.max_context - len(incoming)
        history = self._tokens[-available:] if available else ()
        prompt_ids = history + incoming
        sequence = TokenSequence(
            self._tokenizer_digest,
            prompt_ids,
            digest_json({"session_turn": self.turns, "token_ids": list(prompt_ids)}),
        )
        binding = self._cache_binding()
        cache = self._prefix_cache
        cache_binding = self._prefix_binding
        # Detach before execution; this private bank is never leased to two
        # concurrent callers or copied into a child session.
        self._clear_prefix_cache()
        revision = self._revision
        reused = 0
        cpu = (self._prefix_cache_bytes and cfg.use_cache
               and self.runtime.device.actual == "cpu"
               and not self.runtime.device.resident
               and self.runtime.model._accel is None
               and not self.runtime.model.use_mod)
        if cpu:
            if (cache is None or cache_binding != binding
                    or cache.owner is not self.runtime.model
                    or cache.next_position != len(cache.tokens)
                    or tuple(cache.tokens) != prompt_ids[:len(cache.tokens)]
                    or self._retained_prefix_size(cache) > self._prefix_cache_bytes):
                cache = KVCache(self.runtime.model.n_layers, self.runtime.limits.max_context)
            else:
                reused = len(cache.tokens)
            with GenerationStream(self.runtime._stream_sequence_impl(
                    sequence, cfg, _private_cpu_cache=cache)) as stream:
                for _event in stream:
                    pass
            result = stream.result
            if result is None:
                raise RuntimeContractError("private CPU prefix generation lacked terminal result")
        else:
            cache = None
            result = self.runtime.generate_sequence(sequence, cfg)
        self._assert_identity()
        if revision != self._revision:
            raise RuntimeContractError("session changed during generation")
        self._tokens = (prompt_ids + result.generated_ids)[-self.runtime.limits.max_context:]
        if (cache is not None and cache.tokens and binding == self._cache_binding()
                and cache.next_position == len(cache.tokens)
                and tuple(cache.tokens) == self._tokens[:len(cache.tokens)]):
            compacted = self._compact_retained_prefix(
                cache, width=self.runtime.model.dim, budget=self._prefix_cache_bytes,
            )
            retained_size = self._retained_prefix_size(cache) if compacted else self._prefix_cache_bytes + 1
            if (retained_size <= self._prefix_cache_bytes
                    and self.runtime._reserve_idle_cpu_prefix(self, retained_size)):
                self._prefix_cache = cache
                self._prefix_binding = binding
        self._prefix_reused_tokens = reused
        self.turns += 1
        self._revision += 1
        self._pending_streams.clear()
        return result

    @property
    def context_used(self) -> int:
        """Number of currently retained context tokens."""
        return len(self._tokens)

    @property
    def context_remaining(self) -> int:
        return self.runtime.limits.max_context - len(self._tokens)

    @property
    def is_empty(self) -> bool:
        return not self._tokens

    def history_text(self) -> str:
        self._assert_identity()
        return self.runtime.decode_ids(self._tokens)

    def history_digest(self) -> str:
        self._assert_identity()
        return digest_json({"tokens": list(self._tokens), "turns": self.turns})

    def preview_tokens(self, text: str) -> tuple[int, ...]:
        self._assert_identity()
        return self.runtime.encode(text).token_ids

    def preview_context(self, text: str) -> tuple[int, ...]:
        incoming = self.preview_tokens(text)
        if not incoming or len(incoming) > self.runtime.limits.max_context:
            raise RuntimeContractError("invalid conversation turn length")
        available = self.runtime.limits.max_context - len(incoming)
        return (self._tokens[-available:] if available else ()) + incoming

    def preview_kv_bytes(self, text: str) -> int:
        return self.runtime.estimate_kv_bytes(len(self.preview_context(text)))

    def infer_next(self, text: str, *, use_cache: bool = True) -> InferenceResult:
        tokens = self.preview_context(text)
        sequence = TokenSequence(self._tokenizer_digest, tokens,
                                 digest_json({"preview": list(tokens)}))
        return self.runtime.infer_sequence(sequence, use_cache=use_cache)

    def append_tokens(self, token_ids: Sequence[int]) -> None:
        self._assert_identity()
        ids = tuple(token_ids)
        if any(type(i) is not int or i < 0 or i >= self.runtime.tokenizer.vocab_size for i in ids):
            raise RuntimeContractError("invalid appended token")
        self._clear_prefix_cache()
        self._tokens = (self._tokens + ids)[-self.runtime.limits.max_context:]
        self._revision += 1

    def append_text(self, text: str) -> None:
        self.append_tokens(self.preview_tokens(text))

    def truncate(self, keep_last: int) -> None:
        self._assert_identity()
        if type(keep_last) is not int or keep_last < 0:
            raise RuntimeContractError("invalid truncation length")
        self._clear_prefix_cache()
        self._tokens = self._tokens[-keep_last:] if keep_last else ()
        self._revision += 1

    def drop_prefix(self, count: int) -> None:
        self._assert_identity()
        if type(count) is not int or count < 0:
            raise RuntimeContractError("invalid prefix count")
        self._clear_prefix_cache()
        self._tokens = self._tokens[count:]
        self._revision += 1

    def fork(self) -> "NativeConversationSession":
        self._assert_identity()
        child = NativeConversationSession(self.runtime)
        child._tokens = self._tokens
        child.turns = self.turns
        child._revision = self._revision
        return child

    def replace_history(self, token_ids: Sequence[int]) -> None:
        self._assert_identity()
        ids = tuple(token_ids)
        if len(ids) > self.runtime.limits.max_context or any(
            type(i) is not int or i < 0 or i >= self.runtime.tokenizer.vocab_size for i in ids
        ):
            raise RuntimeContractError("invalid replacement history")
        self._clear_prefix_cache()
        self._tokens = ids
        self._revision += 1

    def merge_history(self, other: "NativeConversationSession") -> None:
        self._assert_identity()
        if not isinstance(other, NativeConversationSession):
            raise RuntimeContractError("conversation session required")
        other._assert_identity()
        if (self._model_digest != other._model_digest or
            self._tokenizer_digest != other._tokenizer_digest):
            raise RuntimeContractError("incompatible conversation histories")
        self.append_tokens(other.token_ids)

    def stream_turn(
        self, text: str, config: GenerationConfig | None = None,
    ) -> GenerationStream:
        """Stream a conversation turn; caller explicitly commits the result."""
        self._assert_identity()
        tokens = self.preview_context(text)
        sequence = TokenSequence(self._tokenizer_digest, tokens,
                                 digest_json({"session_turn": self.turns, "token_ids": list(tokens)}))
        self._clear_prefix_cache()
        stream = self.runtime.stream_sequence(sequence, config)
        self._pending_streams[id(stream)] = (self._revision, sequence.digest)
        return stream

    def commit_stream(self, stream: GenerationStream) -> GenerationResult:
        self._assert_identity()
        if not isinstance(stream, GenerationStream) or stream.result is None:
            raise RuntimeContractError("completed generation stream required")
        result = stream.result
        pending = self._pending_streams.pop(id(stream), None)
        if pending is None or pending != (self._revision, result.prompt_sequence.digest):
            raise RuntimeContractError("stream is stale or not owned by session")
        if result.replay_receipt.model_digest != self._model_digest or (
            result.replay_receipt.tokenizer_digest != self._tokenizer_digest
        ):
            raise RuntimeContractError("stream identity mismatch")
        if self._tokens:
            prompt = result.prompt_sequence.token_ids
            history_len = min(len(self._tokens), len(prompt))
            if prompt[:history_len] != self._tokens[-history_len:]:
                raise RuntimeContractError("stream history diverged")
        self._clear_prefix_cache()
        self._tokens = (result.prompt_sequence.token_ids + result.generated_ids)[
            -self.runtime.limits.max_context:]
        self.turns += 1
        self._revision += 1
        self._pending_streams.clear()
        return result

    def export_token_ids(self) -> list[int]:
        self._assert_identity()
        return list(self._tokens)

    def capacity_for(self, text: str) -> int:
        """Remaining context slots after preparing a prospective prompt."""
        return self.runtime.limits.max_context - len(self.preview_context(text))

    def snapshot(self) -> Mapping[str, Any]:
        self._assert_identity()
        return {
            "model_digest": self._model_digest,
            "tokenizer_digest": self._tokenizer_digest,
            "token_ids": list(self._tokens),
            "turns": self.turns,
            "digest": digest_json({
                "model_digest": self._model_digest,
                "tokenizer_digest": self._tokenizer_digest,
                "token_ids": list(self._tokens),
                "turns": self.turns,
            }),
        }

    @classmethod
    def restore(
        cls,
        runtime: NativeLLMRuntime,
        snapshot: Mapping[str, Any],
    ) -> "NativeConversationSession":
        if not isinstance(snapshot, Mapping):
            raise RuntimeContractError("session snapshot mapping required")
        session = cls(runtime)
        try:
            tokens = snapshot["token_ids"]
            turns = snapshot["turns"]
            if (not isinstance(tokens, list) or
                any(type(t) is not int or t < 0 or t >= runtime.tokenizer.vocab_size for t in tokens) or
                len(tokens) > runtime.limits.max_context or
                type(turns) is not int or turns < 0):
                raise ValueError("invalid session state")
            payload = {
                "model_digest": session._model_digest,
                "tokenizer_digest": session._tokenizer_digest,
                "token_ids": tokens,
                "turns": turns,
            }
            if (not hmac.compare_digest(snapshot["model_digest"], session._model_digest) or
                not hmac.compare_digest(snapshot["tokenizer_digest"], session._tokenizer_digest) or
                not hmac.compare_digest(snapshot["digest"], digest_json(payload))):
                raise ValueError("session identity or digest mismatch")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise RuntimeContractError("invalid or incompatible session snapshot") from exc
        session._tokens = tuple(tokens)
        session.turns = turns
        return session


__all__ = [
    "BatchGenerationResult",
    "GenerationResult",
    "GenerationStream",
    "InferenceResult",
    "NativeLLMRuntime",
    "NativeConversationSession",
]
