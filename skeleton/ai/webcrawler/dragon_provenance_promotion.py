"""Fail-closed custody-bound adapter for the existing knowledge promotion gate.

The legacy promotion API accepts caller-labelled source groups for backwards
compatibility. New crawler ingestion paths should use this adapter: it replaces
those labels with the conservative dependency closure of a complete manifest
before invoking calibrated promotion checks.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from .dragon_analysis_chains import LayerReceipt
from .dragon_analysis_quality_gates import Measurement
from .dragon_empirical_calibration import CalibrationArtifact
from .dragon_knowledge_promotion import (
    PromotionDecision, PromotionPolicy, assess_promotion,
)
from .dragon_probabilistic_distillation import EvidencePass
from .dragon_provenance_assurance import (
    AssurancePolicy, ProvenanceAssurance, assure_crawler_evidence,
)
from .dragon_source_independence import SourceProvenance
from .dragon_provenance_registry import ProvenanceRegistry


@dataclass(frozen=True)
class CustodyPromotionReview:
    """Human-readable evidence/decision pair bound to the same normalized input."""

    claim_id: str
    assurance: ProvenanceAssurance
    decision: PromotionDecision
    normalized_evidence_digest: str
    manifest_fingerprint: str


def assess_custodied_promotion(
    claim_id: str,
    readings: Iterable[EvidencePass],
    source_manifest: Iterable[SourceProvenance],
    receipts: tuple[LayerReceipt, ...],
    measurements: tuple[Measurement, ...],
    *,
    authorized: bool,
    policy: PromotionPolicy = PromotionPolicy(),
    assurance_policy: AssurancePolicy = AssurancePolicy(),
    calibration: CalibrationArtifact | None = None,
    attestation_registry: ProvenanceRegistry | None = None,
) -> CustodyPromotionReview:
    """Bind source-lineage assurance to empirical-calibration/promotion gates.

    Does not emit a layer receipt, forge an approval, or write to memory.
    A missing or incomplete custody manifest fails closed. Custom relaxing
    promotion policies are honored only after provenance assurance succeeds.
    """
    if not authorized:
        raise PermissionError("custodied promotion requires authorization")
    values = tuple(readings)
    manifest = tuple(source_manifest)
    assurance = assure_crawler_evidence(
        claim_id, values, manifest, authorized=True,
        assurance_policy=assurance_policy,
        attestation_registry=attestation_registry,
    )
    by_source: dict[str, str] = {}
    for cluster in assurance.clusters:
        for sid in cluster.source_ids:
            by_source[sid] = cluster.cluster_id
    normalized = tuple(
        replace(item, independence_group=by_source[item.source_id])
        for item in values
    )
    decision = assess_promotion(
        claim_id, normalized, receipts, measurements,
        authorized=True, policy=policy, calibration=calibration,
    )
    if decision.evidence_digest != assurance.belief.evidence_digest:
        raise RuntimeError("custody-normalized promotion evidence digest mismatch")
    failures = list(decision.reasons)
    # Deterministic, explicit dispositions instead of representing the
    # absence of a problem as evidence of provenance authenticity.
    for blocker in assurance.blockers:
        human_reason = "Custody assurance: " + blocker.replace("_", " ")
        if human_reason not in failures:
            failures.append(human_reason)
    if not assurance.candidate_for_review:
        eligible = False
    else:
        eligible = decision.eligible and not failures
    merged_decision = replace(
        decision, eligible=eligible, reasons=tuple(failures),
    )
    return CustodyPromotionReview(
        claim_id, assurance, merged_decision,
        assurance.belief.evidence_digest, assurance.fingerprint,
    )
