"""Pack F egress gateway — signed callbacks, allowlist/SSRF, retries, redelivery, DLQ."""

from __future__ import annotations

import json
import random

import pytest

from skeleton.gate_plane.egress import (
    Callback,
    DeadLetter,
    DeadLetterQueue,
    DeliveryOutcome,
    EgressAllowlist,
    EgressDenyReason,
    EgressGateway,
    ScriptedTransport,
    SecretSet,
    Subscription,
    TransportResponse,
    WebhookSignatureError,
    WebhookSigner,
    WebhookVerifier,
    decode_secret,
    encode_secret,
    is_public_address,
)
from skeleton.gate_plane.egress.transport import TransportRequest, UrllibTransport
from skeleton.gate_plane.hardening.request_id import RequestContext, TraceParent, bind_context
from skeleton.gate_plane.pipeline.breaker import BreakerConfig
from skeleton.gate_plane.pipeline.retry import RetrySpec
from skeleton.gate_plane.s2s.clock import ManualClock

SECRET = encode_secret(b"s" * 32)
SECRET2 = encode_secret(b"t" * 32)
URL = "https://hooks.example.com/cb"
PUBLIC = {"hooks.example.com": ["93.184.216.34"], "b.example.com": ["93.184.216.35"],
          "evil.example.com": ["169.254.169.254"], "mixed.example.com": ["93.184.216.34", "10.0.0.1"]}


def resolver(host):
    if host not in PUBLIC:
        raise OSError("nxdomain")
    return PUBLIC[host]


@pytest.fixture
def clock():
    return ManualClock()


def make(clock, transport=None, **kw):
    allow = EgressAllowlist(["hooks.example.com", "*.example.com"], resolver=resolver)
    tr = transport or ScriptedTransport()
    kw.setdefault("retry", RetrySpec(max_attempts=3, base_backoff_s=0.1, max_backoff_s=0.5, jitter=0))
    kw.setdefault("redelivery_jitter", 0.0)
    gw = EgressGateway(allow, tr, clock=clock, rng=random.Random(7), **kw)
    gw.register(Subscription("sub-a", URL, SecretSet.of(SECRET), event_types=frozenset({"forge.*"})))
    return gw, tr


# -- signing -----------------------------------------------------------------------


class TestSigning:
    def test_roundtrip_and_headers(self, clock):
        secrets = SecretSet.of(SECRET)
        hdrs = WebhookSigner(clock=clock).headers(secrets, "msg_1", b'{"a":1}')
        assert hdrs["webhook-id"] == "msg_1" and hdrs["webhook-timestamp"] == str(int(clock.now()))
        assert hdrs["webhook-signature"].startswith("v1,")
        assert WebhookVerifier(secrets, clock=clock).verify(hdrs, b'{"a":1}') == "msg_1"

    def test_known_vector(self):
        # Standard Webhooks reference vector.
        secrets = SecretSet.of("whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw")
        body = b'{"test": 2432232314}'
        hdrs = WebhookSigner().headers(secrets, "msg_p5jXN8AQM9LWM0D4loKWxJek", body, timestamp=1614265330)
        assert hdrs["webhook-signature"] == "v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE="

    def test_tamper_skew_replay(self, clock):
        secrets = SecretSet.of(SECRET)
        signer, verifier = WebhookSigner(clock=clock), WebhookVerifier(secrets, clock=clock, tolerance_s=60)
        hdrs = signer.headers(secrets, "msg_2", b"x")
        with pytest.raises(WebhookSignatureError, match="signature_mismatch"):
            verifier.verify(hdrs, b"y")
        verifier.verify(hdrs, b"x")
        with pytest.raises(WebhookSignatureError, match="replayed"):
            verifier.verify(hdrs, b"x")
        old = signer.headers(secrets, "msg_3", b"x")
        clock.advance(61)
        with pytest.raises(WebhookSignatureError, match="tolerance"):
            verifier.verify(old, b"x")

    def test_rotation_both_signatures(self, clock):
        old = SecretSet.of(SECRET)
        rotated = old.rotate(SECRET2)
        hdrs = WebhookSigner(clock=clock).headers(rotated, "msg_4", b"x")
        assert len(hdrs["webhook-signature"].split()) == 2
        WebhookVerifier(old, clock=clock).verify(hdrs, b"x")
        WebhookVerifier(SecretSet.of(SECRET2), clock=clock).verify(hdrs, b"x")
        single = WebhookSigner(clock=clock, sign_with_previous=False).headers(rotated, "msg_5", b"x")
        with pytest.raises(WebhookSignatureError):
            WebhookVerifier(old, clock=clock).verify(single, b"x")

    @pytest.mark.parametrize(
        "headers,reason",
        [
            ({}, "missing_headers"),
            ({"webhook-id": "bad id", "webhook-timestamp": "1", "webhook-signature": "v1,x"}, "bad_message_id"),
            ({"webhook-id": "m", "webhook-timestamp": "soon", "webhook-signature": "v1,x"}, "bad_timestamp"),
        ],
    )
    def test_verify_rejects(self, clock, headers, reason):
        with pytest.raises(WebhookSignatureError, match=reason):
            WebhookVerifier(SecretSet.of(SECRET), clock=clock).verify(headers, b"")

    def test_no_v1(self, clock):
        hdrs = {"webhook-id": "m", "webhook-timestamp": str(int(clock.now())), "webhook-signature": "v2,abc"}
        with pytest.raises(WebhookSignatureError, match="no_v1"):
            WebhookVerifier(SecretSet.of(SECRET), clock=clock).verify(hdrs, b"")

    @pytest.mark.parametrize("bad", ["whsec_short", "whsec_%%%", b"x" * 8, b"x" * 100])
    def test_secret_validation(self, bad):
        with pytest.raises(ValueError):
            decode_secret(bad)

    def test_secret_type_and_fingerprint(self):
        with pytest.raises(TypeError):
            decode_secret(123)  # type: ignore[arg-type]
        assert SecretSet.of(SECRET).fingerprint() != SecretSet.of(SECRET2).fingerprint()
        assert "s" * 8 not in repr(SecretSet.of(SECRET))


