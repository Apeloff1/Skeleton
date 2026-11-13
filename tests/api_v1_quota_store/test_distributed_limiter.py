import pytest

from skeleton.api.v1_edge.envelope import EdgeError
from skeleton.api.v1_edge.quota_store import (CODE_RATE_LIMITED, CODE_STORE_DOWN, CODE_TOO_COSTLY,
                                              DistributedQuotas, InMemoryCounterStore, Limit,
                                              QuotaPlan, QuotaTelemetry, RemoteCounterStore)
from skeleton.api.v1_edge.quota_store.testing import FakeRemoteClient, FlakyCounterStore
from skeleton.api.v1_edge.quotas import QuotaPolicy, TenantQuotas
from skeleton.api.v1_edge.registry import RouteSpec

POST = RouteSpec("POST", "/projects", quota_class="writes")
GET = RouteSpec("GET", "/projects/{pid}")


def build(now, **kw):
    plan = kw.pop("plan", None) or QuotaPlan(
        {"default": Limit(1, 3), "writes": Limit(1, 2)},
        route_limits={"POST /projects": Limit(1, 3)},
        tenant_route_limits={"GET /projects/{pid}": Limit(1, 2)},
        method_cost=kw.pop("cost", {}))
    store = kw.pop("store", None)
    if store is None:
        store = InMemoryCounterStore(clock=lambda: now[0])
    return DistributedQuotas(plan, store=store, **kw)


def test_empty_injected_counter_store_is_not_replaced():
    # An empty store defines __len__ and is falsy. Caller-supplied counters
    # must retain their clock, identity, and process-local quota custody.
    now = [0.0]
    store = InMemoryCounterStore(clock=lambda: now[0])
    q = build(now, store=store)
    assert q.store is store
    assert len(store) == 0
    assert q.check_request("t1", GET, "GET")["ratelimit-remaining"] == "1"
    assert len(store) == 2
    q.check_request("t1", GET, "GET")
    with pytest.raises(EdgeError) as denied:
        q.check_request("t1", GET, "GET")
    assert denied.value.code == CODE_RATE_LIMITED
    now[0] = 1.0
    assert q.check_request("t1", GET, "GET")["ratelimit-remaining"] == "0"


def test_tenant_bucket_and_headers():
    now = [0.0]
    q = build(now)
    h = q.check_request("t1", GET, "GET")
    assert h["ratelimit-remaining"] == "1" and h["ratelimit-limit"] == "2"
    q.check_request("t1", GET, "GET")
    with pytest.raises(EdgeError) as e:
        q.check_request("t1", GET, "GET")
    err = e.value
    assert err.status == 429 and err.code == CODE_RATE_LIMITED
    assert err.headers["retry-after"] == "1" and err.headers["x-ratelimit-scope"] == "tenant_route"
    assert q.check_request("t2", GET, "GET")["ratelimit-remaining"] == "1"  # isolated
    now[0] = 1.0
    q.check_request("t1", GET, "GET")


def test_route_bucket_shared_across_tenants():
    now = [0.0]
    q = build(now)
    q.check_request("a", POST, "POST")
    q.check_request("b", POST, "POST")
    q.check_request("c", POST, "POST")
    with pytest.raises(EdgeError) as e:
        q.check_request("d", POST, "POST")
    assert e.value.context["scope"] == "route"


def test_narrow_denial_does_not_spend_broad_bucket():
    now = [0.0]
    plan = QuotaPlan({"default": Limit(0.01, 5)},
                     tenant_route_limits={"GET /projects/{pid}": Limit(0.01, 1)})
    q = build(now, plan=plan)
    q.check_request("t", GET, "GET")
    for _ in range(3):
        with pytest.raises(EdgeError):
            q.check_request("t", GET, "GET")
    assert q.remaining("t", "default", "GET", "/projects/{pid}") == {"tenant_route": 0, "tenant": 4}


