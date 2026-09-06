"""Tests for skeleton.kernel.keyholder (gameforge-rs keyholder.rs port)."""

from __future__ import annotations

import hashlib

import pytest

from skeleton.kernel import keyholder as kh


SEED = bytes(range(32))
SEED_HEX = SEED.hex()


@pytest.fixture(autouse=True)
def _reset():
    kh.reset_keyholder_for_tests()
    yield
    kh.reset_keyholder_for_tests()


def test_from_env_seed_public_is_truncated_sha256(monkeypatch):
    monkeypatch.setenv("GF_KEYHOLDER_SEED", SEED_HEX)
    k = kh.Keyholder.from_env()
    expected = hashlib.sha256(SEED).digest()[:16].hex()
    assert k.public_hex == expected


def test_sign_verify_roundtrip(monkeypatch):
    monkeypatch.setenv("GF_KEYHOLDER_SEED", SEED_HEX)
    k = kh.Keyholder.from_env()
    msg = b"ledger-entry-1"
    sig = k.sign(msg)
    assert len(sig) == 64
    assert k.verify(msg, sig) is True
    assert k.verify(b"other", sig) is False


def test_sign_is_deterministic(monkeypatch):
    monkeypatch.setenv("GF_KEYHOLDER_SEED", SEED_HEX)
    k = kh.Keyholder.from_env()
    assert k.sign(b"x") == k.sign(b"x")


def test_get_keyholder_singleton(monkeypatch):
    monkeypatch.setenv("GF_KEYHOLDER_SEED", SEED_HEX)
    a = kh.get_keyholder()
    b = kh.get_keyholder()
    assert a is b
    assert a.public_hex == b.public_hex


def test_ephemeral_without_env(monkeypatch):
    monkeypatch.delenv("GF_KEYHOLDER_SEED", raising=False)
    k = kh.Keyholder.from_env()
    assert len(k.public_hex) == 32
    assert k.verify(b"m", k.sign(b"m"))


def test_bad_seed_length(monkeypatch):
    monkeypatch.setenv("GF_KEYHOLDER_SEED", "abcd")
    with pytest.raises(ValueError):
        kh.Keyholder.from_env()
