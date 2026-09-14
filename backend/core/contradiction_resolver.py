"""Strict contradiction analysis for empirical claims.

A numerical evidence majority is not truth. When active empirical sources support
and contradict the same claim, the claim remains contested. This engine produces
a deterministic resolution plan and attestation; it never promotes a claim merely
because one side has more votes or higher caller-supplied confidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Iterable

from core.truth_verifier import EvidenceItem, EvidenceKind, effective_evidence_quality


_EMPIRICAL = {
    EvidenceKind.PRIMARY_EMPIRICAL, EvidenceKind.REPLICATION,
    EvidenceKind.SYSTEMATIC_REVIEW, EvidenceKind.OFFICIAL_DATA,
    EvidenceKind.PRIMARY_DOCUMENT, EvidenceKind.DIRECT_OBSERVATION,
}


@dataclass(frozen=True, slots=True)
class ContradictionResolution:
    claim: str
    state: str
    support_groups: tuple[str, ...]
    contradiction_groups: tuple[str, ...]
    support_quality: float
    contradiction_quality: float
    methodological_conflict: bool
    required_actions: tuple[str, ...]
    attestation_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class ContradictionResolver:
    def resolve(self, claim: str, evidence: Iterable[EvidenceItem]) -> ContradictionResolution:
        claim = " ".join(str(claim).split()).strip()
        if not claim: raise ValueError("claim cannot be blank")
        empirical = [x for x in evidence if x.kind in _EMPIRICAL and x.provenance_verified]
        support = [x for x in empirical if x.supports]
        oppose = [x for x in empirical if not x.supports]
        support_groups = tuple(sorted({x.independence_group for x in support if x.independence_group}))
        oppose_groups = tuple(sorted({x.independence_group for x in oppose if x.independence_group}))
        support_quality = round(sum(effective_evidence_quality(x) for x in support), 6)
        oppose_quality = round(sum(effective_evidence_quality(x) for x in oppose), 6)

        actions: list[str] = []
        methodological_conflict = bool(support_groups and oppose_groups)
        if methodological_conflict:
            state = "contested"
            actions += [
                "Do not expose the claim as authoritative while active empirical contradiction remains.",
                "Audit whether opposing sources share hidden dependencies, datasets, instruments, or analysis pipelines.",
                "Compare preregistration, sampling, measurement definitions, uncertainty treatment, exclusions, and statistical methods.",
                "Seek independent replication designed specifically to discriminate between the competing empirical results.",
            ]
        elif support_groups:
            state = "support_only"
            if len(support_groups) < 2:
                actions.append("Obtain independent empirical support before verification.")
            if not any(x.kind == EvidenceKind.REPLICATION for x in support):
                actions.append("Obtain an independent replication before treating an experimental claim as verified.")
        elif oppose_groups:
            state = "refutation_only"
            actions.append("Treat the original claim as unsupported; preserve the refuting evidence and re-evaluate any dependent claims.")
        else:
            state = "insufficient_evidence"
            actions.append("Acquire provenance-verified empirical evidence before evaluating the claim.")

        payload = {
            "claim": claim, "state": state, "support_groups": support_groups,
            "contradiction_groups": oppose_groups, "support_quality": support_quality,
            "contradiction_quality": oppose_quality, "methodological_conflict": methodological_conflict,
            "required_actions": tuple(actions),
        }
        return ContradictionResolution(
            claim=claim, state=state, support_groups=support_groups, contradiction_groups=oppose_groups,
            support_quality=support_quality, contradiction_quality=oppose_quality,
            methodological_conflict=methodological_conflict, required_actions=tuple(actions),
            attestation_sha256=_sha(payload),
        )

    @staticmethod
    def verify(report: ContradictionResolution) -> bool:
        payload = asdict(report); digest = payload.pop("attestation_sha256")
        return _sha(payload) == digest
