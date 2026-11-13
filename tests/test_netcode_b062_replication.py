"""B062: authoritative state replication is bandwidth-budgeted and deterministic under loss/reordering."""
import struct

from skeleton.netcode.replication import (BandwidthBudget, ClientReplica, LossyLink, ServerReplicator,
                                          decode_delta, encode_delta)


def _world(n=40, budget=4096, **kw):
    srv = ServerReplicator(BandwidthBudget(budget), **kw)
    for e in range(n):
        srv.set(e, x=e, y=-e, hp=100)
    return srv


def _simulate(seed, loss, dup, delay, ticks=300, budget=400, mutate_until=200):
    srv = _world(budget=budget)
    srv.add_client("c")
    cli = ClientReplica()
    down, up = LossyLink(seed, loss, dup, delay), LossyLink(seed + 1, loss, dup, delay)
    for t in range(ticks):
        if t < mutate_until:
            srv.set(t % 40, x=t, hp=100 - (t % 7))
            if t == 50:
                srv.remove(3)
            if t == 60:
                srv.set(99, x=1, y=2)
        srv.step()
        down.send(srv.snapshot_for("c"))
        for pkt in down.advance():
            acked = cli.receive(pkt)
            if acked is not None:
                up.send(struct.pack(">I", acked))
        for pkt in up.advance():
            srv.ack("c", struct.unpack(">I", pkt)[0])
    return srv, cli


def test_b062_delta_roundtrip_and_removal():
    base = {1: {"x": 1, "y": 2}, 2: {"x": 0}}
    cur = {1: {"x": 5, "y": 2}, 3: {"hp": 9}}
    data, used = encode_delta(7, 3, base, cur)
    snap = decode_delta(data)
    assert snap.tick == 7 and snap.baseline == 3
    assert snap.entities == {1: {"x": 5}, 2: None, 3: {"hp": 9}}


def test_b062_delta_is_smaller_than_full_snapshot():
    srv = _world()
    srv.add_client("c")
    full = srv.snapshot_for("c")
    srv.ack("c", srv.tick)
    srv.set(0, x=999)
    srv.step()
    assert len(srv.snapshot_for("c")) < len(full) / 10


def test_b062_bandwidth_budget_is_never_exceeded():
    srv, _ = _simulate(5, 0.2, 0.05, 3, budget=300)
    assert max(srv.bytes_sent) <= 300


def test_b062_priority_and_starvation_age_get_everyone_through():
    srv = _world(n=40, budget=200, priority=lambda e, s: 10.0 if e == 0 else 1.0)
    srv.add_client("c")
    cli = ClientReplica()
    first = decode_delta(srv.snapshot_for("c"))
    assert 0 in first.entities  # high priority goes first
    for _ in range(60):
        srv.step()
        cli.receive(srv.snapshot_for("c"))
        srv.ack("c", cli.tick)
    assert cli.state == srv.state


def test_b062_relevancy_filters_entities_per_client():
    srv = _world(n=10, relevant=lambda c, e, s: e % 2 == 0)
    srv.add_client("c")
    cli = ClientReplica()
    cli.receive(srv.snapshot_for("c"))
    assert set(cli.state) == {0, 2, 4, 6, 8}


def test_b062_converges_under_packet_loss():
    srv, cli = _simulate(11, loss=0.3, dup=0.0, delay=0)
    assert cli.state == srv.state


def test_b062_converges_under_reordering_and_duplication():
    srv, cli = _simulate(12, loss=0.0, dup=0.2, delay=5)
    assert cli.state == srv.state


def test_b062_converges_under_loss_and_reorder_combined():
    for seed in range(10):
        srv, cli = _simulate(seed, loss=0.25, dup=0.1, delay=4)
        assert cli.state == srv.state, seed


def test_b062_simulation_is_deterministic_for_a_seed():
    a = _simulate(42, 0.2, 0.1, 3)
    b = _simulate(42, 0.2, 0.1, 3)
    assert a[0].bytes_sent == b[0].bytes_sent and a[1].state == b[1].state


def test_b062_client_rejects_stale_and_malformed_snapshots():
    srv = _world(n=2)
    srv.add_client("c")
    cli = ClientReplica()
    srv.step()
    s1 = srv.snapshot_for("c")
    srv.step()
    s2 = srv.snapshot_for("c")
    assert cli.receive(s2) is not None
    assert cli.receive(s1) is None
    assert cli.receive(b"\x00\x01") is None
    assert cli.rejected == 2


def test_b062_client_never_writes_authoritative_state():
    srv = _world(n=3)
    srv.add_client("c")
    cli = ClientReplica()
    cli.receive(srv.snapshot_for("c"))
    cli.state[0]["x"] = 12345
    assert srv.state[0]["x"] == 0