# -- allowlist -----------------------------------------------------------------------


class TestAllowlist:
    def allow(self, **kw):
        return EgressAllowlist(["hooks.example.com", "*.example.com"], resolver=resolver, **kw)

    def test_allowed(self):
        v = self.allow().check(URL)
        assert v.allowed and v.host == "hooks.example.com" and v.port == 443 and v.addresses == ("93.184.216.34",)

    @pytest.mark.parametrize(
        "url,reason",
        [
            ("http://hooks.example.com/cb", EgressDenyReason.SCHEME),
            ("ftp://hooks.example.com/cb", EgressDenyReason.SCHEME),
            ("https://user:pw@hooks.example.com/cb", EgressDenyReason.USERINFO),
            ("https://hooks.example.com/cb#frag", EgressDenyReason.FRAGMENT),
            ("https://example.com/cb", EgressDenyReason.HOST),
            ("https://hooks.example.com.evil.io/cb", EgressDenyReason.HOST),
            ("https://hooks.example.com:8443/cb", EgressDenyReason.PORT),
            ("https://evil.example.com/cb", EgressDenyReason.PRIVATE_ADDRESS),
            ("https://mixed.example.com/cb", EgressDenyReason.PRIVATE_ADDRESS),
            ("https://nx.example.com/cb", EgressDenyReason.RESOLVE),
            ("https://hooks.example.com/c b", EgressDenyReason.BAD_URL),
            ("https://hooks.example.com:99999/", EgressDenyReason.BAD_URL),
            ("", EgressDenyReason.BAD_URL),
            ("https://" + "a" * 3000, EgressDenyReason.TOO_LONG),
        ],
    )
    def test_denied(self, url, reason):
        assert self.allow().check(url).reason is reason

    def test_ip_literals(self):
        allow = EgressAllowlist(["127.0.0.1", "93.184.216.34", "[::1]".strip("[]")], resolver=resolver)
        assert allow.check("https://127.0.0.1/x").reason is EgressDenyReason.PRIVATE_ADDRESS
        assert allow.check("https://93.184.216.34/x").allowed
        assert allow.check("https://[::1]/x").reason is EgressDenyReason.PRIVATE_ADDRESS

    def test_allowed_networks_and_http_dev(self):
        allow = EgressAllowlist(["localhost"], allow_http=True, allowed_networks=["127.0.0.0/8"],
                                resolver=lambda h: ["127.0.0.1"])
        assert allow.check("http://localhost/cb").allowed
        assert allow.check("http://localhost:8080/cb").reason is EgressDenyReason.PORT

    def test_empty_resolution(self):
        allow = EgressAllowlist(["x.example.com"], resolver=lambda h: [])
        assert allow.check("https://x.example.com/").reason is EgressDenyReason.RESOLVE

    @pytest.mark.parametrize("pattern", ["*example.com", "a.*.com", "user@x", "x/y", ""])
    def test_bad_patterns(self, pattern):
        with pytest.raises(ValueError):
            EgressAllowlist([pattern])

    @pytest.mark.parametrize(
        "addr,public",
        [("93.184.216.34", True), ("10.1.2.3", False), ("169.254.169.254", False), ("100.64.1.1", False),
         ("::ffff:10.0.0.1", False), ("2606:4700::1111", True), ("0.0.0.0", False), ("224.0.0.1", False)],
    )
    def test_is_public(self, addr, public):
        import ipaddress

        assert is_public_address(ipaddress.ip_address(addr)) is public


