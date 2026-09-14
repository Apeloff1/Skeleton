"""Truth-gated Curiosity Engine.

Raw research is never written directly into authoritative knowledge. Findings are
first evaluated by EpistemicGate. Only empirically VERIFIED claims become the
record claims/Orientation context. Provisional, contradicted, unverified and
speculative material is retained as research gaps for HOAG and future inquiry.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.curiosity_engine import CuriosityEngine, Inquiry
from core.evidence_registry import EvidenceRegistry
from core.epistemic_gate import EpistemicDecision, EpistemicGate
from core.knowledge_fabric import EvidenceRef, KnowledgeFabric, KnowledgeRecord
from core.truth_verifier import TruthVerifier, VerificationPolicy


class VerifiedCuriosityEngine(CuriosityEngine):
    def __init__(
        self,
        root: str | Path,
        *,
        fabric: KnowledgeFabric | None = None,
        verifier: TruthVerifier | None = None,
        policy: VerificationPolicy | None = None,
    ) -> None:
        super().__init__(root, fabric=fabric)
        self.evidence_registry = EvidenceRegistry(self.root / "evidence")
        self.verifier = verifier or TruthVerifier(policy)
        self.epistemic_gate = EpistemicGate(self.verifier, self.evidence_registry)

    @staticmethod
    def _orientation_summary(decision: EpistemicDecision) -> str:
        if decision.verified_claims:
            return "Verified knowledge: " + " ".join(decision.verified_claims[:8])
        return (
            "No claim in this research cycle met the empirical verification standard. "
            "Material is retained only as research gaps/hypotheses and must not be used as verified fact."
        )

    @staticmethod
    def _verified_evidence(finding: dict[str, Any], decision: EpistemicDecision) -> tuple[EvidenceRef, ...]:
        rows: list[EvidenceRef] = []
        claim_evidence = finding.get("claim_evidence") or {}
        if not isinstance(claim_evidence, dict):
            return ()
        verified = set(decision.verified_claims)
        seen: set[tuple[str, str]] = set()
        for claim, evidence_rows in claim_evidence.items():
            if claim not in verified or not isinstance(evidence_rows, (list, tuple)):
                continue
            for raw in evidence_rows:
                if not isinstance(raw, dict):
                    continue
                source = str(raw.get("source_id") or raw.get("source") or "").strip()
                locator = str(raw.get("locator") or "").strip()
                key = (source, locator)
                if not source or key in seen:
                    continue
                seen.add(key)
                rows.append(EvidenceRef(
                    source=source[:1000], locator=locator[:2000],
                    confidence=max(0.0, min(1.0, float(raw.get("quality", raw.get("confidence", 0.0)) or 0.0))),
                    observed_at=str(raw.get("observed_at") or "")[:100],
                ))
        return tuple(rows[:128])

    def accept_finding(self, inquiry: Inquiry, finding: dict[str, Any]) -> KnowledgeRecord:
        if not isinstance(finding, dict):
            raise ValueError("research finding must be an object")
        decision = self.epistemic_gate.evaluate(finding)
        gaps = list(self.epistemic_gate.hoag_gaps(decision))
        gaps.extend(str(x) for x in (finding.get("questions") or ()) if str(x).strip())
        contradictions = [
            f"CONTRADICTION — {claim}" for claim in decision.contradicted_claims
        ]
        verified_evidence = self._verified_evidence(finding, decision)
        verified_count = len(decision.verified_claims)
        confidence = 0.0
        if verified_count:
            confidence = min(
                self.verifier.verify_claim(
                    claim,
                    self.evidence_registry.evidence_for(claim),
                    falsifiable=(finding.get("falsifiable") or {}).get(claim) if isinstance(finding.get("falsifiable"), dict) else None,
                ).mean_quality
                for claim in decision.verified_claims
            )
        previous = self.fabric.search(inquiry.subject, limit=12)
        previous_verified = {claim.casefold() for record in previous for claim in record.claims}
        novel_verified = sum(1 for claim in decision.verified_claims if claim.casefold() not in previous_verified)
        novelty = min(1.0, (novel_verified + len(gaps)) / max(1, verified_count + len(gaps) + 2))
        record = self.fabric.publish(
            subject=inquiry.subject,
            title=str(finding.get("title") or f"Verified curiosity brief: {inquiry.subject}"),
            summary=self._orientation_summary(decision),
            claims=decision.verified_claims,
            questions=tuple(dict.fromkeys(gaps)),
            contradictions=tuple(contradictions),
            evidence=verified_evidence,
            tags=tuple(inquiry.keywords) + ("truth-gated",),
            confidence=confidence,
            novelty=novelty,
            parent_prompt_id=inquiry.id,
            created_at=datetime.now(UTC).isoformat(),
        )
        with self._lease.acquire():
            topics = self._load_frontier()
            raw = topics.get(inquiry.subject)
            if raw is not None:
                raw["research_count"] = int(raw.get("research_count", 0)) + 1
                raw["last_researched_at"] = datetime.now(UTC).isoformat()
                raw["last_record_id"] = record.id
                raw["unresolved_count"] = len(gaps) + len(contradictions)
                topics[inquiry.subject] = raw
                self._write_frontier(topics)
        return record

    def verification_status(self) -> dict[str, Any]:
        evidence = self.evidence_registry.stats()
        knowledge = self.fabric.stats()
        return {
            "truth_gated": True,
            "speculation_authoritative": False,
            "model_consensus_is_empirical_evidence": False,
            "evidence_registry": evidence,
            "knowledge": knowledge,
            "verification_policy": {
                "minimum_independent_support": self.verifier.policy.minimum_independent_support,
                "minimum_total_quality": self.verifier.policy.minimum_total_quality,
                "minimum_mean_quality": self.verifier.policy.minimum_mean_quality,
                "require_empirical_support": self.verifier.policy.require_empirical_support,
                "require_reproducibility_signal": self.verifier.policy.require_reproducibility_signal,
                "require_falsifiable_claim": self.verifier.policy.require_falsifiable_claim,
                "contradiction_blocks": self.verifier.policy.contradiction_blocks,
            },
        }

    def stats(self) -> dict[str, Any]:
        stats = super().stats()
        stats["verification"] = self.verification_status()
        return stats
