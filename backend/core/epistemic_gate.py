"""Epistemic promotion gate between research findings and durable knowledge.

Research may be exploratory; Orientation Room is not. This gate converts a raw
finding into separated verified/provisional/speculative/contradicted projections.
Only VERIFIED claims are eligible for authoritative reasoning context.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Iterable

from core.evidence_registry import EvidenceRegistry
from core.truth_verifier import (
    EvidenceItem,
    EvidenceKind,
    TruthVerifier,
    VerificationBatch,
    VerificationState,
)


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


def evidence_item_from_dict(raw: dict[str, Any]) -> EvidenceItem:
    source_id = str(raw.get("source_id") or raw.get("source") or "").strip()
    locator = str(raw.get("locator") or "").strip()
    independence = str(raw.get("independence_group") or source_id or "unknown").strip()
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
    )


class EpistemicGate:
    def __init__(self, verifier: TruthVerifier | None = None, registry: EvidenceRegistry | None = None) -> None:
        self.verifier = verifier or TruthVerifier()
        self.registry = registry

    def evaluate(self, finding: dict[str, Any]) -> EpistemicDecision:
        claims = tuple(" ".join(str(x).split()).strip() for x in (finding.get("claims") or ()) if str(x).strip())
        claim_evidence_raw = finding.get("claim_evidence") or {}
        if not isinstance(claim_evidence_raw, dict):
            raise ValueError("claim_evidence must be an object mapping claims to evidence arrays")

        generic_raw = finding.get("evidence") or ()
        if not isinstance(generic_raw, (list, tuple)):
            generic_raw = ()

        evidence_by_claim: dict[str, tuple[EvidenceItem, ...]] = {}
        for claim in claims:
            explicit = claim_evidence_raw.get(claim)
            if explicit is None:
                # Generic evidence is intentionally NOT assumed to support every
                # claim unless the finding explicitly marks it applies_to_all.
                source_rows = generic_raw if finding.get("evidence_applies_to_all") is True else ()
            else:
                source_rows = explicit
            if not isinstance(source_rows, (list, tuple)):
                source_rows = ()
            items = tuple(evidence_item_from_dict(x) for x in source_rows if isinstance(x, dict))
            if self.registry is not None:
                for item in items:
                    self.registry.register(claim, item)
                items = self.registry.evidence_for(claim)
            evidence_by_claim[claim] = items

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
                    "total_quality": item.total_quality,
                    "mean_quality": item.mean_quality,
                    "reproducibility_signal": item.reproducibility_signal,
                    "falsifiable": item.falsifiable,
                    "reasons": list(item.reasons),
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
        """Non-verified material is retained only as an auditable research gap."""
        rows = []
        for claim in decision.provisional_claims:
            rows.append(f"PROVISIONAL — requires stronger independent empirical support: {claim}")
        for claim in decision.contradicted_claims:
            rows.append(f"CONTRADICTED — requires resolution before use: {claim}")
        for claim in decision.unverified_claims:
            rows.append(f"UNVERIFIED — excluded from authoritative context: {claim}")
        for claim in decision.irrelevant_speculation:
            rows.append(f"IRRELEVANT SPECULATION — not evidence: {claim}")
        return tuple(rows)
