"""Recovered API v1 edge adversarial quarantine boundaries."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import pytest
from skeleton.api.v1_edge.auth import ApiKeyStore, EdgeAuthenticator
from skeleton.api.v1_edge.envelope import EdgeError
from skeleton.api.v1_edge.idempotency import IdempotencyCache
from skeleton.api.v1_edge.registry import RouteSpec
from skeleton.api.v1_edge.webhook_ingress import WebhookIngressVerifier, sign

def test_public_tenant_cannot_be_spoofed():
    auth = EdgeAuthenticator()
    principal = auth.enforce(RouteSpec("GET", "/ping", auth="public"),
        {"headers": [(b"x-tenant-id", b"victim-tenant")]})
    assert principal.method == "anonymous" and principal.tenant == "public"

def test_key_minimum_secret_no_identifier_reuse():
    keys=ApiKeyStore()
    with pytest.raises(ValueError): keys.add("x","guess",subject="u",tenant="t")
    key=keys.add("x","q"*32,subject="u",tenant="t")
    assert keys.verify(key) is not None
    with pytest.raises(ValueError): keys.add("x","z"*32,subject="u",tenant="t")

def test_simultaneous_idempotency_requests_cannot_both_execute():
    cache=IdempotencyCache(max_entries=1)
    def request(_):
        try:
            cache.begin("key","a"*64)
            return "leader"
        except EdgeError as e:
            return e.code
    with ThreadPoolExecutor(max_workers=16) as pool:
        result=list(pool.map(request,range(100)))
    assert result.count("leader")==1
    assert all(x=="leader" or x=="EDGE.IDEMPOTENCY.IN_FLIGHT" for x in result)
    with pytest.raises(EdgeError) as held:
        cache.begin("other","b"*64)
    assert held.value.code=="EDGE.IDEMPOTENCY.CAPACITY"

def test_webhook_no_replay_eviction_and_strict_timestamp():
    key=b"k"*32
    clock=lambda:1000.
    guard=WebhookIngressVerifier({"gh":key},clock=clock,replay_capacity=1)
    first=sign(key,1000,b"one")
    assert guard.verify("gh",first,b"one")==1000
    with pytest.raises(EdgeError) as capacity:
        guard.verify("gh",sign(key,1000,b"two"),b"two")
    assert capacity.value.code=="EDGE.WEBHOOK.REPLAY_CAPACITY"
    with pytest.raises(EdgeError) as replay:
        guard.verify("gh",first,b"one")
    assert replay.value.code=="EDGE.WEBHOOK.REPLAY"
    for sig in ("t=1000,t=1000,v1="+first.split("v1=")[1],
                "t=1000,v1=nan","t=1000,v1="+first.split("v1=")[1]+",hack=true"):
        with pytest.raises(EdgeError):
            guard.verify("gh",sig,b"one")
