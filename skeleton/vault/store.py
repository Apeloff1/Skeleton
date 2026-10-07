"""Vault sealed store — authenticated encryption at rest with seal awareness.

AccessPolicy gates who may read; SealedStore is what the storage layer
actually does. Every value is sealed in its own AES-256-GCM envelope via
:class:`~skeleton.vault.kms.EnvelopeKMS` before it touches the slot map:

- **Per-secret envelopes.** ``put`` asks the KMS for a fresh data key and
  nonce per write, so no two secrets ever share a keystream.
- **Slot binding.** The envelope's AEAD context is bound to the secret id.
  Moving a ciphertext from one slot to another (a classic confused-deputy
  swap) is rejected on read, even though each envelope is individually
  valid.
- **Seal awareness.** A store may be *detached* from its KMS (the vault is
  sealed). Ciphertext stays in place, but every payload operation raises
  :class:`~skeleton.kernel.errors.SealedVaultError` until a KMS is attached.
- **Atomic re-key.** :meth:`SealedStore.reencrypt` migrates every envelope
  to a new KMS (new master key) all-or-nothing; a single undecryptable slot
  aborts the migration and leaves the store untouched.
- **Policies.** An optional :class:`~skeleton.vault.policies.PolicyRegistry`
  is evaluated before every write.

Only ciphertext envelopes ever leave the store (:meth:`export_envelopes`);
plaintext is returned exclusively by :meth:`get`.
"""

from __future__ import annotations

import copy
from typing import Callable, Dict, Mapping, Optional, Tuple

from skeleton.kernel.errors import SealedVaultError, VaultError
from skeleton.vault.kms import EnvelopeKMS
from skeleton.vault.policies import PolicyRegistry

CONTEXT_PREFIX = "skeleton.vault.sealed:"

AccessHook = Callable[[str, str], None]


class IntegrityError(VaultError):
    code = "VLT.INTEGRITY"


def slot_context(secret_id: str) -> str:
    """AEAD context that binds an envelope to exactly one secret slot."""
    return CONTEXT_PREFIX + secret_id


def _validate_id(secret_id: str) -> str:
    if not isinstance(secret_id, str) or not secret_id or secret_id != secret_id.strip():
        raise IntegrityError("secret id must be a nonempty, unpadded string",
                             context={"secret": repr(secret_id)[:64]})
    return secret_id


class SealedStore:
    """In-memory envelope-encrypted store wired through the vault EnvelopeKMS."""

    def __init__(
        self,
        kms: Optional[EnvelopeKMS] = None,
        *,
        on_access: Optional[AccessHook] = None,
        policies: Optional[PolicyRegistry] = None,
    ) -> None:
        self._kms: Optional[EnvelopeKMS] = kms
        self._slots: Dict[str, dict] = {}
        self._on_access = on_access
        self._policies = policies

    # -- seal state ---------------------------------------------------------
    @property
    def sealed(self) -> bool:
        return self._kms is None

    def attach(self, kms: EnvelopeKMS) -> None:
        """Attach (unseal) with a KMS. Verifies every slot decrypts first."""
        if not isinstance(kms, EnvelopeKMS):
            raise TypeError("kms must be an EnvelopeKMS")
        for secret_id, envelope in self._slots.items():
            self._open(kms, secret_id, envelope)
        self._kms = kms

    def detach(self) -> None:
        """Drop the KMS reference (seal). Ciphertext is retained."""
        self._kms = None

    def _require_kms(self) -> EnvelopeKMS:
        if self._kms is None:
            raise SealedVaultError("sealed store has no KMS attached", context={})
        return self._kms

    # -- payload operations -------------------------------------------------
    def put(self, secret_id: str, plaintext: bytes) -> None:
        _validate_id(secret_id)
        if not isinstance(plaintext, bytes):
            raise TypeError("plaintext must be bytes")
        kms = self._require_kms()
        if self._policies is not None:
            self._policies.evaluate(secret_id, plaintext)
        self._slots[secret_id] = kms.encrypt(plaintext, slot_context(secret_id))
        self._notify(secret_id, "write")

    def get(self, secret_id: str) -> bytes:
        kms = self._require_kms()
        envelope = self._slots.get(secret_id)
        if envelope is None:
            raise IntegrityError("unknown secret", context={"secret": secret_id})
        plaintext = self._open(kms, secret_id, envelope)
        self._notify(secret_id, "read")
        return plaintext

    def delete(self, secret_id: str) -> bool:
        removed = self._slots.pop(secret_id, None) is not None
        if removed:
            self._notify(secret_id, "delete")
        return removed

    def names(self) -> Tuple[str, ...]:
        return tuple(sorted(self._slots))

    def __contains__(self, secret_id: object) -> bool:
        return secret_id in self._slots

    def __len__(self) -> int:
        return len(self._slots)

    # -- ciphertext transport -----------------------------------------------
    def export_envelopes(self) -> Dict[str, dict]:
        """Deep copy of every sealed envelope. Never contains plaintext."""
        return {name: copy.deepcopy(self._slots[name]) for name in sorted(self._slots)}

    def import_envelopes(self, envelopes: Mapping[str, dict], *, replace: bool = False) -> int:
        """Load envelopes atomically after proving each opens under the KMS."""
        kms = self._require_kms()
        staged: Dict[str, dict] = {}
        for secret_id, envelope in envelopes.items():
            _validate_id(secret_id)
            self._open(kms, secret_id, envelope)
            staged[secret_id] = copy.deepcopy(envelope)
        if replace:
            self._slots = staged
        else:
            self._slots.update(staged)
        return len(staged)

    def reencrypt(self, new_kms: EnvelopeKMS) -> int:
        """Re-seal every slot under ``new_kms``, all-or-nothing, then attach it."""
        if not isinstance(new_kms, EnvelopeKMS):
            raise TypeError("new_kms must be an EnvelopeKMS")
        kms = self._require_kms()
        staged: Dict[str, dict] = {}
        for secret_id, envelope in self._slots.items():
            plaintext = self._open(kms, secret_id, envelope)
            staged[secret_id] = new_kms.encrypt(plaintext, slot_context(secret_id))
        self._slots = staged
        self._kms = new_kms
        return len(staged)

    # -- internals ----------------------------------------------------------
    @staticmethod
    def _open(kms: EnvelopeKMS, secret_id: str, envelope: object) -> bytes:
        if not isinstance(envelope, dict) or envelope.get("context") != slot_context(secret_id):
            raise IntegrityError("envelope is not bound to this slot", context={"secret": secret_id})
        try:
            return kms.decrypt(envelope)
        except Exception as exc:  # InvalidTag, malformed hex, unknown key version
            raise IntegrityError("integrity check failed",
                                 context={"secret": secret_id, "error": type(exc).__name__},
                                 cause=exc) from exc

    def _notify(self, secret_id: str, operation: str) -> None:
        if self._on_access is not None:
            self._on_access(secret_id, operation)


__all__ = ["CONTEXT_PREFIX", "IntegrityError", "SealedStore", "slot_context"]
