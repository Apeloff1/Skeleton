"""Pack F — s2s key ring, signed service tokens, rotation and revocation."""

from __future__ import annotations

import json

import pytest

from skeleton.gate_plane.s2s.clock import ManualClock
from skeleton.gate_plane.s2s.keyring import (
    KeyRing,
    KeyRingError,
    KeyState,
    NoActiveKeyError,
    UnknownKeyError,
    fingerprint,
    validate_kid,
)
from skeleton.gate_plane.s2s.rotation import (
    RevocationList,
    RotationPolicy,
    RotationScheduler,
    derived_secret_factory,
    random_secret_factory,
)
from skeleton.gate_plane.s2s.tokens import (
    MAX_TOKEN_BYTES,
    ReplayCache,
    ServiceClaims,
    TokenError,
    TokenErrorCode,
    TokenSigner,
    TokenVerifier,
    b64url_decode,
    b64url_encode,
    canonical_json,
    encode_token,
    scope_granted,
    split_token,
)

MASTER = b"m" * 32
SECRET_A = b"a" * 32
SECRET_B = b"b" * 32
SECRET_C = b"c" * 32


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def ring(clock: ManualClock) -> KeyRing:
    r = KeyRing(clock=clock)
    r.add_key("k1", SECRET_A, activate=True)
    return r


def _jti_seq():
    n = iter(range(1, 10_000))
    return lambda: f"jti-{next(n):08d}"


def _signer(ring: KeyRing, clock: ManualClock, service: str = "forge") -> TokenSigner:
    return TokenSigner(service, ring, clock=clock, jti_factory=_jti_seq())


def _verifier(ring: KeyRing, clock: ManualClock, **kw) -> TokenVerifier:
    return TokenVerifier("gateway", ring, clock=clock, **kw)


# --- clock -----------------------------------------------------------------


def test_manual_clock_sleep_advances_and_records(clock: ManualClock):
    t0, m0 = clock.now(), clock.monotonic()
    clock.sleep(1.5)
    clock.sleep(-3)
    assert clock.now() == t0 + 1.5
    assert clock.monotonic() == m0 + 1.5
    assert clock.sleeps == [1.5, 0.0]


def test_manual_clock_rejects_negative_advance(clock: ManualClock):
    with pytest.raises(ValueError):
        clock.advance(-1)


def test_manual_clock_set_wall_keeps_monotonic(clock: ManualClock):
    m0 = clock.monotonic()
    clock.set_wall(10.0)
    assert clock.now() == 10.0
    assert clock.monotonic() == m0


# --- key ring --------------------------------------------------------------


@pytest.mark.parametrize("kid", ["k1", "svc.key-01", "A:b_c", "x" * 64])
def test_validate_kid_accepts(kid):
    assert validate_kid(kid) == kid


@pytest.mark.parametrize("kid", ["", "-lead", "has space", "x" * 65, "k/1", None, 7])
def test_validate_kid_rejects(kid):
    with pytest.raises(KeyRingError):
        validate_kid(kid)


def test_add_key_rejects_short_secret(clock):
    ring = KeyRing(clock=clock)
    with pytest.raises(KeyRingError):
        ring.add_key("k1", b"short")


def test_add_key_rejects_non_bytes(clock):
    ring = KeyRing(clock=clock)
    with pytest.raises(KeyRingError):
        ring.add_key("k1", "a" * 40)  # type: ignore[arg-type]


def test_add_key_rejects_duplicate(ring):
    with pytest.raises(KeyRingError):
        ring.add_key("k1", SECRET_B)


def test_max_keys_minimum():
    with pytest.raises(KeyRingError):
        KeyRing(max_keys=1)


def test_key_ring_full(clock):
    ring = KeyRing(clock=clock, max_keys=2)
    ring.add_key("k1", SECRET_A, activate=True)
    ring.add_key("k2", SECRET_B)
    with pytest.raises(KeyRingError):
        ring.add_key("k3", SECRET_C)
    ring.revoke("k2")
    ring.add_key("k3", SECRET_C)
    assert "k3" in ring


