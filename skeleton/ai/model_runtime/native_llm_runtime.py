"""Executable native LLM serving boundary over Skeleton's causal transformer."""
from __future__ import annotations
import math

from dataclasses import dataclass
import math
import hmac
import random
from typing import Any, Iterator, Mapping, Sequence

from skeleton.cortex.attn import sample_logits
from skeleton.cortex.transformer import KVCache, TinyTransformer

from .flgb_model_runtime import ModelIdentity, TokenSequence, digest_json
from .runtime_checkpoint import (
    checkpoint_json as encode_checkpoint_json,
    logical_bytes,
    make_checkpoint,
    parse_checkpoint_json,
    portable_model_snapshot,
    restore_components,
    snapshot_digest,
    validate_model_snapshot,
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


class GenerationStream:
    """Streaming iterator whose terminal GenerationResult is retained."""

    def __init__(self, iterator: Iterator[RuntimeEvent]) -> None:
        self._iterator = iterator
        self.result: GenerationResult | None = None

    def __iter__(self) -> "GenerationStream":
        return self

    def __next__(self) -> RuntimeEvent:
        try:
            return next(self._iterator)
        except StopIteration as exc:
            if exc.value is not None and not isinstance(exc.value, GenerationResult):
                raise RuntimeContractError("stream returned invalid terminal result")
            self.result = exc.value
            raise

    def close(self) -> None:
        """Cancel a partially consumed stream and release its generator state."""
        close = getattr(self._iterator, "close", None)
        if close is not None:
            close()

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
        if self.limits.max_context > model.ctx:
            raise RuntimeContractError("runtime context exceeds model context")
        self.device_policy = device_policy or DevicePolicy()

        self._model_snapshot = portable_model_snapshot(model)
        validate_model_snapshot(self._model_snapshot)
        self._model_digest = snapshot_digest(self._model_snapshot)
        self._model_bytes = logical_bytes(self._model_snapshot)
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

    def estimate_kv_bytes(self, tokens: int) -> int:
        count = max(0, int(tokens))
        return count * self.model.n_layers * self.model.dim * 2 * 8 + count * 8

    def _bind_device(self, policy: DevicePolicy) -> DeviceReceipt:
        requested = policy.requested
        current = str(getattr(self.model, "device", "cpu") or "cpu")
        if requested == "cpu" and current == "cpu":
            actual = "cpu"
            resident = bool(getattr(self.model, "resident", False))
        else:
            try:
                self.model.to(requested)
            except Exception as exc:
                raise RuntimeContractError("device binding failed") from exc
            actual = str(getattr(self.model, "device", "cpu") or "cpu")
            resident = bool(getattr(self.model, "resident", False))
        if requested in {"cuda", "gpu"}:
            degraded = actual != "cuda"
        elif requested in {"torch", "torch-cpu"}:
            degraded = not resident
        else:
            degraded = False
        if degraded and not policy.allow_fallback:
            raise RuntimeContractError(
                "requested device unavailable and fallback is disabled"
            )
        return DeviceReceipt(requested, actual, resident, degraded)

    def bind_device(self, policy: DevicePolicy) -> DeviceReceipt:
        if not isinstance(policy, DevicePolicy):
            raise RuntimeContractError("DevicePolicy required")
        receipt = self._bind_device(policy)
        self.device_policy = policy
        self.device = receipt
        return receipt

    def _current_model_digest(self) -> str:
        snapshot = portable_model_snapshot(self.model)
        validate_model_snapshot(snapshot)
        return snapshot_digest(snapshot)

    def assert_model_unchanged(self) -> None:
        if not hmac.compare_digest(self._current_model_digest(), self.model_digest):
            raise RuntimeContractError(
                "model mutated after admission; call refresh_model_identity"
            )

    def refresh_model_identity(self) -> str:
        snapshot = portable_model_snapshot(self.model)
        validate_model_snapshot(snapshot)
        size = logical_bytes(snapshot)
        if size > self.limits.max_model_bytes:
            raise RuntimeContractError("mutated model exceeds runtime memory budget")
        tokenizer = NativeTokenizer(self.model)
        architecture = self._architecture()
        if self.limits.max_context > self.model.ctx:
            raise RuntimeContractError("mutated model context below runtime limit")
        if self.estimate_kv_bytes(self.limits.max_context) > self.limits.max_kv_bytes:
            raise RuntimeContractError("mutated model exceeds KV memory budget")
        digest = snapshot_digest(snapshot)
        self._model_snapshot = snapshot
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
    ) -> InferenceResult:
        """Run embeddings → position/RoPE → transformer blocks → LM head.

        This exposes the executable inference graph independently of decoding so
        loaders, portability checks, and samplers can validate identical model
        state against a canonical pre-tokenized input.
        """
        if not isinstance(sequence, TokenSequence):
            raise RuntimeContractError("TokenSequence required")
        if not isinstance(use_cache, bool):
            raise RuntimeContractError("use_cache must be boolean")
        self.assert_model_unchanged()
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
        cache = KVCache(self.model.n_layers, self.limits.max_context) if use_cache else None
        logits = tuple(float(value) for value in self.model._logits_window(window, cache))
        if len(logits) != self.tokenizer.vocab_size:
            raise RuntimeContractError("inference graph emitted invalid logits shape")
        if any(value != value or value in (float("inf"), float("-inf")) for value in logits):
            raise RuntimeContractError("inference graph emitted non-finite logits")
        return InferenceResult(
            prompt_sequence=sequence,
            logits=logits,
            cache_tokens=len(cache.tokens) if cache is not None else 0,
            model_digest=self.model_digest,
            architecture_digest=self.architecture.digest,
        )

    def infer_text(self, text: str, *, use_cache: bool = True) -> InferenceResult:
        """Tokenize text and execute one next-token inference graph pass."""
        return self.infer_sequence(self.encode(text), use_cache=use_cache)

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
    ) -> InferenceResult:
        """Execute next-token inference directly from a bounded text feed."""
        return self.infer_sequence(self._finalize_feed(feed), use_cache=use_cache)

    def _config_digest(self, config: GenerationConfig) -> str:
        return digest_json(config.to_dict())

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
    ) -> GenerationStream:
        cfg = config or GenerationConfig(
            max_new_tokens=min(32, self.limits.max_new_tokens)
        )
        return GenerationStream(self._stream_impl(prompt, cfg))

    def _stream_impl(
        self,
        prompt: str,
        config: GenerationConfig,
    ) -> Iterator[RuntimeEvent]:
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
        return (yield from self._stream_sequence_impl(sequence, config))

    def stream_sequence(
        self,
        sequence: TokenSequence,
        config: GenerationConfig | None = None,
    ) -> GenerationStream:
        """Stream pre-tokenized inference through the canonical decoder."""
        cfg = config or GenerationConfig(max_new_tokens=min(32, self.limits.max_new_tokens))
        return GenerationStream(self._stream_sequence_impl(sequence, cfg))

    def _stream_sequence_impl(
        self,
        prompt_sequence: TokenSequence,
        config: GenerationConfig,
    ) -> Iterator[RuntimeEvent]:
        self._admit_sequence(prompt_sequence, config)
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
            if config.use_cache
            else None
        )
        output = list(prompt_sequence.token_ids)
        generated: list[int] = []
        stop_ids = set(config.stop_token_ids)
        finish_reason = "length"
        cache_resets = 0
        kv_peak = 0

        for _ in range(config.max_new_tokens):
            window = output[-self.limits.max_context :]
            before = len(cache.tokens) if cache is not None else 0
            primed = cache.primed_for(window) if cache is not None else False
            logits = tuple(float(value) for value in self.model._logits_window(window, cache))
            if len(logits) != self.tokenizer.vocab_size:
                raise RuntimeContractError("generation graph emitted invalid logits shape")
            if any(not math.isfinite(value) for value in logits):
                raise RuntimeContractError("generation graph emitted non-finite logits")
            if cache is not None and before and not primed:
                cache_resets += 1

            next_id = int(
                sample_logits(
                    logits,
                    rng,
                    temperature=config.temperature,
                    top_k=config.top_k,
                    top_p=config.top_p,
                )
            )
            if not 0 <= next_id < self.tokenizer.vocab_size:
                raise RuntimeContractError("sampler emitted token outside vocabulary")
            output.append(next_id)
            generated.append(next_id)
            token_text = self.tokenizer.token_text(next_id)
            cache_tokens = len(cache.tokens) if cache is not None else 0
            if cache is not None:
                kv_peak = max(kv_peak, self.estimate_kv_bytes(cache_tokens))
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
                text_delta=token_text,
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

            if next_id in stop_ids:
                finish_reason = "stop_token"
                event = RuntimeEvent(
                    sequence,
                    "stopped",
                    token_id=next_id,
                    text_delta=token_text,
                    cache_tokens=cache_tokens,
                    detail_digest=event.detail_digest,
                )
                events.append(event)
                yield event
                sequence += 1
                break

        if config.max_new_tokens == 0:
            finish_reason = "completed"

        generated_ids = tuple(generated)
        generated_tokens = tuple(
            self.tokenizer.token_text(token_id) for token_id in generated_ids
        )
        text = self.tokenizer.decode_ids(generated_ids)
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
        checkpoint = self.checkpoint()
        event = RuntimeEvent(
            sequence,
            "completed",
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

    def generate_sequence(
        self,
        sequence: TokenSequence,
        config: GenerationConfig | None = None,
    ) -> GenerationResult:
        """Generate from token IDs without lossy decoding and retokenization."""
        stream = self.stream_sequence(sequence, config)
        for _event in stream:
            pass
        if stream.result is None:
            raise RuntimeContractError("generation terminated without result")
        return stream.result

    def stream_feed(
        self,
        feed: StreamingTextFeed,
        config: GenerationConfig | None = None,
    ) -> GenerationStream:
        """Execute a bounded text feed as a stream of real transformer tokens.

        The feed is finalized once; token IDs are forwarded without a lossy
        text round-trip, and generation uses the canonical decoder.
        """
        return self.stream_sequence(self._finalize_feed(feed), config)

    def generate_feed(
        self,
        feed: StreamingTextFeed,
        config: GenerationConfig | None = None,
    ) -> GenerationResult:
        """Finalize a StreamingTextFeed and execute it end-to-end."""
        return self.generate_sequence(self._finalize_feed(feed), config)

    def generate(
        self,
        prompt: str,
        config: GenerationConfig | None = None,
    ) -> GenerationResult:
        stream = self.stream(prompt, config)
        for _event in stream:
            pass
        if stream.result is None:
            raise RuntimeContractError("generation terminated without result")
        return stream.result

    def generate_batch(
        self,
        requests: Sequence[BatchGenerationRequest],
    ) -> tuple[BatchGenerationResult, ...]:
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
            sequence, _ = self._admit(request.prompt, request.config)
            aggregate += len(sequence.token_ids) + request.config.max_new_tokens
            if aggregate > self.limits.max_batch_tokens:
                raise RuntimeContractError("batch token budget exceeded")
            admitted.append((request, sequence))

        # Each admitted sequence is immutable and bound to the tokenizer
        # digest. Re-encoding a prompt here would create a second admission
        # boundary and allow a different token trajectory after preflight.
        return tuple(
            BatchGenerationResult(
                request.request_id,
                self.generate_sequence(sequence, request.config),
            )
            for request, sequence in admitted
        )

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

    def __init__(self, runtime: NativeLLMRuntime) -> None:
        if not isinstance(runtime, NativeLLMRuntime):
            raise RuntimeContractError("NativeLLMRuntime required")
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

    def reset(self) -> None:
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
        result = self.runtime.generate_sequence(sequence, cfg)
        self._assert_identity()
        self._tokens = (prompt_ids + result.generated_ids)[-self.runtime.limits.max_context:]
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
        self._tokens = (self._tokens + ids)[-self.runtime.limits.max_context:]
        self._revision += 1

    def append_text(self, text: str) -> None:
        self.append_tokens(self.preview_tokens(text))

    def truncate(self, keep_last: int) -> None:
        self._assert_identity()
        if type(keep_last) is not int or keep_last < 0:
            raise RuntimeContractError("invalid truncation length")
        self._tokens = self._tokens[-keep_last:] if keep_last else ()
        self._revision += 1

    def drop_prefix(self, count: int) -> None:
        self._assert_identity()
        if type(count) is not int or count < 0:
            raise RuntimeContractError("invalid prefix count")
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
