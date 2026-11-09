"""Packet schema, canonical serialization, and validation for replication.

Authoritative snapshots, ordered deltas, acknowledgements, schema compatibility,
prediction reconciliation, and rollback evidence are defined here as pure data
and in-memory session rules. Callers supply ticks and packets explicitly. This
module does not import sockets, start servers, perform matchmaking, or bind an
engine adapter.

Deterministic serialization uses canonical JSON (sorted keys, tight separators,
finite numbers only). Sequence numbers are strictly monotonic on the producer.
History and reorder buffers are bounded; stale, duplicate, and out-of-order
deltas return typed outcomes. Incompatible schema, checksum mismatch, and
rollback past retained history fail closed.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from skeleton.kernel.errors import KernelError

SCHEMA_VERSION = 1
MAX_HISTORY = 64
MAX_REORDER_WINDOW = 16
MAX_ENTITIES = 256
MAX_FIELDS = 32
MAX_PATCHES = 64
MAX_TOKEN_CHARS = 64
MAX_STRING_CHARS = 256
MAX_LIST_ITEMS = 64
MAX_PEER_ID_CHARS = 64
MAX_MISSING_REPORT = 16
MAX_PACKET_BYTES = 262_144
MAX_CHANNEL_PACKETS = 256
MAX_CANONICAL_DEPTH = 16

_PACKET_KEYS = ("kind", "schema_version", "sequence", "payload", "checksum")
_SNAPSHOT_KEYS = ("tick", "entities", "digest", "state_digest")
_DELTA_KEYS = (
    "base_sequence",
    "base_digest",
    "tick",
    "patches",
    "resulting_digest",
    "resulting_state_digest",
)
_ACK_KEYS = (
    "peer_id",
    "last_applied_sequence",
    "last_applied_digest",
    "last_received_sequence",
    "tick",
    "missing_sequences",
)


class ReplicationError(KernelError):
    code = "NET.REPLICATION"
    http_status = 400


class SchemaCompatibilityError(ReplicationError):
    code = "NET.SCHEMA_INCOMPATIBLE"
    http_status = 422


class HistoryExhaustedError(ReplicationError):
    code = "NET.HISTORY_EXHAUSTED"
    http_status = 409


class SequenceError(ReplicationError):
    code = "NET.SEQUENCE"
    http_status = 409


class SerializationError(ReplicationError):
    code = "NET.SERIALIZATION"
    http_status = 400


class PatchOp(str, Enum):
    SET = "set"
    REPLACE = "replace"
    DELETE = "delete"


class DeliveryOutcome(str, Enum):
    APPLIED = "applied"
    INITIALIZED = "initialized"
    STALE = "stale"
    DUPLICATE = "duplicate"
    BUFFERED = "buffered"
    REJECTED_GAP = "rejected_gap"


@dataclass(frozen=True, slots=True)
class Patch:
    entity_id: str
    op: PatchOp
    fields: tuple[tuple[str, Any], ...] = ()

    @classmethod
    def set(cls, entity_id: str, fields: Mapping[str, Any]) -> "Patch":
        return cls(_bounded_token("entity_id", entity_id), PatchOp.SET, _frozen_fields(fields))

    @classmethod
    def replace(cls, entity_id: str, fields: Mapping[str, Any]) -> "Patch":
        return cls(_bounded_token("entity_id", entity_id), PatchOp.REPLACE, _frozen_fields(fields))

    @classmethod
    def delete(cls, entity_id: str) -> "Patch":
        return cls(_bounded_token("entity_id", entity_id), PatchOp.DELETE, ())

    def to_payload(self) -> dict[str, Any]:
        fields = _validated_patch_fields(self)
        return {
            "entity_id": _bounded_token("entity_id", self.entity_id),
            "op": self.op.value,
            "fields": fields,
        }


@dataclass(frozen=True, slots=True)
class Packet:
    kind: str
    schema_version: int
    sequence: int
    payload: dict[str, Any]
    checksum: str

    def encode(self) -> bytes:
        _validate_packet_envelope(self)
        expected = _packet_checksum(self.kind, self.schema_version, self.sequence, self.payload)
        if self.checksum != expected:
            raise ReplicationError(
                "packet checksum mismatch",
                context={"sequence": self.sequence, "kind": self.kind},
            )
        return canonical_dumps(
            {
                "kind": self.kind,
                "schema_version": self.schema_version,
                "sequence": self.sequence,
                "payload": self.payload,
                "checksum": self.checksum,
            }
        ).encode("utf-8")

    @classmethod
    def decode(cls, raw: bytes) -> "Packet":
        return decode_packet(raw)


@dataclass(frozen=True, slots=True)
class Ack:
    peer_id: str
    last_applied_sequence: int
    last_applied_digest: str
    last_received_sequence: int
    tick: int
    missing_sequences: tuple[int, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "peer_id": self.peer_id,
            "last_applied_sequence": self.last_applied_sequence,
            "last_applied_digest": self.last_applied_digest,
            "last_received_sequence": self.last_received_sequence,
            "tick": self.tick,
            "missing_sequences": list(self.missing_sequences),
        }


@dataclass(frozen=True, slots=True)
class IngestResult:
    outcome: DeliveryOutcome
    sequence: int
    applied_sequences: tuple[int, ...]
    digest: str | None
    ack: Ack | None
    diagnostics: str
    reconciliation: "ReconciliationEvidence | None" = None


@dataclass(frozen=True, slots=True)
class RollbackEvidence:
    from_sequence: int
    to_sequence: int
    from_digest: str
    to_digest: str
    replayed_sequences: tuple[int, ...]
    reproduced: bool


@dataclass(frozen=True, slots=True)
class ReconciliationEvidence:
    tick: int
    sequence: int
    predicted_digest: str
    confirmed_digest: str
    divergent: bool
    rolled_back: bool
    resimulated_ticks: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _HistoryFrame:
    sequence: int
    tick: int
    kind: str
    digest: str
    state_digest: str
    entities: dict[str, Any]
    patches: tuple[Patch, ...]
    snapshot_entities: dict[str, Any] | None
    packet: Packet | None


@dataclass(frozen=True, slots=True)
class _Prediction:
    tick: int
    patches: tuple[Patch, ...]
    digest: str


def canonical_dumps(value: Any) -> str:
    """Return canonical JSON for a value, failing closed on non-canonical input."""
    return json.dumps(
        _canonicalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def state_digest(entities: Mapping[str, Any]) -> str:
    return _sha256(canonical_dumps({"entities": _canonicalize_entities(entities)}))


def frame_digest(
    *,
    schema_version: int,
    sequence: int,
    tick: int,
    entities: Mapping[str, Any],
) -> str:
    schema_version = _require_int("schema_version", schema_version, minimum=1)
    sequence = _require_int("sequence", sequence, minimum=0)
    tick = _require_int("tick", tick, minimum=0)
    return _sha256(
        canonical_dumps(
            {
                "entities": _canonicalize_entities(entities),
                "schema_version": schema_version,
                "sequence": sequence,
                "tick": tick,
            }
        )
    )


def decode_packet(raw: bytes) -> Packet:
    if not isinstance(raw, (bytes, bytearray)):
        raise SerializationError("packet must be bytes")
    if len(raw) > MAX_PACKET_BYTES:
        raise SerializationError(
            "packet exceeds byte bound",
            context={"max_bytes": MAX_PACKET_BYTES, "actual": len(raw)},
        )
    try:
        data = json.loads(
            bytes(raw).decode("utf-8"),
            object_pairs_hook=_json_object_no_duplicates,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SerializationError("malformed packet") from exc
    if not isinstance(data, dict):
        raise SerializationError("packet must be an object")
    _require_exact_keys(data, _PACKET_KEYS, "packet")
    kind = data["kind"]
    if not isinstance(kind, str) or kind not in {"snapshot", "delta", "ack"}:
        raise SerializationError("unknown packet kind", context={"kind": kind})
    schema_version = _require_int("schema_version", data["schema_version"], minimum=1)
    if schema_version != SCHEMA_VERSION:
        raise SchemaCompatibilityError(
            "incompatible replication schema",
            context={"schema_version": schema_version, "supported": SCHEMA_VERSION},
        )
    sequence = _require_int("sequence", data["sequence"], minimum=0)
    payload = data["payload"]
    if not isinstance(payload, dict):
        raise SerializationError("payload must be an object")
    checksum = _require_digest(data["checksum"])
    expected = _packet_checksum(kind, schema_version, sequence, payload)
    if checksum != expected:
        raise ReplicationError(
            "packet checksum mismatch",
            context={"sequence": sequence, "kind": kind},
        )
    return Packet(
        kind=kind,
        schema_version=schema_version,
        sequence=sequence,
        payload=_clone(payload),
        checksum=checksum,
    )


def apply_patches(entities: Mapping[str, Any], patches: Sequence[Patch]) -> dict[str, Any]:
    working = _canonicalize_entities(entities)
    if len(patches) > MAX_PATCHES:
        raise ReplicationError("delta exceeds patch bound", context={"max_patches": MAX_PATCHES})
    for patch in patches:
        if not isinstance(patch, Patch):
            raise SerializationError("patches must be Patch values")
        entity_id = _bounded_token("entity_id", patch.entity_id)
        fields = _validated_patch_fields(patch)
        if patch.op is PatchOp.DELETE:
            if fields:
                raise ReplicationError("delete patches must not carry fields")
            if entity_id not in working:
                raise ReplicationError(
                    "delete targeted a missing entity",
                    context={"entity_id": entity_id},
                )
            del working[entity_id]
            continue
        if not fields and patch.op is PatchOp.SET:
            raise ReplicationError("set patches must include fields")
        if len(fields) > MAX_FIELDS:
            raise ReplicationError(
                "entity exceeds field bound",
                context={"entity_id": entity_id, "max_fields": MAX_FIELDS},
            )
        if patch.op is PatchOp.REPLACE:
            working[entity_id] = fields
        elif patch.op is PatchOp.SET:
            current = dict(working.get(entity_id, {}))
            current.update(fields)
            if len(current) > MAX_FIELDS:
                raise ReplicationError(
                    "entity exceeds field bound",
                    context={"entity_id": entity_id, "max_fields": MAX_FIELDS},
                )
            working[entity_id] = current
        else:
            raise ReplicationError("unknown patch op", context={"op": patch.op})
        if len(working) > MAX_ENTITIES:
            raise ReplicationError(
                "state exceeds entity bound",
                context={"max_entities": MAX_ENTITIES},
            )
    return working


def _reconcile_predictions(
    predictions: list[_Prediction] | None,
    *,
    tick: int,
    sequence: int,
    confirmed_entities: Mapping[str, Any],
) -> ReconciliationEvidence | None:
    if not predictions:
        return None
    confirmed_digest = state_digest(confirmed_entities)
    due = [prediction for prediction in predictions if prediction.tick <= tick]
    if not due:
        return None
    predicted_digest = due[-1].digest
    divergent = predicted_digest != confirmed_digest
    remaining = tuple(prediction.tick for prediction in predictions if prediction.tick > tick)
    return ReconciliationEvidence(
        tick=tick,
        sequence=sequence,
        predicted_digest=predicted_digest,
        confirmed_digest=confirmed_digest,
        divergent=divergent,
        rolled_back=divergent,
        resimulated_ticks=remaining,
    )


def _json_object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SerializationError(
                "JSON object contains duplicate keys",
                context={"key": key},
            )
        result[key] = value
    return result


def _validate_delta_payload_shape(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise SerializationError("delta payload must be an object")
    _require_exact_keys(payload, _DELTA_KEYS, "delta")
    _require_int("base_sequence", payload["base_sequence"], minimum=0)
    _require_digest(payload["base_digest"])
    _require_int("tick", payload["tick"], minimum=0)
    _decode_patches(payload["patches"])
    _require_digest(payload["resulting_digest"])
    _require_digest(payload["resulting_state_digest"])


def _validated_patch_fields(patch: Patch) -> dict[str, Any]:
    if not isinstance(patch.op, PatchOp):
        raise SerializationError(
            "patch op must be a PatchOp",
            context={"op": repr(patch.op)},
        )
    if not isinstance(patch.fields, tuple):
        raise SerializationError("patch fields must be a tuple")
    if len(patch.fields) > MAX_FIELDS:
        raise ReplicationError(
            "patch fields exceed field bound",
            context={"max_fields": MAX_FIELDS},
        )
    fields: dict[str, Any] = {}
    for entry in patch.fields:
        if not isinstance(entry, tuple) or len(entry) != 2:
            raise SerializationError("patch field entry must be a (name, value) pair")
        key, value = entry
        token = _bounded_token("field", key)
        if token in fields:
            raise SerializationError(
                "patch contains duplicate field names",
                context={"field": token},
            )
        fields[token] = _canonicalize(value)
    return fields


def _wrap_packet(kind: str, sequence: int, payload: Mapping[str, Any]) -> Packet:
    encoded = _encode_packet(kind, SCHEMA_VERSION, sequence, payload)
    return decode_packet(encoded)


def _encode_packet(kind: str, schema_version: int, sequence: int, payload: Mapping[str, Any]) -> bytes:
    checksum = _packet_checksum(kind, schema_version, sequence, payload)
    body = {
        "kind": kind,
        "schema_version": schema_version,
        "sequence": sequence,
        "payload": payload,
        "checksum": checksum,
    }
    return canonical_dumps(body).encode("utf-8")


def _packet_checksum(kind: str, schema_version: int, sequence: int, payload: Mapping[str, Any]) -> str:
    return _sha256(
        canonical_dumps(
            {
                "kind": kind,
                "payload": payload,
                "schema_version": schema_version,
                "sequence": sequence,
            }
        )
    )


def _ack_from_payload(payload: Mapping[str, Any]) -> Ack:
    if not isinstance(payload, Mapping):
        raise SerializationError("ack payload must be an object")
    data = dict(payload)
    _require_exact_keys(data, _ACK_KEYS, "ack")
    missing = data["missing_sequences"]
    if not isinstance(missing, list) or any(
        isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in missing
    ):
        raise SerializationError("missing_sequences must be a list of non-negative integers")
    if len(missing) > MAX_MISSING_REPORT:
        raise ReplicationError("ack missing_sequences exceeds bound")
    if missing != sorted(missing) or len(set(missing)) != len(missing):
        raise SerializationError("missing_sequences must be sorted and unique")
    last_applied = _require_int(
        "last_applied_sequence", data["last_applied_sequence"], minimum=0
    )
    last_received = _require_int(
        "last_received_sequence", data["last_received_sequence"], minimum=0
    )
    if last_received < last_applied:
        raise SequenceError(
            "last_received_sequence cannot precede last_applied_sequence",
            context={"last_applied": last_applied, "last_received": last_received},
        )
    if any(item <= last_applied or item > last_received for item in missing):
        raise SequenceError(
            "missing_sequences must fall strictly after applied and at or before received",
            context={"last_applied": last_applied, "last_received": last_received},
        )
    if last_received > last_applied and (
        not missing or missing[0] != last_applied + 1
    ):
        raise SequenceError(
            "missing_sequences must begin with the next unapplied sequence",
            context={
                "last_applied": last_applied,
                "last_received": last_received,
                "first_missing": missing[0] if missing else None,
            },
        )
    return Ack(
        peer_id=_bounded_token("peer_id", data["peer_id"], maximum=MAX_PEER_ID_CHARS),
        last_applied_sequence=last_applied,
        last_applied_digest=_require_digest(data["last_applied_digest"]),
        last_received_sequence=last_received,
        tick=_require_int("tick", data["tick"], minimum=0),
        missing_sequences=tuple(missing),
    )


def _decode_patches(raw: Any) -> tuple[Patch, ...]:
    if not isinstance(raw, list):
        raise SerializationError("patches must be a list")
    if len(raw) > MAX_PATCHES:
        raise ReplicationError("delta exceeds patch bound", context={"max_patches": MAX_PATCHES})
    patches: list[Patch] = []
    for item in raw:
        if not isinstance(item, dict):
            raise SerializationError("patch must be an object")
        _require_exact_keys(item, ("entity_id", "op", "fields"), "patch")
        try:
            op = PatchOp(item["op"])
        except (TypeError, ValueError) as exc:
            raise ReplicationError("unknown patch op", context={"op": item["op"]}) from exc
        fields = item["fields"]
        if not isinstance(fields, dict):
            raise SerializationError("patch fields must be an object")
        if op is PatchOp.DELETE:
            patches.append(Patch.delete(item["entity_id"]))
            if fields:
                raise ReplicationError("delete patches must not carry fields")
        elif op is PatchOp.REPLACE:
            patches.append(Patch.replace(item["entity_id"], fields))
        else:
            patches.append(Patch.set(item["entity_id"], fields))
    return tuple(patches)


def _canonicalize_entities(entities: Mapping[str, Any] | None) -> dict[str, Any]:
    if entities is None:
        return {}
    if not isinstance(entities, Mapping):
        raise SerializationError("entities must be an object")
    if len(entities) > MAX_ENTITIES:
        raise ReplicationError(
            "state exceeds entity bound",
            context={"max_entities": MAX_ENTITIES},
        )
    canonical: dict[str, Any] = {}
    for entity_id, fields in entities.items():
        token = _bounded_token("entity_id", entity_id)
        if not isinstance(fields, Mapping):
            raise SerializationError(
                "entity fields must be an object",
                context={"entity_id": token},
            )
        if len(fields) > MAX_FIELDS:
            raise ReplicationError(
                "entity exceeds field bound",
                context={"entity_id": token, "max_fields": MAX_FIELDS},
            )
        canonical_fields: dict[str, Any] = {}
        for key, value in fields.items():
            if not isinstance(key, str):
                raise SerializationError(
                    "entity field names must be strings",
                    context={"entity_id": token},
                )
            _bounded_token("field", key)
            canonical_fields[key] = _canonicalize(value)
        canonical[token] = canonical_fields
    return canonical


def _canonicalize(value: Any, *, depth: int = 0) -> Any:
    if depth > MAX_CANONICAL_DEPTH:
        raise SerializationError(
            "canonical value exceeds nesting bound",
            context={"max_depth": MAX_CANONICAL_DEPTH},
        )
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SerializationError("non-finite numbers are not canonical")
        return value
    if isinstance(value, str):
        if len(value) > MAX_STRING_CHARS:
            raise SerializationError(
                "string exceeds bound",
                context={"max_chars": MAX_STRING_CHARS},
            )
        return value
    if isinstance(value, list):
        if len(value) > MAX_LIST_ITEMS:
            raise SerializationError(
                "list exceeds bound",
                context={"max_items": MAX_LIST_ITEMS},
            )
        return [_canonicalize(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > MAX_FIELDS:
            raise SerializationError(
                "object exceeds field bound",
                context={"max_fields": MAX_FIELDS},
            )
        canonical: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise SerializationError("object keys must be strings")
            _bounded_token("key", key)
            canonical[key] = _canonicalize(item, depth=depth + 1)
        return canonical
    raise SerializationError(
        "non-canonical value type",
        context={"type": type(value).__name__},
    )


def _frozen_fields(fields: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    if not isinstance(fields, Mapping):
        raise SerializationError("patch fields must be an object")
    if len(fields) > MAX_FIELDS:
        raise ReplicationError(
            "patch fields exceed field bound",
            context={"max_fields": MAX_FIELDS},
        )
    canonical: dict[str, Any] = {}
    for key, value in fields.items():
        if not isinstance(key, str):
            raise SerializationError("object keys must be strings")
        _bounded_token("field", key)
        canonical[key] = _canonicalize(value)
    return tuple(sorted(canonical.items(), key=lambda item: item[0]))


def _clone(value: Any) -> Any:
    return json.loads(canonical_dumps(value))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bounded_token(name: str, value: Any, *, maximum: int = MAX_TOKEN_CHARS) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SerializationError(f"{name} must be a non-empty trimmed string")
    token = value
    if any(ord(char) < 32 for char in token):
        raise SerializationError(f"{name} contains control characters")
    if len(token) > maximum:
        raise SerializationError(
            f"{name} exceeds bound",
            context={"max_chars": maximum},
        )
    return token


def _require_int(name: str, value: Any, *, minimum: int, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SerializationError(f"{name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise ReplicationError(
            f"{name} is outside the accepted range",
            context={"minimum": minimum, "maximum": maximum, "value": value},
        )
    return value


def _require_digest(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise SerializationError("digest must be a 64-character lowercase hex digest")
    return value


def _validate_packet_envelope(packet: Packet) -> None:
    if not isinstance(packet.kind, str) or packet.kind not in {"snapshot", "delta", "ack"}:
        raise SerializationError("unknown packet kind", context={"kind": packet.kind})
    schema_version = _require_int("schema_version", packet.schema_version, minimum=1)
    if schema_version != SCHEMA_VERSION:
        raise SchemaCompatibilityError(
            "incompatible replication schema",
            context={"schema_version": schema_version, "supported": SCHEMA_VERSION},
        )
    _require_int("sequence", packet.sequence, minimum=0)
    if not isinstance(packet.payload, dict):
        raise SerializationError("payload must be an object")
    _require_digest(packet.checksum)


def _require_exact_keys(data: Mapping[str, Any], keys: Iterable[str], label: str) -> None:
    expected = tuple(keys)
    actual = tuple(data.keys())
    if set(actual) != set(expected):
        raise SerializationError(
            f"{label} keys are not exact",
            context={"expected": list(expected), "actual": sorted(actual)},
        )