def test_new_key_is_pending(ring):
    k = ring.add_key("k2", SECRET_B)
    assert k.state is KeyState.PENDING
    assert not k.can_sign()
    assert ring.signing_key().kid == "k1"


def test_signing_key_requires_active(clock):
    ring = KeyRing(clock=clock)
    ring.add_key("k1", SECRET_A)
    with pytest.raises(NoActiveKeyError):
        ring.signing_key()


def test_rotate_moves_previous_to_retiring(ring, clock):
    ring.rotate("k2", SECRET_B, overlap_s=60)
    assert ring.signing_key().kid == "k2"
    old = ring.get("k1")
    assert old.state is KeyState.RETIRING
    assert old.retire_at == clock.now() + 60


def test_retiring_key_verifies_within_overlap_only(ring, clock):
    ring.rotate("k2", SECRET_B, overlap_s=60)
    assert ring.verification_key("k1") is not None
    clock.advance(59.9)
    assert ring.verification_key("k1") is not None
    clock.advance(0.2)
    assert ring.verification_key("k1") is None
    assert ring.state_of("k1") is KeyState.EXPIRED


def test_zero_overlap_rotation_expires_immediately(ring):
    ring.rotate("k2", SECRET_B, overlap_s=0)
    assert ring.state_of("k1") is KeyState.EXPIRED
    assert ring.verification_key("k1") is None


def test_negative_overlap_rejected(ring):
    ring.add_key("k2", SECRET_B)
    with pytest.raises(KeyRingError):
        ring.activate("k2", overlap_s=-1)


def test_activate_is_idempotent_for_active(ring):
    assert ring.activate("k1").state is KeyState.ACTIVE
    assert ring.kids(states=[KeyState.ACTIVE]) == ["k1"]


def test_cannot_activate_revoked_or_expired(ring):
    ring.add_key("k2", SECRET_B)
    ring.revoke("k2", reason="leak")
    with pytest.raises(KeyRingError):
        ring.activate("k2")
    ring.rotate("k3", SECRET_C, overlap_s=0)
    with pytest.raises(KeyRingError):
        ring.activate("k1")


def test_revoke_is_immediate_even_in_overlap(ring):
    ring.rotate("k2", SECRET_B, overlap_s=600)
    ring.revoke("k1", reason="compromised")
    assert ring.verification_key("k1") is None
    assert ring.get("k1").revoked_reason == "compromised"
    assert ring.revoke("k1").state is KeyState.REVOKED  # idempotent


def test_revoke_active_leaves_no_signer(ring):
    ring.revoke("k1")
    with pytest.raises(NoActiveKeyError):
        ring.signing_key()


def test_unknown_kid_raises(ring):
    with pytest.raises(UnknownKeyError):
        ring.get("nope")
    with pytest.raises(UnknownKeyError):
        ring.revoke("nope")


def test_pending_verifies_only_when_accepted(ring):
    ring.add_key("k2", SECRET_B)
    assert ring.verification_key("k2") is None
    assert ring.verification_key("k2", accept_pending=True) is not None


def test_shorten_overlap_only_moves_earlier(ring, clock):
    ring.rotate("k2", SECRET_B, overlap_s=600)
    ring.shorten_overlap("k1", clock.now() + 10_000)
    assert ring.get("k1").retire_at == clock.now() + 600
    ring.shorten_overlap("k1", clock.now() + 5)
    assert ring.get("k1").retire_at == clock.now() + 5
    ring.shorten_overlap("k1", clock.now() - 1)
    assert ring.state_of("k1") is KeyState.EXPIRED


def test_shorten_overlap_requires_retiring(ring):
    with pytest.raises(KeyRingError):
        ring.shorten_overlap("k1", 0)


def test_prune_drops_expired_and_revoked(ring, clock):
    ring.rotate("k2", SECRET_B, overlap_s=10)
    ring.add_key("k3", SECRET_C)
    ring.revoke("k3")
    clock.advance(11)
    dropped = ring.prune()
    assert dropped == ["k1", "k3"]
    assert ring.kids() == ["k2"]
    assert len(ring) == 1


