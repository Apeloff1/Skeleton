"""Milestone 9: bounded, content-addressed campaign archive.

Candidate-only in-memory index over previously verified milestone-8 exports.
No persisted session payloads or external archival durability are claimed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import re

from .game_frontier_milestone_8 import CampaignExport

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MAX_ENTRIES = 4096


class ArchiveError(ValueError):
    """Invalid evidence, duplicate admission or a missing campaign manifest."""


def _verified_copy(export: CampaignExport) -> CampaignExport:
    """Reject forged manifests; avoid holding references to untrusted inputs."""
    if not isinstance(export, CampaignExport):
        raise ArchiveError("campaign export type required")
    if type(export.campaign_id) is not str or not 1 <= len(export.campaign_id) <= 80:
        raise ArchiveError("campaign identity invalid")
    if type(export.session_count) is not int or export.session_count < 1:
        raise ArchiveError("campaign session count invalid")
    for value in (export.head, export.audit, export.manifest):
        if type(value) is not str or _DIGEST.fullmatch(value) is None:
            raise ArchiveError("campaign evidence digest invalid")
    payload = json.dumps(
        {
            "campaign": export.campaign_id,
            "sessions": export.session_count,
            "head": export.head,
            "audit": export.audit,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if sha256(payload).hexdigest() != export.manifest:
        raise ArchiveError("campaign export manifest does not bind its content")
    return CampaignExport(
        campaign_id=export.campaign_id,
        session_count=export.session_count,
        head=export.head,
        audit=export.audit,
        manifest=export.manifest,
    )


@dataclass
class CampaignArchive:
    """Bounded memory-only campaign index; manifest identity is immutable."""

    entries: dict[str, CampaignExport] = field(default_factory=dict)
    max_entries: int = _MAX_ENTRIES

    def __post_init__(self) -> None:
        if type(self.max_entries) is not int or not 1 <= self.max_entries <= _MAX_ENTRIES:
            raise ArchiveError("archive capacity must be bounded")
        if not isinstance(self.entries, dict) or len(self.entries) > self.max_entries:
            raise ArchiveError("invalid initial archive")
        self.entries = {
            manifest: self._check_index_entry(manifest, item)
            for manifest, item in self.entries.items()
        }

    @staticmethod
    def _check_index_entry(manifest: str, export: CampaignExport) -> CampaignExport:
        verified = _verified_copy(export)
        if type(manifest) is not str or manifest != verified.manifest:
            raise ArchiveError("archive key does not match export identity")
        return verified

    def store(self, export: CampaignExport) -> str:
        verified = _verified_copy(export)
        key = verified.manifest
        if key in self.entries:
            raise ArchiveError("manifest already archived")
        if len(self.entries) >= self.max_entries:
            raise ArchiveError("archive memory capacity exceeded")
        self.entries[key] = verified
        return key

    def get(self, manifest: str) -> CampaignExport:
        if type(manifest) is not str or _DIGEST.fullmatch(manifest) is None:
            raise ArchiveError("manifest identity invalid")
        try:
            item = self.entries[manifest]
        except KeyError as exc:
            raise ArchiveError("manifest not found") from exc
        return self._check_index_entry(manifest, item)

    def list_manifests(self) -> tuple[str, ...]:
        # Validate mutable public index state before exposing catalog entries.
        for manifest, item in self.entries.items():
            self._check_index_entry(manifest, item)
        return tuple(sorted(self.entries))

    def __len__(self) -> int:
        return len(self.entries)
