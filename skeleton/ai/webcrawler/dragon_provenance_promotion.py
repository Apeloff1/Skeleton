"""Fail-closed custody-bound adapter for the existing knowledge promotion gate.

The legacy promotion API accepts caller-labelled source groups for backwards
compatibility. New crawler ingestion paths should use this adapter: it replaces
those labels with the conservative dependency closure of a complete manifest
before invoking calibrated promotion checks.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from math import isfinite
from itertools import islice
import json
import re
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
from .core import CrawlPolicy


@dataclass(frozen=True)
class EmpiricalCitation:
    """Claim-specific review supplied by an authenticated evidence custodian.

    These fields record a review, not a machine's proof that a paper is true.
    The embedding process verifies reviewers and artifacts before calling this
    boundary. Publisher prestige and repeated reads never replace measurements.
    """

    source_id: str
    source_revision: str
    claim_id: str
    source_url: str
    source_digest: str
    study_id: str
    artifact_url: str
    artifact_digest: str
    evidence_kind: str
    methods: str
    measured_result: str
    sample_size: int
    applicability: str
    limitations: str
    reputation_basis: str
    reputation_reference: str
    reviewer_id: str
    review_reference: str
    reviewed_locators: tuple[str, ...]
    reviewed_at: float
    expires_at: float


def _empirical_records(claim_id, values, manifest, citations, now):
    """Validate complete claim/revision/span bindings before counting studies."""
    if len(citations) > 10000:
        raise ValueError("empirical citation budget exceeded")
    if now is not None and (type(now) not in (int, float) or not isfinite(now)):
        raise ValueError("invalid empirical review clock")
    sources = {s.source_id: s for s in manifest}
    readings_by_source = {}
    for reading in values:
        readings_by_source.setdefault(reading.source_id, []).append(reading)
    by_source = {}
    failures = []
    url_policy = CrawlPolicy()
    for c in citations:
        if not isinstance(c, EmpiricalCitation):
            raise ValueError("typed empirical citation required")
        for field in ("source_id", "source_revision", "claim_id", "study_id", "reviewer_id"):
            value = getattr(c, field)
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
                raise ValueError("invalid empirical identity")
        for field in ("source_digest", "artifact_digest"):
            if not isinstance(getattr(c, field), str) or not re.fullmatch(r"[0-9a-f]{64}", getattr(c, field)):
                raise ValueError("invalid empirical digest")
        for field in ("source_url", "artifact_url", "reputation_reference", "review_reference"):
            value = getattr(c, field)
            if (not isinstance(value, str) or len(value) > 2048
                    or not value.startswith("https://") or not url_policy.admits(value)):
                raise ValueError("invalid empirical citation URL")
        for field in ("methods", "measured_result", "applicability", "limitations"):
            value = getattr(c, field)
            if not isinstance(value, str) or not value.strip() or len(value) > 4000:
                raise ValueError("incomplete empirical review")
        if c.evidence_kind not in ("experiment", "benchmark", "systematic_observation"):
            raise ValueError("empirical evidence kind required")
        if c.reputation_basis not in ("peer_reviewed", "official_technical_report", "independent_lab"):
            raise ValueError("documented reputable-source review required")
        if type(c.sample_size) is not int or not 1 <= c.sample_size <= 10**12:
            raise ValueError("positive empirical sample size required")
        if (not isinstance(c.reviewed_locators, tuple) or not 1 <= len(c.reviewed_locators) <= 100
                or any(not isinstance(x, str) or not x.strip() or len(x) > 512 for x in c.reviewed_locators)
                or len(set(c.reviewed_locators)) != len(c.reviewed_locators)):
            raise ValueError("bounded unique reviewed citation locators required")
        if (any(type(t) not in (int, float) or not isfinite(t)
                for t in (c.reviewed_at, c.expires_at)) or c.reviewed_at < 0
                or c.expires_at <= c.reviewed_at):
            raise ValueError("invalid empirical review validity interval")
        if c.source_id in by_source:
            raise ValueError("duplicate empirical source review")
        source = sources.get(c.source_id)
        readings = readings_by_source.get(c.source_id, [])
        if (source is None or not readings or c.claim_id != claim_id
                or c.source_url != source.canonical_uri or c.source_digest != source.content_digest
                or any(r.source_revision != c.source_revision for r in readings)
                or set(c.reviewed_locators) != {r.evidence_locator for r in readings}):
            raise ValueError("empirical citation does not bind exact claim/source/revision/locators")
        if now is None or not c.reviewed_at <= now < c.expires_at:
            failures.append("Empirical review expired, future-dated or clock missing: " + c.source_id)
        by_source[c.source_id] = c
    for sid in sorted({r.source_id for r in values} - by_source.keys()):
        failures.append("Empirical citation review missing: " + sid)
    # Conservative dependencies: one experiment or raw artifact is one study,
    # even when different publishers report it under different source IDs.
    augmented = tuple(replace(s, lineage_tokens=tuple(sorted(set(s.lineage_tokens) | {
        "empirical-study:" + by_source[s.source_id].study_id,
        "empirical-artifact:" + by_source[s.source_id].artifact_digest,
    }))) if s.source_id in by_source else s for s in manifest)
    payload = {"claim_id": claim_id, "as_of": now,
               "citations": [asdict(by_source[k]) for k in sorted(by_source)]}
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               allow_nan=False).encode()).hexdigest()
    return augmented, tuple(failures), digest


@dataclass(frozen=True)
class CustodyPromotionReview:
    """Human-readable evidence/decision pair bound to the same normalized input."""

    claim_id: str
    assurance: ProvenanceAssurance
    decision: PromotionDecision
    normalized_evidence_digest: str
    manifest_fingerprint: str
    empirical_review_digest: str
    citations: tuple[EmpiricalCitation, ...]


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
    empirical_citations: tuple[EmpiricalCitation, ...] = (),
    now: float | None = None,
) -> CustodyPromotionReview:
    """Bind source-lineage assurance to empirical-calibration/promotion gates.

    Does not emit a layer receipt, forge an approval, or write to memory.
    A missing or incomplete custody manifest fails closed. Custom relaxing
    promotion policies are honored only after provenance assurance succeeds.
    """
    if authorized is not True:
        raise PermissionError("custodied promotion requires authorization")
    values = tuple(islice(readings, 10001))
    manifest = tuple(islice(source_manifest, 10001))
    empirical_citations = tuple(islice(empirical_citations, 10001))
    if len(values) > 10000 or len(manifest) > 10000:
        raise ValueError("empirical promotion input budget exceeded")
    if any(not isinstance(r, EvidencePass) for r in values):
        raise ValueError("typed evidence readings required")
    if any(not isinstance(s, SourceProvenance) for s in manifest):
        raise ValueError("typed source manifest required")
    manifest, empirical_failures, empirical_digest = _empirical_records(
        claim_id, values, manifest, empirical_citations, now,
    )
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
    failures.extend(empirical_failures)
    if attestation_registry is None or not attestation_registry.policy.require_attestation:
        failures.append("Verified publisher ownership registry required")
    # The user-facing quality requirement cannot be relaxed by a promotion
    # score policy. All qualification still passes through the existing gate.
    supporting_groups = sum(c.supporting_readings > 0 for c in assurance.clusters)
    if supporting_groups < 2:
        failures.append("At least two independent empirical supporting studies required")
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
        empirical_digest, tuple(sorted(empirical_citations, key=lambda c: c.source_id)),
    )
