"""Pack F hardening — request-id propagation, claim policy, mutual auth, rate limits."""

from __future__ import annotations

import base64
import hashlib

import pytest

from skeleton.gate_plane.hardening.claims import (
    ClaimsPolicy,
    HardenedVerifier,
    HardeningCode,
    HardeningError,
    VerificationScope,
    bound_extra,
    normalize_thumbprint,
    thumbprint_b64url,
    verification_scope,
)
from skeleton.gate_plane.hardening.mutual import (
    MutualAuthCode,
    MutualAuthMode,
    MutualAuthPolicy,
    NonceCache,
    PeerExtractor,
    PeerResult,
    PeerCertificate,
    RequestSigner,
    RequestVerifier,
    SpiffeMap,
    canonical_request,
    parse_signature_header,
    parse_xfcc,
    pem_to_der,
    thumbprint_from_der,
)
from skeleton.gate_plane.hardening.ratelimit import RateRule, ServiceRateLimiter, limiter_from_config
from skeleton.gate_plane.hardening.request_id import (
    HOP_HEADER,
    REQUEST_ID_HEADER,
    TRACEPARENT_HEADER,
    VIA_HEADER,
    HopLimitExceeded,
    PropagationPolicy,
    RequestContext,
    RequestIdStage,
    TraceParent,
    bind_context,
    current_context,
    envelope_headers,
    extract_context,
    propagate,
    valid_request_id,
)
from skeleton.gate_plane.pipeline.core import Pipeline, PipelineRequest, PipelineResponse
from skeleton.gate_plane.s2s.clock import ManualClock
from skeleton.gate_plane.s2s.keyring import KeyRing
from skeleton.gate_plane.s2s.tokens import ReplayCache, TokenError, TokenErrorCode, TokenSigner, TokenVerifier

TP = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
DER = b"\x30\x82fake-der-certificate-bytes"
THUMB = hashlib.sha256(DER).hexdigest()


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


# -- request id / trace ------------------------------------------------------


class TestTraceParent:
    def test_parse_roundtrip(self):
        tp = TraceParent.parse(TP)
        assert tp is not None and tp.header() == TP and tp.sampled

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            "",
            "garbage",
            "ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "00-00000000000000000000000000000000-00f067aa0ba902b7-01",
            "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01",
            "00-4bf92f3577b34da6a3ce929d0e0e473-00f067aa0ba902b7-01",
        ],
    )
    def test_rejects_invalid(self, raw):
        assert TraceParent.parse(raw) is None

    def test_child_keeps_trace_new_span(self):
        tp = TraceParent.parse(TP)
        child = tp.child()
        assert child.trace_id == tp.trace_id and child.span_id != tp.span_id

    def test_unsampled_flag(self):
        assert not TraceParent.fresh(sampled=False).sampled


class TestExtractContext:
    def test_trusts_valid_inbound(self):
        ctx = extract_context({"X-Request-Id": "req-abcdef123456", "traceparent": TP, "x-s2s-hop": "2"})
        assert ctx.request_id == "req-abcdef123456" and ctx.origin == "inbound"
        assert ctx.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736" and ctx.hop == 2

    @pytest.mark.parametrize("bad", ["short", "x" * 200, "req id with spaces", "req-\r\nset-cookie:1", "-leadingdash1"])
    def test_regenerates_invalid_request_id(self, bad):
        ctx = extract_context({REQUEST_ID_HEADER: bad})
        assert ctx.request_id != bad and ctx.origin == "generated" and valid_request_id(ctx.request_id)

    def test_untrusted_policy_ignores_inbound(self):
        pol = PropagationPolicy(trust_inbound_request_id=False, trust_inbound_trace=False)
        ctx = extract_context({REQUEST_ID_HEADER: "req-abcdef123456", TRACEPARENT_HEADER: TP}, policy=pol)
        assert ctx.request_id != "req-abcdef123456" and ctx.trace_id != "4bf92f3577b34da6a3ce929d0e0e4736"

    def test_hop_limit(self):
        with pytest.raises(HopLimitExceeded):
            extract_context({HOP_HEADER: "16"})
        extract_context({HOP_HEADER: "15"})

    def test_garbage_hop_is_zero(self):
        assert extract_context({HOP_HEADER: "-3"}).hop == 0
        assert extract_context({HOP_HEADER: "99999"}).hop == 0

    def test_cycle_detection(self):
        with pytest.raises(HopLimitExceeded):
            extract_context({VIA_HEADER: "gateway,forge"}, service="forge")
        ctx = extract_context({VIA_HEADER: "gateway,forge"}, service="swarm")
        assert ctx.via == ("gateway", "forge")

    def test_cycles_allowed_when_disabled(self):
        ctx = extract_context({VIA_HEADER: "forge"}, service="forge", policy=PropagationPolicy(reject_cycles=False))
        assert ctx.via == ("forge",)

    def test_via_drops_invalid_entries(self):
        ctx = extract_context({VIA_HEADER: "ok-svc, BAD SVC ,,  second"})
        assert ctx.via == ("ok-svc", "second")

    def test_tracestate_kept_only_with_trace(self):
        ctx = extract_context({TRACEPARENT_HEADER: TP, "tracestate": "vendor=abc"})
        assert ctx.tracestate == "vendor=abc"
        assert extract_context({"tracestate": "vendor=abc"}).tracestate is None

    def test_max_hops_bounds(self):
        with pytest.raises(ValueError):
            PropagationPolicy(max_hops=0)


