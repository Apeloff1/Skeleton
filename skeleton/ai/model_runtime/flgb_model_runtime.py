"""FLGB-02 deterministic model-runtime and serving control contracts.

These primitives govern identities, placement, caches, batching, quantization,
speculative receipts, routing, local-model boundaries, and lifecycle state.
They do not silently load weights, execute vendor kernels, or widen authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID_CHARS = 256
MAX_TOKEN_ID = 2**31 - 1
MAX_TOKENS = 1_000_000
MAX_MODELS = 4096
MAX_WEIGHT_SHARDS = 65_536
MAX_WEIGHT_BYTES = 2**63 - 1
MAX_DEVICES = 256
MAX_BATCH_SIZE = 4096
MAX_REPLICAS = 1024
MAX_GENERATION = 1_000_000


class ModelRuntimeError(ValueError):
    """Fail-closed FLGB-02 contract violation."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def require_id(value: str, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_ID_CHARS
        or any(ord(ch) < 32 for ch in value)
    ):
        raise ModelRuntimeError(f"invalid {name}")
    return value


def require_digest(value: str, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ModelRuntimeError(f"invalid {name}")
    return value


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ModelRuntimeError("value is not canonical-json encodable") from exc


def digest_json(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class TokenSequence:
    tokenizer_digest: str
    token_ids: tuple[int, ...]
    source_text_digest: str

    def __post_init__(self) -> None:
        require_digest(self.tokenizer_digest, "tokenizer_digest")
        require_digest(self.source_text_digest, "source_text_digest")
        if len(self.token_ids) > MAX_TOKENS:
            raise ModelRuntimeError("token sequence exceeds budget")
        for token in self.token_ids:
            if not _is_int(token) or not 0 <= token <= MAX_TOKEN_ID:
                raise ModelRuntimeError("invalid token id")

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "tokenizer_digest": self.tokenizer_digest,
                "token_ids": list(self.token_ids),
                "source_text_digest": self.source_text_digest,
            }
        )


@dataclass(frozen=True)
class VocabularyManifest:
    tokenizer_id: str
    version: str
    tokens: tuple[tuple[str, int], ...]
    special_tokens: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_id(self.tokenizer_id, "tokenizer_id")
        require_id(self.version, "version")
        if not self.tokens or len(self.tokens) > MAX_TOKEN_ID:
            raise ModelRuntimeError("vocabulary size out of bounds")
        expected_ids = list(range(len(self.tokens)))
        observed_ids: list[int] = []
        observed_text: set[str] = set()
        for token, token_id in self.tokens:
            if not isinstance(token, str) or token in observed_text:
                raise ModelRuntimeError("duplicate or invalid vocabulary token")
            observed_text.add(token)
            if not _is_int(token_id):
                raise ModelRuntimeError("invalid vocabulary token id")
            observed_ids.append(token_id)
        if observed_ids != expected_ids:
            raise ModelRuntimeError("vocabulary ids must be contiguous and canonical")
        specials = dict(self.special_tokens)
        for name, token_id in specials.items():
            require_id(name, "special token name")
            if not _is_int(token_id) or token_id not in expected_ids:
                raise ModelRuntimeError("special token references unknown vocabulary id")
        object.__setattr__(self, "special_tokens", MappingProxyType(specials))

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "tokenizer_id": self.tokenizer_id,
                "version": self.version,
                "tokens": [[text, token_id] for text, token_id in self.tokens],
                "special_tokens": dict(self.special_tokens),
            }
        )


@dataclass(frozen=True)
class ModelIdentity:
    model_id: str
    revision: str
    architecture: str
    config_digest: str
    tokenizer_digest: str
    weights_digest: str

    def __post_init__(self) -> None:
        require_id(self.model_id, "model_id")
        require_id(self.revision, "revision")
        require_id(self.architecture, "architecture")
        require_digest(self.config_digest, "config_digest")
        require_digest(self.tokenizer_digest, "tokenizer_digest")
        require_digest(self.weights_digest, "weights_digest")

    @property
    def identity_digest(self) -> str:
        return digest_json(self.__dict__)


