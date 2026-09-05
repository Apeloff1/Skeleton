"""Unit tests for skeleton.api.hmac_seal (seal.rs wire format)."""

from __future__ import annotations

import os
import time

import pytest
from fastapi import HTTPException

from skeleton.api.hmac_seal import mint_seal, require_seal, verify_seal
from skeleton.api.middleware import AuthError

SECRET = "unit-test-seal-secret"


def test_mint_verify_roundtrip():
    token = mint_seal("alice", ttl_secs=60, secret=SECRET, now=1_700_000_000)
    assert token is not None
    assert verify_seal(token, secret=SECRET, now=1_700_000_000) == "alice"


def test_attester_with_dots():
    token = mint_seal("org.team.bot", ttl_secs=120, secret=SECRET, now=1_700_000_000)
    assert verify_seal(token, secret=SECRET, now=1_700_000_010) == "org.team.bot"


def test_mint_returns_none_without_secret(monkeypatch):
    monkeypatch.delenv("GF_SEAL_SECRET", raising=False)
    assert mint_seal("alice", secret="") is None
    assert mint_seal("alice", secret=None) is None


def test_verify_expired():
    token = mint_seal("alice", ttl_secs=10, secret=SECRET, now=1000)
    with pytest.raises(AuthError):
        verify_seal(token, secret=SECRET, now=1020)


def test_verify_bad_sig():
    token = mint_seal("alice", ttl_secs=60, secret=SECRET, now=1000)
    parts = token.rsplit(".", 2)
    bad = f"{parts[0]}.{parts[1]}.{'0' * 64}"
    with pytest.raises(AuthError):
        verify_seal(bad, secret=SECRET, now=1000)


def test_verify_malformed():
    with pytest.raises(AuthError):
        verify_seal("not-a-seal", secret=SECRET)
    with pytest.raises(AuthError):
        verify_seal(None, secret=SECRET)
    with pytest.raises(AuthError):
        verify_seal("a.b", secret=SECRET)


def test_require_seal_503_when_secret_unset(monkeypatch):
    monkeypatch.delenv("GF_SEAL_SECRET", raising=False)
    with pytest.raises(HTTPException) as ei:
        require_seal(x_gf_seal="anything")
    assert ei.value.status_code == 503


def test_require_seal_401_missing_header(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    with pytest.raises(AuthError):
        require_seal(x_gf_seal=None)


def test_require_seal_ok(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    token = mint_seal("bob", secret=SECRET)
    assert require_seal(x_gf_seal=token) == "bob"