class TestPropagate:
    def test_outbound_increments_hop_and_appends_via(self):
        ctx = extract_context({REQUEST_ID_HEADER: "req-abcdef123456", TRACEPARENT_HEADER: TP, HOP_HEADER: "1"})
        out = propagate({"Accept": "x"}, service="gateway", ctx=ctx)
        assert out["Accept"] == "x"
        assert out[REQUEST_ID_HEADER] == "req-abcdef123456"
        assert out[HOP_HEADER] == "2" and out[VIA_HEADER] == "gateway"
        assert TraceParent.parse(out[TRACEPARENT_HEADER]).trace_id == ctx.trace_id

    def test_bound_context_is_authoritative(self):
        ctx = RequestContext(request_id="req-boundctx0001", trace=TraceParent.fresh())
        with bind_context(ctx):
            assert current_context() is ctx
            out = propagate({"X-Request-Id": "req-forgedvalue99"})
        assert out[REQUEST_ID_HEADER] == "req-boundctx0001"
        assert "X-Request-Id" not in out
        assert current_context() is None

    def test_root_context_when_unbound(self):
        out = propagate()
        assert valid_request_id(out[REQUEST_ID_HEADER]) and out[HOP_HEADER] == "1"

    def test_envelope_headers_preserve_chain_across_bus_hops(self):
        first = envelope_headers(None, service="planner")
        second = envelope_headers(first, service="worker")
        third = envelope_headers(second, service="reviewer")
        assert first[REQUEST_ID_HEADER] == second[REQUEST_ID_HEADER] == third[REQUEST_ID_HEADER]
        t1, t3 = TraceParent.parse(first[TRACEPARENT_HEADER]), TraceParent.parse(third[TRACEPARENT_HEADER])
        assert t1.trace_id == t3.trace_id and t1.span_id != t3.span_id
        assert third[HOP_HEADER] == "3" and third[VIA_HEADER] == "planner,worker,reviewer"

    def test_envelope_headers_use_bound_context(self):
        ctx = RequestContext(request_id="req-fromhttpcall1", trace=TraceParent.fresh())
        with bind_context(ctx):
            hdrs = envelope_headers(None, service="agent-a")
        assert hdrs[REQUEST_ID_HEADER] == "req-fromhttpcall1"

    def test_via_is_bounded(self):
        ctx = RequestContext(request_id="req-viabounded01", trace=TraceParent.fresh(), via=tuple(f"s{i}" for i in range(40)))
        out = ctx.outbound_headers("last")
        assert len(out[VIA_HEADER].split(",")) == 32 and out[VIA_HEADER].endswith("last")


class TestRequestIdStage:
    def test_retries_share_request_id_new_spans(self, clock):
        seen = []

        def handler(req, ctx):
            seen.append(dict(req.headers))
            return PipelineResponse(200)

        pipe = Pipeline([RequestIdStage(service="gw")], clock=clock)
        req = PipelineRequest("GET", "/x", headers={REQUEST_ID_HEADER: "req-stagetest001"})
        ctx = pipe.new_context()
        pipe.run(req, handler, ctx=ctx)
        assert seen[0][REQUEST_ID_HEADER] == "req-stagetest001"
        assert seen[0][VIA_HEADER] == "gw"
        assert ctx.attrs["request_context"]["request_id"] == "req-stagetest001"
        assert "request_id" in ctx.event_names()

    def test_generates_when_missing(self, clock):
        captured = {}
        pipe = Pipeline([RequestIdStage()], clock=clock)
        pipe.run(PipelineRequest("GET", "/x"), lambda r, c: captured.update(r.headers) or PipelineResponse(204))
        assert valid_request_id(captured[REQUEST_ID_HEADER])


