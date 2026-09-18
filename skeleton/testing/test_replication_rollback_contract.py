"""Offline contract tests for engine-neutral replication and rollback.

These tests never open sockets. Packet reordering, loss, and duplication are
exercised through OfflineChannel, which only stores canonical packet bytes.
"""

from __future__ import annotations

import ast
import inspect
import json
import math

import pytest

from skeleton.network import (
    SCHEMA_VERSION,
    Authority,
    DeliveryOutcome,
    HistoryExhaustedError,
    OfflineChannel,
    Patch,
    Replica,
    ReplicationError,
    SchemaCompatibilityError,
    SequenceError,
    SerializationError,
    canonical_dumps,
    frame_digest,
    state_digest,
)
from skeleton.network import replication as replication_mod
from skeleton.network.replication import Packet, decode_packet


def _hero(x: int, y: int | None = None) -> dict[str, dict[str, int]]:
    fields = {"x": x}
    if y is not None:
        fields["y"] = y
    return {"hero": fields}


def _move(x: int, y: int | None = None) -> tuple[Patch, ...]:
    fields = {"x": x}
    if y is not None:
        fields["y"] = y
    return (Patch.set("hero", fields),)


def _stream(*packets: Packet) -> Replica:
    replica = Replica("client-a")
    for packet in packets:
        replica.ingest(packet)
    return replica


def test_canonical_serialization_is_order_independent_and_stable():
    left = canonical_dumps({"hero": {"y": 2, "x": 1}, "npc": {"hp": 3}})
    right = canonical_dumps({"npc": {"hp": 3}, "hero": {"x": 1, "y": 2}})
    assert left == right
    assert left == '{"hero":{"x":1,"y":2},"npc":{"hp":3}}'
    assert state_digest({"npc": {"hp": 3}, "hero": {"x": 1}}) == state_digest(
        {"hero": {"x": 1}, "npc": {"hp": 3}}
    )


def test_non_canonical_values_fail_closed():
    authority = Authority()
    with pytest.raises(SerializationError):
        authority.snapshot(1, {"hero": {"x": math.nan}})
    with pytest.raises(SerializationError):
        canonical_dumps({"hero": {"x": math.inf}})
    with pytest.raises(SerializationError):
        canonical_dumps({"hero": {"pos": (1, 2)}})
    with pytest.raises(SerializationError):
        Patch.set("hero", {1: 2})  # type: ignore[dict-item]


def test_monotonic_sequences_and_ticks():
    authority = Authority()
    first = authority.snapshot(0, _hero(0, 0))
    second = authority.mutate(1, _move(1, 0))
    third = authority.mutate(1, _move(2, 0))
    assert (first.sequence, second.sequence, third.sequence) == (1, 2, 3)
    with pytest.raises(SequenceError):
        authority.mutate(0, _move(3, 0))
    assert authority.sequence == 3
    assert authority.tick == 1


def test_packet_bytes_round_trip_through_offline_channel():
    authority = Authority()
    snapshot = authority.snapshot(0, _hero(4, 1))
    channel = OfflineChannel()
    channel.submit(snapshot)
    restored = channel.pop()
    assert restored is not None
    assert restored.encode() == snapshot.encode()
    assert decode_packet(snapshot.encode()).checksum == snapshot.checksum


def test_packet_reordering_applies_in_sequence_and_matches_authority():
    authority = Authority()
    snapshot = authority.snapshot(0, _hero(0, 0))
    delta_a = authority.mutate(1, _move(1, 0))
    delta_b = authority.mutate(2, _move(2, 1))
    channel = OfflineChannel()
    for packet in (snapshot, delta_a, delta_b):
        channel.submit(packet)
    channel.reorder((1, 2, 0))
    replica = Replica("client-a")
    first, second, third = (replica.ingest(packet) for packet in channel.drain())
    assert first.outcome is DeliveryOutcome.BUFFERED
    assert second.outcome is DeliveryOutcome.BUFFERED
    assert third.outcome is DeliveryOutcome.INITIALIZED
    assert third.applied_sequences == (1, 2, 3)
    assert replica.digest == authority.digest
    assert replica.entities == authority.entities


