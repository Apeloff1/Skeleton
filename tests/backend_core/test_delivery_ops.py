"""Delivery log, DLQ and per-subscription retry policy — service level,
run against both the in-memory and SQLite adapters."""
import pytest

from core.core_v1.clock import FakeClock
from core.core_v1.delivery_ops import DeliveryOps, parse_set, parse_time
from core.core_v1.errors import CoreError
from core.core_v1.log_store import MemoryDeliveryLog, MemoryRetryPolicyRepository
from core.core_v1.models import Scope, SubscriptionDraft
from core.core_v1.pagination import CursorCodec
from core.core_v1.ports import TransportResult
from core.core_v1.retry import RetryPolicy, policy_from_dict
from core.core_v1.transport import AllowAllPolicy, RecordingTransport
from core.core_v1_webhooks import build_runtime

from ._support import ADMIN, OTHER, VIEWER, memory_service

EDITOR = Scope("t1", "e@example.com", "editor")
FAIL = TransportResult(500, "", 1.0)


@pytest.fixture(params=["memory", "sqlite"])
def env(request, tmp_path):
    clock, transport = FakeClock(), RecordingTransport()
    if request.param == "memory":
        policies = MemoryRetryPolicyRepository()
        svc, _, _ = memory_service(clock=clock, transport=transport, retry_policies=policies)
        ops = DeliveryOps(webhooks=svc, log=MemoryDeliveryLog(svc.deliveries), policies=policies,
                          cursor_codec=CursorCodec(b"k" * 32))
    else:
        rt = build_runtime(str(tmp_path / "o.db"), clock=clock, transport=transport,
                           url_policy=AllowAllPolicy(), cursor_key=b"k" * 32, key_provider=None)
        svc, ops = rt.webhooks, rt.ops
    return ops, svc, clock, transport


def _hook(svc, scope=ADMIN, max_attempts=3):
    return svc.create(scope, SubscriptionDraft("https://h.example.com/x", (), max_attempts=max_attempts)
                      ).subscription.webhook_id


def _kill_all(svc, clock, transport, rounds=10):
    transport.responder = lambda call: FAIL
    for _ in range(rounds):
        svc.dispatch_due()
        clock.advance(7 * 86400)
    transport.responder = None


# ------------------------------------------------------------------ parsing
def test_parse_time_and_set():
    assert parse_time("2027-01-01T00:00:00Z", "since") == 1798761600.0
    assert parse_time("1798761600", "since") == parse_time(1798761600, "since") == 1798761600.0
    assert parse_time(None, "x") is None and parse_time("", "x") is None
    for bad in ("2027-01-01T00:00:00", "yesterday", True, -5, float("nan")):
        with pytest.raises(CoreError) as ei:
            parse_time(bad, "since")
        assert ei.value.code == "CORE.DELIVERY_LOG.INVALID_FILTER"
    assert parse_set("dead, failed", frozenset({"dead", "failed"}), "status") == ("dead", "failed")
    with pytest.raises(CoreError):
        parse_set("bogus", frozenset({"dead"}), "status")


# ------------------------------------------------------------- delivery log
def test_log_filters_and_pagination(env):
    ops, svc, clock, _ = env
    w1, w2 = _hook(svc), _hook(svc)
    events = []
    for i in range(5):
        clock.advance(1)
        ev, _, _ = svc.publish(ADMIN, "a.b", {"i": i})
        events.append(ev.event_id)
    svc.dispatch_due()
    all_ids, cursor = [], None
    while True:
        page = ops.deliveries(ADMIN, limit=3, cursor=cursor)
        all_ids += [d.delivery_id for d in page.items]
        if not page.next_cursor:
            break
        cursor = page.next_cursor
    assert len(all_ids) == len(set(all_ids)) == 10
    assert len(ops.deliveries(ADMIN, limit=50, webhook_id=w1).items) == 5
    assert len(ops.deliveries(ADMIN, limit=50, event_id=events[0]).items) == 2
    assert len(ops.deliveries(ADMIN, limit=50, status="succeeded").items) == 10
    assert ops.deliveries(ADMIN, limit=50, status="dead").items == ()
    t3 = svc.events.get("t1", events[2]).created_at
    win = ops.deliveries(ADMIN, limit=50, since=t3, until=t3 + 1)
    assert {d.event_id for d in win.items} == {events[2]}
    assert ops.deliveries(OTHER, limit=50).items == ()  # tenant scoped


