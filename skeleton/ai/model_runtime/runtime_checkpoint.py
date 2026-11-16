"""Checkpoint identity, validation, and portable restoration for native LLMs."""
from __future__ import annotations

from hashlib import sha256
import hmac
import json
import math
from typing import Any, Mapping

from skeleton.cortex.bpe import BytePairEncoder
from skeleton.cortex.transformer import TinyTransformer

from .flgb_model_runtime import canonical_bytes
from .runtime_contracts import (
    DevicePolicy,
    MAX_CHECKPOINT_BYTES,
    RUNTIME_SCHEMA,
    RuntimeContractError,
    RuntimeLimits,
    is_int,
    nonnegative_int,
    positive_int,
)


def _canonical_digest_and_size(value: Any, *, maximum: int | None = None) -> tuple[str, int]:
    """Hash canonical JSON without retaining a second full checkpoint buffer.

    Identical JSON configuration to canonical_bytes. Batch encoder fragments
    to avoid allocating a contiguous serialized copy of the weight graph.
    The largest individual string remains an encoder allocation.
    """
    from .flgb_model_runtime import ModelRuntimeError
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"),
                               allow_nan=False, ensure_ascii=False)
    hasher = sha256()
    pending = bytearray()
    total = 0
    try:
        for fragment in encoder.iterencode(value):
            raw = fragment.encode("utf-8")
            total += len(raw)
            if maximum is not None and total > maximum:
                raise RuntimeContractError("checkpoint exceeds byte budget")
            if len(raw) >= 65536:
                if pending:
                    hasher.update(pending)
                    pending.clear()
                hasher.update(raw)
            else:
                pending.extend(raw)
                if len(pending) >= 65536:
                    hasher.update(pending)
                    pending.clear()
        if pending:
            hasher.update(pending)
    except RuntimeContractError:
        raise
    except (TypeError, ValueError, RecursionError) as exc:
        raise ModelRuntimeError("value is not canonical-json encodable") from exc
    return hasher.hexdigest(), total


def _large_snapshot(value: Mapping[str, Any]) -> bool:
    graph = value.get("model", value)
    if not isinstance(graph, Mapping):
        return False
    dimensions = (graph.get("dim", 0), graph.get("ctx", 0),
                  graph.get("n_layers", 0), graph.get("d_ff", 0))
    if any(type(x) is not int or x < 0 for x in dimensions):
        return False
    dim, context, layers, ff = dimensions
    vocab = graph.get("itos")
    vocab_size = len(vocab) if isinstance(vocab, (list, tuple)) else 0
    cells = 2 * vocab_size * dim + context * dim + layers * (4 * dim * dim + 3 * dim * ff)
    return cells >= 131072


def _digest_and_size(value: Mapping[str, Any], *, maximum: int | None = None) -> tuple[str, int]:
    # Small checkpoints benefit from CPython's fast C JSON encoder.
    # Stream larger graphs without changing canonical identities.
    if _large_snapshot(value):
        return _canonical_digest_and_size(value, maximum=maximum)
    raw = canonical_bytes(value)
    if maximum is not None and len(raw) > maximum:
        raise RuntimeContractError("checkpoint exceeds byte budget")
    return sha256(raw).hexdigest(), len(raw)


def portable_model_snapshot(model: TinyTransformer) -> dict[str, Any]:
    raw = model.snapshot()
    if not isinstance(raw, dict):
        raise RuntimeContractError("model snapshot must be a mapping")
    snapshot = dict(raw)
    snapshot.pop("device", None)
    snapshot.pop("resident", None)
    _digest_and_size(snapshot)
    return snapshot


def snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    return _digest_and_size(snapshot)[0]