def test_loss_simulation_reports_gap_then_applies_retransmit():
    authority = Authority()
    snapshot = authority.snapshot(0, _hero(0, 0))
    lost = authority.mutate(1, _move(1, 0))
    later = authority.mutate(2, _move(2, 0))
    replica = Replica("client-a", reorder_window=4)
    assert replica.ingest(snapshot).outcome is DeliveryOutcome.INITIALIZED
    buffered = replica.ingest(later)
    assert buffered.outcome is DeliveryOutcome.BUFFERED
    assert buffered.ack is not None
    assert buffered.ack.last_received_sequence == later.sequence
    assert buffered.ack.missing_sequences == (2,)
    assert replica.missing_sequences() == (2,)
    assert replica.sequence == 1
    ack = replica.acknowledge()
    recorded = authority.record_ack(ack)
    assert recorded.missing_sequences == (2,)
    recovered = replica.ingest(authority.retransmit(lost.sequence))
    assert recovered.outcome is DeliveryOutcome.APPLIED
    assert recovered.applied_sequences == (2, 3)
    assert replica.digest == authority.digest
    assert replica.missing_sequences() == ()


def test_duplicate_delivery_does_not_mutate_state():
    authority = Authority()
    snapshot = authority.snapshot(0, _hero(0, 0))
    delta = authority.mutate(1, _move(5, 5))
    channel = OfflineChannel()
    channel.submit(snapshot)
    channel.submit(delta)
    channel.duplicate_index(1)
    replica = Replica("client-a")
    results = [replica.ingest(packet) for packet in channel.drain()]
    assert [result.outcome for result in results] == [
        DeliveryOutcome.INITIALIZED,
        DeliveryOutcome.APPLIED,
        DeliveryOutcome.DUPLICATE,
    ]
    assert replica.entities == _hero(5, 5)
    assert replica.digest == authority.digest


def test_stale_delta_after_catch_up_snapshot_is_explicit():
    authority = Authority(history_limit=8)
    snapshot = authority.snapshot(0, _hero(0, 0))
    stale = authority.mutate(1, _move(1, 0))
    authority.mutate(2, _move(2, 0))
    catch_up = authority.snapshot(3, _hero(9, 9))
    replica = Replica("client-a")
    replica.ingest(snapshot)
    replica.ingest(catch_up)
    result = replica.ingest(stale)
    assert result.outcome is DeliveryOutcome.STALE
    assert replica.entities == _hero(9, 9)
    assert replica.digest == authority.digest


def test_divergent_prediction_reconciles_to_authority_digest():
    authority = Authority()
    snapshot = authority.snapshot(0, _hero(0, 0))
    confirmed = authority.mutate(1, _move(3, 0))
    replica = Replica("client-a")
    replica.ingest(snapshot)
    predicted = replica.predict(1, _move(8, 0))
    assert predicted != state_digest(authority.entities)
    result = replica.ingest(confirmed)
    assert result.reconciliation is not None
    assert result.reconciliation.divergent is True
    assert result.reconciliation.rolled_back is True
    assert result.reconciliation.predicted_digest == predicted
    assert result.reconciliation.confirmed_digest == state_digest(authority.entities)
    assert replica.entities == authority.entities
    assert replica.predicted_digest == state_digest(authority.entities)


def test_matching_prediction_is_not_divergent():
    authority = Authority()
    snapshot = authority.snapshot(0, _hero(0, 0))
    confirmed = authority.mutate(1, _move(4, 1))
    replica = Replica("client-a")
    replica.ingest(snapshot)
    replica.predict(1, _move(4, 1))
    result = replica.ingest(confirmed)
    assert result.reconciliation is not None
    assert result.reconciliation.divergent is False
    assert replica.digest == authority.digest


def test_rollback_replays_from_snapshot_and_reproduces_prior_digest():
    authority = Authority()
    replica = Replica("client-a")
    packets = [
        authority.snapshot(0, _hero(0, 0)),
        authority.mutate(1, _move(1, 0)),
        authority.mutate(2, _move(2, 0)),
        authority.mutate(3, _move(3, 1)),
    ]
    for packet in packets:
        replica.ingest(packet)
    prior = frame_digest(
        schema_version=SCHEMA_VERSION,
        sequence=1,
        tick=0,
        entities=_hero(0, 0),
    )
    evidence = replica.rollback_to(1)
    assert evidence.reproduced is True
    assert evidence.to_sequence == 1
    assert evidence.to_digest == prior
    assert evidence.replayed_sequences == (1,)
    assert replica.digest == prior
    assert replica.entities == _hero(0, 0)
    replica.ingest(packets[1])
    replica.ingest(packets[2])
    assert replica.digest == frame_digest(
        schema_version=SCHEMA_VERSION,
        sequence=3,
        tick=2,
        entities=_hero(2, 0),
    )