# -- dlq -----------------------------------------------------------------------------


class TestDeadLetterQueue:
    def letter(self, mid="m1", sub="s", reason="r"):
        return DeadLetter(mid, sub, "forge.done", URL, reason, 3, 1.0, 2.0, 503, "abc", 2, "e30=")

    def test_put_get_list_remove(self, clock):
        q = DeadLetterQueue(clock=clock)
        seen = []
        q.add_listener(seen.append)
        q.put(self.letter("m1"))
        q.put(self.letter("m2", sub="other"))
        assert len(q) == 2 and q.get("m1").body() == b"{}" and seen[0].message_id == "m1"
        assert [d.message_id for d in q.list(subscription="other")] == ["m2"]
        assert q.list(limit=1)[0].message_id == "m1"
        assert q.remove("m1").message_id == "m1" and q.get("m1") is None

    def test_capacity_eviction(self, clock):
        q = DeadLetterQueue(capacity=2, clock=clock)
        for i in range(4):
            q.put(self.letter(f"m{i}"))
        assert [d.message_id for d in q] == ["m2", "m3"] and q.evicted == 2

    def test_sink_persist_and_reload(self, tmp_path, clock):
        path = str(tmp_path / "dlq.jsonl")
        q = DeadLetterQueue(sink_path=path, clock=clock)
        q.put(self.letter("m1", reason="a"))
        q.put(self.letter("m2", reason="b"))
        q.remove("m1")
        with open(path, "a") as fh:
            fh.write("not json\n\n")
        q2 = DeadLetterQueue(sink_path=path, clock=clock)
        assert q2.load() == 1 and q2.get("m2").reason == "b" and q2.sink_errors == 1
        assert q2.stats()["by_reason"] == {"b": 1}

    def test_sink_error_counted(self, tmp_path, clock):
        q = DeadLetterQueue(sink_path=str(tmp_path / "missing" / "x.jsonl"), clock=clock)
        q.put(self.letter())
        assert q.sink_errors == 1 and len(q) == 1

    def test_listener_errors_swallowed(self, clock):
        q = DeadLetterQueue(clock=clock)
        q.add_listener(lambda d: 1 / 0)
        q.put(self.letter())
        assert len(q) == 1

    def test_load_without_sink(self, clock):
        assert DeadLetterQueue(clock=clock).load() == 0
        with pytest.raises(ValueError):
            DeadLetterQueue(capacity=0)


# -- gateway ---------------------------------------------------------------------------


class TestSubscription:
    def test_accepts(self):
        sub = Subscription("s1", URL, SecretSet.of(SECRET), event_types=frozenset({"forge.*", "swarm.done"}))
        assert sub.accepts("forge.build.done") and sub.accepts("swarm.done") and not sub.accepts("swarm.start")
        assert sub.public_view()["secret_fingerprint"] and "secrets" not in sub.public_view()

    @pytest.mark.parametrize("kw", [{"id": "Bad Id"}, {"headers": {"Webhook-Id": "x"}}, {"headers": {"Authorization": "x"}}])
    def test_validation(self, kw):
        args = {"id": "s1", "url": URL, "secrets": SecretSet.of(SECRET), **kw}
        with pytest.raises(ValueError):
            Subscription(**args)

    def test_callback_build(self):
        cb = Callback.build("forge.done", {"x": 1}, message_id="msg_x")
        assert json.loads(cb.body) == {"data": {"x": 1}, "type": "forge.done"} and cb.message_id == "msg_x"
        with pytest.raises(ValueError):
            Callback.build("Bad Type", b"")
        assert Callback.build("forge.done", b"raw").body == b"raw"


