"""Checkpoint identity, validation, and portable restoration for native LLMs."""
from __future__ import annotations

from hashlib import sha256
import hmac
import json
import math
from typing import Any, Mapping

from skeleton.cortex.bpe import BytePairEncoder
from skeleton.cortex.transformer import TinyTransformer, TransformerBlock

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


# Native checkpoints have many numeric rows. Encode bounded runs through
# CPython's C encoder instead of yielding a Python fragment per parameter.
# Keep standard JSON escaping, numeric formatting and key ordering.
_NUMERIC_RUN = 1024


def _canonical_fragments(value: Any, encoder: json.JSONEncoder, ancestors: set[int]):
    if type(value) is dict and all(type(key) is str for key in value):
        identity = id(value)
        if identity in ancestors:
            raise ValueError("circular reference")
        ancestors.add(identity)
        try:
            yield b"{"
            for index, key in enumerate(sorted(value)):
                if index:
                    yield b","
                yield encoder.encode(key).encode("utf-8")
                yield b":"
                yield from _canonical_fragments(value[key], encoder, ancestors)
            yield b"}"
        finally:
            ancestors.remove(identity)
    elif type(value) in (list, tuple):
        identity = id(value)
        if identity in ancestors:
            raise ValueError("circular reference")
        ancestors.add(identity)
        try:
            yield b"["
            for start in range(0, len(value), _NUMERIC_RUN):
                block = value[start:start + _NUMERIC_RUN]
                if not block:
                    continue
                if start:
                    yield b","
                # Strict builtin scalar types only; strings or exotic
                # containers fall back to canonical encoder semantics.
                if all(type(item) in (int, float, bool, type(None)) for item in block):
                    yield encoder.encode(block)[1:-1].encode("utf-8")
                else:
                    for index, item in enumerate(block):
                        if index:
                            yield b","
                        yield from _canonical_fragments(item, encoder, ancestors)
            yield b"]"
        finally:
            ancestors.remove(identity)
    else:
        for fragment in encoder.iterencode(value):
            yield fragment.encode("utf-8")


def _canonical_digest_and_size(value: Any, *, maximum: int | None = None) -> tuple[str, int]:
    """Hash exactly the canonical JSON, accelerating bounded numeric runs.

    Memory is proportional to a bounded run and the largest individual
    encoded scalar rather than total checkpoint serialization. Unknown
    container types retain the standard encoder's behavior.
    """
    from .flgb_model_runtime import ModelRuntimeError
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"),
                               allow_nan=False, ensure_ascii=False)
    hasher = sha256()
    pending = bytearray()
    total = 0
    try:
        for raw in _canonical_fragments(value, encoder, set()):
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


def _capture_model_snapshot(model: TinyTransformer) -> dict[str, Any]:
    raw = model.snapshot()
    if not isinstance(raw, dict):
        raise RuntimeContractError("model snapshot must be a mapping")
    snapshot = dict(raw)
    snapshot.pop("device", None)
    snapshot.pop("resident", None)
    return snapshot


def portable_model_snapshot(model: TinyTransformer) -> dict[str, Any]:
    snapshot = _capture_model_snapshot(model)
    _digest_and_size(snapshot)  # preserve public encodability contract
    return snapshot


def capture_validated_model(model: TinyTransformer) -> tuple[dict[str, Any], str]:
    """Single observation of the copied graph, with all original checks.

    Callers that require BOTH shape verification and canonical digest use
    this path instead of separately encoding the same portable snapshot
    twice. No cached/remembered hash stands in for current weight bytes.
    """
    snapshot = _capture_model_snapshot(model)
    validate_model_snapshot(snapshot)
    return snapshot, _digest_and_size(snapshot)[0]


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
    snapshot, observed_model_digest = capture_validated_model(model)
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
    digest, body_bytes = _digest_and_size(body, maximum=limits.max_checkpoint_bytes)
    if _envelope_size(body_bytes, digest) > limits.max_checkpoint_bytes:
        raise RuntimeContractError("checkpoint envelope exceeds byte budget")
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


def _envelope_size(body_bytes: int, digest: str) -> int:
    # Body is a nonempty canonical JSON object with no digest key. Adding
    # one fixed ASCII SHA-256 field adds exactly one comma plus its bytes,
    # regardless of where sorted-key serialization inserts the field.
    return body_bytes + len(canonical_bytes({"digest": digest})) - 1