def test_history_exhaustion_fails_closed():
    authority = Authority(history_limit=3)
    replica = Replica("client-b", history_limit=3)
    packets = [authority.snapshot(0, _hero(0, 0))]
    for tick in range(1, 5):
        packets.append(authority.mutate(tick, _move(tick)))
    for packet in packets:
        replica.ingest(packet)
    with pytest.raises(HistoryExhaustedError):
        replica.rollback_to(1)
    with pytest.raises(HistoryExhaustedError):
        authority.retransmit(1)


def test_incompatible_schema_fails_closed():
    authority = Authority()
    snapshot = authority.snapshot(0, _hero(0, 0))
    body = json.loads(snapshot.encode())
    body["schema_version"] = SCHEMA_VERSION + 1
    body["checksum"] = "0" * 64
    tampered = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(SchemaCompatibilityError):
        decode_packet(tampered)
    replica = Replica("client-a")
    forged = Packet(
        kind="snapshot",
        schema_version=SCHEMA_VERSION + 1,
        sequence=1,
        payload={"tick": 0, "entities": {}, "digest": "0" * 64, "state_digest": "0" * 64},
        checksum="0" * 64,
    )
    with pytest.raises(SchemaCompatibilityError):
        replica.ingest(forged)


def test_checksum_mismatch_fails_closed():
    authority = Authority()
    snapshot = authority.snapshot(0, _hero(0, 0))
    body = json.loads(snapshot.encode())
    body["payload"]["entities"]["hero"]["x"] = 99
    tampered = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(ReplicationError, match="checksum mismatch"):
        decode_packet(tampered)


def test_reorder_window_exhaustion_rejects_the_gap():
    authority = Authority()
    snapshot = authority.snapshot(0, _hero(0, 0))
    for tick in range(1, 5):
        authority.mutate(tick, _move(tick))
    far = authority.mutate(5, _move(5))
    replica = Replica("client-a", reorder_window=2)
    replica.ingest(snapshot)
    result = replica.ingest(far)
    assert result.outcome is DeliveryOutcome.REJECTED_GAP
    assert replica.sequence == 1
    assert replica.entities == _hero(0, 0)


def test_two_replicas_converge_on_the_same_digest():
    authority = Authority()
    packets = [
        authority.snapshot(0, _hero(0, 0)),
        authority.mutate(1, _move(1, 1)),
        authority.mutate(2, (Patch.set("hero", {"hp": 7}),)),
        authority.mutate(3, (Patch.delete("hero"),)),
    ]
    left = _stream(*packets)
    right = Replica("client-b")
    channel = OfflineChannel()
    for packet in packets:
        channel.submit(packet)
    channel.reorder((3, 1, 0, 2))
    for packet in channel.drain():
        right.ingest(packet)
    assert left.digest == right.digest == authority.digest
    assert left.entities == {}


def test_entity_and_patch_bounds_fail_closed():
    authority = Authority()
    authority.snapshot(0, _hero(0, 0))
    too_many = tuple(Patch.set(f"e{index:02d}", {"x": index}) for index in range(65))
    with pytest.raises(ReplicationError, match="patch bound"):
        authority.mutate(1, too_many)
    with pytest.raises(ReplicationError, match="entity bound"):
        authority.snapshot(1, {f"e{index:03d}": {"x": 1} for index in range(257)})


def _ack_packet(
    authority: Authority,
    *,
    peer_id: str = "client-a",
    applied: int | None = None,
    received: int | None = None,
    missing: list[int] | None = None,
    digest: str | None = None,
    tick: int | None = None,
    packet_sequence: int | None = None,
) -> Packet:
    applied = authority.sequence if applied is None else applied
    received = applied if received is None else received
    if digest is None:
        frame = authority._core._frame(applied)  # type: ignore[attr-defined]
        assert frame is not None
        digest = frame.digest
        if tick is None:
            tick = frame.tick
    if tick is None:
        tick = authority.tick
    payload = {
        "peer_id": peer_id,
        "last_applied_sequence": applied,
        "last_applied_digest": digest,
        "last_received_sequence": received,
        "tick": tick,
        "missing_sequences": list(missing or []),
    }
    return replication_mod._wrap_packet(  # type: ignore[attr-defined]
        "ack",
        applied if packet_sequence is None else packet_sequence,
        payload,
    )


