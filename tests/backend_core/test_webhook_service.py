import pytest

from core.core_v1.concurrency import etag
from core.core_v1.errors import CoreError
from core.core_v1.models import SubscriptionDraft
from core.core_v1.service import MAX_ACTIVE_PER_TENANT

from ._support import ADMIN, OTHER, VIEWER, memory_service


def _create(svc, scope=ADMIN, filters=()):
    return svc.create(scope, SubscriptionDraft("https://hooks.example.com/x", tuple(filters)))


def test_create_returns_secret_once_and_tenant_isolation():
    svc, _, _ = memory_service()
    c = _create(svc)
    assert c.secret.startswith("whsec_") and c.subscription.version == 1
    assert svc.get(ADMIN, c.subscription.webhook_id) == c.subscription
    with pytest.raises(CoreError) as ei:
        svc.get(OTHER, c.subscription.webhook_id)
    assert ei.value.http_status == 404


def test_viewer_cannot_write():
    svc, _, _ = memory_service()
    with pytest.raises(CoreError) as ei:
        _create(svc, VIEWER)
    assert ei.value.http_status == 403


def test_update_requires_matching_etag():
    svc, clock, _ = memory_service()
    s = _create(svc).subscription
    with pytest.raises(CoreError) as ei:
        svc.update(ADMIN, s.webhook_id, {"description": "d"}, None)
    assert ei.value.http_status == 428
    clock.advance(1)
    u = svc.update(ADMIN, s.webhook_id, {"description": "d"}, etag(s.webhook_id, 1))
    assert u.version == 2 and u.description == "d"
    with pytest.raises(CoreError) as ei:
        svc.update(ADMIN, s.webhook_id, {"description": "e"}, etag(s.webhook_id, 1))
    assert ei.value.http_status == 412
    with pytest.raises(CoreError):
        svc.update(ADMIN, s.webhook_id, {"secret_ids": []}, "*")


def test_active_limit():
    svc, _, _ = memory_service()
    for _ in range(MAX_ACTIVE_PER_TENANT):
        _create(svc)
    with pytest.raises(CoreError) as ei:
        _create(svc)
    assert ei.value.code == "CORE.WEBHOOK.LIMIT_REACHED"
    _create(svc, OTHER)  # other tenant unaffected


def test_list_pagination_walks_all():
    svc, clock, _ = memory_service()
    ids = []
    for _ in range(5):
        clock.advance(1)
        ids.append(_create(svc).subscription.webhook_id)
    seen, cursor = [], None
    while True:
        p = svc.list(ADMIN, 2, cursor)
        seen += [s.webhook_id for s in p.items]
        cursor = p.next_cursor
        if not cursor:
            break
    assert seen == ids
    with pytest.raises(CoreError):
        svc.list(OTHER, 2, svc.list(ADMIN, 2, None).next_cursor)


def test_publish_fanout_and_dedupe():
    svc, _, _ = memory_service()
    _create(svc, filters=["project.*"])
    _create(svc, filters=["build.done"])
    _create(svc)  # no filters = all
    e, n, dup = svc.publish(ADMIN, "project.created", {"id": 1}, "k1")
    assert (n, dup) == (2, False)
    e2, n2, dup2 = svc.publish(ADMIN, "project.created", {"id": 1}, "k1")
    assert (e2.event_id, n2, dup2) == (e.event_id, 0, True)


@pytest.mark.parametrize("etype,data", [("bad", {}), ("a.b", []), ("a.b", {"x": "y" * 70000}),
                                        ("a.b", {"x": float("nan")})])
def test_publish_validation(etype, data):
    svc, _, _ = memory_service()
    with pytest.raises(CoreError):
        svc.publish(ADMIN, etype, data)


def test_delete_is_soft_and_stops_fanout():
    svc, _, _ = memory_service()
    s = _create(svc).subscription
    d = svc.delete(ADMIN, s.webhook_id, etag(s.webhook_id, 1))
    assert not d.active and d.disabled_reason == "deleted"
    assert svc.publish(ADMIN, "a.b", {})[1] == 0


def test_rotate_secret_keeps_previous():
    svc, _, _ = memory_service()
    c = _create(svc)
    r = svc.rotate_secret(ADMIN, c.subscription.webhook_id, etag(c.subscription.webhook_id, 1))
    assert r.secret != c.secret and len(r.subscription.secret_ids) == 2
    assert r.subscription.secret_ids[1] == c.subscription.secret_ids[0]