class ModelRegistry:
    """Immutable-by-revision model registry."""

    def __init__(self, models: Sequence[ModelIdentity] = ()) -> None:
        if len(models) > MAX_MODELS:
            raise ModelRuntimeError("model registry exceeds budget")
        entries: dict[tuple[str, str], ModelIdentity] = {}
        for model in models:
            if not isinstance(model, ModelIdentity):
                raise ModelRuntimeError("ModelIdentity required")
            key = (model.model_id, model.revision)
            if key in entries:
                raise ModelRuntimeError("duplicate model revision")
            entries[key] = model
        self._entries = MappingProxyType(entries)

    def register(self, model: ModelIdentity) -> "ModelRegistry":
        if not isinstance(model, ModelIdentity):
            raise ModelRuntimeError("ModelIdentity required")
        key = (model.model_id, model.revision)
        if key in self._entries:
            if self._entries[key] != model:
                raise ModelRuntimeError("model revision is immutable")
            return self
        if len(self._entries) >= MAX_MODELS:
            raise ModelRuntimeError("model registry exceeds budget")
        return ModelRegistry(tuple(self._entries.values()) + (model,))

    def resolve(self, model_id: str, revision: str) -> ModelIdentity:
        key = (require_id(model_id, "model_id"), require_id(revision, "revision"))
        try:
            return self._entries[key]
        except KeyError as exc:
            raise ModelRuntimeError("unknown model revision") from exc

    @property
    def digest(self) -> str:
        ordered = sorted(
            (model.__dict__ for model in self._entries.values()),
            key=lambda item: (item["model_id"], item["revision"]),
        )
        return digest_json(ordered)


@dataclass(frozen=True)
class WeightShard:
    index: int
    digest: str
    bytes: int
    source: str

    def __post_init__(self) -> None:
        if not _is_int(self.index) or self.index < 0:
            raise ModelRuntimeError("invalid shard index")
        require_digest(self.digest, "weight shard digest")
        if not _is_int(self.bytes) or not 1 <= self.bytes <= MAX_WEIGHT_BYTES:
            raise ModelRuntimeError("weight shard bytes out of bounds")
        require_id(self.source, "weight shard source")


@dataclass(frozen=True)
class WeightLoadPlan:
    model_identity_digest: str
    shards: tuple[WeightShard, ...]
    expected_total_bytes: int

    def __post_init__(self) -> None:
        require_digest(self.model_identity_digest, "model_identity_digest")
        if not self.shards or len(self.shards) > MAX_WEIGHT_SHARDS:
            raise ModelRuntimeError("weight shard count out of bounds")
        for index, shard in enumerate(self.shards):
            if not isinstance(shard, WeightShard) or shard.index != index:
                raise ModelRuntimeError("weight shards must be contiguous and ordered")
        total = sum(shard.bytes for shard in self.shards)
        if not _is_int(self.expected_total_bytes) or self.expected_total_bytes != total:
            raise ModelRuntimeError("weight byte total mismatch")
        if total > MAX_WEIGHT_BYTES:
            raise ModelRuntimeError("aggregate weight bytes out of bounds")

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "model_identity_digest": self.model_identity_digest,
                "shards": [shard.__dict__ for shard in self.shards],
                "expected_total_bytes": self.expected_total_bytes,
            }
        )


@dataclass(frozen=True)
class DeviceDescriptor:
    device_id: str
    kind: str
    memory_bytes: int
    available: bool = True

    def __post_init__(self) -> None:
        require_id(self.device_id, "device_id")
        if self.kind not in {"cpu", "cuda", "rocm", "metal", "xpu", "npu", "other"}:
            raise ModelRuntimeError("invalid device kind")
        if not _is_int(self.memory_bytes) or self.memory_bytes <= 0:
            raise ModelRuntimeError("invalid device memory")
        if not isinstance(self.available, bool):
            raise ModelRuntimeError("available must be boolean")


@dataclass(frozen=True)
class Placement:
    shard_index: int
    device_id: str
    bytes: int

    def __post_init__(self) -> None:
        if not _is_int(self.shard_index) or self.shard_index < 0:
            raise ModelRuntimeError("invalid placement shard index")
        require_id(self.device_id, "device_id")
        if not _is_int(self.bytes) or self.bytes <= 0:
            raise ModelRuntimeError("invalid placement bytes")


