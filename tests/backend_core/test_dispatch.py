from core.core_v1 import signing
from core.core_v1.models import DeliveryStatus, SubscriptionDraft
from core.core_v1.ports import TransportResult
from core.core_v1.transport import RecordingTransport

from ._support import ADMIN, memory_service


def _setup(responses=(), max_attempts=3):
    t = RecordingTransport(list(responses))
    svc, clock, _ = memory_service(transport=t)
    c = svc.create(ADMIN, SubscriptionDraft("https://h.example.com/x", max_attempts=max_attempts))
    svc.publish(ADMIN, "a.b", {"v": 1})
    return svc, clock, t, c


def test_success_signed_with_headers():
    svc, clock, t, c = _setup()
    r = svc.dispatch_due()
    assert (r.claimed, r.succeeded) == (1, 1)
    call = t.calls[0]
    assert call.headers["Skeleton-Event-Type"] == "a.b"
    assert call.headers["Skeleton-Delivery-Attempt"] == "1"
    assert signing.verify(call.headers[signing.HEADER], call.body,
                          signing.secret_bytes(c.secret), clock.now())
    assert svc.dispatch_due().claimed == 0


def test_retry_then_dead_letter():
    svc, clock, t, c = _setup([TransportResult(503)] * 3, max_attempts=3)
    assert svc.dispatch_due().retried == 1
    assert svc.dispatch_due().claimed == 0  # not due yet
    clock.advance(3600)
    assert svc.dispatch_due().retried == 1
    clock.advance(3600)
    assert svc.dispatch_due().dead == 1
    page = svc.list_deliveries(ADMIN, c.subscription.webhook_id, 10, None, "dead")
    d, attempts = svc.get_delivery(ADMIN, page.items[0].delivery_id)
    assert d.status is DeliveryStatus.DEAD and [a.outcome for a in attempts] == ["retry", "retry", "dead"]


def test_permanent_failure_dead_immediately():
    svc, _, _, _ = _setup([TransportResult(400)])
    assert svc.dispatch_due().dead == 1


def test_expired_lease_is_reclaimed_and_stale_complete_rejected():
    svc, clock, t, _ = _setup()
    leased = svc.deliveries.claim_due(clock.now(), 60, 10)
    assert len(leased) == 1 and svc.dispatch_due().claimed == 0
    clock.advance(61)
    assert svc.dispatch_due().succeeded == 1
    assert svc._attempt(leased[0]) == "stale"


def test_replay_dead_delivery():
    svc, clock, t, c = _setup([TransportResult(410)])
    svc.dispatch_due()
    dead = svc.list_deliveries(ADMIN, c.subscription.webhook_id, 10, None, None).items[0]
    new = svc.replay(ADMIN, dead.delivery_id)
    assert new.replay_of == dead.delivery_id and new.status is DeliveryStatus.PENDING
    assert svc.dispatch_due().succeeded == 1


def test_inactive_subscription_dead_letters_pending():
    svc, _, t, c = _setup()
    svc.update(ADMIN, c.subscription.webhook_id, {"active": False}, "*")
    r = svc.dispatch_due()
    assert r.dead == 1 and t.calls == []