def test_tick_reports_expired(ring, clock):
    ring.rotate("k2", SECRET_B, overlap_s=10)
    assert ring.tick() == []
    clock.advance(10)
    assert ring.tick() == ["k1"]


def test_snapshot_has_no_secrets(ring):
    ring.rotate("k2", SECRET_B, overlap_s=10)
    snap = ring.snapshot()
    blob = json.dumps(snap)
    assert "aaaa" not in blob and "bbbb" not in blob
    assert snap["active_kid"] == "k2"
    assert {k["kid"] for k in snap["keys"]} == {"k1", "k2"}
    assert snap["keys"][0]["fingerprint"] == fingerprint(SECRET_A)


def test_repr_hides_secret(ring):
    assert "aaaa" not in repr(ring.get("k1"))


def test_events_log_lifecycle(ring):
    ring.rotate("k2", SECRET_B, overlap_s=10)
    ring.revoke("k1", reason="r")
    actions = [(e.action, e.kid) for e in ring.events()]
    assert ("add", "k1") in actions
    assert ("activate", "k2") in actions
    assert ("retire", "k1") in actions
    assert ("revoke", "k1") in actions
    assert all("at" in e.as_dict() for e in ring.events())


def test_fingerprint_stable_and_distinct():
    assert fingerprint(SECRET_A) == fingerprint(SECRET_A)
    assert fingerprint(SECRET_A) != fingerprint(SECRET_B)
    assert len(fingerprint(SECRET_A)) == 16


# --- encoding helpers ------------------------------------------------------


@pytest.mark.parametrize("raw", [b"", b"a", b"ab", b"abc", bytes(range(256))])
def test_b64url_roundtrip(raw):
    if raw == b"":
        assert b64url_encode(raw) == ""
        return
    assert b64url_decode(b64url_encode(raw)) == raw


@pytest.mark.parametrize("bad", ["", "abc=", "a+b", "a/b", "a b", None])
def test_b64url_decode_rejects(bad):
    with pytest.raises(TokenError) as ei:
        b64url_decode(bad)  # type: ignore[arg-type]
    assert ei.value.code is TokenErrorCode.MALFORMED


def test_canonical_json_sorted_compact():
    assert canonical_json({"b": 1, "a": [1, 2]}) == b'{"a":[1,2],"b":1}'


@pytest.mark.parametrize(
    "granted,required,ok",
    [
        ({"forge:write"}, "forge:write", True),
        ({"forge:*"}, "forge:write", True),
        ({"forge:*"}, "forgery:write", False),
        ({"forge:read"}, "forge:write", False),
        (set(), "forge:read", False),
        ({"a:b:*"}, "a:b:c", True),
    ],
)
def test_scope_granted(granted, required, ok):
    assert scope_granted(granted, required) is ok


# --- sign / verify ---------------------------------------------------------


def test_mint_and_verify_roundtrip(ring, clock):
    token = _signer(ring, clock).mint("gateway", ["forge:write", "forge:read"])
    v = _verifier(ring, clock).verify(token)
    assert v.service == "forge"
    assert v.kid == "k1"
    assert v.claims.scopes == frozenset({"forge:write", "forge:read"})
    assert v.claims.has_scope("forge:write")
    assert not v.in_overlap


def test_token_is_deterministic_for_same_inputs(ring, clock):
    s1 = TokenSigner("forge", ring, clock=clock, jti_factory=lambda: "fixed-jti-1")
    s2 = TokenSigner("forge", ring, clock=clock, jti_factory=lambda: "fixed-jti-1")
    assert s1.mint("gateway", ["b:x", "a:y"]) == s2.mint("gateway", ["a:y", "b:x"])


def test_default_jti_unique(ring, clock):
    s = TokenSigner("forge", ring, clock=clock)
    jtis = {_verifier(ring, clock).verify(s.mint("gateway")).claims.jti for _ in range(50)}
    assert len(jtis) == 50


def test_extra_claims_roundtrip(ring, clock):
    token = _signer(ring, clock).mint("gateway", extra={"tenant": "t1", "trace": "abc"})
    assert dict(_verifier(ring, clock).verify(token).claims.extra) == {"tenant": "t1", "trace": "abc"}


