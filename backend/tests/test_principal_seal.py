import hashlib
import hmac

import pytest

from core.principal_seal import (
    MAX_ID_LENGTH,
    PrincipalSealCodec,
    RouteDomainPolicy,
    RouteRule,
    SealConfigurationError,
    SealExpired,
    SealMalformed,
    SealSignatureInvalid,
    SealUnknownKey,
    VerifiedPrincipal,
)


KEY_OLD = b"o" * 32
KEY_NEW = b"n" * 32
NOW = 1_800_000_000


def codec(*, keys=None, signing_key_id="new", max_ttl_seconds=3600, clock_skew_seconds=30):
    return PrincipalSealCodec(
        keys or {"new": KEY_NEW},
        signing_key_id=signing_key_id,
        max_ttl_seconds=max_ttl_seconds,
        clock_skew_seconds=clock_skew_seconds,
    )


def test_round_trip_produces_verified_identity_only_after_signature_check():
    seals = codec()
    token = seals.issue("operator_7", "control-plane", ttl_seconds=300, now=NOW)
    principal = seals.verify(token, now=NOW + 5)
    assert principal == VerifiedPrincipal(
        principal_id="operator_7",
        attester_id="control-plane",
        key_id="new",
        issued_at=NOW,
        expires_at=NOW + 300,
    )
    assert principal.ttl_seconds == 300


def test_wire_format_is_versioned_key_addressed_and_signature_covers_key_id():
    seals = codec()
    token = seals.issue("alice", "ops", ttl_seconds=120, now=NOW)
    parts = token.split(".")
    assert parts[:6] == ["v1", "new", "alice", "ops", str(NOW), str(NOW + 120)]
    assert len(parts[6]) == 64
    tampered = token.replace("v1.new.", "v1.old.", 1)
    verifier = PrincipalSealCodec({"old": KEY_OLD, "new": KEY_NEW})
    with pytest.raises(SealSignatureInvalid):
        verifier.verify(tampered, now=NOW + 1)


def test_tampered_principal_or_expiry_is_rejected():
    seals = codec()
    token = seals.issue("alice", "ops", ttl_seconds=120, now=NOW)
    with pytest.raises(SealSignatureInvalid):
        seals.verify(token.replace(".alice.", ".mallory.", 1), now=NOW + 1)
    with pytest.raises(SealSignatureInvalid):
        seals.verify(token.replace(str(NOW + 120), str(NOW + 121), 1), now=NOW + 1)


def test_expired_and_not_yet_valid_credentials_fail_closed_outside_skew():
    seals = codec(clock_skew_seconds=10)
    token = seals.issue("alice", "ops", ttl_seconds=60, now=NOW)
    assert seals.verify(token, now=NOW + 70).principal_id == "alice"
    with pytest.raises(SealExpired, match="expired"):
        seals.verify(token, now=NOW + 71)
    with pytest.raises(SealExpired, match="not yet valid"):
        seals.verify(token, now=NOW - 11)


def test_verifier_rejects_credential_ttl_beyond_local_maximum_even_with_valid_hmac():
    payload = f"v1.new.alice.ops.{NOW}.{NOW + 7200}"
    signature = hmac.new(KEY_NEW, payload.encode(), hashlib.sha256).hexdigest()
    with pytest.raises(SealExpired, match="TTL"):
        codec(max_ttl_seconds=3600).verify(f"{payload}.{signature}", now=NOW + 1)


def test_rotation_accepts_old_live_key_while_issuance_moves_to_new_key():
    old_issuer = PrincipalSealCodec({"old": KEY_OLD}, signing_key_id="old")
    old_token = old_issuer.issue("alice", "ops", ttl_seconds=60, now=NOW)

    rotating = PrincipalSealCodec(
        {"old": KEY_OLD, "new": KEY_NEW},
        signing_key_id="new",
    )
    assert rotating.verify(old_token, now=NOW + 1).key_id == "old"
    new_token = rotating.issue("alice", "ops", ttl_seconds=60, now=NOW)
    assert rotating.verify(new_token, now=NOW + 1).key_id == "new"

    old_only = PrincipalSealCodec({"old": KEY_OLD})
    with pytest.raises(SealUnknownKey):
        old_only.verify(new_token, now=NOW + 1)


def test_verification_only_codec_cannot_mint_credentials():
    verifier = PrincipalSealCodec({"new": KEY_NEW})
    with pytest.raises(SealConfigurationError, match="verification-only"):
        verifier.issue("alice", "ops", now=NOW)