def plan_device_placement(
    shards: Sequence[WeightShard],
    devices: Sequence[DeviceDescriptor],
    *,
    reserve_bytes_per_device: int = 0,
) -> tuple[Placement, ...]:
    if not devices or len(devices) > MAX_DEVICES:
        raise ModelRuntimeError("device set out of bounds")
    if not _is_int(reserve_bytes_per_device) or reserve_bytes_per_device < 0:
        raise ModelRuntimeError("invalid device reserve")
    ids = [device.device_id for device in devices]
    if len(set(ids)) != len(ids):
        raise ModelRuntimeError("duplicate device id")
    remaining = {
        device.device_id: max(0, device.memory_bytes - reserve_bytes_per_device)
        for device in devices
        if device.available
    }
    if not remaining:
        raise ModelRuntimeError("no available devices")
    placements: list[Placement] = []
    ordered_devices = {device.device_id: device for device in devices if device.available}
    for index, shard in enumerate(shards):
        if not isinstance(shard, WeightShard) or shard.index != index:
            raise ModelRuntimeError("weight shard sequence drift")
        choices = [
            ordered_devices[device_id]
            for device_id, capacity in remaining.items()
            if capacity >= shard.bytes
        ]
        if not choices:
            raise ModelRuntimeError(f"insufficient device memory for shard {index}")
        chosen = sorted(
            choices,
            key=lambda device: (-remaining[device.device_id], device.device_id),
        )[0]
        remaining[chosen.device_id] -= shard.bytes
        placements.append(Placement(index, chosen.device_id, shard.bytes))
    return tuple(placements)


@dataclass(frozen=True)
class KVCacheEntry:
    request_id: str
    bytes: int
    last_used_sequence: int
    pinned: bool = False

    def __post_init__(self) -> None:
        require_id(self.request_id, "request_id")
        if not _is_int(self.bytes) or self.bytes <= 0:
            raise ModelRuntimeError("invalid KV cache bytes")
        if not _is_int(self.last_used_sequence) or self.last_used_sequence < 0:
            raise ModelRuntimeError("invalid KV cache sequence")
        if not isinstance(self.pinned, bool):
            raise ModelRuntimeError("pinned must be boolean")


def plan_kv_admission(
    entries: Sequence[KVCacheEntry],
    incoming: KVCacheEntry,
    *,
    capacity_bytes: int,
) -> tuple[tuple[str, ...], bool]:
    if not isinstance(incoming, KVCacheEntry):
        raise ModelRuntimeError("KVCacheEntry required")
    if not _is_int(capacity_bytes) or capacity_bytes <= 0:
        raise ModelRuntimeError("invalid KV capacity")
    if incoming.bytes > capacity_bytes:
        raise ModelRuntimeError("incoming KV entry exceeds total capacity")
    ids = [entry.request_id for entry in entries]
    if incoming.request_id in ids or len(set(ids)) != len(ids):
        raise ModelRuntimeError("duplicate KV request identity")
    total = sum(entry.bytes for entry in entries) + incoming.bytes
    if total <= capacity_bytes:
        return (), True
    candidates = sorted(
        (entry for entry in entries if not entry.pinned),
        key=lambda item: (item.last_used_sequence, item.request_id),
    )
    evicted: list[str] = []
    for entry in candidates:
        total -= entry.bytes
        evicted.append(entry.request_id)
        if total <= capacity_bytes:
            return tuple(evicted), True
    return tuple(evicted), False


@dataclass(frozen=True)
class BatchRequest:
    request_id: str
    prompt_tokens: int
    max_new_tokens: int
    priority: int = 0

    def __post_init__(self) -> None:
        require_id(self.request_id, "request_id")
        if not _is_int(self.prompt_tokens) or not 0 <= self.prompt_tokens <= MAX_TOKENS:
            raise ModelRuntimeError("invalid prompt_tokens")
        if not _is_int(self.max_new_tokens) or not 0 <= self.max_new_tokens <= MAX_TOKENS:
            raise ModelRuntimeError("invalid max_new_tokens")
        if self.prompt_tokens + self.max_new_tokens <= 0:
            raise ModelRuntimeError("empty batch request")
        if not _is_int(self.priority) or not -1_000_000 <= self.priority <= 1_000_000:
            raise ModelRuntimeError("invalid priority")