@pytest.mark.parametrize("ttl", [0, -1, 3601])
def test_mint_rejects_bad_ttl(ring, clock, ttl):
    with pytest.raises(ValueError):
        _signer(ring, clock).mint("gateway", ttl_s=ttl)


def test_signer_rejects_bad_default_ttl(ring, clock):
    with pytest.raises(ValueError):
        TokenSigner("forge", ring, clock=clock, default_ttl_s=0)


@pytest.mark.parametrize("name", ["Forge", "1svc", "", "a" * 64, "svc!"])
def test_signer_rejects_bad_service_name(ring, clock, name):
    with pytest.raises(ValueError):
        TokenSigner(name, ring, clock=clock)


def test_mint_rejects_bad_scope(ring, clock):
    with pytest.raises(ValueError):
        _signer(ring, clock).mint("gateway", ["Forge:Write"])


def test_mint_with_explicit_non_active_kid_fails(ring, clock):
    ring.add_key("k2", SECRET_B)
    with pytest.raises(NoActiveKeyError):
        _signer(ring, clock).mint("gateway", kid="k2")


def test_mint_with_explicit_active_kid(ring, clock):
    token = _signer(ring, clock).mint("gateway", kid="k1")
    assert split_token(token)[0]["kid"] == "k1"


def test_expired_token(ring, clock):
    token = _signer(ring, clock).mint("gateway", ttl_s=60)
    v = _verifier(ring, clock, leeway_s=5)
    clock.advance(64)
    v.verify(token)
    clock.advance(1)
    with pytest.raises(TokenError) as ei:
        v.verify(token)
    assert ei.value.code is TokenErrorCode.EXPIRED


def test_not_yet_valid(ring, clock):
    token = _signer(ring, clock).mint("gateway", not_before_s=30)
    v = _verifier(ring, clock, leeway_s=5)
    with pytest.raises(TokenError) as ei:
        v.verify(token)
    assert ei.value.code is TokenErrorCode.NOT_YET_VALID
    clock.advance(25)
    v.verify(token)


def test_bad_audience(ring, clock):
    token = _signer(ring, clock).mint("billing")
    with pytest.raises(TokenError) as ei:
        _verifier(ring, clock).verify(token)
    assert ei.value.code is TokenErrorCode.BAD_AUDIENCE


def test_untrusted_issuer(ring, clock):
    token = _signer(ring, clock, service="rogue").mint("gateway")
    with pytest.raises(TokenError) as ei:
        _verifier(ring, clock, trusted_issuers={"forge"}).verify(token)
    assert ei.value.code is TokenErrorCode.BAD_ISSUER


def test_lifetime_exceeded(ring, clock):
    token = _signer(ring, clock).mint("gateway", ttl_s=3600)
    with pytest.raises(TokenError) as ei:
        _verifier(ring, clock, max_lifetime_s=600).verify(token)
    assert ei.value.code is TokenErrorCode.LIFETIME_EXCEEDED


def test_verifier_rejects_bad_leeway(ring, clock):
    with pytest.raises(ValueError):
        _verifier(ring, clock, leeway_s=-1)
    with pytest.raises(ValueError):
        _verifier(ring, clock, leeway_s=301)


def test_tampered_claims_bad_signature(ring, clock):
    token = _signer(ring, clock).mint("gateway", ["forge:read"])
    h, c, s = token.split(".")
    claims = json.loads(b64url_decode(c))
    claims["scp"] = ["forge:admin"]
    forged = ".".join([h, b64url_encode(canonical_json(claims)), s])
    with pytest.raises(TokenError) as ei:
        _verifier(ring, clock).verify(forged)
    assert ei.value.code is TokenErrorCode.BAD_SIGNATURE


def test_signature_from_other_key_rejected(ring, clock):
    other = KeyRing(clock=clock)
    other.add_key("k1", SECRET_B, activate=True)
    token = _signer(other, clock).mint("gateway")
    with pytest.raises(TokenError) as ei:
        _verifier(ring, clock).verify(token)
    assert ei.value.code is TokenErrorCode.BAD_SIGNATURE


