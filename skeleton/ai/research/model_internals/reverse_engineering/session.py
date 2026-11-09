"""High-level governed reverse-engineering session orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .contracts import AuthorizationScope, EvidenceBundle, InferenceClaim, ProbeCase, stable_digest
from .fingerprint import BehavioralFingerprint, fingerprint_bundle
from .inference import infer_architecture
from .probes import FeatureExtractor, ProbeRunner, Target


@dataclass(frozen=True)
class SessionReport:
    target_id: str
    evidence: EvidenceBundle
    fingerprint: BehavioralFingerprint
    claims: tuple[InferenceClaim, ...]
    report_digest: str

    @property
    def supported_claims(self) -> tuple[InferenceClaim, ...]:
        return tuple(claim for claim in self.claims if claim.status == "supported")

    @property
    def promotable_claims(self) -> tuple[InferenceClaim, ...]:
        return tuple(claim for claim in self.claims if claim.promotable)


@dataclass(frozen=True)
class ReverseEngineeringSession:
    authorization: AuthorizationScope
    feature_extractors: tuple[FeatureExtractor, ...] = ()

    def inspect(
        self,
        *,
        target_id: str,
        target: Target,
        probes: Sequence[ProbeCase],
        repeats: int = 1,
    ) -> SessionReport:
        runner = ProbeRunner(
            authorization=self.authorization,
            feature_extractors=self.feature_extractors,
        )
        evidence = runner.run(
            target_id=target_id,
            target=target,
            probes=probes,
            repeats=repeats,
        )
        fingerprint = fingerprint_bundle(evidence)
        claims = infer_architecture(evidence)
        digest = stable_digest(
            {
                "target_id": target_id,
                "evidence_digest": evidence.digest,
                "fingerprint_digest": fingerprint.digest,
                "claims": [
                    {
                        "claim_id": claim.claim_id,
                        "confidence": claim.confidence,
                        "status": claim.status,
                        "evidence_probe_ids": list(claim.evidence_probe_ids),
                    }
                    for claim in claims
                ],
            }
        )
        return SessionReport(
            target_id=target_id,
            evidence=evidence,
            fingerprint=fingerprint,
            claims=claims,
            report_digest=digest,
        )
