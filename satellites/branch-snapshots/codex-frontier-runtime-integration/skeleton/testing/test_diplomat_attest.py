"""Tests for diplomat-direct in-court attestation envelopes (AUDIT F4)."""

from __future__ import annotations

import hashlib
import time

import pytest

from skeleton.kernel import keyholder as kh
from skeleton.kernel.attest import (
    AttestError,
    canonical_bytes,
    sign_envelope,
    value_hash,
    verify_envelope,
)
from skeleton.kernel.court_attest import require_signed_attest

SEED = bytes(range(32))
SEED_HEX = SEED.hex()
OTHER_SEED = bytes(range(1, 33))


@pytest.fixture(autouse=True)
def _reset():
    kh.reset_keyholder_for_tests()
    yield
    kh.reset_keyholder_for_tests()


def test_sign_verify_roundtrip(monkeypatch):
    monkeypatch.setenv("GF_KEYHOLDER_SEED", SEED_HEX)
    env = sign_envelope(proposal_id="p1", value='{"n":1}')
    assert env["proposal_id"] == "p1"
    assert env["value_hash"] == value_hash('{"n":1}')
    assert env["attester_public"] == kh.get_keyholder().public_hex
    assert len(env["signature"]) == 64
    assert verify_envelope(env) == env["attester_public"]


def test_canonical_bytes_deterministic():
    a = canonical_bytes(
        proposal_id="p",
        value_hash="abc",
        attester_public="def",
        expiry=None,
    )
    b = canonical_bytes(
        proposal_id="p",
        value_hash="abc",
        attester_public="def",
        expiry=None,
    )
    assert a == b
    assert a.startswith(b"ATTEST-V1\n")
    assert a.endswith(b"\n")
    assert b"expiry:-\n" in a


def test_reject_tampered_value_hash(monkeypatch):
    monkeypatch.setenv("GF_KEYHOLDER_SEED", SEED_HEX)
    env = sign_envelope(proposal_id="p1", value="good")
    env["value_hash"] = hashlib.sha256(b"evil").hexdigest()
    with pytest.raises(AttestError, match="bad attestation signature"):
        verify_envelope(env)


def test_reject_wrong_public(monkeypatch):
    monkeypatch.setenv("GF_KEYHOLDER_SEED", SEED_HEX)
    env = sign_envelope(proposal_id="p1", value="x")
    env["attester_public"] = "00" * 16
    with pytest.raises(AttestError, match="does not match verifying keyholder"):
        verify_envelope(env)


def test_reject_bad_signature(monkeypatch):
    monkeypatch.setenv("GF_KEYHOLDER_SEED", SEED_HEX)
    env = sign_envelope(proposal_id="p1", value="x")
    env["signature"] = "ab" * 32
    with pytest.raises(AttestError, match="bad attestation signature"):
        verify_envelope(env)


def test_reject_missing_and_empty_fields(monkeypatch):
    monkeypatch.setenv("GF_KEYHOLDER_SEED", SEED_HEX)
    env = sign_envelope(proposal_id="p1", value="x")
    for field in ("proposal_id", "value_hash", "attester_public", "signature"):
        broken = dict(env)
        broken[field] = ""
        with pytest.raises(AttestError, match="empty field"):
            verify_envelope(broken)
        missing = dict(env)
        del missing[field]
        with pytest.raises(AttestError, match="missing field"):
            verify_envelope(missing)


def test_reject_unsigned_and_bare_attester(monkeypatch):
    monkeypatch.setenv("GF_KEYHOLDER_SEED", SEED_HEX)
    with pytest.raises(AttestError, match="envelope required"):
        require_signed_attest(None)
    with pytest.raises(AttestError, match="bare attester"):
        require_signed_attest("self-declared-attester")
    with pytest.raises(AttestError, match="empty envelope"):
        require_signed_attest({})
    with pytest.raises(AttestError, match="empty attester"):
        require_signed_attest({"attester_public": "  ", "proposal_id": "p"})


def test_trusted_publics_allowlist(monkeypatch):
    monkeypatch.setenv("GF_KEYHOLDER_SEED", SEED_HEX)
    env = sign_envelope(proposal_id="p1", value="x")
    pub = env["attester_public"]
    assert require_signed_attest(env, trusted_publics={pub}) == pub
    with pytest.raises(AttestError, match="trusted_publics"):
        require_signed_attest(env, trusted_publics={"deadbeef" * 4})


def test_expiry_respected(monkeypatch):
    monkeypatch.setenv("GF_KEYHOLDER_SEED", SEED_HEX)
    past = int(time.time()) - 60
    env = sign_envelope(proposal_id="p1", value="x", expiry=past)
    with pytest.raises(AttestError, match="expired"):
        verify_envelope(env)
    future = int(time.time()) + 3600
    env2 = sign_envelope(proposal_id="p2", value="x", expiry=future)
    assert verify_envelope(env2) == env2["attester_public"]


def test_included_value_mismatch(monkeypatch):
    monkeypatch.setenv("GF_KEYHOLDER_SEED", SEED_HEX)
    env = sign_envelope(proposal_id="p1", value="good", include_value=True)
    env["value"] = "tampered"
    with pytest.raises(AttestError, match="value does not match"):
        verify_envelope(env)


def test_verify_with_explicit_other_keyholder():
    a = kh.Keyholder.mint(SEED)
    b = kh.Keyholder.mint(OTHER_SEED)
    env = sign_envelope(proposal_id="p1", value="x", keyholder=a)
    assert verify_envelope(env, keyholder=a) == a.public_hex
    with pytest.raises(AttestError, match="does not match"):
        verify_envelope(env, keyholder=b)


def test_require_signed_attest_happy(monkeypatch):
    monkeypatch.setenv("GF_KEYHOLDER_SEED", SEED_HEX)
    env = sign_envelope(proposal_id="court-1", value='{"ok":true}')
    assert require_signed_attest(env) == kh.get_keyholder().public_hex
