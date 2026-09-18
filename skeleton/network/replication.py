"""Engine-neutral replication and rollback contract.

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


class OfflineChannel:
    """In-memory packet pipe. Delivery order is explicit; no sockets are used."""

    def __init__(self) -> None:
        self._queue: list[bytes] = []

    def __len__(self) -> int:
        return len(self._queue)

    def submit(self, packet: Packet) -> None:
        if not isinstance(packet, Packet):
            raise SerializationError("channel submit requires a Packet")
        if len(self._queue) >= MAX_CHANNEL_PACKETS:
            raise ReplicationError(
                "offline channel exceeds packet bound",
                context={"max_packets": MAX_CHANNEL_PACKETS},
            )
        self._queue.append(packet.encode())

    def drop_index(self, index: int) -> bytes:
        index = _require_int("index", index, minimum=0)
        if index >= len(self._queue):
            raise ReplicationError("drop index out of range", context={"index": index})
        return self._queue.pop(index)

    def duplicate_index(self, index: int) -> None:
        index = _require_int("index", index, minimum=0)
        if index >= len(self._queue):
            raise ReplicationError("duplicate index out of range", context={"index": index})
        if len(self._queue) >= MAX_CHANNEL_PACKETS:
            raise ReplicationError(
                "offline channel exceeds packet bound",
                context={"max_packets": MAX_CHANNEL_PACKETS},
            )
        self._queue.insert(index + 1, self._queue[index])

    def reorder(self, permutation: Sequence[int]) -> None:
        if isinstance(permutation, (str, bytes, bytearray)) or not isinstance(
            permutation, Sequence
        ):
            raise SerializationError("reorder permutation must be a sequence of integers")
        if any(isinstance(item, bool) or not isinstance(item, int) for item in permutation):
            raise SerializationError("reorder permutation must contain integers")
        if sorted(permutation) != list(range(len(self._queue))):
            raise ReplicationError(
                "reorder permutation must list each queued index once",
                context={"length": len(self._queue)},
            )
        self._queue = [self._queue[index] for index in permutation]

    def pop(self) -> Packet | None:
        if not self._queue:
            return None
        return decode_packet(self._queue.pop(0))

    def drain(self) -> tuple[Packet, ...]:
        packets = tuple(decode_packet(raw) for raw in self._queue)
        self._queue.clear()
        return packets


class _ReplicationCore:
    def __init__(
        self,
        peer_id: str,
        *,
        history_limit: int = 32,
        reorder_window: int = 8,
    ) -> None:
        self.peer_id = _bounded_token("peer_id", peer_id, maximum=MAX_PEER_ID_CHARS)
        self.history_limit = _require_int("history_limit", history_limit, minimum=1, maximum=MAX_HISTORY)
        self.reorder_window = _require_int(
            "reorder_window", reorder_window, minimum=1, maximum=MAX_REORDER_WINDOW
        )
        self.schema_version = SCHEMA_VERSION
        self._entities: dict[str, Any] = {}
        self._sequence = 0
        self._tick = 0
        genesis_digest = frame_digest(
            schema_version=SCHEMA_VERSION,
            sequence=0,
            tick=0,
            entities={},
        )
        genesis = _HistoryFrame(
            sequence=0,
            tick=0,
            kind="snapshot",
            digest=genesis_digest,
            state_digest=state_digest({}),
            entities={},
            patches=(),
            snapshot_entities={},
            packet=None,
        )
        self._history: list[_HistoryFrame] = [genesis]
        self._buffer: dict[int, Packet] = {}
        self._last_received = 0

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def entities(self) -> dict[str, Any]:
        return _clone(self._entities)

    @property
    def digest(self) -> str:
        return frame_digest(
            schema_version=self.schema_version,
            sequence=self._sequence,
            tick=self._tick,
            entities=self._entities,
        )

    @property
    def payload_digest(self) -> str:
        return state_digest(self._entities)

    def missing_sequences(self) -> tuple[int, ...]:
        if not self._buffer:
            return ()
        highest = max(self._buffer)
        missing: list[int] = []
        for sequence in range(self._sequence + 1, highest + 1):
            if sequence not in self._buffer:
                missing.append(sequence)
            if len(missing) >= MAX_MISSING_REPORT:
                break
        return tuple(missing)

    def acknowledge(self) -> Packet:
        ack = Ack(
            peer_id=self.peer_id,
            last_applied_sequence=self._sequence,
            last_applied_digest=self.digest,
            last_received_sequence=max(self._last_received, self._sequence),
            tick=self._tick,
            missing_sequences=self.missing_sequences(),
        )
        return _wrap_packet("ack", ack.last_applied_sequence, ack.to_payload())

    def packet_for(self, sequence: int) -> Packet:
        frame = self._frame(sequence)
        if frame is None:
            raise HistoryExhaustedError(
                "requested sequence is outside retained history",
                context={"sequence": sequence, "retained": self._retained_sequences()},
            )
        if frame.packet is not None:
            return decode_packet(frame.packet.encode())
        if frame.kind == "snapshot":
            payload = {
                "tick": frame.tick,
                "entities": _clone(frame.snapshot_entities or {}),
                "digest": frame.digest,
                "state_digest": frame.state_digest,
            }
            return _wrap_packet("snapshot", frame.sequence, payload)
        raise HistoryExhaustedError(
            "delta packet is no longer retained",
            context={"sequence": sequence},
        )

    def rollback_to(self, sequence: int) -> RollbackEvidence:
        target = _require_int("sequence", sequence, minimum=0)
        from_sequence = self._sequence
        from_digest = self.digest
        if target > from_sequence:
            raise SequenceError(
                "cannot roll forward through rollback",
                context={"current": from_sequence, "requested": target},
            )
        recorded = self._frame(target)
        if recorded is None:
            raise HistoryExhaustedError(
                "rollback target is outside retained history",
                context={"requested": target, "retained": self._retained_sequences()},
            )
        snapshot = self._baseline_at_or_before(target)
        if snapshot is None:
            raise HistoryExhaustedError(
                "no retained frame remains from which to replay rollback",
                context={"requested": target, "retained": self._retained_sequences()},
            )
        entities = _clone(snapshot.snapshot_entities or {})
        tick = snapshot.tick
        replayed = [snapshot.sequence]
        cursor = snapshot.sequence
        for frame in self._history:
            if frame.sequence <= snapshot.sequence or frame.sequence > target:
                continue
            if frame.sequence != cursor + 1:
                raise HistoryExhaustedError(
                    "history gap prevents deterministic rollback replay",
                    context={"expected": cursor + 1, "found": frame.sequence},
                )
            if frame.kind == "snapshot":
                entities = _clone(frame.snapshot_entities or {})
            else:
                entities = apply_patches(entities, frame.patches)
            tick = frame.tick
            cursor = frame.sequence
            replayed.append(cursor)
        reproduced_digest = frame_digest(
            schema_version=self.schema_version,
            sequence=target,
            tick=tick,
            entities=entities,
        )
        if reproduced_digest != recorded.digest:
            raise ReplicationError(
                "rollback failed to reproduce recorded digest",
                context={
                    "requested": target,
                    "recorded": recorded.digest,
                    "reproduced": reproduced_digest,
                },
            )
        self._entities = entities
        self._sequence = target
        self._tick = tick
        self._history = [frame for frame in self._history if frame.sequence <= target]
        self._buffer = {
            seq: packet for seq, packet in self._buffer.items() if seq > target
        }
        self._last_received = max([self._sequence, *self._buffer], default=self._sequence)
        return RollbackEvidence(
            from_sequence=from_sequence,
            to_sequence=target,
            from_digest=from_digest,
            to_digest=reproduced_digest,
            replayed_sequences=tuple(replayed),
            reproduced=True,
        )

    def ingest(self, packet: Packet, *, predictions: list[_Prediction] | None = None) -> IngestResult:
        if not isinstance(packet, Packet):
            raise SerializationError("ingest requires a decoded Packet")
        _validate_packet_envelope(packet)
        if packet.schema_version != SCHEMA_VERSION:
            raise SchemaCompatibilityError(
                "incompatible replication schema",
                context={"schema_version": packet.schema_version, "supported": SCHEMA_VERSION},
            )
        expected_checksum = _packet_checksum(
            packet.kind, packet.schema_version, packet.sequence, packet.payload
        )
        if packet.checksum != expected_checksum:
            raise ReplicationError(
                "packet checksum mismatch",
                context={"sequence": packet.sequence, "kind": packet.kind},
            )
        if packet.kind == "ack":
            raise ReplicationError("replicas do not ingest acknowledgement packets as state")
        if packet.sequence in {frame.sequence for frame in self._history}:
            return self._result(
                DeliveryOutcome.DUPLICATE,
                packet.sequence,
                (),
                self.digest,
                "sequence already applied",
            )
        if packet.sequence < self._sequence:
            return self._result(
                DeliveryOutcome.STALE,
                packet.sequence,
                (),
                self.digest,
                "sequence is behind the confirmed head",
            )
        if packet.kind == "snapshot":
            result = self._ingest_snapshot(packet, predictions)
            self._last_received = max(self._last_received, packet.sequence)
            return result
        if packet.kind == "delta":
            _validate_delta_payload_shape(packet.payload)
            return self._ingest_delta(packet, predictions)
        raise SerializationError("unknown packet kind", context={"kind": packet.kind})

    def append_produced(
        self,
        *,
        kind: str,
        tick: int,
        entities: dict[str, Any],
        patches: tuple[Patch, ...] = (),
        snapshot_entities: dict[str, Any] | None = None,
        packet: Packet,
    ) -> _HistoryFrame:
        frame = _HistoryFrame(
            sequence=self._sequence,
            tick=tick,
            kind=kind,
            digest=frame_digest(
                schema_version=self.schema_version,
                sequence=self._sequence,
                tick=tick,
                entities=entities,
            ),
            state_digest=state_digest(entities),
            entities=_clone(entities),
            patches=patches,
            snapshot_entities=_clone(snapshot_entities) if snapshot_entities is not None else None,
            packet=packet,
        )
        self._entities = _clone(entities)
        self._tick = tick
        self._retain(frame)
        return frame

    def _ingest_snapshot(
        self, packet: Packet, predictions: list[_Prediction] | None
    ) -> IngestResult:
        payload = packet.payload
        _require_exact_keys(payload, _SNAPSHOT_KEYS, "snapshot")
        tick = _require_int("tick", payload["tick"], minimum=0)
        if tick < self._tick:
            raise SequenceError(
                "snapshot tick moved backwards",
                context={"current_tick": self._tick, "packet_tick": tick},
            )
        entities = _canonicalize_entities(payload["entities"])
        expected_digest = frame_digest(
            schema_version=packet.schema_version,
            sequence=packet.sequence,
            tick=tick,
            entities=entities,
        )
        expected_state = state_digest(entities)
        supplied_digest = _require_digest(payload["digest"])
        supplied_state = _require_digest(payload["state_digest"])
        if supplied_digest != expected_digest or supplied_state != expected_state:
            raise ReplicationError(
                "snapshot digest mismatch",
                context={"sequence": packet.sequence},
            )
        prior = self._capture_ingest_state()
        try:
            previous_sequence = self._sequence
            self._entities = entities
            self._sequence = packet.sequence
            self._tick = tick
            self._retain(
                _HistoryFrame(
                    sequence=packet.sequence,
                    tick=tick,
                    kind="snapshot",
                    digest=expected_digest,
                    state_digest=expected_state,
                    entities=_clone(entities),
                    patches=(),
                    snapshot_entities=_clone(entities),
                    packet=packet,
                )
            )
            self._drop_buffer_through(packet.sequence)
            applied = [packet.sequence]
            applied.extend(self._drain_buffer())
            outcome = (
                DeliveryOutcome.INITIALIZED if previous_sequence == 0 else DeliveryOutcome.APPLIED
            )
            reconciliation = _reconcile_predictions(
                predictions,
                tick=self._tick,
                sequence=self._sequence,
                confirmed_entities=self._entities,
            )
            return self._result(
                outcome,
                packet.sequence,
                tuple(applied),
                self.digest,
                "snapshot applied",
                reconciliation,
            )
        except BaseException:
            self._restore_ingest_state(prior)
            raise

    def _ingest_delta(
        self, packet: Packet, predictions: list[_Prediction] | None
    ) -> IngestResult:
        if packet.sequence == self._sequence + 1:
            prior = self._capture_ingest_state()
            try:
                applied = [packet.sequence]
                self._apply_delta_packet(packet)
                applied.extend(self._drain_buffer())
                reconciliation = _reconcile_predictions(
                    predictions,
                    tick=self._tick,
                    sequence=self._sequence,
                    confirmed_entities=self._entities,
                )
                return self._result(
                    DeliveryOutcome.APPLIED,
                    packet.sequence,
                    tuple(applied),
                    self.digest,
                    "delta applied",
                    reconciliation,
                )
            except BaseException:
                self._restore_ingest_state(prior)
                raise
        gap = packet.sequence - self._sequence - 1
        if gap <= 0:
            return self._result(
                DeliveryOutcome.STALE,
                packet.sequence,
                (),
                self.digest,
                "delta is not ahead of the confirmed head",
            )
        if packet.sequence in self._buffer:
            return self._result(
                DeliveryOutcome.DUPLICATE,
                packet.sequence,
                (),
                self.digest,
                "delta is already buffered",
            )
        if gap > self.reorder_window or len(self._buffer) >= self.reorder_window:
            return self._result(
                DeliveryOutcome.REJECTED_GAP,
                packet.sequence,
                (),
                self.digest,
                "delta exceeds the bounded reorder window",
            )
        self._buffer[packet.sequence] = packet
        self._last_received = max(self._last_received, packet.sequence)
        return self._result(
            DeliveryOutcome.BUFFERED,
            packet.sequence,
            (),
            self.digest,
            "delta buffered pending missing predecessors",
        )

    def _apply_delta_packet(self, packet: Packet) -> None:
        payload = packet.payload
        _require_exact_keys(payload, _DELTA_KEYS, "delta")
        tick = _require_int("tick", payload["tick"], minimum=0)
        if tick < self._tick:
            raise SequenceError(
                "delta tick moved backwards",
                context={"current_tick": self._tick, "packet_tick": tick},
            )
        base_sequence = _require_int("base_sequence", payload["base_sequence"], minimum=0)
        if base_sequence != self._sequence:
            raise SequenceError(
                "delta base sequence does not match confirmed head",
                context={"expected": self._sequence, "base_sequence": base_sequence},
            )
        base_digest = _require_digest(payload["base_digest"])
        if base_digest != self.digest:
            raise ReplicationError(
                "delta base digest does not match confirmed head",
                context={"sequence": packet.sequence},
            )
        patches = _decode_patches(payload["patches"])
        entities = apply_patches(self._entities, patches)
        next_sequence = packet.sequence
        expected_digest = frame_digest(
            schema_version=packet.schema_version,
            sequence=next_sequence,
            tick=tick,
            entities=entities,
        )
        expected_state = state_digest(entities)
        resulting_digest = _require_digest(payload["resulting_digest"])
        resulting_state_digest = _require_digest(payload["resulting_state_digest"])
        if resulting_digest != expected_digest:
            raise ReplicationError(
                "delta resulting digest mismatch",
                context={"sequence": next_sequence},
            )
        if resulting_state_digest != expected_state:
            raise ReplicationError(
                "delta resulting state digest mismatch",
                context={"sequence": next_sequence},
            )
        self._entities = entities
        self._sequence = next_sequence
        self._tick = tick
        self._retain(
            _HistoryFrame(
                sequence=next_sequence,
                tick=tick,
                kind="delta",
                digest=expected_digest,
                state_digest=expected_state,
                entities=_clone(entities),
                patches=patches,
                snapshot_entities=None,
                packet=packet,
            )
        )
        self._buffer.pop(next_sequence, None)

    def _drain_buffer(self) -> list[int]:
        applied: list[int] = []
        while self._sequence + 1 in self._buffer:
            next_sequence = self._sequence + 1
            packet = self._buffer[next_sequence]
            self._apply_delta_packet(packet)
            self._buffer.pop(next_sequence, None)
            applied.append(self._sequence)
        return applied

    def _drop_buffer_through(self, sequence: int) -> None:
        self._buffer = {seq: packet for seq, packet in self._buffer.items() if seq > sequence}

    def _capture_ingest_state(self) -> tuple[
        dict[str, Any],
        int,
        int,
        list[_HistoryFrame],
        dict[int, Packet],
        int,
    ]:
        return (
            _clone(self._entities),
            self._sequence,
            self._tick,
            list(self._history),
            dict(self._buffer),
            self._last_received,
        )

    def _restore_ingest_state(
        self,
        state: tuple[
            dict[str, Any],
            int,
            int,
            list[_HistoryFrame],
            dict[int, Packet],
            int,
        ],
    ) -> None:
        (
            entities,
            sequence,
            tick,
            history,
            buffer,
            last_received,
        ) = state
        self._entities = _clone(entities)
        self._sequence = sequence
        self._tick = tick
        self._history = list(history)
        self._buffer = dict(buffer)
        self._last_received = last_received

    def _retain(self, frame: _HistoryFrame) -> None:
        self._history.append(frame)
        overflow = len(self._history) - self.history_limit
        if overflow > 0:
            del self._history[:overflow]

    def _frame(self, sequence: int) -> _HistoryFrame | None:
        for frame in self._history:
            if frame.sequence == sequence:
                return frame
        return None

    def _baseline_at_or_before(self, sequence: int) -> _HistoryFrame | None:
        snapshot = None
        fallback = None
        for frame in self._history:
            if frame.sequence > sequence:
                continue
            if fallback is None:
                fallback = frame
            if frame.kind == "snapshot":
                snapshot = frame
        if snapshot is not None:
            return snapshot
        if fallback is None:
            return None
        return _HistoryFrame(
            sequence=fallback.sequence,
            tick=fallback.tick,
            kind="snapshot",
            digest=fallback.digest,
            state_digest=fallback.state_digest,
            entities=_clone(fallback.entities),
            patches=(),
            snapshot_entities=_clone(fallback.entities),
            packet=fallback.packet,
        )

    def _retained_sequences(self) -> tuple[int, ...]:
        return tuple(frame.sequence for frame in self._history)

    def _result(
        self,
        outcome: DeliveryOutcome,
        sequence: int,
        applied: tuple[int, ...],
        digest: str | None,
        diagnostics: str,
        reconciliation: ReconciliationEvidence | None = None,
    ) -> IngestResult:
        ack_packet = self.acknowledge()
        ack = _ack_from_payload(ack_packet.payload)
        return IngestResult(
            outcome=outcome,
            sequence=sequence,
            applied_sequences=applied,
            digest=digest,
            ack=ack,
            diagnostics=diagnostics,
            reconciliation=reconciliation,
        )


class Authority:
    """Producer of authoritative snapshots and ordered deltas."""

    def __init__(self, *, history_limit: int = 32, reorder_window: int = 8) -> None:
        self._core = _ReplicationCore(
            "authority",
            history_limit=history_limit,
            reorder_window=reorder_window,
        )
        self._acks: dict[str, Ack] = {}

    @property
    def sequence(self) -> int:
        return self._core.sequence

    @property
    def tick(self) -> int:
        return self._core.tick

    @property
    def entities(self) -> dict[str, Any]:
        return self._core.entities

    @property
    def digest(self) -> str:
        return self._core.digest

    def snapshot(self, tick: int, entities: Mapping[str, Any] | None = None) -> Packet:
        tick = _require_int("tick", tick, minimum=0)
        if tick < self._core.tick:
            raise SequenceError(
                "snapshot tick moved backwards",
                context={"current_tick": self._core.tick, "tick": tick},
            )
        state = (
            _canonicalize_entities(entities)
            if entities is not None
            else _clone(self._core._entities)
        )
        next_sequence = self._core.sequence + 1
        digest = frame_digest(
            schema_version=SCHEMA_VERSION,
            sequence=next_sequence,
            tick=tick,
            entities=state,
        )
        payload = {
            "tick": tick,
            "entities": state,
            "digest": digest,
            "state_digest": state_digest(state),
        }
        packet = _wrap_packet("snapshot", next_sequence, payload)
        self._core._sequence = next_sequence
        self._core.append_produced(
            kind="snapshot",
            tick=tick,
            entities=state,
            snapshot_entities=state,
            packet=packet,
        )
        return packet

    def mutate(self, tick: int, patches: Sequence[Patch]) -> Packet:
        tick = _require_int("tick", tick, minimum=0)
        if tick < self._core.tick:
            raise SequenceError(
                "delta tick moved backwards",
                context={"current_tick": self._core.tick, "tick": tick},
            )
        decoded = tuple(patches)
        if not decoded:
            raise ReplicationError("delta must contain at least one patch")
        if len(decoded) > MAX_PATCHES:
            raise ReplicationError(
                "delta exceeds patch bound",
                context={"max_patches": MAX_PATCHES},
            )
        for patch in decoded:
            if not isinstance(patch, Patch):
                raise SerializationError("patches must be Patch values")
        base_sequence = self._core.sequence
        base_digest = self._core.digest
        entities = apply_patches(self._core._entities, decoded)
        next_sequence = base_sequence + 1
        digest = frame_digest(
            schema_version=SCHEMA_VERSION,
            sequence=next_sequence,
            tick=tick,
            entities=entities,
        )
        payload = {
            "base_sequence": base_sequence,
            "base_digest": base_digest,
            "tick": tick,
            "patches": [patch.to_payload() for patch in decoded],
            "resulting_digest": digest,
            "resulting_state_digest": state_digest(entities),
        }
        packet = _wrap_packet("delta", next_sequence, payload)
        self._core._sequence = next_sequence
        self._core.append_produced(
            kind="delta",
            tick=tick,
            entities=entities,
            patches=decoded,
            packet=packet,
        )
        return packet

    def record_ack(self, packet: Packet) -> Ack:
        if not isinstance(packet, Packet):
            raise SerializationError("record_ack requires a decoded Packet")
        _validate_packet_envelope(packet)
        if packet.kind != "ack":
            raise ReplicationError("expected acknowledgement packet")
        if packet.schema_version != SCHEMA_VERSION:
            raise SchemaCompatibilityError(
                "incompatible acknowledgement schema",
                context={"schema_version": packet.schema_version},
            )
        expected_checksum = _packet_checksum(
            packet.kind, packet.schema_version, packet.sequence, packet.payload
        )
        if packet.checksum != expected_checksum:
            raise ReplicationError("packet checksum mismatch", context={"kind": "ack"})
        ack = _ack_from_payload(packet.payload)
        if packet.sequence != ack.last_applied_sequence:
            raise SequenceError(
                "ack packet sequence does not match last applied sequence",
                context={"packet_sequence": packet.sequence, "last_applied": ack.last_applied_sequence},
            )
        if ack.last_applied_sequence > self.sequence or ack.last_received_sequence > self.sequence:
            raise SequenceError(
                "acknowledgement refers to future authority sequence",
                context={
                    "authority_sequence": self.sequence,
                    "last_applied": ack.last_applied_sequence,
                    "last_received": ack.last_received_sequence,
                },
            )
        previous = self._acks.get(ack.peer_id)
        if previous is not None and (
            ack.last_applied_sequence < previous.last_applied_sequence
            or ack.last_received_sequence < previous.last_received_sequence
            or ack.tick < previous.tick
        ):
            raise SequenceError(
                "acknowledgement regressed peer state",
                context={"peer_id": ack.peer_id},
            )
        frame = self._core._frame(ack.last_applied_sequence)
        if frame is None:
            raise HistoryExhaustedError(
                "acknowledgement frame is outside retained authority history",
                context={
                    "peer_id": ack.peer_id,
                    "sequence": ack.last_applied_sequence,
                    "retained": self._core._retained_sequences(),
                },
            )
        if ack.last_applied_digest != frame.digest or ack.tick != frame.tick:
            raise ReplicationError(
                "acknowledgement does not match retained authority frame",
                context={"peer_id": ack.peer_id, "sequence": ack.last_applied_sequence},
            )
        self._acks[ack.peer_id] = ack
        return ack

    def last_ack(self, peer_id: str) -> Ack | None:
        return self._acks.get(peer_id)

    def retransmit(self, sequence: int) -> Packet:
        return self._core.packet_for(sequence)

    def rollback_to(self, sequence: int) -> RollbackEvidence:
        return self._core.rollback_to(sequence)


class Replica:
    """Consumer of authoritative packets with prediction and rollback."""

    def __init__(
        self,
        peer_id: str,
        *,
        history_limit: int = 32,
        reorder_window: int = 8,
    ) -> None:
        self._core = _ReplicationCore(
            peer_id,
            history_limit=history_limit,
            reorder_window=reorder_window,
        )
        self._predicted_entities: dict[str, Any] = {}
        self._predictions: list[_Prediction] = []

    @property
    def peer_id(self) -> str:
        return self._core.peer_id

    @property
    def sequence(self) -> int:
        return self._core.sequence

    @property
    def tick(self) -> int:
        return self._core.tick

    @property
    def entities(self) -> dict[str, Any]:
        return self._core.entities

    @property
    def digest(self) -> str:
        return self._core.digest

    @property
    def predicted_entities(self) -> dict[str, Any]:
        return _clone(self._predicted_entities)

    @property
    def predicted_digest(self) -> str:
        return state_digest(self._predicted_entities) if self._predictions else self._core.payload_digest

    def ingest(self, packet: Packet) -> IngestResult:
        result = self._core.ingest(packet, predictions=self._predictions)
        if result.reconciliation is not None:
            self._apply_reconciliation(result.reconciliation)
        elif result.outcome in {DeliveryOutcome.APPLIED, DeliveryOutcome.INITIALIZED}:
            self._predicted_entities = _clone(self._core._entities)
            self._predictions = [
                prediction for prediction in self._predictions if prediction.tick > self._core.tick
            ]
        return result

    def predict(self, tick: int, patches: Sequence[Patch]) -> str:
        tick = _require_int("tick", tick, minimum=0)
        if tick <= self._core.tick:
            raise SequenceError(
                "predictions must target a future tick",
                context={"confirmed_tick": self._core.tick, "tick": tick},
            )
        if any(prediction.tick == tick for prediction in self._predictions):
            raise SequenceError("prediction already exists for tick", context={"tick": tick})
        decoded = tuple(patches)
        if not decoded:
            raise ReplicationError("prediction must contain at least one patch")
        if not self._predictions:
            self._predicted_entities = _clone(self._core._entities)
        self._predicted_entities = apply_patches(self._predicted_entities, decoded)
        digest = state_digest(self._predicted_entities)
        self._predictions.append(_Prediction(tick=tick, patches=decoded, digest=digest))
        self._predictions.sort(key=lambda item: item.tick)
        return digest

    def acknowledge(self) -> Packet:
        return self._core.acknowledge()

    def missing_sequences(self) -> tuple[int, ...]:
        return self._core.missing_sequences()

    def rollback_to(self, sequence: int) -> RollbackEvidence:
        evidence = self._core.rollback_to(sequence)
        self._predicted_entities = _clone(self._core._entities)
        self._predictions = []
        return evidence

    def _apply_reconciliation(self, evidence: ReconciliationEvidence) -> None:
        confirmed = _clone(self._core._entities)
        remaining = [prediction for prediction in self._predictions if prediction.tick > evidence.tick]
        self._predicted_entities = confirmed
        resimulated: list[_Prediction] = []
        for prediction in remaining:
            self._predicted_entities = apply_patches(self._predicted_entities, prediction.patches)
            resimulated.append(
                _Prediction(
                    tick=prediction.tick,
                    patches=prediction.patches,
                    digest=state_digest(self._predicted_entities),
                )
            )
        self._predictions = resimulated


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
    _require_int("schema_version", packet.schema_version, minimum=1)
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