# -- claims policy -----------------------------------------------------------


def _ring(clock, kids=("forge:1",)):
    r = KeyRing(clock=clock)
    for i, kid in enumerate(kids):
        r.add_key(kid, bytes([65 + i]) * 32, activate=(i == 0))
    return r


class TestClaimsPolicy:
    def _verify(self, clock, policy, token, scope=None, ring=None):
        ring = ring
        hv = HardenedVerifier(TokenVerifier("swarm", ring, clock=clock, replay_cache=ReplayCache()), policy)
        if scope is None:
            return hv.verify(token)
        with verification_scope(scope):
            return hv.verify(token)

    def test_plain_policy_passes(self, clock):
        ring = _ring(clock)
        tok = TokenSigner("forge", ring, clock=clock).mint("swarm", ["swarm:read"])
        v = self._verify(clock, ClaimsPolicy(), tok, ring=ring)
        assert v.claims.iss == "forge"

    def test_kid_pinning(self, clock):
        ring = _ring(clock, kids=("telemetry:1",))
        tok = TokenSigner("forge", ring, clock=clock).mint("swarm", [])
        with pytest.raises(HardeningError) as ei:
            self._verify(clock, ClaimsPolicy.build(pin_kids_to_issuer=True), tok, ring=ring)
        assert ei.value.hardening_code is HardeningCode.KID_NOT_PINNED
        assert ei.value.code is TokenErrorCode.BAD_CLAIMS and isinstance(ei.value, TokenError)

    def test_kid_owner_map_overrides_prefix(self, clock):
        ring = _ring(clock, kids=("shared-1",))
        tok = TokenSigner("forge", ring, clock=clock).mint("swarm", [])
        self._verify(clock, ClaimsPolicy.build(pin_kids_to_issuer=True, kid_owners={"shared-1": "forge"}), tok, ring=ring)
        tok2 = TokenSigner("telemetry", ring, clock=clock).mint("swarm", [])
        with pytest.raises(HardeningError):
            self._verify(clock, ClaimsPolicy.build(kid_owners={"shared-1": "forge"}), tok2, ring=ring)

    def test_scope_ceiling(self, clock):
        ring = _ring(clock)
        signer = TokenSigner("forge", ring, clock=clock)
        pol = ClaimsPolicy.build(scope_ceilings={"forge": ["swarm:read", "telemetry:*"]})
        self._verify(clock, pol, signer.mint("swarm", ["swarm:read", "telemetry:write"]), ring=ring)
        with pytest.raises(HardeningError) as ei:
            self._verify(clock, pol, signer.mint("swarm", ["swarm:read", "admin:control"]), ring=ring)
        assert ei.value.hardening_code is HardeningCode.SCOPE_CEILING and "admin:control" in str(ei.value)

    def test_default_ceiling(self, clock):
        ring = _ring(clock)
        pol = ClaimsPolicy.build(default_scope_ceiling=["swarm:read"])
        with pytest.raises(HardeningError):
            self._verify(clock, pol, TokenSigner("forge", ring, clock=clock).mint("swarm", ["swarm:write"]), ring=ring)

    def test_freshness(self, clock):
        ring = _ring(clock)
        tok = TokenSigner("forge", ring, clock=clock).mint("swarm", [], ttl_s=600)
        clock.advance(120)
        with pytest.raises(HardeningError) as ei:
            self._verify(clock, ClaimsPolicy.build(max_token_age_s=60), tok, ring=ring)
        assert ei.value.hardening_code is HardeningCode.STALE_TOKEN

    def test_required_and_constrained_ext(self, clock):
        ring = _ring(clock)
        signer = TokenSigner("forge", ring, clock=clock)
        pol = ClaimsPolicy.build(required_ext=["tenant"], ext_allowed_values={"tenant": ["t1", "t2"]})
        self._verify(clock, pol, signer.mint("swarm", [], extra={"tenant": "t1"}), ring=ring)
        with pytest.raises(HardeningError) as e1:
            self._verify(clock, pol, signer.mint("swarm", []), ring=ring)
        assert e1.value.hardening_code is HardeningCode.MISSING_CLAIM
        with pytest.raises(HardeningError) as e2:
            self._verify(clock, pol, signer.mint("swarm", [], extra={"tenant": "evil"}), ring=ring)
        assert e2.value.hardening_code is HardeningCode.BAD_CLAIM_VALUE

    def test_binding_required_missing_cnf(self, clock):
        ring = _ring(clock)
        tok = TokenSigner("forge", ring, clock=clock).mint("swarm", [])
        scope = VerificationScope(peer_thumbprint=THUMB)
        with pytest.raises(HardeningError) as ei:
            self._verify(clock, ClaimsPolicy.build(require_binding_for=["forge"]), tok, scope=scope, ring=ring)
        assert ei.value.hardening_code is HardeningCode.BINDING_REQUIRED
        assert scope.failure is HardeningCode.BINDING_REQUIRED

    def test_binding_match_and_mismatch(self, clock):
        ring = _ring(clock)
        signer = TokenSigner("forge", ring, clock=clock)
        tok = signer.mint("swarm", [], extra=bound_extra(thumbprint=THUMB))
        scope = VerificationScope(peer_thumbprint=THUMB)
        self._verify(clock, ClaimsPolicy.build(require_binding=True), tok, scope=scope, ring=ring)
        assert scope.verified is not None
        tok2 = signer.mint("swarm", [], extra=bound_extra(thumbprint=THUMB))
        with pytest.raises(HardeningError) as ei:
            self._verify(clock, ClaimsPolicy(), tok2, scope=VerificationScope(peer_thumbprint="ab" * 32), ring=ring)
        assert ei.value.hardening_code is HardeningCode.BINDING_MISMATCH

    def test_bound_token_without_peer(self, clock):
        ring = _ring(clock)
        tok = TokenSigner("forge", ring, clock=clock).mint("swarm", [], extra=bound_extra(thumbprint=THUMB))
        with pytest.raises(HardeningError) as ei:
            self._verify(clock, ClaimsPolicy(), tok, scope=VerificationScope(), ring=ring)
        assert ei.value.hardening_code is HardeningCode.PEER_REQUIRED

    def test_bound_token_ignored_when_enforcement_off(self, clock):
        ring = _ring(clock)
        tok = TokenSigner("forge", ring, clock=clock).mint("swarm", [], extra=bound_extra(thumbprint=THUMB))
        self._verify(clock, ClaimsPolicy.build(enforce_binding_when_present=False), tok, scope=VerificationScope(), ring=ring)

    def test_peer_identity_mismatch(self, clock):
        ring = _ring(clock)
        tok = TokenSigner("forge", ring, clock=clock).mint("swarm", [], extra=bound_extra(thumbprint=THUMB))
        with pytest.raises(HardeningError) as ei:
            self._verify(clock, ClaimsPolicy(), tok, scope=VerificationScope(peer_thumbprint=THUMB, peer_service="telemetry"), ring=ring)
        assert ei.value.hardening_code is HardeningCode.PEER_IDENTITY_MISMATCH

    def test_request_id_binding(self, clock):
        ring = _ring(clock)
        signer = TokenSigner("forge", ring, clock=clock)
        tok = signer.mint("swarm", [], extra=bound_extra(request_id="req-boundreq0001"))
        self._verify(clock, ClaimsPolicy(), tok, scope=VerificationScope(request_id="req-boundreq0001"), ring=ring)
        tok2 = signer.mint("swarm", [], extra=bound_extra(request_id="req-boundreq0001"))
        with pytest.raises(HardeningError) as ei:
            self._verify(clock, ClaimsPolicy(), tok2, scope=VerificationScope(request_id="req-otherreq00001"), ring=ring)
        assert ei.value.hardening_code is HardeningCode.REQUEST_ID_MISMATCH

    def test_inner_errors_pass_through(self, clock):
        ring = _ring(clock)
        tok = TokenSigner("forge", ring, clock=clock).mint("telemetry", [])
        with pytest.raises(TokenError) as ei:
            self._verify(clock, ClaimsPolicy(), tok, ring=ring)
        assert ei.value.code is TokenErrorCode.BAD_AUDIENCE and not isinstance(ei.value, HardeningError)

    def test_policy_validation_and_dict(self):
        with pytest.raises(ValueError):
            ClaimsPolicy.build(max_token_age_s=0)
        d = ClaimsPolicy.build(scope_ceilings={"forge": ["a:b"]}, require_binding_for=["forge"]).as_dict()
        assert d["scope_ceilings"] == {"forge": ["a:b"]} and d["require_binding_for"] == ["forge"]


