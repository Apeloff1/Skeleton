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


SEED2 = bytes(range(32, 64))
SEED3 = bytes(range(64, 96))


def test_key_continuity_rotation_preserves_non_revoked_historical_verification():
    ring = kh.KeyContinuityRing(kh.Keyholder.mint(SEED))
    first = ring.sign(b"before")
    assert first.generation == 1

    receipt = ring.rotate(SEED2)
    assert receipt.previous_key_id == first.key_id
    assert receipt.new_key_id == ring.active_key_id
    assert receipt.generation == 2
    assert receipt.revoked_previous is False
    assert len(receipt.receipt_digest) == 64

    second = ring.sign(b"after")
    assert second.generation == 2
    assert ring.verify(b"before", first) is True
    assert ring.verify_historical(b"before", first, at_generation=1) is True
    assert ring.verify(b"after", second) is True


def test_rotation_with_revocation_rejects_old_key_now_but_preserves_history():
    ring = kh.KeyContinuityRing(kh.Keyholder.mint(SEED))
    old = ring.sign(b"signed-before-rotation")

    ring.rotate(SEED2, revoke_previous=True)
    assert ring.generation == 2

    with pytest.raises(kh.KeyRevokedError, match="revoked"):
        ring.verify(b"signed-before-rotation", old)

    assert ring.verify_historical(
        b"signed-before-rotation",
        old,
        at_generation=1,
    ) is True
    with pytest.raises(kh.KeyRevokedError, match="revoked"):
        ring.verify_historical(
            b"signed-before-rotation",
            old,
            at_generation=2,
        )


def test_explicit_revocation_advances_generation_and_is_idempotent():
    ring = kh.KeyContinuityRing(kh.Keyholder.mint(SEED))
    old_id = ring.active_key_id
    ring.rotate(SEED2)
    assert ring.generation == 2

    revoked = ring.revoke(old_id)
    assert revoked.revoked_generation == 3
    assert ring.generation == 3

    again = ring.revoke(old_id)
    assert again == revoked
    assert ring.generation == 3


def test_active_key_cannot_be_revoked_without_rotation():
    ring = kh.KeyContinuityRing(kh.Keyholder.mint(SEED))
    with pytest.raises(kh.KeyContinuityError, match="rotated before revocation"):
        ring.revoke(ring.active_key_id)


def test_key_continuity_snapshot_restore_preserves_identity_without_exporting_seeds():
    ring = kh.KeyContinuityRing(kh.Keyholder.mint(SEED))
    old = ring.sign(b"old")
    ring.rotate(SEED2)
    current = ring.sign(b"current")
    snapshot = ring.snapshot()

    serialized = repr(snapshot)
    assert SEED.hex() not in serialized
    assert SEED2.hex() not in serialized

    restored = kh.KeyContinuityRing.restore(
        snapshot,
        seeds_by_key_id={
            old.key_id: SEED,
            current.key_id: SEED2,
        },
    )
    assert restored.generation == ring.generation
    assert restored.active_key_id == ring.active_key_id
    assert restored.entries() == ring.entries()
    assert restored.verify(b"old", old) is True
    assert restored.verify(b"current", current) is True


def test_key_continuity_restore_rejects_wrong_or_missing_seed():
    ring = kh.KeyContinuityRing(kh.Keyholder.mint(SEED))
    old_id = ring.active_key_id
    ring.rotate(SEED2)
    snapshot = ring.snapshot()

    with pytest.raises(kh.KeyContinuityError, match="missing seed"):
        kh.KeyContinuityRing.restore(
            snapshot,
            seeds_by_key_id={ring.active_key_id: SEED2},
        )

    with pytest.raises(kh.KeyContinuityError, match="does not match"):
        kh.KeyContinuityRing.restore(
            snapshot,
            seeds_by_key_id={
                old_id: SEED3,
                ring.active_key_id: SEED2,
            },
        )


def test_historical_verification_rejects_signature_from_future_generation():
    ring = kh.KeyContinuityRing(kh.Keyholder.mint(SEED))
    ring.rotate(SEED2)
    signed = ring.sign(b"generation-two")

    with pytest.raises(kh.KeyContinuityError, match="postdates"):
        ring.verify_historical(
            b"generation-two",
            signed,
            at_generation=1,
        )


def test_rotation_rejects_reusing_existing_identity():
    ring = kh.KeyContinuityRing(kh.Keyholder.mint(SEED))
    ring.rotate(SEED2)
    with pytest.raises(kh.KeyContinuityError, match="already exists"):
        ring.rotate(SEED)