def plan_continuous_batches(
    requests: Sequence[BatchRequest],
    *,
    max_batch_size: int,
    max_tokens_per_batch: int,
) -> tuple[tuple[str, ...], ...]:
    if not _is_int(max_batch_size) or not 1 <= max_batch_size <= MAX_BATCH_SIZE:
        raise ModelRuntimeError("invalid max_batch_size")
    if not _is_int(max_tokens_per_batch) or not 1 <= max_tokens_per_batch <= MAX_TOKENS:
        raise ModelRuntimeError("invalid max_tokens_per_batch")
    ids = [request.request_id for request in requests]
    if len(set(ids)) != len(ids):
        raise ModelRuntimeError("duplicate batch request")
    ordered = sorted(requests, key=lambda item: (-item.priority, item.request_id))
    batches: list[tuple[str, ...]] = []
    current: list[str] = []
    current_tokens = 0
    for request in ordered:
        demand = request.prompt_tokens + request.max_new_tokens
        if demand > max_tokens_per_batch:
            raise ModelRuntimeError(f"request {request.request_id} exceeds batch token budget")
        if current and (
            len(current) >= max_batch_size
            or current_tokens + demand > max_tokens_per_batch
        ):
            batches.append(tuple(current))
            current = []
            current_tokens = 0
        current.append(request.request_id)
        current_tokens += demand
    if current:
        batches.append(tuple(current))
    return tuple(batches)


@dataclass(frozen=True)
class QuantizationProfile:
    scheme: str
    bits: int
    group_size: int | None
    calibration_digest: str | None = None

    def __post_init__(self) -> None:
        if self.scheme not in {"none", "int8", "int4", "nf4", "fp8"}:
            raise ModelRuntimeError("invalid quantization scheme")
        if not _is_int(self.bits) or self.bits not in {4, 8, 16, 32}:
            raise ModelRuntimeError("invalid quantization bits")
        expected_bits = {"int8": 8, "int4": 4, "nf4": 4, "fp8": 8}
        if self.scheme in expected_bits and self.bits != expected_bits[self.scheme]:
            raise ModelRuntimeError("quantization scheme/bit mismatch")
        if self.scheme == "none" and self.bits not in {16, 32}:
            raise ModelRuntimeError("unquantized precision must be 16 or 32 bits")
        if self.group_size is not None:
            if not _is_int(self.group_size) or self.group_size <= 0 or self.group_size > 1_000_000:
                raise ModelRuntimeError("invalid quantization group_size")
        if self.scheme in {"int4", "nf4"} and self.group_size is None:
            raise ModelRuntimeError("grouped low-bit quantization requires group_size")
        if self.calibration_digest is not None:
            require_digest(self.calibration_digest, "calibration_digest")


@dataclass(frozen=True)
class SpeculativeReceipt:
    request_id: str
    draft_model_digest: str
    target_model_digest: str
    proposed_tokens: tuple[int, ...]
    accepted_prefix: int

    def __post_init__(self) -> None:
        require_id(self.request_id, "request_id")
        require_digest(self.draft_model_digest, "draft_model_digest")
        require_digest(self.target_model_digest, "target_model_digest")
        if len(self.proposed_tokens) > MAX_TOKENS:
            raise ModelRuntimeError("speculative token proposal exceeds budget")
        for token in self.proposed_tokens:
            if not _is_int(token) or not 0 <= token <= MAX_TOKEN_ID:
                raise ModelRuntimeError("invalid speculative token")
        if not _is_int(self.accepted_prefix) or not 0 <= self.accepted_prefix <= len(self.proposed_tokens):
            raise ModelRuntimeError("invalid accepted prefix")

    @property
    def accepted_tokens(self) -> tuple[int, ...]:
        return self.proposed_tokens[: self.accepted_prefix]

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "request_id": self.request_id,
                "draft_model_digest": self.draft_model_digest,
                "target_model_digest": self.target_model_digest,
                "proposed_tokens": list(self.proposed_tokens),
                "accepted_prefix": self.accepted_prefix,
            }
        )


@dataclass(frozen=True)
class Replica:
    replica_id: str
    model_identity_digest: str
    endpoint_digest: str
    healthy: bool
    inflight: int = 0

    def __post_init__(self) -> None:
        require_id(self.replica_id, "replica_id")
        require_digest(self.model_identity_digest, "model_identity_digest")
        require_digest(self.endpoint_digest, "endpoint_digest")
        if not isinstance(self.healthy, bool):
            raise ModelRuntimeError("healthy must be boolean")
        if not _is_int(self.inflight) or self.inflight < 0:
            raise ModelRuntimeError("invalid inflight count")