class TestThumbprints:
    def test_normalize_hex_b64_colon(self):
        b64 = thumbprint_b64url(THUMB)
        assert normalize_thumbprint(b64) == THUMB
        assert normalize_thumbprint(THUMB.upper()) == THUMB
        colon = ":".join(THUMB[i:i + 2] for i in range(0, 64, 2))
        assert normalize_thumbprint(colon) == THUMB

    @pytest.mark.parametrize("bad", ["", "zz", base64.urlsafe_b64encode(b"short").decode()])
    def test_normalize_rejects(self, bad):
        with pytest.raises(ValueError):
            normalize_thumbprint(bad)


# -- mutual auth ---------------------------------------------------------------


def _pem(der: bytes) -> str:
    body = base64.b64encode(der).decode()
    return f"-----BEGIN CERTIFICATE-----\n{body}\n-----END CERTIFICATE-----\n"


class TestXfcc:
    def test_parse_envoy_header(self):
        raw = (
            'By=spiffe://prod/svc/gateway;Hash=' + THUMB + ';Subject="CN=forge,O=Skel";URI=spiffe://prod/svc/forge,'
            'By=spiffe://prod/svc/swarm;Hash=' + "a" * 64 + ';URI=spiffe://prod/svc/gateway'
        )
        els = parse_xfcc(raw)
        assert len(els) == 2
        assert els[0]["hash"] == [THUMB] and els[0]["subject"] == ["CN=forge,O=Skel"]
        assert els[1]["uri"] == ["spiffe://prod/svc/gateway"]

    @pytest.mark.parametrize("bad", ["", "novalue", 'Hash="unterminated', "=x"])
    def test_parse_rejects(self, bad):
        with pytest.raises(ValueError):
            parse_xfcc(bad)

    def test_too_large(self):
        with pytest.raises(ValueError):
            parse_xfcc("Hash=" + "a" * 20_000)


