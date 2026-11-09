"""G084: compromised trust roots cannot appoint, admit, or re-sign past the cut."""

from __future__ import annotations

import hashlib

import pytest

from skeleton.security.trust_root_recovery import (
    RootIdentity,
    TrustRootLedger,
    TrustRootRecoveryError,
    admission_payload,
    appointment_payload,
    resign_payload,
    revocation_payload,
)

DIGEST = "a" * 64
LATE = "b" * 64


class Key:
    def __init__(self, key_id: str, secret: bytes) -> None:
        self.key_id = key_id
        self._secret = secret

    def sign(self, payload: bytes) -> str:
        return hashlib.sha256(self._secret + payload).hexdigest()

    def verify(self, payload: bytes, signature: str) -> bool:
        if not isinstance(payload, bytes) or not isinstance(signature, str):
            return False
        return hashlib.sha256(self._secret + payload).hexdigest() == signature


def _roots() -> tuple[RootIdentity, RootIdentity, Key, Key]:
    genesis = RootIdentity("root.genesis", "key.genesis", "test-hmac-sha256")
    successor = RootIdentity("root.successor", "key.successor", "test-hmac-sha256")
    return (
        genesis,
        successor,
        Key(genesis.key_id, b"genesis"),
        Key(successor.key_id, b"successor"),
    )


def _appointed(trust_cut: int = 2):
    genesis, successor, old, new = _roots()
    ledger = TrustRootLedger()
    ledger.install_genesis(genesis, tick=0)
    ledger.admit(
        "artifact.early",
        DIGEST,
        old.sign(admission_payload(genesis, "artifact.early", DIGEST, 1)),
        old,
        tick=1,
    )
    payload = appointment_payload(genesis, successor, 2)
    ledger.precommit_successor(successor, old.sign(payload), old, tick=2)
    ledger.admit(
        "artifact.late",
        LATE,
        old.sign(admission_payload(genesis, "artifact.late", LATE, 3)),
        old,
        tick=3,
    )
    revocation = revocation_payload(genesis, successor, 4, trust_cut)
    ledger.revoke_and_reroot(
        new.sign(revocation), new, tick=4, trusted_through_tick=trust_cut
    )
    return ledger, genesis, successor, old, new


def test_successor_revocation_rejects_old_key_and_resigns_only_pre_cut() -> None:
    ledger, genesis, successor, old, new = _appointed(trust_cut=2)
    assert ledger.current() == successor
    assert ledger.is_revoked_key(genesis.key_id)
    assert ledger.revocation(genesis.root_id).trusted_through_tick == 2

    with pytest.raises(TrustRootRecoveryError, match="verifier key"):
        ledger.admit(
            "artifact.evil",
            DIGEST,
            old.sign(admission_payload(genesis, "artifact.evil", DIGEST, 5)),
            old,
            tick=5,
        )

    receipt = ledger.resign(
        "artifact.early",
        DIGEST,
        new.sign(resign_payload(genesis, successor, "artifact.early", DIGEST, 5, 2)),
        new,
        tick=5,
    )
    assert receipt.successor_key_id == successor.key_id
    assert receipt.predecessor_key_id == genesis.key_id
    again = ledger.resign("artifact.early", DIGEST, "ignored", new, tick=6)
    assert again == receipt

    with pytest.raises(TrustRootRecoveryError, match="pre-cut"):
        ledger.resign("artifact.late", LATE, "unused", new, tick=6)


def test_compromised_root_cannot_replace_or_authorize_revocation() -> None:
    genesis, successor, old, new = _roots()
    attacker = RootIdentity("root.attacker", "key.attacker", "test-hmac-sha256")
    ledger = TrustRootLedger()
    ledger.install_genesis(genesis, tick=0)
    ledger.precommit_successor(
        successor,
        old.sign(appointment_payload(genesis, successor, 1)),
        old,
        tick=1,
    )
    with pytest.raises(TrustRootRecoveryError, match="immutable"):
        ledger.precommit_successor(
            attacker,
            old.sign(appointment_payload(genesis, attacker, 2)),
            old,
            tick=2,
        )
    with pytest.raises(TrustRootRecoveryError, match="verifier key"):
        ledger.revoke_and_reroot(
            old.sign(revocation_payload(genesis, successor, 2, 1)),
            old,
            tick=2,
            trusted_through_tick=1,
        )
    assert ledger.current() == genesis
    assert ledger.appointment() is not None
    ledger.revoke_and_reroot(
        new.sign(revocation_payload(genesis, successor, 2, 1)),
        new,
        tick=2,
        trusted_through_tick=1,
    )
    assert ledger.current() == successor


def test_revocation_without_successor_and_bad_signature_fail_closed() -> None:
    genesis, successor, old, _new = _roots()
    ledger = TrustRootLedger()
    with pytest.raises(TrustRootRecoveryError, match="not installed"):
        ledger.current()
    ledger.install_genesis(genesis, tick=0)
    with pytest.raises(TrustRootRecoveryError, match="precommitted"):
        ledger.revoke_and_reroot("deadbeef", old, tick=1, trusted_through_tick=0)
    with pytest.raises(TrustRootRecoveryError, match="signature rejected"):
        ledger.precommit_successor(successor, "0" * 64, old, tick=1)
    assert ledger.appointment() is None
    ledger.precommit_successor(
        successor,
        old.sign(appointment_payload(genesis, successor, 1)),
        old,
        tick=1,
    )
    with pytest.raises(TrustRootRecoveryError, match="trust cut"):
        ledger.revoke_and_reroot(
            "11",
            Key(successor.key_id, b"successor"),
            tick=2,
            trusted_through_tick=2,
        )
    assert ledger.current() == genesis


def test_rejected_attempt_does_not_burn_the_tick() -> None:
    genesis, successor, old, _new = _roots()
    ledger = TrustRootLedger()
    ledger.install_genesis(genesis, tick=0)
    with pytest.raises(TrustRootRecoveryError):
        ledger.precommit_successor(successor, "nope", old, tick=4)
    ledger.precommit_successor(
        successor,
        old.sign(appointment_payload(genesis, successor, 4)),
        old,
        tick=4,
    )
    assert ledger.appointment().appointed_tick == 4


def test_verifier_exception_and_distinct_successor_are_rejected() -> None:
    genesis, _successor, old, _new = _roots()

    class Boom:
        key_id = genesis.key_id

        def verify(self, payload: bytes, signature: str) -> bool:
            raise RuntimeError("verifier down")

    ledger = TrustRootLedger()
    ledger.install_genesis(genesis, tick=0)
    with pytest.raises(TrustRootRecoveryError, match="verifier failed"):
        ledger.precommit_successor(
            RootIdentity("root.successor", "key.successor", "test-hmac-sha256"),
            "aa",
            Boom(),
            tick=1,
        )
    with pytest.raises(TrustRootRecoveryError, match="distinct"):
        ledger.precommit_successor(genesis, old.sign(b"unused"), old, tick=1)
    with pytest.raises(TrustRootRecoveryError, match="immutable"):
        ledger.install_genesis(genesis, tick=2)


def test_facade_reexports_canonical_owner() -> None:
    from skeleton.ai.runtime.security.trust_root_recovery import (
        TrustRootLedger as Mirrored,
    )

    assert Mirrored is TrustRootLedger


def test_resign_rejects_unknown_artifact() -> None:
    ledger, _genesis, _successor, _old, new = _appointed()
    with pytest.raises(TrustRootRecoveryError, match="pre-cut"):
        ledger.resign("artifact.missing", DIGEST, "00", new, tick=5)
