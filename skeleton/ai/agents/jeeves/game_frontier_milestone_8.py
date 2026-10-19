"""Milestone 8: campaign export bundle.

Packs a verified campaign ledger into a portable export record
with a content-addressed manifest. Candidate-only.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .game_frontier_campaign import CampaignLedger, CampaignError


@dataclass(frozen=True)
class CampaignExport:
    campaign_id: str
    session_count: int
    head: str
    audit: str
    manifest: str


def export_campaign(ledger: CampaignLedger, audit: str) -> CampaignExport:
    if not ledger.verify():
        raise CampaignError("ledger must verify before export")
    if len(audit) != 64:
        raise CampaignError("audit must be SHA-256")
    payload = json.dumps(
        {
            "campaign": ledger.campaign_id,
            "sessions": len(ledger.sessions),
            "head": ledger.head,
            "audit": audit,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return CampaignExport(
        campaign_id=ledger.campaign_id,
        session_count=len(ledger.sessions),
        head=ledger.head,
        audit=audit,
        manifest=sha256(payload.encode()).hexdigest(),
    )