@pytest.mark.parametrize(
    "header",
    [
        {"alg": "none", "kid": "k1", "typ": "s2s+v1"},
        {"alg": "HS512", "kid": "k1", "typ": "s2s+v1"},
        {"alg": "HS256", "kid": "k1", "typ": "JWT"},
        {"alg": "HS256", "kid": "k1", "typ": "s2s+v1", "jku": "http://evil"},
        {"alg": "HS256", "kid": 1, "typ": "s2s+v1"},
    ],
)
def test_bad_header_rejected(ring, clock, header):
    token = _signer(ring, clock).mint("gateway")
    _, c, s = token.split(".")
    forged = ".".join([b64url_encode(canonical_json(header)), c, s])
    with pytest.raises(TokenError) as ei:
        _verifier(ring, clock).verify(forged)
    assert ei.value.code is TokenErrorCode.BAD_HEADER


@pytest.mark.parametrize(
    "token",
    ["", "a.b", "a.b.c.d", "!!.!!.!!", b64url_encode(b"[]") + "." + b64url_encode(b"{}") + ".AA"],
)
def test_malformed_tokens(ring, clock, token):
    with pytest.raises(TokenError) as ei:
        _verifier(ring, clock).verify(token)
    assert ei.value.code is TokenErrorCode.MALFORMED


def test_non_json_segment(ring, clock):
    token = b64url_encode(b"not json") + "." + b64url_encode(b"{}") + ".AA"
    with pytest.raises(TokenError) as ei:
        _verifier(ring, clock).verify(token)
    assert ei.value.code is TokenErrorCode.MALFORMED


def test_non_string_token(ring, clock):
    with pytest.raises(TokenError):
        _verifier(ring, clock).verify(123)  # type: ignore[arg-type]


def test_oversize_token(ring, clock):
    with pytest.raises(TokenError) as ei:
        _verifier(ring, clock).verify("a" * (MAX_TOKEN_BYTES + 1))
    assert ei.value.code is TokenErrorCode.TOO_LARGE


def test_unknown_kid_code(ring, clock):
    other = KeyRing(clock=clock)
    other.add_key("zz", SECRET_A, activate=True)
    token = _signer(other, clock).mint("gateway")
    with pytest.raises(TokenError) as ei:
        _verifier(ring, clock).verify(token)
    assert ei.value.code is TokenErrorCode.UNKNOWN_KID


def test_revoked_kid_code(ring, clock):
    token = _signer(ring, clock).mint("gateway")
    ring.revoke("k1")
    with pytest.raises(TokenError) as ei:
        _verifier(ring, clock).verify(token)
    assert ei.value.code is TokenErrorCode.REVOKED_KID


def test_expired_kid_code_after_overlap(ring, clock):
    token = _signer(ring, clock).mint("gateway", ttl_s=3600)
    ring.rotate("k2", SECRET_B, overlap_s=30)
    v = _verifier(ring, clock)
    assert v.verify(token).in_overlap
    clock.advance(31)
    with pytest.raises(TokenError) as ei:
        v.verify(token)
    assert ei.value.code is TokenErrorCode.EXPIRED_KID


def test_pending_kid_accepted_when_configured(ring, clock):
    ring.add_key("k2", SECRET_B)
    token = encode_token(
        ServiceClaims("forge", "gateway", frozenset(), clock.now(), clock.now(), clock.now() + 60, "jti-pending"),
        "k2",
        SECRET_B,
    )
    with pytest.raises(TokenError):
        _verifier(ring, clock).verify(token)
    assert _verifier(ring, clock, accept_pending=True).verify(token).kid == "k2"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.pop("iss"),
        lambda c: c.update(iss="Bad Name"),
        lambda c: c.update(scp="forge:read"),
        lambda c: c.update(scp=["BAD"]),
        lambda c: c.update(exp="soon"),
        lambda c: c.update(exp=True),
        lambda c: c.update(jti="short"),
        lambda c: c.update(ext={"a": 1}),
        lambda c: c.update(exp=c["nbf"]),
        lambda c: c.update(nbf=c["iat"] - 100),
    ],
)
def test_bad_claims_rejected(ring, clock, mutate):
    now = clock.now()
    wire = ServiceClaims("forge", "gateway", frozenset({"forge:read"}), now, now, now + 60, "jti-12345678").to_wire()
    mutate(wire)
    import hashlib
    import hmac as _hmac

    h = b64url_encode(canonical_json({"alg": "HS256", "kid": "k1", "typ": "s2s+v1"}))
    c = b64url_encode(canonical_json(wire))
    sig = b64url_encode(_hmac.new(SECRET_A, f"{h}.{c}".encode(), hashlib.sha256).digest())
    with pytest.raises(TokenError) as ei:
        _verifier(ring, clock).verify(f"{h}.{c}.{sig}")
    assert ei.value.code is TokenErrorCode.BAD_CLAIMS