def test_method_cost_and_too_costly():
    now = [0.0]
    q = build(now, cost={"POST": 2})
    assert q.check_request("t", POST, "POST")["ratelimit-remaining"] == "0"
    q2 = build(now, cost={"POST": 9})
    with pytest.raises(EdgeError) as e:
        q2.check_request("t", POST, "POST")
    assert e.value.code == CODE_TOO_COSTLY and e.value.status == 429


def test_store_down_fails_closed_with_503_and_audit():
    now = [0.0]
    flaky = FlakyCounterStore(InMemoryCounterStore(clock=lambda: now[0]))
    tel = QuotaTelemetry()
    q = build(now, store=flaky, telemetry=tel)
    q.check_request("t", GET, "GET")
    flaky.down = True
    with pytest.raises(EdgeError) as e:
        q.check_request("t", GET, "GET")
    assert e.value.status == 503 and e.value.code == CODE_STORE_DOWN
    assert e.value.headers["retry-after"] == "1"
    ev = tel.recent("quota.store_unavailable")
    assert len(ev) == 1 and ev[0]["backend"] == "flaky" and "t" != ev[0]["tenant_ref"]
    with pytest.raises(EdgeError) as e2:
        q.remaining("t", "default", "GET", "/projects/{pid}")
    assert e2.value.status == 503
    assert not q.health_check()


def test_remote_store_outage_fails_closed():
    now = [0.0]
    client = FakeRemoteClient()
    q = build(now, store=RemoteCounterStore(client, clock=lambda: now[0]))
    assert q.check_request("t", GET, "GET")
    client.down = True
    with pytest.raises(EdgeError) as e:
        q.check_request("t", GET, "GET")
    assert e.value.status == 503


def test_two_edges_share_quota_through_remote():
    now = [0.0]
    client = FakeRemoteClient()
    e1 = build(now, store=RemoteCounterStore(client, clock=lambda: now[0]))
    e2 = build(now, store=RemoteCounterStore(client, clock=lambda: now[0]))
    e1.check_request("t", GET, "GET")
    e2.check_request("t", GET, "GET")
    with pytest.raises(EdgeError):
        e1.check_request("t", GET, "GET")


def test_extends_legacy_tenant_quotas():
    now = [0.0]
    legacy = TenantQuotas({"default": QuotaPolicy(100, 100, window_s=60, window_limit=2)},
                          clock=lambda: now[0])
    q = build(now, legacy=legacy)
    h = q.check_request("t", GET, "GET")
    assert h["x-quota-remaining"] == "1" and h["ratelimit-remaining"] == "1"
    q.check_request("t2", GET, "GET")
    q.check_request("t", GET, "GET")
    with pytest.raises(EdgeError) as e:
        q.check_request("t", GET, "GET")
    assert e.value.code == "EDGE.QUOTA.EXHAUSTED"  # legacy window still enforced


def test_back_compat_check_and_exempt():
    now = [0.0]
    plan = QuotaPlan({"default": Limit(1, 1)}, exempt_tenants=frozenset({"ops"}))
    tel = QuotaTelemetry()
    q = build(now, plan=plan, telemetry=tel)
    assert q.check("t", "default")["ratelimit-remaining"] == "0"
    with pytest.raises(EdgeError):
        q.check("t", "default")
    for _ in range(5):
        assert q.check_request("ops", GET, "GET") == {}
    assert len(tel.recent("quota.exempt")) == 5


def test_reset_is_audited_and_skips_shared_route_bucket():
    now = [0.0]
    tel = QuotaTelemetry()
    q = build(now, telemetry=tel)
    q.check_request("t", POST, "POST")
    q.check_request("t", POST, "POST")
    with pytest.raises(EdgeError):
        q.check_request("t", POST, "POST")
    assert q.reset("t", "writes", "POST", "/projects", actor="ops@test") == ["tenant"]
    assert q.remaining("t", "writes", "POST", "/projects") == {"route": 1, "tenant": 2}
    ev = tel.recent("quota.reset")[0]
    assert ev["actor"] == "ops@test" and ev["scopes"] == ["tenant"]
    assert q.health_check()
