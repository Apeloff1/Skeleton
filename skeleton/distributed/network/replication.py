"""Engine-neutral replication sessions and rollback contract.

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

from skeleton.distributed.network._replication_protocol import (
    SCHEMA_VERSION,
    MAX_HISTORY,
    MAX_REORDER_WINDOW,
    MAX_ENTITIES,
    MAX_FIELDS,
    MAX_PATCHES,
    MAX_TOKEN_CHARS,
    MAX_STRING_CHARS,
    MAX_LIST_ITEMS,
    MAX_PEER_ID_CHARS,
    MAX_MISSING_REPORT,
    MAX_PACKET_BYTES,
    MAX_CHANNEL_PACKETS,
    MAX_CANONICAL_DEPTH,
    _PACKET_KEYS,
    _SNAPSHOT_KEYS,
    _DELTA_KEYS,
    _ACK_KEYS,
    ReplicationError,
    SchemaCompatibilityError,
    HistoryExhaustedError,
    SequenceError,
    SerializationError,
    PatchOp,
    DeliveryOutcome,
    Patch,
    Packet,
    Ack,
    IngestResult,
    RollbackEvidence,
    ReconciliationEvidence,
    _HistoryFrame,
    _Prediction,
    canonical_dumps,
    state_digest,
    frame_digest,
    decode_packet,
    apply_patches,
    _reconcile_predictions,
    _json_object_no_duplicates,
    _validate_delta_payload_shape,
    _validated_patch_fields,
    _wrap_packet,
    _encode_packet,
    _packet_checksum,
    _ack_from_payload,
    _decode_patches,
    _canonicalize_entities,
    _canonicalize,
    _frozen_fields,
    _clone,
    _sha256,
    _bounded_token,
    _require_int,
    _require_digest,
    _validate_packet_envelope,
    _require_exact_keys,
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
