"""Transparency anchoring for epistemic checkpoints.

The checkpoint ledger preserves local hash ancestry; the transparency log preserves
append-only public history. Reconciliation requires the log to be an exact prefix
of the verified checkpoint ledger and only backfills a missing suffix. Any divergent
prefix is treated as equivocation/corruption and fails closed.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.epistemic_checkpoint import EpistemicCheckpoint, EpistemicCheckpointLedger
from core.transparency_log import TransparencyIntegrityError, TransparencyLog, verify_consistency, verify_inclusion


class EpistemicTransparencyError(RuntimeError):
    pass


class EpistemicTransparency:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.checkpoints = EpistemicCheckpointLedger(self.root / "checkpoints")
        self.log = TransparencyLog(self.root / "log", log_id="epistemic-checkpoints")
        self.reconcile()

    @staticmethod
    def _payload(checkpoint: EpistemicCheckpoint) -> dict[str, Any]:
        return {"kind": "epistemic_checkpoint", **asdict(checkpoint)}

    def reconcile(self) -> dict[str, Any]:
        checkpoints = self.checkpoints.snapshot(); entries = self.log.snapshot()
        if len(entries) > len(checkpoints):
            raise EpistemicTransparencyError("transparency log is longer than checkpoint ledger")
        for index, entry in enumerate(entries):
            expected = self._payload(checkpoints[index])
            if entry.payload != expected:
                raise EpistemicTransparencyError(f"transparency/checkpoint divergence at index {index}")
        appended = 0
        for checkpoint in checkpoints[len(entries):]:
            self.log.append(self._payload(checkpoint), observed_at=checkpoint.observed_at); appended += 1
        descriptor = self.log.descriptor()
        return {"checkpoint_entries": len(checkpoints), "transparency_entries": descriptor["tree_size"],
                "appended": appended, "prefix_aligned": True, "root_sha256": descriptor["root_sha256"]}

    def publish(self, *, authority_root_sha256: str, epistemic_root_sha256: str,
                observed_at: str | None = None) -> dict[str, Any]:
        checkpoint = self.checkpoints.record(
            authority_root_sha256=authority_root_sha256,
            epistemic_root_sha256=epistemic_root_sha256,
            observed_at=observed_at,
        )
        self.reconcile()
        entries = self.log.snapshot()
        index = next((row.index for row in entries if row.payload.get("sha256") == checkpoint.sha256), None)
        if index is None:
            raise EpistemicTransparencyError("published checkpoint missing from transparency log")
        proof = self.log.inclusion(index)
        if not verify_inclusion(proof):
            raise EpistemicTransparencyError("published checkpoint inclusion proof failed")
        return {"checkpoint": asdict(checkpoint), "transparency": self.log.descriptor(),
                "inclusion": asdict(proof), "verified": True}

    def inclusion_for_checkpoint(self, checkpoint_sha256: str) -> dict[str, Any]:
        entries = self.log.snapshot()
        index = next((row.index for row in entries if row.payload.get("sha256") == checkpoint_sha256), None)
        if index is None: raise KeyError(checkpoint_sha256)
        proof = self.log.inclusion(index)
        return {**asdict(proof), "verified": verify_inclusion(proof)}

    def consistency_from(self, old_size: int) -> dict[str, Any]:
        proof = self.log.consistency(old_size)
        return {**asdict(proof), "verified": verify_consistency(proof)}

    def health(self) -> dict[str, Any]:
        reconciliation = self.reconcile(); checkpoint_health = self.checkpoints.health(); log_health = self.log.descriptor()
        return {"verified": True, "checkpoint": checkpoint_health, "transparency": log_health,
                "prefix_aligned": reconciliation["prefix_aligned"], "checkpoint_entries": reconciliation["checkpoint_entries"],
                "transparency_entries": reconciliation["transparency_entries"], "root_sha256": log_health["root_sha256"]}
