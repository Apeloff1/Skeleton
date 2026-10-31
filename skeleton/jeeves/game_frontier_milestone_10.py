"""Milestone 10: archive retention and query.

Applies a retention bound to a campaign archive and answers
simple queries over stored exports. Candidate-only. In-memory.
"""

from __future__ import annotations

from dataclasses import dataclass

from .game_frontier_milestone_9 import CampaignArchive, ArchiveError
from .game_frontier_milestone_8 import CampaignExport


class RetentionError(ValueError):
    pass


@dataclass(frozen=True)
class RetentionPolicy:
    """Bound on how many exports an archive may hold."""

    max_entries: int

    def __post_init__(self) -> None:
        if type(self.max_entries) is not int or not 1 <= self.max_entries <= 4096:
            raise RetentionError("max_entries must be 1..4096")


def apply_retention(archive: CampaignArchive, policy: RetentionPolicy) -> int:
    """Drop oldest manifests until the archive fits the policy.

    Returns the number of manifests removed. The archive's insertion
    order preserves admission age; digest ordering does not.
    """
    overflow = len(archive) - policy.max_entries
    if overflow <= 0:
        return 0
    # Validate the complete public index before changing any retained content.
    archive.list_manifests()
    removed = 0
    for manifest in tuple(archive.entries)[:overflow]:
        del archive.entries[manifest]
        removed += 1
    return removed


def query_by_campaign(archive: CampaignArchive, campaign_id: str) -> tuple[CampaignExport, ...]:
    """Return exports whose campaign_id matches, in manifest order."""
    if not campaign_id:
        raise ArchiveError("campaign_id required")
    return tuple(
        archive.get(manifest)
        for manifest in archive.list_manifests()
        if archive.get(manifest).campaign_id == campaign_id
    )