class TestSpiffeMap:
    def test_svc_prefix_and_k8s(self):
        m = SpiffeMap("prod", namespaces=frozenset({"core"}))
        assert m.service_for("spiffe://prod/svc/forge") == "forge"
        assert m.service_for("spiffe://prod/ns/core/sa/swarm") == "swarm"
        assert m.service_for("spiffe://prod/ns/other/sa/swarm") is None
        assert m.service_for("spiffe://evil/svc/forge") is None
        assert m.service_for("spiffe://prod/svc/a/b") is None
        assert m.service_for("spiffe://prod/svc/BAD") is None
        assert m.service_for(None) is None

    def test_explicit(self):
        m = SpiffeMap("prod", explicit={"spiffe://other/x": "telemetry"})
        assert m.service_for("spiffe://other/x") == "telemetry"


class TestPeerExtractor:
    def test_tls_extension(self):
        ex = PeerExtractor()
        res = ex.extract({"extensions": {"tls": {"client_cert_chain": [_pem(DER)]}}}, {})
        assert res.ok and res.peer.thumbprint == THUMB and res.peer.source == "tls"

    def test_tls_bad_cert(self):
        res = PeerExtractor().extract({"extensions": {"tls": {"client_cert_chain": ["not a pem"]}}}, {})
        assert res.code is MutualAuthCode.BAD_CERT

    def test_xfcc_requires_trusted_proxy(self):
        ex = PeerExtractor(trusted_proxies=["10.0.0.0/8"], spiffe=SpiffeMap("prod"))
        hdr = {"x-forwarded-client-cert": f"Hash={THUMB};URI=spiffe://prod/svc/forge"}
        assert ex.extract({"client": ("203.0.113.9", 4000)}, hdr).code is MutualAuthCode.UNTRUSTED_PROXY
        res = ex.extract({"client": ("10.1.2.3", 4000)}, hdr)
        assert res.ok and res.service == "forge" and res.peer.source == "xfcc"

    def test_xfcc_cert_field(self):
        from urllib.parse import quote

        ex = PeerExtractor(trusted_proxies=["127.0.0.1/32"])
        hdr = {"x-forwarded-client-cert": f'Cert="{quote(_pem(DER))}"'}
        res = ex.extract({"client": ("127.0.0.1", 1)}, hdr)
        assert res.ok and res.peer.thumbprint == THUMB

    def test_xfcc_without_hash_or_cert(self):
        ex = PeerExtractor(trusted_proxies=["127.0.0.1/32"])
        res = ex.extract({"client": ("127.0.0.1", 1)}, {"x-forwarded-client-cert": "By=spiffe://x/y"})
        assert res.code is MutualAuthCode.BAD_XFCC

    def test_tls_wins_over_xfcc(self):
        ex = PeerExtractor(trusted_proxies=["127.0.0.1/32"])
        scope = {"client": ("127.0.0.1", 1), "extensions": {"tls": {"client_cert_chain": [_pem(DER)]}}}
        res = ex.extract(scope, {"x-forwarded-client-cert": "Hash=" + "b" * 64})
        assert res.peer.source == "tls"

    def test_no_peer(self):
        assert PeerExtractor().extract({}, {}).code is MutualAuthCode.NO_PEER

    def test_bad_client_address(self):
        ex = PeerExtractor(trusted_proxies=["127.0.0.1/32"])
        assert ex.extract({"client": ("not-an-ip", 1)}, {"x-forwarded-client-cert": "Hash=" + "b" * 64}).code is (
            MutualAuthCode.UNTRUSTED_PROXY
        )

    def test_spiffe_from_real_certificate(self):
        crypto = pytest.importorskip("cryptography")
        del crypto
        import datetime

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "forge")])
        now = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.UniformResourceIdentifier("spiffe://prod/svc/forge")]), False)
            .sign(key, hashes.SHA256())
        )
        pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        res = PeerExtractor(spiffe=SpiffeMap("prod")).extract({"extensions": {"tls": {"client_cert_chain": [pem]}}}, {})
        assert res.ok and res.peer.spiffe_id == "spiffe://prod/svc/forge" and res.service == "forge"
        assert res.peer.thumbprint == thumbprint_from_der(pem_to_der(pem))


