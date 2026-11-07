"""Vault seal lifecycle — Shamir custodians, unseal ceremony, quorum re-key.

This module is the glue that turns the vault's parts into one working
lifecycle. Nothing here invents crypto; it composes:

- :class:`~skeleton.vault.entropy.EntropyRegistry` — audited master-key entropy
- :class:`~skeleton.vault.shamir.ShamirSeal` — k-of-n custodian shares with a
  verification commitment
- :class:`~skeleton.vault.kms.EnvelopeKMS` — AES-256-GCM envelope encryption
- :class:`~skeleton.vault.store.SealedStore` — slot-bound ciphertext at rest
- :class:`~skeleton.vault.quorum.QuorumGate` — dual control for re-key
- :class:`~skeleton.vault.audit.AuditLog` — hash-chained (optionally WORM) audit

Lifecycle::

    UNINITIALIZED --initialize()--> SEALED --submit_share() x k--> UNSEALED
          UNSEALED --seal()--> SEALED          UNSEALED --rekey()--> UNSEALED

Laws:

- The master key exists in memory only while UNSEALED (inside the KMS);
  it is never stored, logged, or returned. ``initialize`` hands out shares
  and a commitment — never the key itself.
- Unseal progress is cumulative across calls (one custodian at a time) and
  shares must all come from the same sealing. A wrong reconstruction is
  detected via the commitment, progress is reset, and the attempt audited.
- ``rekey`` re-encrypts every slot under a fresh master atomically and
  issues new shares; old shares become useless. When a quorum gate is
  configured it must release the ``rekey`` action first.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from skeleton.kernel.errors import SealedVaultError, VaultError
from skeleton.vault.audit import AuditLog
from skeleton.vault.entropy import EntropyRegistry
from skeleton.vault.kms import EnvelopeKMS
from skeleton.vault.quorum import QuorumGate
from skeleton.vault.shamir import SealingError, ShamirSeal, Share
from skeleton.vault.store import SealedStore

MASTER_KEY_BYTES = 32
REKEY_ACTION = "vault.rekey"


class UnsealError(VaultError):
    code = "VLT.UNSEAL"


class SealState(str, Enum):
    UNINITIALIZED = "uninitialized"
    SEALED = "sealed"
    UNSEALED = "unsealed"


@dataclass(frozen=True)
class SealKeys:
    """Result of initialize/rekey: shares to distribute plus the commitment."""
    shares: Tuple[Share, ...]
    threshold: int
    commitment: str

    def __repr__(self) -> str:  # never print share material
        return f"SealKeys(shares={len(self.shares)}, threshold={self.threshold})"


@dataclass(frozen=True)
class SealStatus:
    state: SealState
    threshold: int
    shares: int
    progress: int
    generation: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "sealed": self.state is not SealState.UNSEALED,
            "threshold": self.threshold,
            "shares": self.shares,
            "progress": self.progress,
            "generation": self.generation,
        }


class VaultSeal:
    """Owns the seal state of one :class:`SealedStore`."""

    def __init__(
        self,
        store: Optional[SealedStore] = None,
        *,
        audit: Optional[AuditLog] = None,
        entropy: Optional[EntropyRegistry] = None,
        quorum: Optional[QuorumGate] = None,
    ) -> None:
        self.store = store if store is not None else SealedStore()
        if not self.store.sealed:
            raise UnsealError("store must start detached; VaultSeal owns its KMS")
        self.audit = audit if audit is not None else AuditLog()
        self._entropy = entropy if entropy is not None else EntropyRegistry()
        self._quorum = quorum
        self._commitment: Optional[str] = None
        self._threshold = 0
        self._shares = 0
        self._generation = 0
        self._pending: List[Share] = []

    # -- state ----------------------------------------------------------------
    @property
    def state(self) -> SealState:
        if self._commitment is None:
            return SealState.UNINITIALIZED
        return SealState.SEALED if self.store.sealed else SealState.UNSEALED

    @property
    def sealed(self) -> bool:
        return self.state is not SealState.UNSEALED

    def status(self) -> SealStatus:
        return SealStatus(self.state, self._threshold, self._shares,
                          len(self._pending), self._generation)

    # -- lifecycle ------------------------------------------------------------
    def initialize(self, *, shares: int, threshold: int, actor: str) -> SealKeys:
        if self._commitment is not None:
            raise UnsealError("vault is already initialized")
        keys = self._issue(shares=shares, threshold=threshold)
        self._record(actor, "initialize", "success",
                     {"shares": shares, "threshold": threshold, "generation": self._generation})
        return keys

    def submit_share(self, share: Share, *, actor: str) -> SealStatus:
        """Add one custodian share; unseals once the threshold is reached."""
        if self._commitment is None:
            raise UnsealError("vault is not initialized")
        if not self.store.sealed:
            raise UnsealError("vault is already unsealed")
        if not isinstance(share, Share):
            raise UnsealError("share must be a Share")
        if len(share.values) != MASTER_KEY_BYTES:
            self._record(actor, "unseal_share", "failure", {"reason": "length"})
            raise UnsealError("share length does not match a vault master key")
        if self._pending and share.nonce != self._pending[0].nonce:
            self._record(actor, "unseal_share", "failure", {"reason": "foreign"})
            raise UnsealError("share belongs to a different sealing")
        if any(p.index == share.index for p in self._pending):
            raise UnsealError("share index already submitted", context={"index": share.index})
        self._pending.append(share)
        self._record(actor, "unseal_share", "success",
                     {"index": share.index, "progress": len(self._pending)})
        if len(self._pending) >= self._threshold:
            self._complete_unseal(actor)
        return self.status()

    def unseal(self, shares: Sequence[Share], *, actor: str) -> SealStatus:
        """Convenience: submit several shares in one call."""
        status = self.status()
        for share in shares:
            status = self.submit_share(share, actor=actor)
            if not self.sealed:
                break
        return status

    def reset_progress(self, *, actor: str) -> None:
        self._pending.clear()
        self._record(actor, "unseal_reset", "success", {})

    def seal(self, *, actor: str) -> SealStatus:
        if self._commitment is None:
            raise UnsealError("vault is not initialized")
        self.store.detach()
        self._pending.clear()
        self._record(actor, "seal", "success", {"generation": self._generation})
        return self.status()

    def rekey(self, *, shares: int, threshold: int, actor: str) -> SealKeys:
        """Rotate the master key: re-encrypt every slot, issue fresh shares."""
        if self.store.sealed:
            raise SealedVaultError("vault must be unsealed to rekey", context={})
        if not (1 < threshold <= shares <= 255):
            raise UnsealError("invalid share/threshold parameters",
                              context={"shares": shares, "threshold": threshold})
        if self._quorum is not None and not self._quorum_released():
            self._record(actor, "rekey", "denied", {"reason": "quorum"})
            raise UnsealError("rekey requires quorum approval",
                              context={"action": REKEY_ACTION})
        master = self._gather_master()
        try:
            # Split first: invalid parameters must fail before any slot moves,
            # otherwise data would be re-encrypted under a key nobody holds.
            issued, commitment = self._split(master, shares=shares, threshold=threshold)
            new_kms = EnvelopeKMS(master)
        finally:
            del master
        try:
            migrated = self.store.reencrypt(new_kms)
        except Exception:
            self._record(actor, "rekey", "failure", {})
            raise
        keys = self._commit(issued, commitment, shares=shares, threshold=threshold)
        self._record(actor, "rekey", "success",
                     {"shares": shares, "threshold": threshold, "migrated": migrated,
                      "generation": self._generation})
        return keys

    # -- internals --------------------------------------------------------------
    def _quorum_released(self) -> bool:
        assert self._quorum is not None
        try:
            return self._quorum.check(REKEY_ACTION)
        except VaultError:
            return False

    def _gather_master(self) -> bytes:
        return self._entropy.gather(MASTER_KEY_BYTES)

    def _issue(self, *, shares: int, threshold: int) -> SealKeys:
        master = self._gather_master()
        try:
            issued, commitment = self._split(master, shares=shares, threshold=threshold)
        finally:
            del master
        return self._commit(issued, commitment, shares=shares, threshold=threshold)

    @staticmethod
    def _split(master: bytes, *, shares: int, threshold: int) -> Tuple[List[Share], str]:
        try:
            return ShamirSeal.split_with_commitment(master, n=shares, k=threshold)
        except SealingError as exc:
            raise UnsealError("invalid share/threshold parameters",
                              context={"shares": shares, "threshold": threshold}, cause=exc) from exc

    def _commit(self, issued: List[Share], commitment: str, *, shares: int, threshold: int) -> SealKeys:
        self._commitment = commitment
        self._threshold = threshold
        self._shares = shares
        self._generation += 1
        self._pending.clear()
        return SealKeys(shares=tuple(issued), threshold=threshold, commitment=commitment)

    def _complete_unseal(self, actor: str) -> None:
        shares, self._pending = list(self._pending), []
        assert self._commitment is not None
        try:
            master = ShamirSeal.combine_verified(shares, self._commitment)
        except SealingError as exc:
            self._record(actor, "unseal", "failure", {"reason": "commitment"})
            raise UnsealError("shares did not reconstruct the vault master key",
                              cause=exc) from exc
        try:
            self.store.attach(EnvelopeKMS(master))
        except VaultError as exc:
            self._record(actor, "unseal", "failure", {"reason": "store-integrity"})
            raise UnsealError("store failed integrity verification on unseal",
                              cause=exc) from exc
        finally:
            del master
        self._record(actor, "unseal", "success", {"generation": self._generation})

    def _record(self, actor: str, action: str, outcome: str, metadata: Dict[str, Any]) -> None:
        self.audit.append(entry_id=uuid.uuid4().hex, actor=actor, action=f"vault.{action}",
                          outcome=outcome, metadata=metadata)


__all__ = [
    "MASTER_KEY_BYTES",
    "REKEY_ACTION",
    "SealKeys",
    "SealState",
    "SealStatus",
    "UnsealError",
    "VaultSeal",
]
