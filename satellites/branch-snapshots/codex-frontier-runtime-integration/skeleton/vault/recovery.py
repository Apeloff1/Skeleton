"""Vault recovery — point-in-time snapshots of the sealed store."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Dict

from skeleton.kernel.errors import VaultError
from skeleton.vault.store import SealedStore


class RecoveryError(VaultError):
    code = "VLT.RECOVERY"


@dataclass(frozen=True)
class RecoverySnapshot:
    taken_at: float
    digest: str
    slots: Dict[str, bytes]  # secret_id -> plaintext copy (in-RAM only)


class RecoveryManager:
    """Snapshot/restore helpers over SealedStore for failover."""

    def __init__(self, store: SealedStore) -> None:
        self._store = store

    def snapshot(self) -> RecoverySnapshot:
        slots: Dict[str, bytes] = {}
        digest = hashlib.sha256()
        for name in self._store.names():
            plaintext = self._store.get(name)
            digest.update(plaintext)
            slots[name] = plaintext
        return RecoverySnapshot(
            taken_at=time.monotonic(),
            digest=digest.hexdigest(),
            slots=slots,
        )

    def restore(self, snapshot: RecoverySnapshot) -> None:
        for name, plaintext in snapshot.slots.items():
            self._store.put(name, plaintext)
