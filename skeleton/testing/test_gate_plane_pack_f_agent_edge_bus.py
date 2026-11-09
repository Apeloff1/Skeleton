"""Agent edge — envelope, dedup, DLQ and the at-least-once ordered bus."""

from __future__ import annotations

import pytest

from skeleton.gate_plane.agent_edge import (
    AgentBus,
    BusFull,
    DeadLetterQueue,
    DeadLetterReason,
    DedupWindow,
    Envelope,
    EnvelopeError,
    PoisonMessage,
    PublishStatus,
    StaleLease,
    UnknownLease,
    backoff_delay,
)
from skeleton.gate_plane.s2s.clock import ManualClock


def env(i=0, *, conv="conv-0001", sender="alpha", recipient="beta", topic="plan.request", **kw):
    kw.setdefault("now", 0.0)
    return Envelope.new(
        sender=sender, recipient=recipient, topic=topic, payload={"i": i},
        conversation_id=conv, message_id=kw.pop("message_id", f"msg-{conv}-{i:04d}"), **kw,
    )


@pytest.fixture
def clock():
    return ManualClock(start=1000.0)


@pytest.fixture
def bus(clock):
    counter = iter(range(1, 1_000_000))
    return AgentBus(clock=clock, default_lease_s=10.0, backoff_base_s=1.0, backoff_cap_s=8.0,
                    lease_id_factory=lambda: f"lease-{next(counter):06d}")


def e(i=0, clock=None, **kw):
    return env(i, now=(clock.now() if clock else 0.0), **kw)


# -- envelope -----------------------------------------------------------------------
def test_envelope_roundtrip_and_digest_stable():
    a = env(1, idempotency_key="idem-1234", headers={"trace-id": "t1"})
    b = Envelope.from_wire(a.to_wire())
    assert a == b and a.digest() == b.digest()
    assert a.dedup_key == "idem:alpha:idem-1234"
    assert env(2).dedup_key.startswith("id:msg-")


@pytest.mark.parametrize(
    "kw",
    [
        {"sender": "Bad Agent"},
        {"recipient": ""},
        {"topic": "UPPER"},
        {"priority": 10},
        {"ttl_s": 0},
        {"max_attempts": 0},
        {"headers": {"Bad Header": "x"}},
    ],
)
def test_envelope_rejects_invalid(kw):
    with pytest.raises(EnvelopeError):
        env(0, **kw)


def test_envelope_payload_limits():
    with pytest.raises(EnvelopeError):
        Envelope.new(sender="a1", recipient="b1", topic="t", payload={"x": "y" * (300 * 1024)})
    with pytest.raises(EnvelopeError):
        Envelope.new(sender="a1", recipient="b1", topic="t", payload={"x": object()})


def test_reply_and_forward_keep_causality():
    a = env(1, now=5.0)
    r = a.reply(payload={"ok": True}, now=6.0)
    assert (r.sender, r.recipient) == ("beta", "alpha")
    assert r.conversation_id == a.conversation_id and r.correlation_id == a.correlation_id
    assert r.causation_id == a.message_id and r.topic == "plan.request.reply"
    f = a.forward("gamma", now=10.0)
    assert f.recipient == "gamma" and f.causation_id == a.message_id
    with pytest.raises(EnvelopeError):
        Envelope.from_wire({**a.to_wire(), "schema": "v0"})
    with pytest.raises(EnvelopeError):
        Envelope.from_wire({"sender": "a1"})


# -- dedup / dlq ----------------------------------------------------------------------
def test_dedup_window_expiry_and_capacity():
    d = DedupWindow(window_s=10, capacity=2)
    assert d.remember("a", 0) and not d.remember("a", 1)
    assert d.seen("a", 5) == "pending"
    d.mark("a", 5, "done")
    assert d.seen("a", 14) == "done" and d.seen("a", 16) is None
    d.remember("x", 20)
    d.remember("y", 20)
    d.remember("z", 20)
    assert len(d) == 2 and d.evicted_early == 1
    with pytest.raises(ValueError):
        DedupWindow(window_s=0)


def test_dlq_bounded_and_filtered():
    from skeleton.gate_plane.agent_edge import DeadLetter

    q = DeadLetterQueue(capacity=2)
    for i in range(3):
        q.put(DeadLetter(env(i), DeadLetterReason.POISON if i else DeadLetterReason.TTL_EXPIRED, 1, float(i)))
    assert len(q) == 2 and q.dropped == 1
    assert [d.envelope.message_id for d in q.list(reason=DeadLetterReason.POISON)] == [env(1).message_id, env(2).message_id]
    assert q.purge(older_than=2.0) == 1 and len(q) == 1
    assert q.stats()["by_reason"] == {"ttl_expired": 1, "poison": 2}


