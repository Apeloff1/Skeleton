"""Vault recovery — sealed, verifiable point-in-time snapshots of the store.

Snapshots carry **ciphertext envelopes only**. A snapshot sitting in a
backup bucket is exactly as safe as the live store: without the master key
(and therefore without a quorum of Shamir custodians) it reveals nothing.

Each snapshot is content-addressed: ``digest`` is a SHA-256 over the
canonical JSON of every ``(secret_id, envelope)`` pair, so a truncated,
reordered, or edited snapshot is detected before it is restored. Restore is
atomic: every envelope must also authenticate under the store's current KMS
or nothing is written.
"""

from __future__ import annotations

import copy
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from skeleton.kernel.errors import VaultError
from skeleton.vault.store import SealedStore

SNAPSHOT_FORMAT = "skeleton.vault.snapshot.v1"


class RecoveryError(VaultError):
    code = "VLT.RECOVERY"


def snapshot_digest(slots: Dict[str, dict]) -> str:
    canonical = json.dumps(
        {"format": SNAPSHOT_FORMAT, "slots": slots},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class RecoverySnapshot:
    taken_at: float
    digest: str
    slots: Dict[str, dict]  # secret_id -> sealed envelope (ciphertext only)

    def to_dict(self) -> dict:
        return {
            "format": SNAPSHOT_FORMAT,
            "taken_at": self.taken_at,
            "digest": self.digest,
            "slots": copy.deepcopy(self.slots),
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "RecoverySnapshot":
        if not isinstance(raw, dict) or raw.get("format") != SNAPSHOT_FORMAT:
            raise RecoveryError("unsupported snapshot format")
        slots = raw.get("slots")
        if not isinstance(slots, dict):
            raise RecoveryError("snapshot slots must be a mapping")
        return cls(taken_at=float(raw["taken_at"]), digest=str(raw["digest"]),
                   slots=copy.deepcopy(slots))


class RecoveryManager:
    """Snapshot/verify/restore helpers over SealedStore for failover."""

    def __init__(self, store: SealedStore, *, clock: Optional[Callable[[], float]] = None) -> None:
        self._store = store
        self._now = clock or time.time

    def snapshot(self) -> RecoverySnapshot:
        slots = self._store.export_envelopes()
        return RecoverySnapshot(taken_at=self._now(), digest=snapshot_digest(slots), slots=slots)

    @staticmethod
    def verify(snapshot: RecoverySnapshot) -> bool:
        return snapshot_digest(snapshot.slots) == snapshot.digest

    def restore(self, snapshot: RecoverySnapshot, *, replace: bool = True) -> int:
        if not self.verify(snapshot):
            raise RecoveryError("snapshot digest mismatch — refusing restore",
                                context={"digest": snapshot.digest})
        try:
            return self._store.import_envelopes(snapshot.slots, replace=replace)
        except VaultError as exc:
            if exc.code == "VLT.SEALED":
                raise
            raise RecoveryError("snapshot does not authenticate under the current key",
                                context={"error": exc.code}, cause=exc) from exc


__all__ = ["RecoveryError", "RecoveryManager", "RecoverySnapshot", "SNAPSHOT_FORMAT", "snapshot_digest"]