def test_configuration_requires_nonempty_strong_keyring_and_valid_signer():
    with pytest.raises(SealConfigurationError, match="cannot be empty"):
        PrincipalSealCodec({})
    with pytest.raises(SealConfigurationError, match="at least 32 bytes"):
        PrincipalSealCodec({"weak": b"tiny"})
    with pytest.raises(SealConfigurationError, match="not present"):
        PrincipalSealCodec({"new": KEY_NEW}, signing_key_id="missing")
    with pytest.raises(SealConfigurationError, match="positive"):
        PrincipalSealCodec({"new": KEY_NEW}, max_ttl_seconds=0)
    with pytest.raises(SealConfigurationError, match="clock skew"):
        PrincipalSealCodec({"new": KEY_NEW}, max_ttl_seconds=10, clock_skew_seconds=11)


def test_issuance_rejects_unbounded_or_ambiguous_identifiers_and_ttl():
    seals = codec()
    with pytest.raises(SealMalformed, match="unsupported"):
        seals.issue("alice.admin", "ops", now=NOW)
    with pytest.raises(SealMalformed, match="exceeds"):
        seals.issue("a" * (MAX_ID_LENGTH + 1), "ops", now=NOW)
    with pytest.raises(SealConfigurationError, match="ttl_seconds"):
        seals.issue("alice", "ops", ttl_seconds=0, now=NOW)
    with pytest.raises(SealConfigurationError, match="ttl_seconds"):
        seals.issue("alice", "ops", ttl_seconds=3601, now=NOW)


def test_malformed_tokens_are_rejected_before_identity_is_returned():
    seals = codec()
    malformed = [
        "",
        "v1.new.alice.ops.1.2",
        "v2.new.alice.ops.1.2." + "0" * 64,
        "v1.new.alice.ops.nope.2." + "0" * 64,
        "v1.new.alice.ops.2.1." + "0" * 64,
        "v1.new.alice.ops.1.2.not-hex",
    ]
    for token in malformed:
        with pytest.raises(SealMalformed):
            seals.verify(token, now=NOW)


def make_policy():
    return RouteDomainPolicy(
        open_prefixes=("/api/health", "/api/ready"),
        domain_rules=(
            RouteRule("/api/studio", "studio"),
            RouteRule("/api/studio/admin", "studio_admin"),
            RouteRule("/api/jeeves", "jeeves"),
        ),
    )


def verified_principal():
    issuer = codec()
    return issuer.verify(issuer.issue("operator", "control", now=NOW), now=NOW + 1)


def test_route_policy_allows_only_explicit_open_prefixes_without_identity():
    policy = make_policy()
    assert policy.admit("/api/health", None).allowed is True
    assert policy.admit("/api/health/live", None).open_route is True
    assert policy.admit("/api/ready", None).status_code == 200
    assert policy.admit("/api/healthcheck", None).status_code == 404


def test_route_policy_is_segment_aware_and_unknown_routes_are_sealed():
    policy = make_policy()
    assert policy.required_domain("/api/studio") == "studio"
    assert policy.required_domain("/api/studio/projects/1") == "studio"
    assert policy.required_domain("/api/studioevil") is None
    denied = policy.admit("/api/not-written", verified_principal())
    assert denied.allowed is False
    assert denied.status_code == 404
    assert denied.reason == "unwritten route is sealed"


def test_longest_route_prefix_selects_more_specific_governance_domain():
    policy = make_policy()
    assert policy.required_domain("/api/studio/admin") == "studio_admin"
    assert policy.required_domain("/api/studio/admin/jobs") == "studio_admin"
    assert policy.required_domain("/api/studio/assets") == "studio"


def test_protected_written_route_requires_verified_principal():
    policy = make_policy()
    denied = policy.admit("/api/jeeves/run", None)
    assert denied.allowed is False
    assert denied.status_code == 401
    assert denied.domain == "jeeves"
    assert denied.principal_id is None
    assert denied.attester_id is None

    principal = verified_principal()
    admitted = policy.admit("/api/jeeves/run", principal)
    assert admitted.allowed is True
    assert admitted.status_code == 200
    assert admitted.domain == "jeeves"
    assert admitted.principal_id == "operator"
    assert admitted.attester_id == "control"


def test_route_policy_rejects_duplicate_or_non_path_rules():
    with pytest.raises(ValueError, match="duplicate"):
        RouteDomainPolicy(
            domain_rules=(RouteRule("/api/x", "x"), RouteRule("/api/x/", "y")),
        )
    with pytest.raises(ValueError, match="absolute URL paths"):
        RouteDomainPolicy(domain_rules=(RouteRule("api/x", "x"),))
    with pytest.raises(ValueError, match="without query"):
        make_policy().admit("/api/studio?admin=true", verified_principal())