# -- bus ---------------------------------------------------------------------------------
def test_publish_assigns_gap_free_sequence_per_conversation(bus, clock):
    r = [bus.publish(e(i, clock)) for i in range(3)]
    other = bus.publish(e(0, clock, conv="conv-0002"))
    assert [x.sequence for x in r] == [1, 2, 3] and other.sequence == 1
    assert all(x.status is PublishStatus.ACCEPTED for x in r)
    assert [m.sequence for m in bus.peek("beta", "conv-0001")] == [1, 2, 3]


def test_duplicate_publish_suppressed_pending_and_after_ack(bus, clock):
    m = e(1, clock)
    assert bus.publish(m).accepted
    assert bus.publish(m).status is PublishStatus.DUPLICATE
    d = bus.pull("beta")[0]
    bus.ack(d.lease_id)
    assert bus.publish(m).status is PublishStatus.ALREADY_PROCESSED
    assert bus.depth() == 0


def test_idempotency_key_scoped_by_sender(bus, clock):
    a = e(1, clock, idempotency_key="order-0001")
    b = e(2, clock, idempotency_key="order-0001")
    c = e(3, clock, idempotency_key="order-0001", sender="gamma")
    assert bus.publish(a).accepted
    assert bus.publish(b).status is PublishStatus.DUPLICATE
    assert bus.publish(c).accepted


def test_expired_on_publish(bus, clock):
    m = env(1, now=clock.now() - 400, ttl_s=300)
    assert bus.publish(m).status is PublishStatus.EXPIRED


def test_strict_order_within_conversation_head_of_line(bus, clock):
    for i in range(3):
        bus.publish(e(i, clock))
    first = bus.pull("beta", max_messages=10)
    assert [d.envelope.sequence for d in first] == [1]  # only the head is eligible
    assert bus.pull("beta", max_messages=10) == []  # head leased -> conversation blocked
    bus.ack(first[0].lease_id)
    nxt = bus.pull("beta", max_messages=10)
    assert [d.envelope.sequence for d in nxt] == [2]


def test_independent_conversations_by_priority_then_fifo(bus, clock):
    bus.publish(e(0, clock, conv="conv-aaaa", priority=5))
    bus.publish(e(0, clock, conv="conv-bbbb", priority=1))
    bus.publish(e(0, clock, conv="conv-cccc", priority=5))
    got = bus.pull("beta", max_messages=3)
    assert [d.envelope.conversation_id for d in got] == ["conv-bbbb", "conv-aaaa", "conv-cccc"]
    assert bus.in_flight("beta") == 3


def test_nack_backoff_and_redelivery_preserves_order(bus, clock):
    bus.publish(e(0, clock))
    bus.publish(e(1, clock))
    d1 = bus.pull("beta")[0]
    assert bus.nack(d1.lease_id, error="boom") is None
    assert bus.pull("beta") == []  # backoff 1s, and seq 2 must wait behind seq 1
    clock.advance(1.01)
    d2 = bus.pull("beta")[0]
    assert d2.envelope.sequence == 1 and d2.attempt == 2 and d2.redelivery
    bus.ack(d2.lease_id)
    assert bus.pull("beta")[0].envelope.sequence == 2


def test_backoff_delay_capped():
    assert backoff_delay(0) == 0.0
    assert [backoff_delay(n, base_s=1, cap_s=8) for n in (1, 2, 3, 4, 5)] == [1, 2, 4, 8, 8]


def test_lease_expiry_redelivers_and_old_lease_is_stale(bus, clock):
    bus.publish(e(0, clock))
    d1 = bus.pull("beta", lease_s=2)[0]
    clock.advance(2.5)
    d2 = bus.pull("beta")[0]
    assert d2.envelope.message_id == d1.envelope.message_id and d2.attempt == 2
    with pytest.raises((StaleLease, UnknownLease)):
        bus.ack(d1.lease_id)
    bus.ack(d2.lease_id)
    with pytest.raises(UnknownLease):
        bus.ack(d2.lease_id)


def test_extend_lease_heartbeat(bus, clock):
    bus.publish(e(0, clock))
    d = bus.pull("beta", lease_s=2)[0]
    clock.advance(1.5)
    assert bus.extend(d.lease_id, lease_s=5) == pytest.approx(clock.now() + 5)
    clock.advance(3)
    assert bus.pull("beta") == []
    bus.ack(d.lease_id)