def test_replay_cache_blocks_second_use(ring, clock):
    cache = ReplayCache()
    v = _verifier(ring, clock, replay_cache=cache)
    token = _signer(ring, clock).mint("gateway", ttl_s=30)
    v.verify(token)
    with pytest.raises(TokenError) as ei:
        v.verify(token)
    assert ei.value.code is TokenErrorCode.REPLAYED


def test_replay_cache_evicts_after_expiry(clock):
    cache = ReplayCache()
    assert cache.check_and_add("j1", exp=clock.now() + 10, now=clock.now())
    assert not cache.check_and_add("j1", exp=clock.now() + 10, now=clock.now())
    assert cache.check_and_add("j1", exp=clock.now() + 30, now=clock.now() + 11)


def test_replay_cache_capacity_bound(clock):
    cache = ReplayCache(capacity=3)
    for i in range(5):
        cache.check_and_add(f"j{i}", exp=clock.now() + 100, now=clock.now())
    assert len(cache) == 3


def test_revoked_jti(ring, clock):
    rl = RevocationList(ring)
    v = _verifier(ring, clock, revoked_jtis=rl)
    token = _signer(ring, clock).mint("gateway", ttl_s=60)
    jti = v.verify(token).claims.jti
    rl.revoke_token(jti, until=clock.now() + 60)
    with pytest.raises(TokenError) as ei:
        v.verify(token)
    assert ei.value.code is TokenErrorCode.REVOKED_TOKEN


# --- rotation --------------------------------------------------------------


def test_rotation_policy_validation():
    with pytest.raises(KeyRingError):
        RotationPolicy(rotate_every_s=0)
    with pytest.raises(KeyRingError):
        RotationPolicy(overlap_s=-1)
    with pytest.raises(KeyRingError):
        RotationPolicy(rotate_every_s=100, prepublish_s=100)
    with pytest.raises(KeyRingError):
        RotationPolicy(rotate_every_s=10, overlap_s=41, prepublish_s=1)
    assert RotationPolicy().as_dict()["kid_prefix"] == "k"


def test_derived_secret_factory_deterministic():
    f = derived_secret_factory(MASTER)
    assert f("k000001") == f("k000001")
    assert f("k000001") != f("k000002")
    assert len(f("k")) == 32
    assert len(derived_secret_factory(MASTER, nbytes=80)("k")) == 80


def test_derived_secret_factory_rejects_short_master():
    with pytest.raises(KeyRingError):
        derived_secret_factory(b"short")


def test_random_secret_factory_length():
    f = random_secret_factory(40)
    assert len(f("x")) == 40 and f("x") != f("x")


def _sched(clock, **policy):
    ring = KeyRing(clock=clock)
    pol = RotationPolicy(**{"rotate_every_s": 100, "overlap_s": 20, "prepublish_s": 10, **policy})
    return ring, RotationScheduler(ring, policy=pol, secret_factory=derived_secret_factory(MASTER), clock=clock)


def test_scheduler_requires_bootstrap(clock):
    _, s = _sched(clock)
    with pytest.raises(KeyRingError):
        s.tick()
    with pytest.raises(KeyRingError):
        s.rotate_now()