def _validate_checkpoint_with_size(checkpoint: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
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
    expected = checkpoint.get("digest")
    if (
        not isinstance(expected, str)
        or len(expected) != 64
        or any(ch not in "0123456789abcdef" for ch in expected)
    ):
        raise RuntimeContractError("runtime checkpoint digest missing")
    body = dict(checkpoint)
    body.pop("digest", None)
    observed, body_bytes = _digest_and_size(body, maximum=MAX_CHECKPOINT_BYTES)
    envelope_bytes = _envelope_size(body_bytes, expected)
    if envelope_bytes > MAX_CHECKPOINT_BYTES:
        raise RuntimeContractError("checkpoint envelope exceeds global byte budget")
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
    return body, envelope_bytes


def validate_checkpoint(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    body, _ = _validate_checkpoint_with_size(checkpoint)
    return body


def _restore_complete_reference_graph(snapshot: Mapping[str, Any]) -> TinyTransformer:
    """Load a previously validated complete CPU graph without random init.

    The historical restore constructs random full-size tensors, replaces
    them with checkpoint weights, and builds every layer twice. For the
    canonical non-routed format, construct only the detached actual
    weights. Legacy/custom/MoD formats retain their original loader.
    Called exclusively after checkpoint, shape and resource admission.
    """
    expected = {
        "dim", "ctx", "n_heads", "n_layers", "d_ff", "fitted", "steps",
        "tied", "norm", "ffn_kind", "itos", "E", "P", "Wq", "Wk", "Wv",
        "Wo", "Wout", "bout", "W1", "b1", "W2", "b2", "layers",
        "use_mod", "mod",
    }
    if (not expected <= set(snapshot)
            or set(snapshot) - expected - {"position_mode", "special_tokens"}
            or snapshot["use_mod"] is not False or snapshot["mod"] is not None
            or type(snapshot["tied"]) is not bool
            or snapshot["dim"] < 4 or snapshot["ctx"] < 2
            or len(snapshot["itos"]) < 2):
        return TinyTransformer.from_snapshot(dict(snapshot))
    matrices = ("Wq", "Wk", "Wv", "Wo", "W1", "Wu", "W2")
    vectors = ("ln1_g", "ln1_b", "ln2_g", "ln2_b", "b1", "bu", "b2")
    layer_keys = set(matrices + vectors + ("dim", "d_ff", "norm", "ffn_kind"))
    if any(set(layer) != layer_keys or layer["dim"] != snapshot["dim"]
           or any(type(layer[name]) is not list for name in matrices + vectors)
           for layer in snapshot["layers"]):
        return TinyTransformer.from_snapshot(dict(snapshot))

    # Mirrored first-layer fields and tied projection must agree before any
    # graph allocation. These are represented redundantly by the old schema.
    for key in ("Wq", "Wk", "Wv", "Wo", "W1", "W2", "b1", "b2"):
        if snapshot[key] != snapshot["layers"][0][key]:
            raise RuntimeContractError("checkpoint first-layer aliases disagree")
    if snapshot["tied"] and snapshot["E"] != snapshot["Wout"]:
        raise RuntimeContractError("checkpoint tied projection disagrees with embedding")

    def matrix(value):
        # Float conversion matches the historical loader, without initializing
        # a throwaway matrix or aliasing mutable rows from the caller.
        return [list(map(float, row)) for row in value]

    model = TinyTransformer.__new__(TinyTransformer)
    model.itos = list(snapshot["itos"])
    model.stoi = {token: i for i, token in enumerate(model.itos)}
    model.unk = 0
    for name, value in snapshot.get("special_tokens", {}).items():
        setattr(model, name, value)
    for name in ("dim", "ctx", "n_heads", "n_layers", "d_ff",
                 "fitted", "steps", "norm", "ffn_kind", "tied"):
        setattr(model, name, snapshot[name])
    model.position_mode = snapshot.get("position_mode", "learned_rope")
    model.device, model.requested, model.resident = "cpu", "cpu", False
    model._accel = None
    model.use_mod, model.mod = False, None
    model.E = matrix(snapshot["E"])
    model.P = matrix(snapshot["P"])
    model.Wout = model.E if model.tied else matrix(snapshot["Wout"])
    model.bout = list(map(float, snapshot["bout"]))
    model.layers = []
    for source in snapshot["layers"]:
        layer = TransformerBlock.__new__(TransformerBlock)
        layer.dim, layer.d_ff = model.dim, model.d_ff
        layer.norm, layer.ffn_kind = model.norm, model.ffn_kind
        for name in matrices:
            setattr(layer, name, matrix(source[name]))
        for name in vectors:
            setattr(layer, name, list(map(float, source[name])))
        model.layers.append(layer)
    return model


def restore_components(
    checkpoint: Mapping[str, Any],
    *,
    device_policy: DevicePolicy | None = None,
) -> tuple[TinyTransformer, RuntimeLimits, DevicePolicy, Mapping[str, Any], Mapping[str, Any]]:
    body, envelope_bytes = _validate_checkpoint_with_size(checkpoint)
    tokenizer_checkpoint = body["tokenizer"]
    bpe_snapshot = tokenizer_checkpoint.get("bpe")
    if bpe_snapshot is not None and not isinstance(bpe_snapshot, Mapping):
        raise RuntimeContractError("invalid runtime checkpoint BPE state")

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
    if envelope_bytes > limits.max_checkpoint_bytes:
        raise RuntimeContractError("checkpoint envelope exceeds byte budget")
    if logical_bytes(body["model"]) > limits.max_model_bytes:
        raise RuntimeContractError("checkpoint model exceeds runtime memory budget")
    if body["model"]["ctx"] < limits.max_context:
        raise RuntimeContractError("runtime context exceeds model context")

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

    # Validate resource and policy declarations before constructing the graph.
    model = _restore_complete_reference_graph(body["model"])
    if bpe_snapshot is not None:
        model.bpe = BytePairEncoder.from_snapshot(dict(bpe_snapshot))
    return model, limits, device_policy, tokenizer_checkpoint, body["architecture"]


__all__ = [
    "capture_validated_model",
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