def test_cursor_bound_to_filter(env):
    ops, svc, clock, _ = env
    w = _hook(svc)
    for _ in range(3):
        clock.advance(1)
        svc.publish(ADMIN, "a.b", {})
    cur = ops.deliveries(ADMIN, limit=1, webhook_id=w).next_cursor
    with pytest.raises(CoreError) as ei:
        ops.deliveries(ADMIN, limit=1, cursor=cur)
    assert ei.value.code == "CORE.PAGINATION.INVALID_CURSOR"
    with pytest.raises(CoreError):
        ops.deliveries(OTHER, limit=1, cursor=cur)


def test_log_unknown_parents_are_404_and_cross_tenant(env):
    ops, svc, _, _ = env
    w = _hook(svc)
    for kw in ({"webhook_id": w}, {"event_id": "evt_nope"}):
        with pytest.raises(CoreError) as ei:
            ops.deliveries(OTHER, limit=5, **kw)
        assert ei.value.http_status == 404
    with pytest.raises(CoreError) as ei:
        ops.deliveries(ADMIN, limit=5, since=10, until=5)
    assert ei.value.code == "CORE.DELIVERY_LOG.INVALID_FILTER"
    with pytest.raises(CoreError):
        ops.deliveries(ADMIN, limit=5, time_field="lease_until")


def test_attempt_log(env):
    ops, svc, clock, transport = env
    w = _hook(svc, max_attempts=3)
    svc.publish(ADMIN, "a.b", {})
    _kill_all(svc, clock, transport)
    page = ops.attempts(ADMIN, limit=2, webhook_id=w)
    assert len(page.items) == 2 and page.next_cursor
    rest = ops.attempts(ADMIN, limit=10, webhook_id=w, cursor=page.next_cursor)
    outcomes = [r.attempt.outcome for r in page.items + rest.items]
    assert outcomes == ["retry", "retry", "dead"]
    assert [r.attempt.outcome for r in ops.attempts(ADMIN, limit=10, outcome="dead").items] == ["dead"]
    did = page.items[0].attempt.delivery_id
    assert len(ops.attempts(ADMIN, limit=10, delivery_id=did).items) == 3
    with pytest.raises(CoreError):
        ops.attempts(OTHER, limit=10, delivery_id=did)
    assert ops.attempts(OTHER, limit=10).items == ()


# ---------------------------------------------------------------------- DLQ
def test_dlq_redrive_by_ids_and_filter(env):
    ops, svc, clock, transport = env
    w = _hook(svc, max_attempts=1)
    for _ in range(3):
        svc.publish(ADMIN, "a.b", {})
    _kill_all(svc, clock, transport, rounds=1)
    dead = ops.dlq(ADMIN, limit=10).items
    assert len(dead) == 3
    rep = ops.redrive(ADMIN, {"delivery_ids": [dead[0].delivery_id, dead[0].delivery_id, "dlv_nope"]})
    assert len(rep.redriven) == 1 and rep.skipped == (("dlv_nope", "not_found"),)
    # second redrive of the same id is skipped while the replay is open
    rep2 = ops.redrive(ADMIN, {"delivery_ids": [dead[0].delivery_id]})
    assert rep2.redriven == () and rep2.skipped[0][1] == "replay_in_progress"
    rep3 = ops.redrive(ADMIN, {"webhook_id": w})
    assert len(rep3.redriven) == 2 and rep3.skipped[0][1] == "replay_in_progress"
    assert svc.dispatch_due().succeeded == 3
    # replays done -> original can be redriven again
    assert len(ops.redrive(ADMIN, {"delivery_ids": [dead[0].delivery_id]}).redriven) == 1


def test_redrive_validation_and_authz(env):
    ops, svc, clock, transport = env
    _hook(svc, max_attempts=1)
    svc.publish(ADMIN, "a.b", {})
    svc.dispatch_due()
    ok = ops.deliveries(ADMIN, limit=1).items[0].delivery_id
    assert ops.redrive(ADMIN, {"delivery_ids": [ok]}).skipped == ((ok, "not_dead"),)
    with pytest.raises(CoreError) as ei:
        ops.redrive(VIEWER, {"delivery_ids": [ok]})
    assert ei.value.http_status == 403
    for bad in ({"delivery_ids": []}, {"delivery_ids": [ok], "webhook_id": "x"}, {"limit": 0},
                {"limit": 101}, {"nope": 1}, []):
        with pytest.raises(CoreError) as ei:
            ops.redrive(ADMIN, bad)
        assert ei.value.code == "CORE.DLQ.INVALID"
    # other tenant can't see our dead letters
    assert ops.redrive(OTHER, {"delivery_ids": [ok]}).skipped == ((ok, "not_found"),)


