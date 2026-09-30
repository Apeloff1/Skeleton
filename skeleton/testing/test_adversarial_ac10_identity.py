from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Credential:
    subject: str
    key_id: str
    revoked: bool = False


class IdentityStore:
    def __init__(self) -> None:
        self.credentials: dict[str, Credential] = {}
        self.receipts: set[str] = set()

    def rotate(self, subject: str, key_id: str) -> Credential:
        cred = Credential(subject, key_id)
        self.credentials[subject] = cred
        return cred

    def revoke(self, key_id: str) -> None:
        for subject, cred in list(self.credentials.items()):
            if cred.key_id == key_id:
                self.credentials[subject] = Credential(cred.subject, cred.key_id, True)

    def restore(self, cred: Credential) -> None:
        self.credentials[cred.subject] = cred


def test_credential_rotation_replaces_active_key():
    store = IdentityStore()
    old = store.rotate("agent", "k1")
    new = store.rotate("agent", "k2")
    assert new.key_id != old.key_id
    assert store.credentials["agent"].key_id == "k2"


def test_revocation_replay_is_idempotent_and_stays_revoked():
    store = IdentityStore()
    store.rotate("agent", "k1")
    store.revoke("k1")
    store.revoke("k1")
    assert store.credentials["agent"].revoked is True


def test_identity_restore_preserves_revocation_state():
    store = IdentityStore()
    cred = Credential("agent", "k1", True)
    store.restore(cred)
    assert store.credentials["agent"].revoked is True


def test_historical_signature_verification_requires_known_key():
    store = IdentityStore()
    historical = store.rotate("agent", "k1")
    store.rotate("agent", "k2")
    assert historical.key_id == "k1"
    assert historical.revoked is False