class TestMutualPolicy:
    def _peer(self, service=None, thumb=THUMB):
        return PeerResult(MutualAuthCode.OK, PeerCertificate(thumb, "tls"), service)

    def test_off_allows_everything(self):
        assert MutualAuthPolicy().evaluate(PeerResult(MutualAuthCode.BAD_CERT), "forge") is MutualAuthCode.OK

    def test_required_no_peer(self):
        pol = MutualAuthPolicy.build("required")
        assert pol.evaluate(PeerResult(MutualAuthCode.NO_PEER), "forge") is MutualAuthCode.NO_PEER

    def test_optional_no_peer_ok_but_broken_peer_rejected(self):
        pol = MutualAuthPolicy.build("optional")
        assert pol.evaluate(PeerResult(MutualAuthCode.NO_PEER), "forge") is MutualAuthCode.OK
        assert pol.evaluate(PeerResult(MutualAuthCode.UNTRUSTED_PROXY), "forge") is MutualAuthCode.UNTRUSTED_PROXY

    def test_required_for_named_services(self):
        pol = MutualAuthPolicy.build("off", required_for=["forge"])
        assert pol.evaluate(PeerResult(MutualAuthCode.NO_PEER), "forge") is MutualAuthCode.NO_PEER
        assert pol.evaluate(PeerResult(MutualAuthCode.NO_PEER), "telemetry") is MutualAuthCode.OK

    def test_identity_mismatch(self):
        pol = MutualAuthPolicy.build(MutualAuthMode.REQUIRED)
        assert pol.evaluate(self._peer("telemetry"), "forge") is MutualAuthCode.PEER_MISMATCH
        assert pol.evaluate(self._peer("forge"), "forge") is MutualAuthCode.OK

    def test_unknown_peer_when_required(self):
        pol = MutualAuthPolicy.build("required")
        assert pol.evaluate(self._peer(None), "forge") is MutualAuthCode.UNKNOWN_PEER
        assert MutualAuthPolicy.build("required", require_known_peer=False).evaluate(self._peer(None), "forge") is (
            MutualAuthCode.OK
        )

    def test_pinned_thumbprints(self):
        pol = MutualAuthPolicy.build("required", pinned_thumbprints={"forge": [THUMB.upper()]})
        assert pol.evaluate(self._peer(None), "forge") is MutualAuthCode.OK
        assert pol.evaluate(self._peer(None, "c" * 64), "forge") is MutualAuthCode.PEER_MISMATCH


