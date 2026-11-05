import pytest

from core.core_v1.clock import FakeClock
from core.core_v1.concurrency import etag
from core.core_v1.idempotency import Idempotency, StoredResponse
from core.core_v1.models import DeliveryStatus, SubscriptionDraft
from core.core_v1.ports import TransportResult
from core.core_v1.sqlite_store import MIGRATIONS, SqliteIdempotencyStore, migrate, open_database
from core.core_v1.transport import AllowAllPolicy, RecordingTransport
from core.core_v1_webhooks import build_runtime

from ._support import ADMIN, OTHER


@pytest.fixture
def rt(tmp_path):
    clock = FakeClock()
    t = RecordingTransport()
    r = build_runtime(str(tmp_path / "core.db"), clock=clock, transport=t,
                      url_policy=AllowAllPolicy(), cursor_key=b"k" * 32)
    return r, clock, t


def test_migrations_idempotent(tmp_path):
    db = open_database(str(tmp_path / "m.db"))
    assert migrate(db) == []
    versions = [r[0] for r in db.query("SELECT version FROM core_v1_migrations ORDER BY version")]
    assert versions == [m[0] for m in MIGRATIONS]


def test_end_to_end_sqlite(rt):
    r, clock, t = rt
    svc = r.webhooks
    c = svc.create(ADMIN, SubscriptionDraft("https://h.example.com/x", ("a.*",), max_attempts=2))
    wid = c.subscription.webhook_id
    assert svc.get(ADMIN, wid) == c.subscription
    with pytest.raises(Exception):
        svc.get(OTHER, wid)
    u = svc.update(ADMIN, wid, {"description": "d"}, etag(wid, 1))
    assert svc.get(ADMIN, wid).version == u.version == 2
    e, n, _ = svc.publish(ADMIN, "a.b", {"k": [1, 2]}, "dk")
    assert n == 1 and svc.publish(ADMIN, "a.b", {"k": 0}, "dk")[2] is True
    t.responses = [TransportResult(500), TransportResult(500)]
    assert svc.dispatch_due().retried == 1
    clock.advance(10_000)
    assert svc.dispatch_due().dead == 1
    d = svc.list_deliveries(ADMIN, wid, 10, None, None).items[0]
    got, attempts = svc.get_delivery(ADMIN, d.delivery_id)
    assert got.status is DeliveryStatus.DEAD and len(attempts) == 2
    replay = svc.replay(ADMIN, d.delivery_id)
    assert svc.dispatch_due().succeeded == 1
    assert svc.get_delivery(ADMIN, replay.delivery_id)[0].status is DeliveryStatus.SUCCEEDED


def test_sqlite_pagination(rt):
    r, clock, _ = rt
    ids = []
    for _ in range(5):
        clock.advance(1)
        ids.append(r.webhooks.create(ADMIN, SubscriptionDraft("https://h.example.com/x")).subscription.webhook_id)
    seen, cur = [], None
    while True:
        p = r.webhooks.list(ADMIN, 2, cur)
        seen += [s.webhook_id for s in p.items]
        cur = p.next_cursor
        if not cur:
            break
    assert seen == ids


def test_sqlite_idempotency_store(tmp_path):
    clock = FakeClock()
    store = SqliteIdempotencyStore(open_database(str(tmp_path / "i.db")))
    idem = Idempotency(store, clock)
    r1, _ = idem.run("key-00001", ("t", "a", "r"), "fp", lambda: StoredResponse(201, {"x": 1}))
    r2, rep = idem.run("key-00001", ("t", "a", "r"), "fp", lambda: StoredResponse(201, {"x": 2}))
    assert rep and r2.body == {"x": 1}
    clock.advance(10 ** 6)
    assert store.purge_expired(clock.now()) == 1