def test_packet_encode_never_repairs_a_tampered_checksum() -> None:
    authority = Authority()
    packet = authority.snapshot(0, _hero(1))
    forged = Packet(
        kind=packet.kind,
        schema_version=packet.schema_version,
        sequence=packet.sequence,
        payload=packet.payload,
        checksum="0" * 64,
    )
    with pytest.raises(ReplicationError, match="checksum mismatch"):
        forged.encode()


def test_decode_packet_rejects_oversize_and_duplicate_key_json() -> None:
    oversized = b" " * (replication_mod.MAX_PACKET_BYTES + 1)
    with pytest.raises(SerializationError, match="byte bound"):
        decode_packet(oversized)

    duplicate = (
        b'{"kind":"snapshot","kind":"snapshot","schema_version":1,'
        b'"sequence":1,"payload":{},"checksum":"' + b"0" * 64 + b'"}'
    )
    with pytest.raises(SerializationError, match="duplicate keys"):
        decode_packet(duplicate)


@pytest.mark.parametrize("checksum", ["g" * 64, "A" * 64, "0" * 63, "0" * 65])
def test_decode_packet_requires_canonical_lowercase_hex_checksum(checksum: str) -> None:
    body = {
        "kind": "snapshot",
        "schema_version": 1,
        "sequence": 1,
        "payload": {},
        "checksum": checksum,
    }
    raw = json.dumps(body, separators=(",", ":")).encode()
    with pytest.raises(SerializationError, match="lowercase hex"):
        decode_packet(raw)


@pytest.mark.parametrize("peer_id", [" client", "client ", "client\nname", "\tclient"])
def test_replication_identity_tokens_are_exact_and_control_free(peer_id: str) -> None:
    with pytest.raises(SerializationError):
        Replica(peer_id)


def test_canonical_values_have_a_nesting_bound() -> None:
    value: object = 1
    for _ in range(replication_mod.MAX_CANONICAL_DEPTH + 2):
        value = [value]
    with pytest.raises(SerializationError, match="nesting bound"):
        canonical_dumps(value)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"schema_version": True, "sequence": 0, "tick": 0}, "schema_version"),
        ({"schema_version": 1, "sequence": True, "tick": 0}, "sequence"),
        ({"schema_version": 1, "sequence": 0, "tick": True}, "tick"),
        ({"schema_version": 0, "sequence": 0, "tick": 0}, "schema_version"),
        ({"schema_version": 1, "sequence": -1, "tick": 0}, "sequence"),
        ({"schema_version": 1, "sequence": 0, "tick": -1}, "tick"),
    ],
)
def test_frame_digest_rejects_invalid_identity_numbers(kwargs: dict[str, object], match: str) -> None:
    with pytest.raises((SerializationError, ReplicationError), match=match):
        frame_digest(entities={}, **kwargs)  # type: ignore[arg-type]


def test_offline_channel_rejects_non_packets_and_noninteger_indices() -> None:
    channel = OfflineChannel()
    with pytest.raises(SerializationError, match="requires a Packet"):
        channel.submit("not-a-packet")  # type: ignore[arg-type]

    authority = Authority()
    channel.submit(authority.snapshot(0, {}))
    with pytest.raises(SerializationError, match="integer"):
        channel.drop_index(True)  # type: ignore[arg-type]
    with pytest.raises(SerializationError, match="integer"):
        channel.duplicate_index(False)  # type: ignore[arg-type]
    with pytest.raises(SerializationError, match="contain integers"):
        channel.reorder([False])  # type: ignore[list-item]


def test_offline_channel_has_a_hard_packet_bound() -> None:
    channel = OfflineChannel()
    authority = Authority()
    packet = authority.snapshot(0, {})
    for _ in range(replication_mod.MAX_CHANNEL_PACKETS):
        channel.submit(packet)
    with pytest.raises(ReplicationError, match="packet bound"):
        channel.submit(packet)
    with pytest.raises(ReplicationError, match="packet bound"):
        channel.duplicate_index(0)