class TestSignedRequests:
    def _pair(self, clock):
        ring = _ring(clock)
        return RequestSigner(ring, clock=clock), RequestVerifier("swarm", ring, clock=clock)

    def test_roundtrip(self, clock):
        signer, verifier = self._pair(clock)
        hdr = signer.sign(method="post", path="/api/v1/swarm/x", audience="swarm", body=b"{}", query="b=2&a=1",
                          request_id="req-signedreq001")
        res = verifier.verify(hdr, method="POST", path="/api/v1/swarm/x", body=b"{}", query="a=1&b=2",
                              request_id="req-signedreq001")
        assert res.ok and res.kid == "forge:1"

    def test_tamper_body_path_rid(self, clock):
        signer, verifier = self._pair(clock)
        kw = dict(method="POST", path="/p", audience="swarm", body=b"one", request_id="req-signedreq002")
        for change in ({"body": b"two"}, {"path": "/q"}, {"request_id": "req-signedreq003"}):
            hdr = signer.sign(**kw)
            args = {k: v for k, v in kw.items() if k != "audience"}
            args.update(change)
            assert verifier.verify(hdr, **args).code is MutualAuthCode.SIGNATURE_INVALID

    def test_wrong_audience(self, clock):
        ring = _ring(clock)
        hdr = RequestSigner(ring, clock=clock).sign(method="GET", path="/", audience="telemetry")
        assert RequestVerifier("swarm", ring, clock=clock).verify(hdr, method="GET", path="/").code is (
            MutualAuthCode.SIGNATURE_INVALID
        )

    def test_skew_and_replay(self, clock):
        signer, verifier = self._pair(clock)
        hdr = signer.sign(method="GET", path="/", audience="swarm")
        assert verifier.verify(hdr, method="GET", path="/").ok
        assert verifier.verify(hdr, method="GET", path="/").code is MutualAuthCode.SIGNATURE_REPLAY
        hdr2 = signer.sign(method="GET", path="/", audience="swarm")
        clock.advance(61)
        assert verifier.verify(hdr2, method="GET", path="/").code is MutualAuthCode.SIGNATURE_SKEW

    def test_unknown_kid_and_bad_header(self, clock):
        signer, verifier = self._pair(clock)
        other = RequestSigner(_ring(clock, kids=("zzz:9",)), clock=clock)
        hdr = other.sign(method="GET", path="/", audience="swarm")
        assert verifier.verify(hdr, method="GET", path="/").code is MutualAuthCode.SIGNATURE_UNKNOWN_KID
        assert verifier.verify("v2;kid=a", method="GET", path="/").code is MutualAuthCode.BAD_SIGNATURE_HEADER
        assert verifier.verify(None, method="GET", path="/").code is MutualAuthCode.NO_PEER

    @pytest.mark.parametrize(
        "raw",
        [
            "v1;kid=a;t=1;n=" + "n" * 16,
            "v1;kid=a;t=x;n=" + "n" * 16 + ";sig=" + "A" * 43,
            "v1;kid=a;t=1;n=short;sig=" + "A" * 43,
            "v1;kid=a;kid=b;t=1;n=" + "n" * 16 + ";sig=" + "A" * 43,
            "v1;kid=a;t=1;n=" + "n" * 16 + ";sig=AAAA",
        ],
    )
    def test_parse_rejects(self, raw):
        with pytest.raises(ValueError):
            parse_signature_header(raw)

    def test_garbage_does_not_consume_nonce(self, clock):
        signer, verifier = self._pair(clock)
        hdr = signer.sign(method="GET", path="/", audience="swarm", nonce="N" * 20)
        forged = hdr.rsplit("sig=", 1)[0] + "sig=" + "A" * 43
        assert verifier.verify(forged, method="GET", path="/").code is MutualAuthCode.SIGNATURE_INVALID
        assert verifier.verify(hdr, method="GET", path="/").ok

    def test_canonical_request_sorts_query(self):
        a = canonical_request(method="get", path="/", query="b=1&a=2", body=b"", request_id="", audience="x",
                              timestamp=1, nonce="n")
        b = canonical_request(method="GET", path="/", query="a=2&b=1", body=b"", request_id="", audience="x",
                              timestamp=1, nonce="n")
        assert a == b

    def test_nonce_cache_bounded(self):
        cache = NonceCache(capacity=2)
        for i in range(5):
            assert cache.check_and_add("k", f"n{i}", 100.0, 0.0)
        assert len(cache) == 2

    def test_tolerance_bounds(self, clock):
        with pytest.raises(ValueError):
            RequestVerifier("swarm", _ring(clock), tolerance_s=0)


