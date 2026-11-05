from skeleton.gate_plane.s2s.audit import InMemoryAuditSink, KIND_DECISION
from skeleton.gate_plane.s2s.assembly import build_registry_s2s_gate
from skeleton.gate_plane.s2s.bound_gate import header_cert_source
from skeleton.gate_plane.s2s.nonce import LocalNonceStoreDouble
from tests.gate_plane_s2s_auth.conftest import FP_A, FP_B


def _asm(ring, registry, nonces, clock, sink=None, cert_source=None):
    return build_registry_s2s_gate(
        audience="gate", keyring=ring, registry=registry, nonce_store=nonces, clock=clock,
        admission=False, audit_sinks=[sink] if sink is not None else (), cert_source=cert_source,
    )


def _h(tok, fp=None):
    h = {"authorization": f"Service {tok}"}
    if fp:
        h["x-client-cert-sha256"] = fp
    return h


def test_allow_and_scope_enforced(ring, registry, nonces, clock, signer_for):
    gate = _asm(ring, registry, nonces, clock).gate
    ok = gate.evaluate("GET", "/api/v1/forge/jobs", _h(signer_for("forge-worker").mint("gate", ["forge:read"])))
    assert ok.http_status == 200
    # swarm-agent asks for forge:read beyond its ceiling -> clamped -> 403
    d = gate.evaluate("GET", "/api/v1/forge/jobs", _h(signer_for("swarm-agent").mint("gate", ["forge:read"])))
    assert d.http_status == 403


def test_replay_rejected_401(ring, registry, nonces, clock, signer_for):
    gate = _asm(ring, registry, nonces, clock).gate
    tok = signer_for("forge-worker").mint("gate", ["forge:read"])
    assert gate.evaluate("GET", "/api/v1/forge/x", _h(tok)).http_status == 200
    assert gate.evaluate("GET", "/api/v1/forge/x", _h(tok)).http_status == 401


def test_binding_required(ring, registry, nonces, clock, signer_for):
    # Test-only stand-in for a TLS terminator that strips untrusted headers.
    gate = _asm(ring, registry, nonces, clock, cert_source=header_cert_source()).gate
    s = signer_for("bound-svc")
    assert gate.evaluate("GET", "/api/v1/forge/x", _h(s.mint("gate", ["forge:read"]))).reason == "binding_missing"
    assert gate.evaluate("GET", "/api/v1/forge/x", _h(s.mint("gate", ["forge:read"]), FP_B)).reason == "binding_mismatch"
    assert nonces.calls == 0  # binding failures never burn a nonce
    assert gate.evaluate("GET", "/api/v1/forge/x", _h(s.mint("gate", ["forge:read"]), FP_A)).http_status == 200


def test_cnf_pin(ring, registry, nonces, clock, signer_for):
    gate = _asm(ring, registry, nonces, clock, cert_source=header_cert_source()).gate
    tok = signer_for("forge-worker").mint("gate", ["forge:read"], extra={"cnf": FP_A})
    assert gate.evaluate("GET", "/api/v1/forge/x", _h(tok, FP_B)).http_status == 401
    tok2 = signer_for("forge-worker").mint("gate", ["forge:read"], extra={"cnf": FP_A})
    assert gate.evaluate("GET", "/api/v1/forge/x", _h(tok2, FP_A)).http_status == 200


def test_nonce_store_full_is_503_fail_closed(ring, registry, clock, signer_for):
    sink = InMemoryAuditSink()
    store = LocalNonceStoreDouble(max_entries=1, clock=clock.now)
    gate = _asm(ring, registry, store, clock, sink).gate
    s = signer_for("forge-worker")
    assert gate.evaluate("GET", "/api/v1/forge/x", _h(s.mint("gate", ["forge:read"]))).http_status == 200
    d = gate.evaluate("GET", "/api/v1/forge/x", _h(s.mint("gate", ["forge:read"])))
    assert d.http_status == 503
    assert d.body()["error"] == "nonce_store_full"
    assert dict(d.headers).get("retry-after")
    evs = sink.events(kind=KIND_DECISION)
    assert len(evs) == 2  # each decision audited exactly once
    assert evs[-1].reason == "nonce_store_full" and evs[-1].security_relevant


def test_open_probe_not_audited(ring, registry, nonces, clock):
    sink = InMemoryAuditSink()
    gate = _asm(ring, registry, nonces, clock, sink).gate
    assert gate.evaluate("GET", "/health/live", {}).http_status == 200
    assert len(sink) == 0


def test_gate_rejects_replay_disabled_verifier(ring, registry, clock):
    import pytest
    from skeleton.gate_plane.s2s.authz import default_gate_plane_policies
    from skeleton.gate_plane.s2s.bound_gate import RegistryS2SAuthGate
    from skeleton.gate_plane.s2s.verifier import RegistryVerifier

    verifier = RegistryVerifier(
        "gate", ring, registry=registry, nonce_store=None,
        clock=clock, require_nonce_store=False,
    )
    with pytest.raises(ValueError, match="requires a replay nonce store"):
        RegistryS2SAuthGate(verifier, default_gate_plane_policies())


def test_gate_rejects_permissive_registry(ring, clock, nonces):
    import pytest
    from skeleton.gate_plane.s2s.authz import default_gate_plane_policies
    from skeleton.gate_plane.s2s.bound_gate import RegistryS2SAuthGate
    from skeleton.gate_plane.s2s.registry import ServiceRegistry
    from skeleton.gate_plane.s2s.verifier import RegistryVerifier

    verifier = RegistryVerifier(
        "gate", ring, registry=ServiceRegistry(strict=False), nonce_store=nonces,
        clock=clock,
    )
    with pytest.raises(ValueError, match="requires strict issuer registration"):
        RegistryS2SAuthGate(verifier, default_gate_plane_policies())


def test_untrusted_client_cert_header_is_not_mtls_proof_by_default(ring, registry, nonces, clock, signer_for):
    gate = _asm(ring, registry, nonces, clock).gate
    tok = signer_for("bound-svc").mint("gate", ["forge:read"])
    decision = gate.evaluate("GET", "/api/v1/forge/x", _h(tok, FP_A))
    assert decision.http_status == 401
    assert decision.reason == "binding_missing"
    assert nonces.calls == 0


def test_untrusted_cnf_header_is_rejected_by_default(ring, registry, nonces, clock, signer_for):
    gate = _asm(ring, registry, nonces, clock).gate
    tok = signer_for("forge-worker").mint("gate", ["forge:read"], extra={"cnf": FP_A})
    decision = gate.evaluate("GET", "/api/v1/forge/x", _h(tok, FP_A))
    assert decision.http_status == 401
    assert decision.reason == "binding_missing"
    assert nonces.calls == 0
