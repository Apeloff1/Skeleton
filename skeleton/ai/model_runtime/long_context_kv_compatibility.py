"""Read-only KV layout and tokenizer/head compatibility for offline CPU planning.

This contract does not read, validate, or allocate actual KV tensor pages.
It binds a declared model layout to a durable token window and rejects stale
heads, malformed window digests, oversize contexts and unsupported devices.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .long_context_progress import LongContextProgressHead, _name
from .long_context_spool import LongContextSpoolError, _canonical, _digest

_SCHEMA = "skeleton.ai.long-context-kv-compatibility.v1"
_HEAD_SCHEMA = "skeleton.ai.long-context-head.v1"


def _int(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise LongContextSpoolError("invalid " + name)
    return value


@dataclass(frozen=True, slots=True)
class KvLayout:
    model_digest: str
    tokenizer_digest: str
    layers: int
    heads: int
    head_dim: int
    context_tokens: int
    vocab_size: int
    bytes_per_element: int = 2
    device_kind: str = "cpu"

    def __post_init__(self) -> None:
        _digest(self.model_digest, "model digest")
        _digest(self.tokenizer_digest, "tokenizer digest")
        _int(self.layers, "KV layers", 1, 4096)
        _int(self.heads, "KV heads", 1, 4096)
        _int(self.head_dim, "KV head dimension", 1, 8192)
        _int(self.context_tokens, "KV context tokens", 1, 65536)
        _int(self.vocab_size, "KV vocabulary", 1, 2**24)
        if self.bytes_per_element not in (1, 2, 4, 8) or type(
            self.bytes_per_element
        ) is not int:
            raise LongContextSpoolError("invalid KV element width")
        if self.device_kind not in ("cpu", "gpu", "m_chip"):
            raise LongContextSpoolError("unsupported KV device kind")
        if (self.layers * self.heads * self.head_dim * self.context_tokens
                * self.bytes_per_element * 2 > 2**63 - 1):
            raise LongContextSpoolError("KV shape exceeds arithmetic bound")


@dataclass(frozen=True, slots=True)
class KvWindowRequest:
    stream_id: str
    checkpoint_digest: str
    generation: int
    max_tokens: int
    max_kv_bytes: int

    def __post_init__(self) -> None:
        _name(self.stream_id)
        _digest(self.checkpoint_digest, "checkpoint digest")
        _int(self.generation, "head generation", 0, 2**63 - 1)
        _int(self.max_tokens, "KV window tokens", 1, 4096)
        _int(self.max_kv_bytes, "KV byte budget", 1, 1024**3)


class LongContextKvCompatibility:
    """Generation-fenced compatibility observation, not KV integrity proof."""

    def __init__(self, heads: LongContextProgressHead):
        if not isinstance(heads, LongContextProgressHead):
            raise LongContextSpoolError("invalid KV progress coordinator")
        self._heads = heads

    @staticmethod
    def _receipt(state: str, reason: str, *,
                 kv_bytes: int | None = None,
                 window_digest: str | None = None) -> dict[str, object]:
        result: dict[str, object] = {
            "schema": _SCHEMA, "state": state, "reason": reason,
            "estimated_kv_bytes": kv_bytes,
            "window_digest": window_digest,
            "model_snapshot_attested": False,
            "tokenizer_state_attested": False,
            "kv_tensor_contents_verified": False,
            "device_qualified": False,
            "is_admission_grant": False,
            "is_execution_lease": False,
            "requires_live_backend_revalidation": True,
        }
        result["observation_digest"] = sha256(_canonical(result)).hexdigest()
        return result

    def observe(self, layout: KvLayout, request: KvWindowRequest, *,
                expected_model_digest: str, max_checkpoints: int = 4096
                ) -> dict[str, object]:
        if not isinstance(layout, KvLayout) or not isinstance(request, KvWindowRequest):
            raise LongContextSpoolError("invalid KV observation request")
        _digest(expected_model_digest, "expected model")
        _int(max_checkpoints, "KV checkpoint bound", 1, 100000)
        if layout.model_digest != expected_model_digest:
            return self._receipt("hold", "model_identity_mismatch")
        if layout.device_kind != "cpu":
            return self._receipt("hold", "unqualified_device")
        try:
            observed = self._heads.compare_window(
                request.stream_id,
                expected_checkpoint_digest=request.checkpoint_digest,
                expected_generation=request.generation,
                expected_tokenizer_digest=layout.tokenizer_digest,
                max_tokens=request.max_tokens,
                max_checkpoints=max_checkpoints,
            )
            if type(observed) is not dict or observed.get("schema") != _HEAD_SCHEMA:
                raise LongContextSpoolError("invalid KV head schema")
            if observed.get("is_execution_lease") is not False:
                raise LongContextSpoolError("KV head claimed execution")
            name = _name(request.stream_id)
            body = {
                "schema": _HEAD_SCHEMA,
                "stream_digest": name,
                "checkpoint_digest": request.checkpoint_digest,
                "tokenizer_digest": layout.tokenizer_digest,
                "generation": request.generation,
            }
            if (any(type(observed.get(key)) is not type(value)
                    or observed.get(key) != value for key, value in body.items())
                    or type(observed.get("record_digest")) is not str
                    or observed.get("record_digest") != sha256(_canonical(body)).hexdigest()):
                raise LongContextSpoolError("KV head identity mismatch")
            window = observed.get("window")
            if window is None:
                return self._receipt("hold", "window_exhausted")
            if type(window) is not dict or set(window) != {
                "start", "stop", "token_ids", "source_sequence_digest", "digest"
            }:
                raise LongContextSpoolError("invalid KV window fields")
            start = _int(window["start"], "KV window start", 0, 65536)
            stop = _int(window["stop"], "KV window stop", 1, 65536)
            tokens = window["token_ids"]
            if (type(tokens) is not list or stop <= start
                    or stop > layout.context_tokens or stop - start > request.max_tokens
                    or len(tokens) != stop - start
                    or any(type(token) is not int or not 0 <= token < layout.vocab_size
                           for token in tokens)):
                raise LongContextSpoolError("KV token window out of bounds")
            _digest(window["source_sequence_digest"], "source sequence digest")
            _digest(window["digest"], "KV window digest")
            body_window = {
                "start": start, "stop": stop,
                "token_ids": tokens,
                "source_sequence_digest": window["source_sequence_digest"],
            }
            digest = sha256(_canonical(body_window)).hexdigest()
            if digest != window["digest"]:
                raise LongContextSpoolError("KV token window digest mismatch")
            estimated = (2 * layout.layers * layout.heads * layout.head_dim
                         * stop * layout.bytes_per_element)
            if estimated > request.max_kv_bytes:
                return self._receipt("hold", "KV_memory_budget_exceeded")
            # Digest only: never expose token IDs or memory contents in receipts.
            return self._receipt("compatible_observed", "backend_must_revalidate",
                                 kv_bytes=estimated, window_digest=digest)
        except (LongContextSpoolError, OSError, ValueError, TypeError, KeyError):
            return self._receipt("hold", "KV_custody_unverified")


__all__ = ["KvLayout", "KvWindowRequest", "LongContextKvCompatibility"]