class TestGateway:
    def test_register_rejects_bad_url(self, clock):
        gw, _ = make(clock)
        with pytest.raises(ValueError, match="private_address"):
            gw.register(Subscription("sub-x", "https://evil.example.com/x", SecretSet.of(SECRET)))

    def test_delivered_signed_correlated(self, clock):
        gw, tr = make(clock)
        ctx = RequestContext(request_id="req-egresstest001", trace=TraceParent.fresh())
        with bind_context(ctx):
            res = gw.deliver("sub-a", Callback.build("forge.done", {"ok": True}, message_id="msg_1"))
        assert res.outcome is DeliveryOutcome.DELIVERED and res.status == 200 and res.attempts == 1
        req = tr.requests[0]
        assert req.method == "POST" and req.url == URL and req.pinned_addresses == ("93.184.216.34",)
        h = req.headers
        assert h["idempotency-key"] == "msg_1" and h["x-request-id"] == "req-egresstest001"
        assert h["x-s2s-via"] == "egress"
        WebhookVerifier(SecretSet.of(SECRET), clock=clock).verify(h, req.body)
        assert gw.pending() == 0 and gw.stats()["outcome:delivered"] == 1

    def test_in_call_retry_then_success_resigns(self, clock):
        tr = ScriptedTransport().script(URL, 503, ConnectionError("reset"), 200)
        gw, _ = make(clock, tr)
        res = gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id="msg_r"))
        assert res.delivered and res.attempts == 3
        ts = [r.headers["webhook-timestamp"] for r in tr.requests]
        assert len(set(r.headers["webhook-id"] for r in tr.requests)) == 1 and len(ts) == 3

    def test_scheduled_redelivery_then_success(self, clock):
        tr = ScriptedTransport().script(URL, 503, 503, 503, 200)
        gw, _ = make(clock, tr)
        res = gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id="msg_s"))
        assert res.outcome is DeliveryOutcome.SCHEDULED and res.round == 1
        assert res.next_attempt_at == pytest.approx(clock.now() + 5.0)
        assert gw.drain() == []
        clock.advance(5.0)
        (res2,) = gw.drain()
        assert res2.delivered and res2.round == 2

    def test_retry_after_pushes_round(self, clock):
        tr = ScriptedTransport().script(URL, TransportResponse(429, (("Retry-After", "120"),)))
        gw, _ = make(clock, tr)
        res = gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id="msg_429"))
        assert res.outcome is DeliveryOutcome.SCHEDULED and res.attempts == 1
        assert res.next_attempt_at == pytest.approx(clock.now() + 120.0)

    def test_exhausted_to_dlq_and_replay(self, clock):
        tr = ScriptedTransport(default=503)
        lenient = BreakerConfig(consecutive_failures=100, min_calls=100, window_size=100)
        gw, _ = make(clock, tr, redelivery_schedule_s=(1.0, 2.0), breaker_config=lenient)
        cb = Callback.build("forge.done", b'{"n":1}', message_id="msg_dead")
        results = [gw.deliver("sub-a", cb)]
        for step in (1.0, 2.0):
            clock.advance(step)
            results += gw.drain()
        assert [r.outcome for r in results] == [DeliveryOutcome.SCHEDULED, DeliveryOutcome.SCHEDULED,
                                                DeliveryOutcome.DEAD_LETTERED]
        letter = gw.dlq.get("msg_dead")
        assert letter.reason == "exhausted:status_503" and letter.attempts == 9 and letter.body() == b'{"n":1}'
        assert len(letter.history) == 3 and gw.pending() == 0
        tr.default = 200
        gw.replay("msg_dead")
        assert gw.dlq.get("msg_dead") is None
        (res,) = gw.drain()
        assert res.delivered and gw.stats()["replayed"] == 1

    def test_breaker_open_pushes_redelivery_past_cooldown(self, clock):
        gw, _ = make(clock, ScriptedTransport(default=503), redelivery_schedule_s=(1.0, 2.0))
        gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id="msg_cool"))
        clock.advance(1.0)
        (res,) = gw.drain()
        assert res.reason == "circuit_open" and res.next_attempt_at > clock.now() + 25

    def test_max_age_dead_letters(self, clock):
        gw, _ = make(clock, ScriptedTransport(default=503), max_age_s=3.0)
        res = gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id="msg_age"))
        assert res.outcome is DeliveryOutcome.DEAD_LETTERED and res.reason.startswith("exhausted")

    def test_gone_disables_subscription(self, clock):
        gw, _ = make(clock, ScriptedTransport(default=410))
        res = gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id="msg_gone"))
        assert res.reason == "gone" and not gw.subscription("sub-a").enabled
        res2 = gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id="msg_after"))
        assert res2.outcome is DeliveryOutcome.DEAD_LETTERED and res2.reason == "subscription_disabled"
        gw.enable("sub-a")
        assert gw.subscription("sub-a").enabled

    def test_permanent_4xx(self, clock):
        gw, tr = make(clock, ScriptedTransport(default=400))
        res = gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id="msg_400"))
        assert res.reason == "permanent:status_400" and len(tr.requests) == 1

    def test_redirect_refused(self, clock):
        tr = ScriptedTransport(default=TransportResponse(302, (("location", "http://169.254.169.254/"),)))
        gw, _ = make(clock, tr)
        res = gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id="msg_302"))
        assert res.reason == "permanent:redirect_refused" and len(tr.requests) == 1

    def test_unknown_transport_bug_is_terminal(self, clock):
        gw, tr = make(clock, ScriptedTransport(default=ValueError("bug")))
        res = gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id="msg_bug"))
        assert res.reason == "permanent:transport_error" and len(tr.requests) == 1

    def test_allowlist_denial_at_delivery_time(self, clock):
        gw, tr = make(clock)
        PUBLIC["hooks.example.com"] = ["10.0.0.7"]  # DNS rebinding after registration
        try:
            res = gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id="msg_rebind"))
        finally:
            PUBLIC["hooks.example.com"] = ["93.184.216.34"]
        assert res.outcome is DeliveryOutcome.REJECTED and res.reason == "egress_denied:private_address"
        assert tr.requests == [] and gw.dlq.get("msg_rebind") is not None

    def test_body_limit_and_missing_sub(self, clock):
        gw, _ = make(clock, max_body_bytes=4)
        res = gw.deliver("sub-a", Callback.build("forge.done", b"0123456789", message_id="msg_big"))
        assert res.outcome is DeliveryOutcome.REJECTED and res.reason == "body_too_large"
        with pytest.raises(KeyError):
            gw.enqueue("nope", Callback.build("forge.done", b"{}"))

    def test_breaker_opens_per_host_and_isolates(self, clock):
        tr = ScriptedTransport(default=503)
        gw, _ = make(
            clock, tr, retry=RetrySpec.no_retry(),
            breaker_config=BreakerConfig(consecutive_failures=2, min_calls=2, window_size=4, cooldown_s=60.0),
        )
        gw.register(Subscription("sub-b", "https://b.example.com/x", SecretSet.of(SECRET)))
        tr.script("https://b.example.com/x", 200, 200, 200)
        for i in range(2):
            gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id=f"msg_f{i}"))
        res = gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id="msg_open"))
        assert res.reason == "circuit_open" and res.outcome is DeliveryOutcome.SCHEDULED
        assert len(tr.calls_to(URL)) == 2
        assert res.next_attempt_at >= clock.now() + 60.0 - 1e-6
        assert gw.deliver("sub-b", Callback.build("forge.done", b"{}", message_id="msg_b")).delivered
        assert gw.stats()["breakers"]["egress:hooks.example.com"] == "open"

    def test_retry_budget_caps_storm(self, clock):
        tr = ScriptedTransport(default=503)
        from skeleton.gate_plane.pipeline.budget import RetryBudgetRegistry

        budgets = RetryBudgetRegistry(clock=clock, retry_ratio=0.0, min_retries_per_s=0.1, window_s=10.0)
        gw, _ = make(clock, tr, budgets=budgets, breaker_config=BreakerConfig(consecutive_failures=100,
                                                                           min_calls=100, window_size=100))
        for i in range(5):
            gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id=f"msg_b{i}"))
        # 5 originals + at most 1 retry token from the floor budget.
        assert len(tr.requests) == 6

    def test_publish_fanout_filters(self, clock):
        gw, tr = make(clock)
        gw.register(Subscription("sub-b", "https://b.example.com/x", SecretSet.of(SECRET2),
                                 event_types=frozenset({"swarm.*"})))
        gw.register(Subscription("sub-t", "https://b.example.com/t", SecretSet.of(SECRET2), tenant_id="t9"))
        ids = gw.publish("forge.done", {"x": 1}, event_id="evt_1", tenant_id="t1")
        assert ids == ["evt_1:sub-a"]
        ids2 = gw.publish("swarm.done", {"x": 1}, event_id="evt_2", tenant_id="t9")
        assert sorted(ids2) == ["evt_2:sub-b", "evt_2:sub-t"]
        results = gw.drain()
        assert all(r.delivered for r in results) and len(results) == 3
        assert gw.publish("forge.done", {}, event_id="evt_3") == ["evt_3:sub-a", "evt_3:sub-t"]

    def test_enqueue_is_idempotent(self, clock):
        gw, tr = make(clock)
        cb = Callback.build("forge.done", b"{}", message_id="msg_dup")
        e1 = gw.enqueue("sub-a", cb)
        assert gw.enqueue("sub-a", cb) is e1 and gw.pending() == 1
        gw.drain(max_items=0)
        assert gw.pending() == 1

    def test_secret_rotation_and_listener(self, clock):
        gw, tr = make(clock)
        seen = []
        gw.add_listener(seen.append)
        gw.add_listener(lambda r: 1 / 0)
        gw.rotate_secret("sub-a", SECRET2)
        gw.deliver("sub-a", Callback.build("forge.done", b"{}", message_id="msg_rot"))
        WebhookVerifier(SecretSet.of(SECRET2), clock=clock).verify(tr.requests[0].headers, b"{}")
        assert seen[0].message_id == "msg_rot"

    def test_disabled_and_removed_subscriptions_dead_letter(self, clock):
        gw, _ = make(clock)
        gw.enqueue("sub-a", Callback.build("forge.done", b"{}", message_id="msg_dis"))
        gw.disable("sub-a", "owner_paused")
        (res,) = gw.drain()
        assert res.outcome is DeliveryOutcome.DEAD_LETTERED
        assert gw.dlq.get("msg_dis").reason == "subscription_disabled:owner_paused"

    def test_replay_errors(self, clock):
        gw, _ = make(clock, store_bodies_in_dlq=False, max_body_bytes=1)
        with pytest.raises(KeyError):
            gw.replay("nope")
        gw.deliver("sub-a", Callback.build("forge.done", b"xx", message_id="msg_nb"))
        with pytest.raises(ValueError):
            gw.replay("msg_nb")

    def test_config_validation(self, clock):
        allow = EgressAllowlist(["x.example.com"], resolver=resolver)
        for kw in ({"timeout_s": 0}, {"timeout_s": 1, "attempt_timeout_s": 2}, {"redelivery_schedule_s": (0,)},
                   {"redelivery_jitter": 0.9}):
            with pytest.raises(ValueError):
                EgressGateway(allow, ScriptedTransport(), clock=clock, **kw)