def test_max_attempts_dead_letters_and_conversation_advances(bus, clock):
    bus.publish(e(0, clock, max_attempts=2))
    bus.publish(e(1, clock))
    d = bus.pull("beta")[0]
    bus.nack(d.lease_id)
    clock.advance(5)
    d = bus.pull("beta")[0]
    letter = bus.nack(d.lease_id, error="still broken")
    assert letter is not None and letter.reason is DeadLetterReason.MAX_ATTEMPTS and letter.attempts == 2
    assert letter.last_error == "still broken"
    assert bus.pull("beta")[0].envelope.sequence == 2


def test_lease_expiry_counts_attempts_until_dlq(bus, clock):
    bus.publish(e(0, clock, max_attempts=2))
    bus.pull("beta", lease_s=1)
    clock.advance(2)
    bus.pull("beta", lease_s=1)
    clock.advance(2)
    assert bus.pull("beta") == []
    assert bus.dlq.get(e(0).message_id).reason is DeadLetterReason.MAX_ATTEMPTS


def test_ttl_expiry_dead_letters(bus, clock):
    bus.publish(e(0, clock, ttl_s=5))
    bus.publish(e(1, clock, ttl_s=500))
    clock.advance(6)
    got = bus.pull("beta")
    assert [d.envelope.sequence for d in got] == [2]
    assert bus.dlq.get(e(0).message_id).reason is DeadLetterReason.TTL_EXPIRED


def test_reject_and_poison_go_to_dlq(bus, clock):
    bus.publish(e(0, clock))
    bus.publish(e(0, clock, conv="conv-0002"))
    a, b = bus.pull("beta", max_messages=2)
    assert bus.nack(a.lease_id, retry=False).reason is DeadLetterReason.REJECTED
    assert bus.nack(b.lease_id, poison=True).reason is DeadLetterReason.POISON
    assert bus.depth() == 0 and len(bus.dlq) == 2


def test_replay_from_dlq(bus, clock):
    m = e(0, clock, max_attempts=1)
    bus.publish(m)
    bus.nack(bus.pull("beta")[0].lease_id)
    assert bus.dlq.get(m.message_id) is not None
    res = bus.replay(m.message_id)
    assert res.accepted and bus.dlq.get(m.message_id) is None
    d = bus.pull("beta")[0]
    assert d.envelope.message_id == m.message_id and d.attempt == 1
    with pytest.raises(KeyError):
        bus.replay("msg-missing-0000")


def test_topic_filter_and_batch_limits(bus, clock):
    bus.publish(e(0, clock, conv="conv-aaaa", topic="a.one"))
    bus.publish(e(0, clock, conv="conv-bbbb", topic="b.two"))
    assert [d.envelope.topic for d in bus.pull("beta", max_messages=5, topics=["b.two"])] == ["b.two"]
    with pytest.raises(ValueError):
        bus.pull("beta", max_messages=0)
    with pytest.raises(ValueError):
        bus.pull("beta", lease_s=10_000)
    assert bus.pull("nobody") == []


def test_capacity_rejects_when_full(clock):
    b = AgentBus(clock=clock, max_pending_per_agent=2)
    b.publish(e(0, clock))
    b.publish(e(1, clock))
    with pytest.raises(BusFull):
        b.publish(e(2, clock))


def test_dispatch_acks_nacks_and_poisons(bus, clock):
    for i in range(3):
        bus.publish(e(0, clock, conv=f"conv-{i:04d}"))

    def handler(m):
        if m.conversation_id == "conv-0001":
            raise RuntimeError("transient")
        if m.conversation_id == "conv-0002":
            raise PoisonMessage("bad schema")

    stats = bus.dispatch("beta", handler)
    assert stats == {"delivered": 3, "acked": 1, "nacked": 1, "dead": 1}
    assert bus.depth("beta") == 1


def test_listeners_never_break_delivery(bus, clock):
    events = []
    bus.add_listener(lambda name, data: events.append(name))
    bus.add_listener(lambda name, data: 1 / 0)
    bus.publish(e(0, clock))
    bus.ack(bus.pull("beta")[0].lease_id)
    assert events == ["published", "delivered", "acked"]
    assert bus.stats()["events"]["acked"] == 1


def test_lease_owner(bus, clock):
    bus.publish(e(0, clock))
    d = bus.pull("beta")[0]
    assert bus.lease_owner(d.lease_id) == "beta"
    bus.ack(d.lease_id)
    assert bus.lease_owner(d.lease_id) is None
