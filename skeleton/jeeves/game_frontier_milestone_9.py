"""Milestone 9: campaign archive.

Stores campaign exports by manifest and retrieves them.
Candidate-only. In-memory. No external persistence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .game_frontier_milestone_8 import CampaignExport


class ArchiveError(ValueError):
    pass


@dataclass
class CampaignArchive:
    """In-memory archive of campaign exports keyed by manifest."""

    entries: dict[str, CampaignExport] = field(default_factory=dict)

    def store(self, export: CampaignExport) -> str:
        if export.manifest in self.entries:
            raise ArchiveError("manifest already archived")
        self.entries[export.manifest] = export
        return export.manifest

    def get(self, manifest: str) -> CampaignExport:
        if manifest not in self.entries:
            raise ArchiveError("manifest not found")
        return self.entries[manifest]

    def list_manifests(self) -> tuple[str, ...]:
        return tuple(sorted(self.entries))

    def __len__(self) -> int:
        return len(self.entries)
