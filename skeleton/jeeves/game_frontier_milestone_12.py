"""Milestone 12: snapshot history log.

Records an ordered chain of archive snapshots and verifies the chain.
Candidate-only. In-memory.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json

from .game_frontier_milestone_11 import ArchiveSnapshot, snapshot
from .game_frontier_milestone_9 import CampaignArchive


class HistoryError(ValueError):
    pass


@dataclass
class SnapshotHistory:
    """Append-only log of archive snapshots."""

    entries: list[ArchiveSnapshot] = field(default_factory=list)
    head: str = ""

    def record(self, archive: CampaignArchive) -> ArchiveSnapshot:
        """Snapshot the archive and append it to the chain."""
        snap = snapshot(archive)
        payload = json.dumps(
            {"prev": self.head, "digest": snap.digest, "index": len(self.entries)},
            sort_keys=True,
            separators=(",", ":"),
        )
        self.head = sha256(payload.encode()).hexdigest()
        self.entries.append(snap)
        return snap

    def verify(self) -> bool:
        """Recompute the chain and confirm the head."""
        if not self.entries:
            return False
        head = ""
        for index, snap in enumerate(self.entries):
            payload = json.dumps(
                {"prev": head, "digest": snap.digest, "index": index},
                sort_keys=True,
                separators=(",", ":"),
            )
            head = sha256(payload.encode()).hexdigest()
        return head == self.head

    def __len__(self) -> int:
        return len(self.entries)