# -- rate limits ---------------------------------------------------------------


class TestRateLimiter:
    def test_burst_then_deny_then_refill(self, clock):
        rl = ServiceRateLimiter(default=RateRule(rate_per_s=2, burst=3), clock=clock)
        assert [rl.check("forge", "p").allowed for _ in range(4)] == [True, True, True, False]
        d = rl.check("forge", "p")
        assert not d.allowed and d.retry_after_s == 0.5
        assert ("retry-after", "1") in d.headers()
        clock.advance(0.5)
        assert rl.check("forge", "p").allowed

    def test_identities_isolated(self, clock):
        rl = ServiceRateLimiter(default=RateRule(rate_per_s=1, burst=1), clock=clock)
        assert rl.check("forge", None).allowed
        assert not rl.check("forge", None).allowed
        assert rl.check("telemetry", None).allowed

    def test_rule_specificity(self, clock):
        rules = {
            ("forge", "swarm-write"): RateRule(1, 1),
            ("forge", "*"): RateRule(100, 100),
            ("*", "admin"): RateRule(1, 2),
        }
        rl = ServiceRateLimiter(rules, clock=clock)
        assert rl.rule_for("forge", "swarm-write")[1] == "forge/swarm-write"
        assert rl.rule_for("forge", "other")[1] == "forge/*"
        assert rl.rule_for("x", "admin")[1] == "*/admin"
        assert rl.rule_for("x", "y") == (None, "")
        assert rl.check("x", "y").allowed and rl.check("x", "y").rule is None

    def test_star_policy_rule_shares_bucket(self, clock):
        rl = ServiceRateLimiter({("forge", "*"): RateRule(1, 2)}, clock=clock)
        assert rl.check("forge", "a").allowed and rl.check("forge", "b").allowed
        assert not rl.check("forge", "c").allowed

    def test_wildcard_service_rule_is_per_service(self, clock):
        rl = ServiceRateLimiter({("*", "admin"): RateRule(1, 1)}, clock=clock)
        assert rl.check("a", "admin").allowed and rl.check("b", "admin").allowed
        assert not rl.check("a", "admin").allowed

    def test_write_cost(self, clock):
        rl = ServiceRateLimiter(default=RateRule(rate_per_s=1, burst=4, write_cost=2), clock=clock)
        assert rl.check("s", None, method="POST").allowed
        assert rl.check("s", None, method="POST").allowed
        assert not rl.check("s", None, method="GET").allowed

    def test_anonymous_and_exempt(self, clock):
        rl = ServiceRateLimiter(default=RateRule(1, 1), clock=clock, exempt_services=["control-plane"])
        assert rl.check(None, None).key == ("anonymous", "*")
        for _ in range(10):
            assert rl.check("control-plane", None).allowed

    def test_lru_bound(self, clock):
        rl = ServiceRateLimiter(default=RateRule(1, 1), clock=clock, max_keys=3)
        for i in range(10):
            rl.check(f"svc{i}", None)
        assert rl.tracked_keys() == 3 and rl.stats()["evicted"] == 7

    def test_reset(self, clock):
        rl = ServiceRateLimiter(default=RateRule(1, 1), clock=clock)
        rl.check("a", None)
        rl.check("b", None)
        rl.reset("a")
        assert rl.check("a", None).allowed and not rl.check("b", None).allowed
        rl.reset()
        assert rl.tracked_keys() == 0

    def test_from_config(self, clock):
        rl = limiter_from_config(
            {"default": {"rate_per_s": 5}, "rules": [{"service": "forge", "rate_per_s": 1, "burst": 1}],
             "exempt": ["ops"]},
            clock=clock,
        )
        assert rl.default.burst == 5 and rl.rule_for("forge", "x")[1] == "forge/*"
        with pytest.raises(ValueError):
            limiter_from_config({"rules": [{"rate_per_s": 1}]})

    @pytest.mark.parametrize("kw", [{"rate_per_s": 0, "burst": 1}, {"rate_per_s": 1, "burst": 0.5},
                                    {"rate_per_s": 1, "burst": 1, "write_cost": 0}])
    def test_rule_validation(self, kw):
        with pytest.raises(ValueError):
            RateRule(**kw)