@pytest.mark.parametrize(
    "fields",
    [
        tuple((f"k{i}", i) for i in range(replication_mod.MAX_FIELDS + 1)),
        (("x", 1), ("x", 2)),
        (("x", 1, 2),),
        ("not-a-pair",),
    ],
)
def test_direct_patch_construction_cannot_bypass_field_validation(fields: object) -> None:
    patch = Patch("hero", replication_mod.PatchOp.SET, fields)  # type: ignore[arg-type]
    with pytest.raises((SerializationError, ReplicationError)):
        patch.to_payload()
    with pytest.raises((SerializationError, ReplicationError)):
        replication_mod.apply_patches({}, (patch,))


def test_direct_patch_requires_enum_operation() -> None:
    patch = Patch("hero", "set", (("x", 1),))  # type: ignore[arg-type]
    with pytest.raises(SerializationError, match="PatchOp"):
        patch.to_payload()


def test_patch_constructor_enforces_field_bound_before_state_application() -> None:
    fields = {f"k{i}": i for i in range(replication_mod.MAX_FIELDS + 1)}
    with pytest.raises(ReplicationError, match="field bound"):
        Patch.set("hero", fields)


@pytest.mark.parametrize(
    ("missing", "received", "match"),
    [
        ([2, 2], 2, "sorted and unique"),
        ([3, 2], 3, "sorted and unique"),
        ([-1], 2, "non-negative"),
        ([1], 2, "strictly after applied"),
        ([3], 2, "strictly after applied"),
    ],
)
def test_ack_missing_sequence_contract_is_strict(
    missing: list[int], received: int, match: str
) -> None:
    authority = Authority()
    authority.snapshot(0, {})
    authority.mutate(1, (Patch.set("hero", {"x": 1}),))
    authority.mutate(2, (Patch.set("hero", {"x": 2}),))
    packet = _ack_packet(authority, applied=1, received=received, missing=missing)
    with pytest.raises((SerializationError, SequenceError), match=match):
        authority.record_ack(packet)


def test_ack_received_sequence_cannot_precede_applied_sequence() -> None:
    authority = Authority()
    authority.snapshot(0, {})
    packet = _ack_packet(authority, applied=1, received=0)
    with pytest.raises(SequenceError, match="cannot precede"):
        authority.record_ack(packet)


def test_ack_packet_sequence_is_bound_to_payload_sequence() -> None:
    authority = Authority()
    authority.snapshot(0, {})
    packet = _ack_packet(authority, packet_sequence=0)
    with pytest.raises(SequenceError, match="does not match"):
        authority.record_ack(packet)


def test_ack_cannot_claim_future_authority_progress() -> None:
    authority = Authority()
    authority.snapshot(0, {})
    payload = {
        "peer_id": "client-a",
        "last_applied_sequence": 2,
        "last_applied_digest": authority.digest,
        "last_received_sequence": 2,
        "tick": authority.tick,
        "missing_sequences": [],
    }
    packet = replication_mod._wrap_packet("ack", 2, payload)  # type: ignore[attr-defined]
    with pytest.raises(SequenceError, match="future authority"):
        authority.record_ack(packet)


def test_ack_for_evicted_frame_is_unverifiable_and_rejected() -> None:
    authority = Authority(history_limit=3)
    first = authority.snapshot(0, {})
    authority.mutate(1, (Patch.set("hero", {"x": 1}),))
    authority.mutate(2, (Patch.set("hero", {"x": 2}),))
    authority.mutate(3, (Patch.set("hero", {"x": 3}),))

    assert authority._core._frame(first.sequence) is None  # type: ignore[attr-defined]
    forged = replication_mod._wrap_packet(  # type: ignore[attr-defined]
        "ack",
        first.sequence,
        {
            "peer_id": "client-old",
            "last_applied_sequence": first.sequence,
            "last_applied_digest": "0" * 64,
            "last_received_sequence": first.sequence,
            "tick": 0,
            "missing_sequences": [],
        },
    )

    with pytest.raises(HistoryExhaustedError, match="outside retained authority history"):
        authority.record_ack(forged)
    assert authority.last_ack("client-old") is None


def test_ack_cannot_regress_or_lie_about_retained_frame() -> None:
    authority = Authority()
    first = authority.snapshot(0, {})
    authority.mutate(1, (Patch.set("hero", {"x": 1}),))
    authority.record_ack(_ack_packet(authority))

    old = _ack_packet(
        authority,
        applied=first.sequence,
        received=first.sequence,
        digest=first.payload["digest"],
        tick=first.payload["tick"],
    )
    with pytest.raises(SequenceError, match="regressed"):
        authority.record_ack(old)

    other = Authority()
    snapshot = other.snapshot(0, {})
    lying = _ack_packet(other, digest="0" * 64)
    with pytest.raises(ReplicationError, match="retained authority frame"):
        other.record_ack(lying)


