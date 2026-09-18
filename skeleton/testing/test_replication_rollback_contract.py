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
    replica.ingest(packets[0])
    stale_ack = replica.acknowledge()
    for tick in range(1, 5):
        packets.append(authority.mutate(tick, _move(tick)))
    for packet in packets[1:]:
        replica.ingest(packet)
    with pytest.raises(HistoryExhaustedError):
        replica.rollback_to(1)
    with pytest.raises(HistoryExhaustedError):
        authority.retransmit(1)
    with pytest.raises(HistoryExhaustedError, match="ack applied sequence"):
        authority.record_ack(stale_ack)


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