def test_purge_by_age(env):
    ops, svc, clock, transport = env
    _hook(svc, max_attempts=1)
    svc.publish(ADMIN, "a.b", {})
    _kill_all(svc, clock, transport, rounds=1)
    old = ops.dlq(ADMIN, limit=5).items[0].delivery_id
    clock.advance(10 * 86400)
    svc.publish(ADMIN, "a.b", {})
    _kill_all(svc, clock, transport, rounds=1)  # advances 7d after the kill
    with pytest.raises(CoreError) as ei:
        ops.purge(EDITOR, {"older_than_seconds": 86400})
    assert ei.value.http_status == 403
    with pytest.raises(CoreError):
        ops.purge(ADMIN, {"older_than_seconds": 60})
    res = ops.purge(ADMIN, {"older_than_seconds": 8 * 86400})
    assert res["delivery_ids"] == [old] and res["purged"] == 1
    assert ops.attempts(ADMIN, limit=10, outcome="dead").items[0].attempt.delivery_id != old
    assert len(ops.dlq(ADMIN, limit=5).items) == 1
    assert ops.purge(OTHER, {"older_than_seconds": 3600})["purged"] == 0


# ----------------------------------------------------------- retry policy
def test_policy_validation():
    base = RetryPolicy()
    p = policy_from_dict({"base_seconds": 5, "max_age_seconds": 600}, base)
    assert p.base_seconds == 5 and p.max_age_seconds == 600 and p.factor == base.factor
    for bad in ({"base_seconds": 0}, {"factor": True}, {"cap_seconds": 2, "base_seconds": 10},
                {"max_age_seconds": 1}, {"zzz": 1}, []):
        with pytest.raises(CoreError) as ei:
            policy_from_dict(bad, base)
        assert ei.value.code == "CORE.RETRY_POLICY.INVALID"


def test_policy_crud(env):
    ops, svc, _, _ = env
    w = _hook(svc)
    p, override = ops.get_policy(ADMIN, w)
    assert not override and p == svc.retry
    ops.put_policy(ADMIN, w, {"base_seconds": 1, "factor": 1, "cap_seconds": 1})
    p, override = ops.get_policy(ADMIN, w)
    assert override and p.base_seconds == 1
    with pytest.raises(CoreError) as ei:
        ops.put_policy(VIEWER, w, {"base_seconds": 1})
    assert ei.value.http_status == 403
    with pytest.raises(CoreError) as ei:
        ops.get_policy(OTHER, w)
    assert ei.value.http_status == 404
    ops.delete_policy(ADMIN, w)
    with pytest.raises(CoreError) as ei:
        ops.delete_policy(ADMIN, w)
    assert ei.value.code == "CORE.RETRY_POLICY.NOT_FOUND" and ei.value.http_status == 404


def test_per_subscription_policy_drives_backoff(env):
    ops, svc, clock, transport = env
    fast, slow = _hook(svc, max_attempts=5), _hook(svc, max_attempts=5)
    ops.put_policy(ADMIN, fast, {"base_seconds": 1, "factor": 1, "cap_seconds": 1})
    transport.responder = lambda call: FAIL
    svc.publish(ADMIN, "a.b", {})
    svc.dispatch_due()
    by_hook = {d.webhook_id: d for d in ops.deliveries(ADMIN, limit=10).items}
    assert by_hook[fast].next_attempt_at - clock.now() <= 1.0
    assert by_hook[slow].next_attempt_at - clock.now() >= svc.retry.base_seconds / 2


def test_max_age_dead_letters_early(env):
    ops, svc, clock, transport = env
    w = _hook(svc, max_attempts=20)
    ops.put_policy(ADMIN, w, {"base_seconds": 100, "factor": 2, "cap_seconds": 3600,
                              "max_age_seconds": 300})
    svc.publish(ADMIN, "a.b", {})
    _kill_all(svc, clock, transport, rounds=6)
    d = ops.deliveries(ADMIN, limit=1).items[0]
    assert d.status.value == "dead" and d.attempts < 20 and "policy:max_age" in d.last_error