def test_scheduler_bootstrap_idempotent(clock):
    ring, s = _sched(clock)
    kid = s.bootstrap()
    assert s.bootstrap() == kid
    assert ring.signing_key().kid == kid == "k000001"
    assert s.next_rotation_at == clock.now() + 100


def test_scheduler_prepublishes_then_rotates(clock):
    ring, s = _sched(clock)
    s.bootstrap()
    clock.advance(89)
    assert s.tick() == []
    clock.advance(1)
    events = s.tick()
    assert [e.action for e in events] == ["prepublish"]
    assert ring.state_of("k000002") is KeyState.PENDING
    clock.advance(10)
    events = s.tick()
    assert [e.action for e in events] == ["rotate"]
    assert ring.signing_key().kid == "k000002"
    assert ring.state_of("k000001") is KeyState.RETIRING


def test_scheduler_prunes_after_overlap(clock):
    ring, s = _sched(clock)
    s.bootstrap()
    clock.advance(100)
    s.tick()
    clock.advance(20)
    events = s.tick()
    assert ("prune", "k000001") in [(e.action, e.kid) for e in events]
    assert "k000001" not in ring


def test_scheduler_catches_up_with_single_rotation(clock):
    ring, s = _sched(clock)
    s.bootstrap()
    clock.advance(1000)
    events = s.tick()
    assert [e.action for e in events].count("rotate") == 1
    assert ring.signing_key().kid == "k000002"


def test_scheduler_rotate_now_and_status(clock):
    ring, s = _sched(clock)
    s.bootstrap()
    kid = s.rotate_now()
    assert kid == "k000002"
    st = s.status()
    assert st["generation"] == 2
    assert st["pending_kid"] is None
    assert set(st["live_kids"]) == {"k000001", "k000002"}


def test_scheduler_skips_existing_kids(clock):
    ring, s = _sched(clock)
    ring.add_key("k000001", SECRET_A)
    assert s.bootstrap() == "k000002"


def test_tokens_survive_scheduled_rotation_within_overlap(clock):
    ring, s = _sched(clock)
    s.bootstrap()
    signer = _signer(ring, clock)
    verifier = _verifier(ring, clock)
    token_old = signer.mint("gateway", ttl_s=300)
    clock.advance(100)
    s.tick()
    token_new = signer.mint("gateway", ttl_s=300)
    assert verifier.verify(token_old).in_overlap
    assert verifier.verify(token_new).kid == "k000002"
    clock.advance(21)
    s.tick()
    with pytest.raises(TokenError):
        verifier.verify(token_old)
    assert verifier.verify(token_new).kid == "k000002"


def test_replicas_with_derived_secrets_interoperate(clock):
    ring_a, sa = _sched(clock)
    ring_b, sb = _sched(clock)
    sa.bootstrap()
    sb.bootstrap()
    token = _signer(ring_a, clock).mint("gateway")
    assert _verifier(ring_b, clock).verify(token).kid == "k000001"


def test_revocation_list_kid_fanout(ring):
    rl = RevocationList(ring)
    rl.revoke_kid("k1", reason="leak")
    assert rl.kid_revoked("k1")
    assert ring.state_of("k1") is KeyState.REVOKED
    rl.revoke_kid("unknown")  # tolerated: not in ring
    assert rl.snapshot()["revoked_kids"] == ["k1", "unknown"]


def test_revocation_list_expiry_and_purge(clock):
    rl = RevocationList()
    now = clock.now()
    rl.revoke_token("j1", until=now + 10)
    rl.revoke_token("j2", until=now + 20)
    assert rl.is_revoked("j1", now)
    assert not rl.is_revoked("j1", now + 10)
    assert rl.purge(now + 30) == 1
    assert rl.snapshot()["revoked_jtis"] == 0


def test_revocation_list_capacity_drops_soonest(clock):
    rl = RevocationList(capacity=2)
    now = clock.now()
    rl.revoke_token("a", until=now + 5)
    rl.revoke_token("b", until=now + 50)
    rl.revoke_token("c", until=now + 30)
    assert not rl.is_revoked("a", now)
    assert rl.is_revoked("b", now) and rl.is_revoked("c", now)
