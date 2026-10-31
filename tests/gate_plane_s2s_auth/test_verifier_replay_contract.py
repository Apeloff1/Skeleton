import pytest

from skeleton.gate_plane.s2s.nonce import LocalNonceStoreDouble, NonceStoreFull, s2s_scope
from skeleton.gate_plane.s2s.tokens import TokenError, TokenErrorCode
from skeleton.gate_plane.s2s.verifier import RegistryVerifier


def _v(ring, registry, nonces, clock, **kw):
    return RegistryVerifier("gate", ring, registry=registry, nonce_store=nonces, clock=clock, **kw)


def test_fresh_then_replay(ring, registry, nonces, clock, signer_for):
    v = _v(ring, registry, nonces, clock)
    tok = signer_for("forge-worker").mint("gate", ["forge:read"])
    vt = v.verify(tok)
    assert vt.nonce_scope == s2s_scope("forge-worker") == "s2s:forge-worker"
    with pytest.raises(TokenError) as ei:
        v.verify(tok)
    assert ei.value.code is TokenErrorCode.REPLAYED


def test_scope_clamped_to_ceiling(ring, registry, nonces, clock, signer_for):
    vt = _v(ring, registry, nonces, clock).verify(signer_for("swarm-agent").mint("gate", ["swarm:read", "forge:write"]))
    assert set(vt.claims.scopes) == {"swarm:read"}
    assert set(vt.stripped) == {"forge:write"}


def test_unregistered_and_disabled_rejected(ring, registry, nonces, clock, signer_for):
    v = _v(ring, registry, nonces, clock)
    with pytest.raises(TokenError) as ei:
        v.verify(signer_for("ghost-svc").mint("gate", ["forge:read"]))
    assert ei.value.code is TokenErrorCode.BAD_ISSUER
    registry.disable("forge-worker")
    with pytest.raises(TokenError) as ei:
        v.verify(signer_for("forge-worker").mint("gate", ["forge:read"]))
    assert ei.value.code is TokenErrorCode.BAD_ISSUER


def test_rejected_tokens_do_not_burn_nonce(ring, registry, nonces, clock, signer_for):
    v = _v(ring, registry, nonces, clock)
    registry.disable("forge-worker")
    with pytest.raises(TokenError):
        v.verify(signer_for("forge-worker").mint("gate", ["forge:read"]))
    assert nonces.calls == 0


def test_too_old_iat_rejected(ring, registry, nonces, clock, signer_for):
    v = _v(ring, registry, nonces, clock, max_age_s=60)
    tok = signer_for("forge-worker").mint("gate", ["forge:read"], ttl_s=300)
    clock.advance(120)
    with pytest.raises(TokenError) as ei:
        v.verify(tok)
    assert ei.value.code is TokenErrorCode.EXPIRED


def test_nonce_store_full_propagates(ring, registry, clock, signer_for):
    store = LocalNonceStoreDouble(max_entries=1, clock=clock.now)
    v = _v(ring, registry, store, clock)
    v.verify(signer_for("forge-worker").mint("gate", ["forge:read"]))
    with pytest.raises(NonceStoreFull):
        v.verify(signer_for("forge-worker").mint("gate", ["forge:read"]))


def test_double_matches_protocol_semantics(clock):
    s = LocalNonceStoreDouble(clock=clock.now)
    assert s.check_and_record("s2s:a", "n1", clock.now(), 10.0) is True
    assert s.check_and_record("s2s:a", "n1", clock.now(), 10.0) is False
    assert s.check_and_record("s2s:b", "n1", clock.now(), 10.0) is True
    assert s.check_and_record("", "n", clock.now(), 10.0) is False
    assert s.check_and_record("s2s:a", "n2", clock.now(), 0.0) is False
