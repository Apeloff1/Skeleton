"""Epistemic promotion gate between research findings and durable knowledge.

Research may be exploratory; Orientation Room is not. Raw evidence metadata is
normalized into TruthVerifier evidence contracts, including provenance and
methodology signals. Correlated sources are conservatively collapsed before
independent-support counting. Only VERIFIED claims enter authoritative context.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from core.evidence_registry import EvidenceRegistry
from core.source_independence import SourceIndependenceAnalyzer
from core.truth_verifier import EvidenceItem, EvidenceKind, TruthVerifier, VerificationBatch


@dataclass(frozen=True, slots=True)
class EpistemicDecision:
    verified_claims: tuple[str, ...]
    provisional_claims: tuple[str, ...]
    contradicted_claims: tuple[str, ...]
    unverified_claims: tuple[str, ...]
    irrelevant_speculation: tuple[str, ...]
    verification: dict[str, dict[str, Any]]
    attestation_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _kind(value: Any) -> EvidenceKind:
    try:
        return EvidenceKind(str(value))
    except ValueError:
        return EvidenceKind.UNSOURCED


def _sample_size(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def evidence_item_from_dict(raw: dict[str, Any]) -> EvidenceItem:
    source_id = str(raw.get("source_id") or raw.get("source") or "").strip()
    locator = str(raw.get("locator") or "").strip()
    independence = str(raw.get("independence_group") or source_id or "unknown").strip()
    provenance_verified = bool(raw.get("provenance_verified", raw.get("verified_locator", False)))
    return EvidenceItem(
        source_id=source_id,
        locator=locator,
        kind=_kind(raw.get("kind") or ("model_observation" if source_id.startswith("model-observation:") else "unsourced")),
        supports=bool(raw.get("supports", True)),
        independence_group=independence,
        quality=float(raw.get("quality", raw.get("confidence", 0.0)) or 0.0),
        observed_at=str(raw.get("observed_at") or ""),
        reproducible=bool(raw.get("reproducible", False)),
        peer_reviewed=bool(raw.get("peer_reviewed", False)),
        primary=bool(raw.get("primary", False)),
        notes=str(raw.get("notes") or "")[:4000],
        provenance_verified=provenance_verified,
        preregistered=bool(raw.get("preregistered", False)),
        data_available=bool(raw.get("data_available", False)),
        code_available=bool(raw.get("code_available", False)),
        sample_size=_sample_size(raw.get("sample_size")),
        uncertainty_reported=bool(raw.get("uncertainty_reported", False)),
    )


class EpistemicGate:
    def __init__(
        self,
        verifier: TruthVerifier | None = None,
        registry: EvidenceRegistry | None = None,
        independence: SourceIndependenceAnalyzer | None = None,
    ) -> None:
        self.verifier = verifier or TruthVerifier()
        self.registry = registry
        self.independence = independence

    @staticmethod
    def _independence_payload(report: Any | None) -> dict[str, Any] | None:
        if report is None:
            return None
        return {
            "raw_sources": report.raw_sources,
            "effective_independent_sources": report.effective_independent_sources,
            "unresolved_sources": list(report.unresolved_sources),
            "clusters": [
                {
                    "id": row.id,
                    "source_ids": list(row.source_ids),
                    "reasons": list(row.reasons),
                    "shared_roots": list(row.shared_roots),
                    "shared_content_sha256": list(row.shared_content_sha256),
                }
                for row in report.clusters
            ],
            "attestation_sha256": report.attestation_sha256,
        }

    def evaluate(self, finding: dict[str, Any]) -> EpistemicDecision:
        claims = tuple(" ".join(str(x).split()).strip() for x in (finding.get("claims") or ()) if str(x).strip())
        claim_evidence_raw = finding.get("claim_evidence") or {}
        if not isinstance(claim_evidence_raw, dict):
            raise ValueError("claim_evidence must be an object mapping claims to evidence arrays")
        generic_raw = finding.get("evidence") or ()
        if not isinstance(generic_raw, (list, tuple)):
            generic_raw = ()

        evidence_by_claim: dict[str, tuple[EvidenceItem, ...]] = {}
        independence_by_claim: dict[str, Any] = {}
        for claim in claims:
            explicit = claim_evidence_raw.get(claim)
            source_rows = generic_raw if explicit is None and finding.get("evidence_applies_to_all") is True else explicit
            if not isinstance(source_rows, (list, tuple)):
                source_rows = ()
            items = tuple(evidence_item_from_dict(x) for x in source_rows if isinstance(x, dict))
            if self.registry is not None:
                for item in items:
                    self.registry.register(claim, item)
                items = self.registry.evidence_for(claim)
            report = None
            if self.independence is not None:
                items, report = self.independence.collapse(items)
            evidence_by_claim[claim] = items
            independence_by_claim[claim] = report

        falsifiability = finding.get("falsifiable") or {}
        if not isinstance(falsifiability, dict):
            falsifiability = {}
        batch: VerificationBatch = self.verifier.verify_many(claims, evidence_by_claim, falsifiability=falsifiability)
        projection = self.verifier.epistemic_projection(batch)
        verification: dict[str, dict[str, Any]] = {}
        for group in (batch.verified, batch.provisional, batch.contradicted, batch.unverified, batch.irrelevant_speculation):
            for item in group:
                verification[item.claim] = {
                    "state": item.state.value,
                    "empirical_support": item.empirical_support,
                    "independent_support": item.independent_support,
                    "independent_contradictions": item.independent_contradictions,
                    "provenance_verified_support": item.provenance_verified_support,
                    "total_quality": item.total_quality,
                    "mean_quality": item.mean_quality,
                    "reproducibility_signal": item.reproducibility_signal,
                    "independent_replication": item.independent_replication,
                    "falsifiable": item.falsifiable,
                    "reasons": list(item.reasons),
                    "independence": self._independence_payload(independence_by_claim.get(item.claim)),
                    "attestation_sha256": item.attestation_sha256,
                }
        payload = {**projection, "verification": verification}
        return EpistemicDecision(
            verified_claims=tuple(projection["verified"]),
            provisional_claims=tuple(projection["provisional"]),
            contradicted_claims=tuple(projection["contradicted"]),
            unverified_claims=tuple(projection["unverified"]),
            irrelevant_speculation=tuple(projection["irrelevant_speculation"]),
            verification=verification,
            attestation_sha256=_digest(payload),
        )

    @staticmethod
    def hoag_gaps(decision: EpistemicDecision) -> tuple[str, ...]:
        rows: list[str] = []
        for claim in decision.provisional_claims:
            rows.append(f"PROVISIONAL — requires stronger independent empirical support: {claim}")
        for claim in decision.contradicted_claims:
            rows.append(f"CONTRADICTED — requires resolution before use: {claim}")
        for claim in decision.unverified_claims:
            rows.append(f"UNVERIFIED — excluded from authoritative context: {claim}")
        for claim in decision.irrelevant_speculation:
            rows.append(f"IRRELEVANT SPECULATION — not evidence: {claim}")
        return tuple(rows)
