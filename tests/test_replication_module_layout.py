"""Public compatibility and frozen wire evidence for the protocol extraction."""
from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize("path", [
    "skeleton.network.replication",
    "skeleton.distributed.network.replication",
])
def test_existing_imports_preserve_replication_wire_contract(path: str) -> None:
    module = importlib.import_module(path)
    authority = module.Authority()
    replica = module.Replica("client-a")
    packets = [
        authority.snapshot(0, {"hero": {"x": 0, "y": 0}}),
        authority.mutate(1, (module.Patch.set("hero", {"x": 4}),)),
    ]
    for packet in packets:
        replica.ingest(module.Packet.decode(packet.encode()))
    acknowledgement = replica.acknowledge()
    # Captured from the pre-extraction implementation at 7057bc6.
    assert [packet.checksum for packet in packets] + [acknowledgement.checksum] == [
        "2ebf9056594ee2c57b729de944ac2f78424616eb203c6d096cbfa19de7f99a03",
        "18b4a3d36b8812981d64b04a47b8331da377388bcc41879b97a3a015caec0553",
        "09193e3b3c3bd831592cb459fd345c4d5a2197677e5db9aed4b112c25ae84454",
    ]
    assert authority.record_ack(acknowledgement).last_applied_sequence == 2
    assert replica.entities == {"hero": {"x": 4, "y": 0}}


def test_legacy_and_canonical_imports_share_packet_and_error_types() -> None:
    legacy = importlib.import_module("skeleton.network.replication")
    canonical = importlib.import_module("skeleton.distributed.network.replication")
    protocol = importlib.import_module("skeleton.distributed.network._replication_protocol")
    for name in ("Packet", "Patch", "Ack", "ReplicationError", "SequenceError"):
        assert getattr(legacy, name) is getattr(canonical, name) is getattr(protocol, name)