def logical_bytes(value: Any) -> int:
    """Portable logical footprint independent of Python object overhead."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return 1
    if isinstance(value, (int, float)):
        return 8
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, Mapping):
        return sum(logical_bytes(key) + logical_bytes(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return sum(logical_bytes(item) for item in value)
    raise RuntimeContractError("snapshot contains unsupported value")


def _number(value: Any, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise RuntimeContractError(f"invalid numeric value in {name}")
    return float(value)


def _vector(value: Any, size: int, name: str) -> None:
    if not isinstance(value, list) or len(value) != size:
        raise RuntimeContractError(f"invalid {name} shape")
    for item in value:
        _number(item, name)


def _matrix(value: Any, rows: int, cols: int, name: str) -> None:
    if not isinstance(value, list) or len(value) != rows:
        raise RuntimeContractError(f"invalid {name} rows")
    for row in value:
        _vector(row, cols, name)


def validate_model_snapshot(snapshot: Mapping[str, Any]) -> None:
    """Reject malformed weight graphs before creating executable state."""
    if not isinstance(snapshot, Mapping):
        raise RuntimeContractError("model snapshot must be a mapping")
    dim = positive_int(snapshot.get("dim"), "model dim", 1_000_000)
    ctx = positive_int(snapshot.get("ctx"), "model context", 1_000_000)
    heads = positive_int(snapshot.get("n_heads"), "model heads", dim)
    layers = positive_int(snapshot.get("n_layers"), "model layers", 65_536)
    d_ff = nonnegative_int(
        snapshot.get("d_ff", 0),
        "model feed-forward width",
        16_000_000,
    )
    if dim % heads:
        raise RuntimeContractError("model dimension must be divisible by head count")
    if snapshot.get("position_mode", "learned_rope") not in {"rope", "learned_rope"}:
        raise RuntimeContractError("unsupported model position mode")

    vocab = snapshot.get("itos")
    if (
        not isinstance(vocab, list)
        or not vocab
        or any(not isinstance(token, str) or not token for token in vocab)
        or len(set(vocab)) != len(vocab)
    ):
        raise RuntimeContractError("invalid model vocabulary")
    vocab_size = len(vocab)
    special_tokens = snapshot.get("special_tokens")
    if special_tokens is not None:
        if (not isinstance(special_tokens, Mapping) or "unk" not in special_tokens
                or set(special_tokens) - {"unk", "pad", "bos", "eos"}):
            raise RuntimeContractError("invalid model special token declarations")
        for token_id in special_tokens.values():
            nonnegative_int(token_id, "special token id", vocab_size - 1)
        if len(set(special_tokens.values())) != len(special_tokens):
            raise RuntimeContractError("special token IDs must be distinct")

    if snapshot.get("norm", "ln") not in {"ln", "rms"}:
        raise RuntimeContractError("unsupported model normalization")
    if snapshot.get("ffn_kind", "gelu") not in {"gelu", "swiglu"}:
        raise RuntimeContractError("unsupported model feed-forward activation")

    _matrix(snapshot.get("E"), vocab_size, dim, "token embedding")
    _matrix(snapshot.get("P"), ctx, dim, "position embedding")
    _matrix(snapshot.get("Wout"), vocab_size, dim, "output projection")
    _vector(snapshot.get("bout"), vocab_size, "output bias")

    raw_layers = snapshot.get("layers")
    if not isinstance(raw_layers, list) or len(raw_layers) != layers:
        raise RuntimeContractError("model layer count mismatch")

    for index, layer in enumerate(raw_layers):
        if not isinstance(layer, Mapping):
            raise RuntimeContractError("invalid transformer layer snapshot")
        prefix = f"layer[{index}]"
        for name in ("Wq", "Wk", "Wv", "Wo"):
            _matrix(layer.get(name), dim, dim, f"{prefix}.{name}")
        for name in ("ln1_g", "ln1_b", "ln2_g", "ln2_b"):
            _vector(layer.get(name), dim, f"{prefix}.{name}")
        layer_ff = nonnegative_int(layer.get("d_ff", d_ff), "layer feed-forward width", 16_000_000)
        if layer_ff != d_ff:
            raise RuntimeContractError("transformer layer FFN width mismatch")
        if layer.get("norm", "ln") != snapshot.get("norm", "ln"):
            raise RuntimeContractError("transformer layer normalization mismatch")
        if layer.get("ffn_kind", "gelu") != snapshot.get("ffn_kind", "gelu"):
            raise RuntimeContractError("transformer layer activation mismatch")
        if d_ff:
            _matrix(layer.get("W1"), d_ff, dim, f"{prefix}.W1")
            _matrix(layer.get("Wu"), d_ff, dim, f"{prefix}.Wu")
            _matrix(layer.get("W2"), dim, d_ff, f"{prefix}.W2")
            _vector(layer.get("b1"), d_ff, f"{prefix}.b1")
            _vector(layer.get("bu"), d_ff, f"{prefix}.bu")
            _vector(layer.get("b2"), dim, f"{prefix}.b2")
        else:
            for name in ("W1", "Wu", "W2", "b1", "bu", "b2"):
                if layer.get(name) not in ([], None):
                    raise RuntimeContractError(f"{prefix}.{name} must be empty without FFN")

    for name in ("fitted", "steps"):
        value = snapshot.get(name, 0)
        if not is_int(value) or value < 0:
            raise RuntimeContractError(f"invalid model {name}")


def make_checkpoint(
    *,
    model: TinyTransformer,
    model_digest: str,
    tokenizer_checkpoint: Mapping[str, Any],
    architecture: Mapping[str, Any],
    limits: RuntimeLimits,
    device_policy: DevicePolicy,
) -> Mapping[str, Any]:
    snapshot = portable_model_snapshot(model)
    validate_model_snapshot(snapshot)
    observed_model_digest = snapshot_digest(snapshot)
    if not hmac.compare_digest(observed_model_digest, model_digest):
        raise RuntimeContractError("model mutated before checkpoint")
    body = {
        "schema": RUNTIME_SCHEMA,
        "model": snapshot,
        "model_digest": model_digest,
        "tokenizer": dict(tokenizer_checkpoint),
        "architecture": dict(architecture),
        "limits": limits.to_dict(),
        "device_policy": device_policy.to_dict(),
    }
    digest, _ = _digest_and_size(body, maximum=limits.max_checkpoint_bytes)
    return {**body, "digest": digest}


def checkpoint_json(checkpoint: Mapping[str, Any], *, max_bytes: int) -> str:
    raw = canonical_bytes(checkpoint)
    if len(raw) > max_bytes:
        raise RuntimeContractError("checkpoint envelope exceeds byte budget")
    return raw.decode("utf-8")


def parse_checkpoint_json(payload: str | bytes) -> Mapping[str, Any]:
    if isinstance(payload, str):
        try:
            raw = payload.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise RuntimeContractError("checkpoint JSON is not valid Unicode") from exc
    elif isinstance(payload, bytes):
        raw = payload
    else:
        raise RuntimeContractError("checkpoint JSON must be str or bytes")
    if len(raw) > MAX_CHECKPOINT_BYTES:
        raise RuntimeContractError("checkpoint JSON exceeds global byte budget")
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeContractError("duplicate runtime checkpoint JSON key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise RuntimeContractError("non-finite runtime checkpoint JSON constant")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                           parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise RuntimeContractError("invalid checkpoint JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeContractError("checkpoint JSON root must be an object")
    return value


def validate_checkpoint(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(checkpoint, Mapping) or checkpoint.get("schema") != RUNTIME_SCHEMA:
        raise RuntimeContractError("unsupported runtime checkpoint")
    expected_keys = {
        "schema",
        "model",
        "model_digest",
        "tokenizer",
        "architecture",
        "limits",
        "device_policy",
        "digest",
    }
    if set(checkpoint) != expected_keys:
        raise RuntimeContractError("runtime checkpoint envelope shape mismatch")
    _digest_and_size(checkpoint, maximum=MAX_CHECKPOINT_BYTES)
    expected = checkpoint.get("digest")
    if (
        not isinstance(expected, str)
        or len(expected) != 64
        or any(ch not in "0123456789abcdef" for ch in expected)
    ):
        raise RuntimeContractError("runtime checkpoint digest missing")
    body = dict(checkpoint)
    body.pop("digest", None)
    observed = _digest_and_size(body)[0]
    if not hmac.compare_digest(observed, expected):
        raise RuntimeContractError("runtime checkpoint integrity failure")

    snapshot = body.get("model")
    if not isinstance(snapshot, Mapping):
        raise RuntimeContractError("runtime checkpoint model missing")
    validate_model_snapshot(snapshot)
    if body.get("model_digest") != snapshot_digest(snapshot):
        raise RuntimeContractError("runtime checkpoint model digest mismatch")

    tokenizer = body.get("tokenizer")
    if not isinstance(tokenizer, Mapping):
        raise RuntimeContractError("runtime checkpoint tokenizer missing")
    architecture = body.get("architecture")
    limits = body.get("limits")
    policy = body.get("device_policy")
    if not isinstance(architecture, Mapping):
        raise RuntimeContractError("runtime checkpoint architecture missing")
    if not isinstance(limits, Mapping):
        raise RuntimeContractError("runtime checkpoint limits missing")
    if not isinstance(policy, Mapping):
        raise RuntimeContractError("runtime checkpoint device policy missing")
    return body


def restore_components(
    checkpoint: Mapping[str, Any],
    *,
    device_policy: DevicePolicy | None = None,
) -> tuple[TinyTransformer, RuntimeLimits, DevicePolicy, Mapping[str, Any], Mapping[str, Any]]:
    body = validate_checkpoint(checkpoint)
    model = TinyTransformer.from_snapshot(dict(body["model"]))

    tokenizer_checkpoint = body["tokenizer"]
    bpe_snapshot = tokenizer_checkpoint.get("bpe")
    if bpe_snapshot is not None:
        if not isinstance(bpe_snapshot, Mapping):
            raise RuntimeContractError("invalid runtime checkpoint BPE state")
        model.bpe = BytePairEncoder.from_snapshot(dict(bpe_snapshot))

    limits_raw = body["limits"]
    required_limit_keys = {
        "max_context",
        "max_new_tokens",
        "max_total_tokens",
        "max_model_bytes",
        "max_kv_bytes",
        "max_batch_size",
        "max_batch_tokens",
        "max_checkpoint_bytes",
    }
    if set(limits_raw) != required_limit_keys:
        raise RuntimeContractError("runtime checkpoint limits shape mismatch")
    limits = RuntimeLimits(**dict(limits_raw))
    _digest_and_size(checkpoint, maximum=limits.max_checkpoint_bytes)

    policy_raw = body["device_policy"]
    required_policy_keys = {"requested", "allow_fallback"}
    allowed_policy_keys = required_policy_keys | {
        "kv_dtype", "kv_limit_bytes", "prefill_query_chunk",
    }
    if (
        not required_policy_keys.issubset(policy_raw)
        or not set(policy_raw).issubset(allowed_policy_keys)
    ):
        raise RuntimeContractError("runtime checkpoint device policy shape mismatch")
    # Validate the embedded policy even when an explicit device override is
    # supplied: a malformed signed checkpoint must never be laundered through
    # a caller-provided otherwise-valid backend selection.
    validated_policy = DevicePolicy(**dict(policy_raw))
    if device_policy is None:
        device_policy = validated_policy

    return model, limits, device_policy, tokenizer_checkpoint, body["architecture"]


__all__ = [
    "checkpoint_json",
    "logical_bytes",
    "make_checkpoint",
    "parse_checkpoint_json",
    "portable_model_snapshot",
    "restore_components",
    "snapshot_digest",
    "validate_checkpoint",
    "validate_model_snapshot",
]