def route_request(
    request_id: str,
    model_identity_digest: str,
    replicas: Sequence[Replica],
) -> Replica:
    require_id(request_id, "request_id")
    require_digest(model_identity_digest, "model_identity_digest")
    if not replicas or len(replicas) > MAX_REPLICAS:
        raise ModelRuntimeError("replica set out of bounds")
    ids = [replica.replica_id for replica in replicas]
    if len(set(ids)) != len(ids):
        raise ModelRuntimeError("duplicate replica id")
    eligible = [
        replica
        for replica in replicas
        if replica.healthy and replica.model_identity_digest == model_identity_digest
    ]
    if not eligible:
        raise ModelRuntimeError("no healthy replica for model")
    min_inflight = min(replica.inflight for replica in eligible)
    tier = sorted(
        (replica for replica in eligible if replica.inflight == min_inflight),
        key=lambda item: item.replica_id,
    )
    offset = int(sha256(request_id.encode("utf-8")).hexdigest(), 16) % len(tier)
    return tier[offset]


@dataclass(frozen=True)
class LocalModelRequest:
    operation_id: str
    model_identity_digest: str
    input_digest: str
    max_output_tokens: int
    deadline_ms: int
    authority_scope: str = "inference-only"

    def __post_init__(self) -> None:
        require_id(self.operation_id, "operation_id")
        require_digest(self.model_identity_digest, "model_identity_digest")
        require_digest(self.input_digest, "input_digest")
        if not _is_int(self.max_output_tokens) or not 1 <= self.max_output_tokens <= MAX_TOKENS:
            raise ModelRuntimeError("invalid max_output_tokens")
        if not _is_int(self.deadline_ms) or not 1 <= self.deadline_ms <= 86_400_000:
            raise ModelRuntimeError("invalid deadline_ms")
        if self.authority_scope != "inference-only":
            raise ModelRuntimeError("local model bridge cannot grant execution authority")


@dataclass(frozen=True)
class LocalModelReceipt:
    operation_id: str
    model_identity_digest: str
    terminal_reason: str
    output_digest: str | None
    usage_digest: str

    def __post_init__(self) -> None:
        require_id(self.operation_id, "operation_id")
        require_digest(self.model_identity_digest, "model_identity_digest")
        require_digest(self.usage_digest, "usage_digest")
        if self.terminal_reason not in {"completed", "cancelled", "deadline", "model_error", "policy_denied"}:
            raise ModelRuntimeError("invalid terminal_reason")
        if self.terminal_reason == "completed":
            if self.output_digest is None:
                raise ModelRuntimeError("completed local-model receipt requires output")
            require_digest(self.output_digest, "output_digest")
        elif self.output_digest is not None:
            raise ModelRuntimeError("failed local-model receipt cannot publish output")


ALLOWED_TRANSITIONS = MappingProxyType(
    {
        "registered": frozenset({"loading", "retired"}),
        "loading": frozenset({"ready", "failed"}),
        "ready": frozenset({"draining", "failed"}),
        "draining": frozenset({"stopped", "failed"}),
        "stopped": frozenset({"loading", "retired"}),
        "failed": frozenset({"loading", "retired"}),
        "retired": frozenset(),
    }
)


@dataclass(frozen=True)
class ModelLifecycle:
    model_identity_digest: str
    state: str = "registered"
    generation: int = 0

    def __post_init__(self) -> None:
        require_digest(self.model_identity_digest, "model_identity_digest")
        if self.state not in ALLOWED_TRANSITIONS:
            raise ModelRuntimeError("invalid lifecycle state")
        if not _is_int(self.generation) or not 0 <= self.generation <= MAX_GENERATION:
            raise ModelRuntimeError("invalid lifecycle generation")

    def transition(self, new_state: str) -> "ModelLifecycle":
        if new_state not in ALLOWED_TRANSITIONS[self.state]:
            raise ModelRuntimeError(f"invalid lifecycle transition {self.state}->{new_state}")
        generation = self.generation + (1 if new_state == "loading" else 0)
        if generation > MAX_GENERATION:
            raise ModelRuntimeError("lifecycle generation exhausted")
        return ModelLifecycle(self.model_identity_digest, new_state, generation)

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)
