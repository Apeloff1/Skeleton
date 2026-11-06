"""Portable, bounded campaign review manifest with exact-source revalidation.

This manifest intentionally contains metadata, receipt IDs and holds, not
page bodies. Its SHA-256 is an integrity checksum, not authentication,
human-source approval, copyright permission or an attestation signature.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable
import json

from ..operations import CrawlRun
from .claims import ClaimReviewMatrix
from .contracts import (
    CampaignMandate, digest, ensure_snapshot_scope, exact_digest, finite,
)
from .coverage import CoverageReport
from .integration import CampaignInspection
from .objectives import ObjectivePlan
from .risk_register import CrawlRiskRegister
from .stopping import ResearchStopGate


REVIEW_SCHEMA = "skeleton.ai.dragon.campaign_review_packet.v1"
MAX_PACKET_BYTES = 256 * 1024


@dataclass(frozen=True)
class PacketReference:
    name: str
    receipt_digest: str
    source_snapshot_digest: str
    review_required: bool


@dataclass(frozen=True)
class ReviewPacket:
    schema_version: str
    mandate_digest: str
    run_id: str
    snapshot_digest: str
    sequence: int
    issued_at: float
    source_count: int
    source_holds: int
    request_count: int
    uncertain_bytes: int
    references: tuple[PacketReference, ...]
    holds: tuple[str, ...]
    packet_digest: str
    authenticated_signature_present: bool = False
    publication_granted: bool = False
    model_training_granted: bool = False


def _envelope(
    mandate: CampaignMandate, report: CampaignInspection,
    *,
    now: float, objectives: ObjectivePlan | None,
    coverage: CoverageReport | None,
    claims: ClaimReviewMatrix | None,
    risks: CrawlRiskRegister | None,
    stopping: ResearchStopGate | None,
) -> dict:
    if report.mandate_digest != mandate.fingerprint:
        raise PermissionError("review packet cross-mandate")
    refs = []
    for name, receipt, snapshot, required in (
        ("campaign_inspection", report.inspection_digest, report.snapshot_digest, True),
        ("objective_plan", objectives.plan_digest if objectives else None, report.snapshot_digest, True),
        ("coverage", coverage.coverage_digest if coverage else None, report.snapshot_digest, True),
        ("claim_matrix", claims.matrix_digest if claims else None, report.snapshot_digest, True),
        ("operational_risks", risks.risk_digest if risks else None,
         risks.source_snapshot_digest if risks else report.snapshot_digest, True),
        ("mission_stop", stopping.decision_digest if stopping else None, report.snapshot_digest, True),
    ):
        if receipt is None:
            continue
        exact_digest(receipt, name + " receipt")
        if snapshot != report.snapshot_digest:
            raise PermissionError("review receipt references a foreign crawl revision")
        refs.append(PacketReference(name, receipt, snapshot, required))
    if objectives and objectives.mandate_digest != mandate.fingerprint:
        raise PermissionError("objective receipt mandate mismatch")
    if coverage and coverage.mandate_digest != mandate.fingerprint:
        raise PermissionError("coverage receipt mandate mismatch")
    if claims and claims.mandate_digest != mandate.fingerprint:
        raise PermissionError("claim receipt mandate mismatch")
    holds = list(report.diagnostics.holds)
    if coverage and coverage.unresolved_count:
        holds.append("unmet_or_unreviewed_mission_objectives")
    if claims and any(x.conflicted for x in claims.claims):
        holds.append("contradictory_claims")
    if stopping and stopping.human_review_required:
        holds.append("research_stop_not_human_fact_review")
    if risks and risks.review_required:
        holds.append("operational_risk_review")
    holds.append("publication_and_training_not_authorized")
    return {
        "schema_version": REVIEW_SCHEMA,
        "mandate_digest": mandate.fingerprint,
        "run_id": report.run_id,
        "snapshot_digest": report.snapshot_digest,
        "sequence": report.run_sequence,
        "issued_at": now,
        "source_count": len(report.evidence.sources),
        "source_holds": len(report.evidence.rejected_sources),
        "request_count": report.budget.requests_used,
        "uncertain_bytes": report.budget.bytes_uncertain,
        "references": [asdict(x) for x in refs],
        "holds": sorted(set(holds)),
    }


def create_review_packet(
    mandate: CampaignMandate,
    report: CampaignInspection,
    *, now: float,
    authorized: bool,
    objectives: ObjectivePlan | None = None,
    coverage: CoverageReport | None = None,
    claims: ClaimReviewMatrix | None = None,
    risks: CrawlRiskRegister | None = None,
    stopping: ResearchStopGate | None = None,
) -> ReviewPacket:
    mandate.admit(now=now, authorized=authorized)
    envelope = _envelope(
        mandate, report, now=now, objectives=objectives,
        coverage=coverage, claims=claims, risks=risks, stopping=stopping,
    )
    serialized = json.dumps(
        envelope, ensure_ascii=True, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    if len(serialized) > MAX_PACKET_BYTES:
        raise ValueError("review packet capacity exceeded")
    return ReviewPacket(
        **{**envelope, "references": tuple(
            PacketReference(**x) for x in envelope["references"]
        ), "holds": tuple(envelope["holds"])},
        packet_digest=digest(envelope),
    )


def verify_review_packet(
    mandate: CampaignMandate, snapshot: dict[str, object],
    packet: ReviewPacket,
    *,
    now: float,
    authorized: bool,
    required_reference_names: Iterable[str] = ("campaign_inspection",),
) -> None:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    if not isinstance(packet, ReviewPacket):
        raise TypeError("typed review packet required")
    if packet.schema_version != REVIEW_SCHEMA or (
        packet.mandate_digest != mandate.fingerprint
    ):
        raise PermissionError("review packet authority mismatch")
    canonical = CrawlRun.from_snapshot(snapshot).snapshot()
    if (
        packet.run_id != canonical["run_id"]
        or packet.snapshot_digest != canonical["snapshot_digest"]
        or packet.sequence != canonical["sequence"]
    ):
        raise PermissionError("review packet bound to stale crawl revision")
    finite(packet.issued_at, "packet creation", mandate.created_at, now)
    if packet.authenticated_signature_present or packet.publication_granted or packet.model_training_granted:
        raise PermissionError("unsupported review packet authority escalation")
    names = tuple(x.name for x in packet.references)
    if len(names) != len(set(names)) or len(names) > 8:
        raise ValueError("duplicate or oversized review packet receipts")
    for name in required_reference_names:
        if name not in names:
            raise ValueError("mandatory review evidence receipt absent")
    for reference in packet.references:
        if reference.source_snapshot_digest != packet.snapshot_digest:
            raise PermissionError("cross-snapshot review reference")
        exact_digest(reference.receipt_digest, "review evidence receipt")
    envelope = {
        name: value for name, value in asdict(packet).items()
        if name not in (
            "packet_digest", "authenticated_signature_present",
            "publication_granted", "model_training_granted",
        )
    }
    if digest(envelope) != packet.packet_digest:
        raise ValueError("review packet checksum mismatch")
    if "publication_and_training_not_authorized" not in packet.holds:
        raise PermissionError("mandatory review hold was removed")
