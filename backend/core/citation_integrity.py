"""Claim-level citation integrity and laundering defenses.

A citation is not evidence merely because it is nearby. Supporting extractive
evidence must preserve a claim's material structure. Contradicting extractive
evidence must contain an explicit opposition signal. Both paths require inspectable
provenance, locators, quantities/units and sufficient claim anchoring.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from core.claim_identity import fingerprint_claim


_ALLOWED_BINDINGS = {
    "direct_quote", "table", "figure", "dataset_query", "primary_document_clause",
    "measurement_record", "analyst_mapping",
}
_EXTRACTIVE = {"direct_quote", "primary_document_clause", "measurement_record"}
_STRUCTURED = {"table", "figure", "dataset_query"}


@dataclass(frozen=True, slots=True)
class CitationBinding:
    claim: str
    source_id: str
    locator: str
    binding_method: str
    evidence_span: str
    supports: bool
    provenance_verified: bool
    source_content_sha256: str = ""
    mapping_rationale: str = ""


@dataclass(frozen=True, slots=True)
class CitationIntegrityReport:
    accepted: bool
    laundering_risk: str
    reasons: tuple[str, ...]
    claim_identity_sha256: str
    evidence_span_sha256: str
    anchor_overlap: float
    attestation_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _tokens(text: str) -> set[str]:
    stop = {"the", "a", "an", "of", "to", "for", "and", "or", "in", "on", "with", "is", "are", "was", "were"}
    return {x for x in re.findall(r"[a-z0-9]+", text.casefold()) if len(x) >= 3 and x not in stop}


def _numbers(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[-+]?\d+(?:\.\d+)?", text.replace(",", "")))


def _overlap(claim: str, span: str) -> float:
    a, b = _tokens(claim), _tokens(span)
    return 1.0 if not a else len(a & b) / len(a)


class CitationIntegrityEngine:
    def validate(self, binding: CitationBinding) -> CitationIntegrityReport:
        reasons: list[str] = []
        method = binding.binding_method.strip().casefold()
        claim = " ".join(binding.claim.split()).strip(); span = " ".join(binding.evidence_span.split()).strip()
        locator = binding.locator.strip(); source = binding.source_id.strip()
        if not claim or not source: reasons.append("claim_or_source_missing")
        if not binding.provenance_verified: reasons.append("source_provenance_unverified")
        if not locator: reasons.append("source_locator_missing")
        if method not in _ALLOWED_BINDINGS: reasons.append("unsupported_binding_method")
        if not span: reasons.append("evidence_span_missing")
        if binding.source_content_sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", binding.source_content_sha256):
            reasons.append("source_content_digest_invalid")

        overlap = round(_overlap(claim, span), 6) if span else 0.0
        claim_numbers = _numbers(claim); span_numbers = _numbers(span)
        if claim_numbers and any(value not in span_numbers for value in claim_numbers):
            reasons.append("claim_quantity_not_present_in_evidence_span")

        claim_fp = fingerprint_claim(claim) if claim else None; span_fp = fingerprint_claim(span) if span else None
        if claim_fp is not None and span_fp is not None:
            if claim_fp.units and any(unit not in span_fp.units for unit in claim_fp.units):
                reasons.append("claim_unit_not_present_in_evidence_span")
            polarity_differs = claim_fp.polarity != span_fp.polarity
            relation_differs = (claim_fp.relation != "unspecified" and span_fp.relation != "unspecified"
                                and claim_fp.relation != span_fp.relation)
            if method in _EXTRACTIVE:
                if binding.supports:
                    if polarity_differs: reasons.append("evidence_polarity_conflict")
                    if relation_differs: reasons.append("evidence_relation_conflict")
                elif not (polarity_differs or relation_differs):
                    reasons.append("contradiction_binding_lacks_opposition_signal")

        if method in _EXTRACTIVE and overlap < 0.30: reasons.append("insufficient_claim_anchor_overlap")
        if method in _STRUCTURED and not binding.mapping_rationale.strip():
            reasons.append("structured_evidence_mapping_rationale_missing")
        if method == "analyst_mapping":
            if len(binding.mapping_rationale.strip()) < 20: reasons.append("analyst_mapping_rationale_insufficient")
            if overlap < 0.10: reasons.append("analyst_mapping_has_no_claim_anchor")

        reasons = list(dict.fromkeys(reasons)); accepted = not reasons
        critical = {"source_provenance_unverified", "source_locator_missing", "evidence_span_missing"}
        high = {"claim_quantity_not_present_in_evidence_span", "claim_unit_not_present_in_evidence_span",
                "evidence_polarity_conflict", "evidence_relation_conflict", "contradiction_binding_lacks_opposition_signal"}
        if accepted: risk = "low"
        elif critical.intersection(reasons): risk = "critical"
        elif high.intersection(reasons): risk = "high"
        else: risk = "medium"
        identity = claim_fp.identity_sha256 if claim_fp is not None else _sha("")
        span_sha = hashlib.sha256(span.encode("utf-8")).hexdigest()
        payload = {"accepted": accepted, "laundering_risk": risk, "reasons": tuple(reasons),
                   "claim_identity_sha256": identity, "evidence_span_sha256": span_sha, "anchor_overlap": overlap}
        return CitationIntegrityReport(accepted, risk, tuple(reasons), identity, span_sha, overlap, _sha(payload))

    @staticmethod
    def verify(report: CitationIntegrityReport) -> bool:
        payload = {"accepted": report.accepted, "laundering_risk": report.laundering_risk,
                   "reasons": report.reasons, "claim_identity_sha256": report.claim_identity_sha256,
                   "evidence_span_sha256": report.evidence_span_sha256, "anchor_overlap": report.anchor_overlap}
        return _sha(payload) == report.attestation_sha256

    def validate_many(self, bindings: Iterable[CitationBinding]) -> tuple[CitationIntegrityReport, ...]:
        return tuple(self.validate(binding) for binding in bindings)