class TestTransports:
    def test_scripted_callable_and_latency(self, clock):
        tr = ScriptedTransport(clock=clock, latency_s=0.5)
        tr.script("u", lambda req: TransportResponse(201, body=req.body))
        resp = tr(TransportRequest("POST", "u", {}, b"hi", 1.0))
        assert resp.status == 201 and resp.body == b"hi" and clock.now() == 1_700_000_000.5
        assert tr(TransportRequest("POST", "u", {}, b"", 1.0)).status == 200

    def test_urllib_transport_against_local_server(self):
        import http.server
        import threading

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("content-length", 0))
                body = self.rfile.read(length)
                if self.path == "/redir":
                    self.send_response(302)
                    self.send_header("location", "/elsewhere")
                    self.end_headers()
                    return
                self.send_response(202 if body == b"ping" else 500)
                self.send_header("x-echo", self.headers.get("webhook-id", ""))
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            base = f"http://127.0.0.1:{srv.server_port}"
            tr = UrllibTransport()
            r = tr(TransportRequest("POST", base + "/cb", {"webhook-id": "m1"}, b"ping", 2.0))
            assert r.status == 202 and r.header("x-echo") == "m1" and r.body == b"ok"
            assert tr(TransportRequest("POST", base + "/cb", {}, b"other", 2.0)).status == 500
            assert tr(TransportRequest("POST", base + "/redir", {}, b"ping", 2.0)).status == 302
        finally:
            srv.shutdown()
            srv.server_close()
        with pytest.raises(ConnectionError):
            UrllibTransport()(TransportRequest("POST", f"http://127.0.0.1:{srv.server_port}/x", {}, b"", 0.5))