@pytest.mark.parametrize("bad_digest", ["f" * 63, "F" * 64, "z" * 64])
def test_ack_digest_must_be_lowercase_sha256(bad_digest: str) -> None:
    authority = Authority()
    authority.snapshot(0, {})
    packet = _ack_packet(authority, digest=bad_digest)
    with pytest.raises(SerializationError, match="lowercase hex"):
        authority.record_ack(packet)


def test_direct_packet_envelope_rejects_boolean_sequence() -> None:
    payload = {"tick": 0, "entities": {}, "digest": "0" * 64, "state_digest": "0" * 64}
    checksum = replication_mod._packet_checksum("snapshot", 1, True, payload)  # type: ignore[attr-defined]
    packet = Packet("snapshot", 1, True, payload, checksum)  # type: ignore[arg-type]
    with pytest.raises(SerializationError, match="sequence"):
        Replica("client-a").ingest(packet)


def test_malformed_buffered_delta_does_not_advance_received_watermark() -> None:
    authority = Authority()
    snapshot = authority.snapshot(0, {})
    replica = Replica("client-a")
    replica.ingest(snapshot)

    malformed = {
        "base_sequence": 2,
        "base_digest": "not-a-digest",
        "tick": 2,
        "patches": [],
        "resulting_digest": "0" * 64,
        "resulting_state_digest": "0" * 64,
    }
    packet = replication_mod._wrap_packet("delta", 3, malformed)  # type: ignore[attr-defined]
    with pytest.raises(SerializationError, match="lowercase hex"):
        replica.ingest(packet)
    assert replica.acknowledge().payload["last_received_sequence"] == snapshot.sequence


def test_module_has_no_socket_or_server_surface():
    tree = ast.parse(inspect.getsource(replication_mod))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module.split(".")[0])
    assert "socket" not in imported
    assert "asyncio" not in imported
    assert "httpx" not in imported
    assert "create_server" not in inspect.getsource(replication_mod)
    assert "create_connection" not in inspect.getsource(replication_mod)


def test_acknowledgement_evidence_rejects_impossible_or_forged_state():
    authority = Authority()
    snapshot = authority.snapshot(0, _hero(0, 0))
    replica = Replica("client-a")
    replica.ingest(snapshot)
    valid = replica.acknowledge()
    assert authority.record_ack(valid).last_applied_sequence == 1

    envelope_mismatch = replication_mod._wrap_packet("ack", 0, valid.payload)
    with pytest.raises(SequenceError, match="packet sequence"):
        authority.record_ack(envelope_mismatch)

    future_payload = dict(valid.payload)
    future_payload["last_applied_sequence"] = authority.sequence + 10
    future_payload["last_received_sequence"] = authority.sequence + 10
    future_payload["missing_sequences"] = []
    future = replication_mod._wrap_packet(
        "ack",
        int(future_payload["last_applied_sequence"]),
        future_payload,
    )
    with pytest.raises(SequenceError, match="future applied sequence"):
        authority.record_ack(future)

    wrong_digest_payload = dict(valid.payload)
    wrong_digest_payload["last_applied_digest"] = "0" * 64
    wrong_digest = replication_mod._wrap_packet("ack", valid.sequence, wrong_digest_payload)
    with pytest.raises(ReplicationError, match="retained authority history"):
        authority.record_ack(wrong_digest)

    non_hex_payload = dict(valid.payload)
    non_hex_payload["last_applied_digest"] = "z" * 64
    non_hex = replication_mod._wrap_packet("ack", valid.sequence, non_hex_payload)
    with pytest.raises(SerializationError, match="lowercase hex"):
        authority.record_ack(non_hex)

    impossible_gap_payload = dict(valid.payload)
    impossible_gap_payload["last_received_sequence"] = 3
    impossible_gap_payload["missing_sequences"] = [1, 2]
    impossible_gap = replication_mod._wrap_packet("ack", valid.sequence, impossible_gap_payload)
    with pytest.raises(SequenceError, match="outside the reported gap"):
        authority.record_ack(impossible_gap)
