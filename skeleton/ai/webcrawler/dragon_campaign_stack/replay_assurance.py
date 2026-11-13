"""Cross-receipt replay attestation with immutable run, policy and scope IDs.

An audit chain is not a distributed transaction: a genuine Mongo commit,
current session authority and physical worker fencing remain required.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope
from .journal import CampaignJournal
from .review_packet import ReviewPacket, verify_review_packet


@dataclass(frozen=True)
class ReplayLink:
    revision: int
    snapshot_digest: str
    operation: str
    parent_digest: str
    link_digest: str


@dataclass(frozen=True)
class ReplayAudit:
    run_id: str
    mandate_digest: str
    snapshot_digest: str
    journal_head: str
    packet_digest: str
    links: tuple[ReplayLink, ...]
    audit_digest: str
    physical_effects_replayed: bool = False
    historical_mongo_commits_verified: bool = False


def audit_campaign_replay(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    journal: CampaignJournal,
    packet: ReviewPacket,
    *,
    now: float,
    authorized: bool,
    links: Iterable[ReplayLink] = (),
) -> ReplayAudit:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    journal.verify(mandate)
    verify_review_packet(
        mandate, snapshot, packet, now=now, authorized=authorized,
    )
    run = CrawlRun.from_snapshot(snapshot)
    canonical = run.snapshot()
    chain = tuple(links)
    if len(chain) > 128:
        raise ValueError("historical replay link budget exceeded")
    predecessor = "0" * 64
    for seq, item in enumerate(chain, 1):
        if not isinstance(item, ReplayLink):
            raise TypeError("typed historical replay link required")
        if item.revision != seq or item.parent_digest != predecessor:
            raise ValueError("replay sequence is not append-only")
        if item.operation not in (
            "checkpoint", "pause", "resume", "cancel",
            "source_withdrawal", "review", "recovery",
        ):
            raise ValueError("unknown historical operation")
        payload = {
            "revision": item.revision,
            "snapshot_digest": item.snapshot_digest,
            "operation": item.operation,
            "parent_digest": item.parent_digest,
        }
        if digest(payload) != item.link_digest:
            raise ValueError("tampered historical replay link")
        predecessor = item.link_digest
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": canonical["snapshot_digest"],
        "journal": journal.head,
        "packet": packet.packet_digest,
        "links": [asdict(x) for x in chain],
    }
    return ReplayAudit(
        run_id=canonical["run_id"],
        mandate_digest=mandate.fingerprint,
        snapshot_digest=canonical["snapshot_digest"],
        journal_head=journal.head,
        packet_digest=packet.packet_digest,
        links=chain,
        audit_digest=digest(payload),
    )
