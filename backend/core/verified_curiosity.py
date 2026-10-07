"""Truth-gated Curiosity Engine with live truth-state projection.

Historical knowledge is append-preserving. Authoritative context is a derived view
governed by claim-bound empirical evidence, source lineage/independence, claim
dependencies, expiry, contradictions and re-verification. Metadata cannot bypass
truth gates: even lineage registration independently validates citation bindings.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from core.calibration_ledger import CalibrationLedger
from core.citation_integrity import CitationBinding, CitationIntegrityEngine
from core.claim_dependency_graph import ClaimDependencyGraph
from core.claim_identity import ClaimIdentityEngine
from core.claim_truth_ledger import ClaimTruthLedger
from core.contradiction_resolver import ContradictionResolver
from core.curiosity_engine import CuriosityEngine, Inquiry
from core.evidence_registry import EvidenceRegistry
from core.epistemic_gate import EpistemicDecision, EpistemicGate
from core.knowledge_fabric import EvidenceRef, KnowledgeFabric, KnowledgeRecord
from core.source_independence import LEGACY_UNRESOLVED_PREFIX, SourceIndependenceAnalyzer
from core.source_lineage import SourceLineageGraph
from core.truth_verifier import TruthVerifier, VerificationPolicy, VerificationState, effective_evidence_quality


def _decision_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class VerifiedCuriosityEngine(CuriosityEngine):
    def __init__(self, root: str | Path, *, fabric: KnowledgeFabric | None = None,
                 verifier: TruthVerifier | None = None, policy: VerificationPolicy | None = None,
                 truth_valid_days: int = 180) -> None:
        super().__init__(root, fabric=fabric)
        self.evidence_registry = EvidenceRegistry(self.root / "evidence")
        self.source_lineage = SourceLineageGraph(self.root / "source-lineage")
        self.independence = SourceIndependenceAnalyzer(self.source_lineage)
        self.truth_ledger = ClaimTruthLedger(self.root / "truth-state", default_valid_days=truth_valid_days)
        self.claim_dependencies = ClaimDependencyGraph(self.root / "claim-dependencies")
        self.claim_identity = ClaimIdentityEngine()
        self.calibration = CalibrationLedger(self.root / "calibration")
        self.citation_integrity = CitationIntegrityEngine()
        self.verifier = verifier or TruthVerifier(policy)
        self.epistemic_gate = EpistemicGate(self.verifier, self.evidence_registry, self.independence)
        self.contradictions = ContradictionResolver()
        self._lineage_backfill = self.backfill_source_lineage()

    @staticmethod
    def _orientation_summary(decision: EpistemicDecision) -> str:
        if decision.verified_claims:
            return "Verified knowledge: " + " ".join(decision.verified_claims[:8])
        return ("No claim in this research cycle met the empirical verification standard. "
                "Material is retained only as research gaps/hypotheses and must not be used as verified fact.")

    def backfill_source_lineage(self) -> dict[str, int]:
        created = 0; existing = 0
        for record in self.evidence_registry.snapshot(include_retracted=True):
            item = record.item
            if not item.source_id:
                continue
            if self.source_lineage.get(item.source_id) is not None:
                existing += 1; continue
            self.source_lineage.register(
                item.source_id,
                source_kind=f"{LEGACY_UNRESOLVED_PREFIX}{item.kind.value}",
                locator=item.locator,
            )
            created += 1
        return {"created": created, "existing": existing}

    def _lineage_row_is_bound(self, claim: str, raw: dict[str, Any]) -> bool:
        binding = raw.get("citation_binding")
        if not isinstance(binding, dict):
            return False
        report = self.citation_integrity.validate(CitationBinding(
            claim=claim,
            source_id=str(raw.get("source_id") or raw.get("source") or ""),
            locator=str(raw.get("locator") or ""),
            binding_method=str(binding.get("binding_method") or ""),
            evidence_span=str(binding.get("evidence_span") or ""),
            supports=bool(raw.get("supports", True)),
            provenance_verified=bool(raw.get("provenance_verified", raw.get("verified_locator", False))),
            source_content_sha256=str(raw.get("content_sha256") or ""),
            mapping_rationale=str(binding.get("mapping_rationale") or ""),
        ))
        return report.accepted

    def _register_lineage(self, finding: dict[str, Any]) -> None:
        claim_evidence = finding.get("claim_evidence") or {}
        if not isinstance(claim_evidence, dict):
            return
        rows: dict[str, dict[str, Any]] = {}
        for claim, evidence_rows in claim_evidence.items():
            claim = " ".join(str(claim).split()).strip()
            if not claim or not isinstance(evidence_rows, (list, tuple)):
                continue
            for raw in evidence_rows:
                if not isinstance(raw, dict) or not self._lineage_row_is_bound(claim, raw):
                    continue
                source_id = str(raw.get("source_id") or raw.get("source") or "").strip()
                if source_id and source_id not in rows:
                    rows[source_id] = raw
        pending = dict(rows)
        for _ in range(len(pending) + 1):
            progressed = False
            for source_id, raw in list(pending.items()):
                parents = tuple(str(x).strip() for x in (raw.get("parent_source_ids") or ()) if str(x).strip())
                if any(self.source_lineage.get(parent) is None for parent in parents):
                    continue
                existing = self.source_lineage.get(source_id)
                if existing is not None and existing.source_kind.startswith(LEGACY_UNRESOLVED_PREFIX):
                    pending.pop(source_id); progressed = True; continue
                self.source_lineage.register(
                    source_id,
                    source_kind=str(raw.get("kind") or "unknown"),
                    locator=str(raw.get("locator") or ""),
                    parent_ids=parents,
                    content_sha256=str(raw.get("content_sha256") or ""),
                )
                pending.pop(source_id); progressed = True
            if not pending or not progressed:
                break

    def _register_claim_dependencies(self, finding: dict[str, Any], claims: tuple[str, ...]) -> None:
        raw = finding.get("claim_dependencies") or {}
        if not isinstance(raw, dict): raw = {}
        for claim in claims:
            deps = raw.get(claim, ())
            if not isinstance(deps, (list, tuple)): deps = ()
            self.claim_dependencies.register(claim, deps)

    def _apply_dependency_gate(self, decision: EpistemicDecision) -> EpistemicDecision:
        accepted: list[str] = []; remaining = list(decision.verified_claims)
        while remaining:
            progressed = False
            for claim in list(remaining):
                deps = self.claim_dependencies.dependencies(claim)
                if all(self.truth_ledger.authoritative(dep) or dep in accepted for dep in deps):
                    accepted.append(claim); remaining.remove(claim); progressed = True
            if not progressed: break
        blocked = tuple(remaining)
        if not blocked: return decision
        verification = {claim: dict(data) for claim, data in decision.verification.items()}
        for claim in blocked:
            blockers = [dep for dep in self.claim_dependencies.dependencies(claim)
                        if not self.truth_ledger.authoritative(dep) and dep not in accepted]
            row = verification.setdefault(claim, {})
            row["state"] = "unverified"; row["dependency_blockers"] = blockers
            row["reasons"] = list(dict.fromkeys([*(row.get("reasons") or []), "non_authoritative_dependency"]))
        unverified = tuple(dict.fromkeys((*decision.unverified_claims, *blocked)))
        payload = {"verified": tuple(accepted), "provisional": decision.provisional_claims,
                   "contradicted": decision.contradicted_claims, "unverified": unverified,
                   "irrelevant_speculation": decision.irrelevant_speculation, "verification": verification}
        return EpistemicDecision(tuple(accepted), decision.provisional_claims, decision.contradicted_claims,
                                 unverified, decision.irrelevant_speculation, verification, _decision_digest(payload))

    def _revoke_dependents(self, claims: tuple[str, ...] | list[str], reason: str) -> tuple[str, ...]:
        affected: set[str] = set()
        for claim in claims:
            affected.update(self.claim_dependencies.dependents(claim, recursive=True))
        for claim in sorted(affected):
            if self.truth_ledger.get(claim) is not None:
                self.truth_ledger.revoke(claim, reason)
        return tuple(sorted(affected))

    def _active_evidence(self, claim: str):
        rows = self.evidence_registry.evidence_for(claim)
        collapsed, _ = self.independence.collapse(rows)
        return collapsed

    def _verified_evidence(self, decision: EpistemicDecision) -> tuple[EvidenceRef, ...]:
        rows: list[EvidenceRef] = []; seen: set[tuple[str, str]] = set()
        for claim in decision.verified_claims:
            for record in self.evidence_registry.records_for(claim, citation_bound_only=True):
                if record.retracted:
                    continue
                item = record.item; key = (item.source_id, item.locator)
                if key in seen: continue
                seen.add(key)
                rows.append(EvidenceRef(source=item.source_id[:1000], locator=item.locator[:2000],
                    confidence=effective_evidence_quality(item), observed_at=item.observed_at[:100]))
        return tuple(rows[:128])

    def _update_truth_states(self, decision: EpistemicDecision) -> None:
        for claim in decision.verified_claims:
            verification = decision.verification[claim]
            evidence_ids = [r.id for r in self.evidence_registry.records_for(claim, citation_bound_only=True) if not r.retracted]
            self.truth_ledger.record(claim=claim, verification_state="verified",
                verification_attestation_sha256=str(verification["attestation_sha256"]), evidence_record_ids=evidence_ids)
        all_nonverified = (*decision.provisional_claims, *decision.contradicted_claims,
                           *decision.unverified_claims, *decision.irrelevant_speculation)
        for claim in all_nonverified:
            if self.truth_ledger.get(claim) is not None:
                state = decision.verification.get(claim, {}).get("state", "unverified")
                self.truth_ledger.revoke(claim, f"latest verification state is {state}")
                self._revoke_dependents((claim,), f"upstream claim no longer authoritative: {claim}")

    def _resolve_calibration(self, claim: str, state: VerificationState, attestation: str) -> int:
        if state not in {VerificationState.VERIFIED, VerificationState.CONTRADICTED}:
            return 0
        outcome = state == VerificationState.VERIFIED; resolved = 0
        for forecast in self.calibration.snapshot():
            if forecast.claim == claim and forecast.outcome is None:
                self.calibration.resolve(forecast.id, outcome=outcome,
                    verification_attestation_sha256=attestation); resolved += 1
        return resolved

    def accept_finding(self, inquiry: Inquiry, finding: dict[str, Any]) -> KnowledgeRecord:
        if not isinstance(finding, dict): raise ValueError("research finding must be an object")
        self._register_lineage(finding)
        claims = tuple(" ".join(str(x).split()).strip() for x in (finding.get("claims") or ()) if str(x).strip())
        self._register_claim_dependencies(finding, claims)
        decision = self._apply_dependency_gate(self.epistemic_gate.evaluate(finding))
        self._update_truth_states(decision)
        for claim in decision.verified_claims:
            attestation = str(decision.verification.get(claim, {}).get("attestation_sha256") or "")
            if len(attestation) == 64: self._resolve_calibration(claim, VerificationState.VERIFIED, attestation)
        for claim in decision.contradicted_claims:
            attestation = str(decision.verification.get(claim, {}).get("attestation_sha256") or "")
            if len(attestation) == 64: self._resolve_calibration(claim, VerificationState.CONTRADICTED, attestation)
        gaps = list(self.epistemic_gate.hoag_gaps(decision)); gaps.extend(str(x) for x in (finding.get("questions") or ()) if str(x).strip())
        contradictions = [f"CONTRADICTION — {claim}" for claim in decision.contradicted_claims]
        verified_evidence = self._verified_evidence(decision); verified_count = len(decision.verified_claims); confidence = 0.0
        if verified_count:
            confidence = min(self.verifier.verify_claim(claim, self._active_evidence(claim),
                falsifiable=(finding.get("falsifiable") or {}).get(claim) if isinstance(finding.get("falsifiable"), dict) else None).mean_quality
                for claim in decision.verified_claims)
        previous = self.fabric.search(inquiry.subject, limit=12)
        previous_verified = {claim.casefold() for record in previous for claim in record.claims}
        novel_verified = sum(1 for claim in decision.verified_claims if claim.casefold() not in previous_verified)
        novelty = min(1.0, (novel_verified + len(gaps)) / max(1, verified_count + len(gaps) + 2))
        record = self.fabric.publish(subject=inquiry.subject,
            title=str(finding.get("title") or f"Verified curiosity brief: {inquiry.subject}"),
            summary=self._orientation_summary(decision), claims=decision.verified_claims,
            questions=tuple(dict.fromkeys(gaps)), contradictions=tuple(contradictions), evidence=verified_evidence,
            tags=tuple(inquiry.keywords) + ("truth-gated",), confidence=confidence, novelty=novelty,
            parent_prompt_id=inquiry.id, created_at=datetime.now(UTC).isoformat())
        with self._lease.acquire():
            topics = self._load_frontier(); raw = topics.get(inquiry.subject)
            if raw is not None:
                raw["research_count"] = int(raw.get("research_count", 0)) + 1
                raw["last_researched_at"] = datetime.now(UTC).isoformat(); raw["last_record_id"] = record.id
                raw["unresolved_count"] = len(gaps) + len(contradictions); topics[inquiry.subject] = raw; self._write_frontier(topics)
        return record

    def reverify_claim(self, claim: str) -> dict[str, Any]:
        evidence, independence = self.independence.collapse(self.evidence_registry.evidence_for(claim))
        result = self.verifier.verify_claim(claim, evidence)
        blockers = self.claim_dependencies.blockers(claim, self.truth_ledger.authoritative)
        evidence_ids = [r.id for r in self.evidence_registry.records_for(claim, citation_bound_only=True) if not r.retracted]
        effective_state = result.state.value; reasons = list(result.reasons)
        if result.state == VerificationState.VERIFIED and not blockers:
            self.truth_ledger.record(claim=claim, verification_state=result.state.value,
                verification_attestation_sha256=result.attestation_sha256, evidence_record_ids=evidence_ids)
        else:
            if blockers: effective_state = "dependency_blocked"; reasons.append("non_authoritative_dependency")
            if self.truth_ledger.get(claim) is not None:
                self.truth_ledger.revoke(claim, f"reverification state: {effective_state}; reasons={','.join(reasons)}")
            self._revoke_dependents((claim,), f"upstream claim no longer authoritative: {claim}")
        calibration_resolved = self._resolve_calibration(claim, result.state, result.attestation_sha256)
        contradiction = self.contradictions.resolve(claim, evidence)
        return {"claim": claim, "state": effective_state, "authoritative": self.truth_ledger.authoritative(claim),
            "reasons": list(dict.fromkeys(reasons)), "dependency_blockers": list(blockers),
            "verification_attestation_sha256": result.attestation_sha256,
            "calibration_forecasts_resolved": calibration_resolved,
            "independence": {"raw_sources": independence.raw_sources,
                "effective_independent_sources": independence.effective_independent_sources,
                "unresolved_sources": list(independence.unresolved_sources), "attestation_sha256": independence.attestation_sha256},
            "contradiction": {"state": contradiction.state, "required_actions": list(contradiction.required_actions),
                "attestation_sha256": contradiction.attestation_sha256}}

    def reverify_expired(self) -> dict[str, Any]:
        expired = self.truth_ledger.expired_claims(); results = [self.reverify_claim(claim) for claim in expired]
        return {"expired": len(expired), "reverified": results}

    def retract_source(self, source_id: str, reason: str, *, cascade: bool = True) -> dict[str, Any]:
        affected_sources = self.source_lineage.retract(source_id, reason, cascade=cascade)
        evidence = self.evidence_registry.retract_sources(affected_sources, f"source retraction: {source_id} — {reason}")
        results = [self.reverify_claim(claim) for claim in evidence["claims"]]
        dependent_claims = self._revoke_dependents(list(evidence["claims"]), f"upstream evidence retracted: {source_id}")
        return {"source_id": source_id, "affected_sources": list(affected_sources),
            "retracted_evidence_records": list(evidence["record_ids"]), "affected_claims": list(evidence["claims"]),
            "dependent_claims_revoked": list(dependent_claims), "reverification": results}

    def resolve_source_lineage(self, source_id: str, *, source_kind: str, locator: str = "",
                               parent_ids: tuple[str, ...] = (), content_sha256: str = "") -> dict[str, Any]:
        node = self.source_lineage.resolve_legacy(source_id, source_kind=source_kind, locator=locator,
                                                  parent_ids=parent_ids, content_sha256=content_sha256)
        affected_claims = tuple(sorted({record.claim for record in self.evidence_registry.records_for_sources(
            (source_id,), include_retracted=False, citation_bound_only=True)}))
        reverification = [self.reverify_claim(claim) for claim in affected_claims]
        return {"source": asdict(node), "affected_claims": list(affected_claims), "reverification": reverification}

    def contradiction_status(self, claim: str) -> dict[str, Any]:
        evidence, independence = self.independence.collapse(self.evidence_registry.evidence_for(claim))
        report = self.contradictions.resolve(claim, evidence)
        return {"claim": report.claim, "state": report.state, "support_groups": list(report.support_groups),
            "contradiction_groups": list(report.contradiction_groups), "support_quality": report.support_quality,
            "contradiction_quality": report.contradiction_quality, "methodological_conflict": report.methodological_conflict,
            "required_actions": list(report.required_actions), "attestation_sha256": report.attestation_sha256,
            "effective_independent_sources": independence.effective_independent_sources}

    def compare_claims(self, left: str, right: str) -> dict[str, Any]:
        return asdict(self.claim_identity.compare(left, right))

    def record_forecast(self, *, claim: str, probability: float, forecaster: str,
                        context_sha256: str = "", forecast_id: str | None = None) -> dict[str, Any]:
        return asdict(self.calibration.forecast(claim=claim, probability=probability, forecaster=forecaster,
                                                context_sha256=context_sha256, forecast_id=forecast_id))

    def orientation_pack(self, query: str, *, limit: int = 6) -> dict[str, Any]:
        self.reverify_expired(); records = self.fabric.search(query, limit=limit)
        active_claims: list[str] = []; unresolved: list[str] = []; record_ids: list[str] = []
        for record in records:
            record_ids.append(record.id)
            for claim in record.claims:
                if self.truth_ledger.authoritative(claim):
                    if claim not in active_claims: active_claims.append(claim)
                else:
                    marker = f"NON-AUTHORITATIVE / REVERIFY: {claim}"
                    if marker not in unresolved: unresolved.append(marker)
            for gap in (*record.contradictions, *record.questions):
                if gap not in unresolved: unresolved.append(gap)
        states = [self.truth_ledger.get(claim) for claim in active_claims]
        working = [f"Verified claims: {' '.join(active_claims[:12])}"] if active_claims else []
        confidences = [record.confidence for record in records if any(claim in active_claims for claim in record.claims)]
        return {"query": query, "record_ids": record_ids, "working_context": working, "claims": active_claims[:24],
            "unresolved": unresolved[:24], "confidence_floor": min(confidences, default=0.0),
            "truth_state_attestations": [x.verification_attestation_sha256 for x in states if x is not None]}

    def verification_status(self) -> dict[str, Any]:
        evidence = self.evidence_registry.stats(); knowledge = self.fabric.stats()
        return {"truth_gated": True, "speculation_authoritative": False,
            "model_consensus_is_empirical_evidence": False, "semantic_similarity_is_truth_identity": False,
            "evidence_registry": evidence, "source_lineage": self.source_lineage.stats(),
            "lineage_backfill": self._lineage_backfill, "truth_ledger": self.truth_ledger.stats(),
            "claim_dependencies": self.claim_dependencies.stats(),
            "calibration": {**self.calibration.stats(), "metrics": self.calibration.metrics()}, "knowledge": knowledge,
            "verification_policy": {"minimum_independent_support": self.verifier.policy.minimum_independent_support,
                "minimum_total_quality": self.verifier.policy.minimum_total_quality,
                "minimum_mean_quality": self.verifier.policy.minimum_mean_quality,
                "require_empirical_support": self.verifier.policy.require_empirical_support,
                "require_reproducibility_signal": self.verifier.policy.require_reproducibility_signal,
                "require_independent_replication_for_experiments": self.verifier.policy.require_independent_replication_for_experiments,
                "require_provenance_verified": self.verifier.policy.require_provenance_verified,
                "require_falsifiable_claim": self.verifier.policy.require_falsifiable_claim,
                "contradiction_blocks": self.verifier.policy.contradiction_blocks}}

    def stats(self) -> dict[str, Any]:
        stats = super().stats(); stats["verification"] = self.verification_status(); return stats
