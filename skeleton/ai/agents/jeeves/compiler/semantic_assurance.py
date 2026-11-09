"""Semantic promotion gate layered over the Jeeves assured compiler.

Structural validity and bounded behavioral validation are necessary but do not
fully protect machine-level semantics.  This module audits explicit semantic
contracts before and after an already-assured pass, rejects risk-surface
escalation, and blocks silent contract mutation for the same provenance/opcode.

The wrapper is transactional: any semantic failure returns the original module.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence, Tuple

from .assurance import (
    AssuranceCertificate,
    AssuredPassManager,
    ExternalValidationEvidence,
)
from .ir import IRModule
from .pipeline import CompilationPass, PassRecord
from .semantics import ModuleSemanticAuditor, SemanticAuditReport, SemanticFact


class SemanticObligationStatus(str, Enum):
    SATISFIED = "satisfied"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class SemanticObligationKind(str, Enum):
    SOURCE_CONTRACTS = "source_contracts"
    CANDIDATE_CONTRACTS = "candidate_contracts"
    CONTRACT_PROVENANCE = "contract_provenance"
    NO_RISK_ESCALATION = "no_risk_escalation"
    NO_SILENT_CONTRACT_MUTATION = "no_silent_contract_mutation"
    BASE_ASSURANCE = "base_assurance"


@dataclass(frozen=True, slots=True)
class SemanticPassObligation:
    kind: SemanticObligationKind
    status: SemanticObligationStatus
    message: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class SemanticPassPolicy:
    require_valid_source: bool = True
    require_valid_candidate: bool = True
    require_contract_provenance: bool = True
    reject_risk_escalation: bool = True
    allow_silent_contract_change: bool = False


@dataclass(frozen=True, slots=True)
class SemanticPassCertificate:
    pass_id: str
    source_fingerprint: str
    base_committed_fingerprint: str
    final_fingerprint: str
    accepted: bool
    base_certificate_fingerprint: str
    source_semantic_fingerprint: str
    candidate_semantic_fingerprint: str
    obligations: Tuple[SemanticPassObligation, ...]
    certificate_fingerprint: str


_RISK_FIELDS = (
    "unknown_alias_accesses",
    "undefined_integer_ops",
    "poison_integer_ops",
    "fast_math_ops",
    "assume_no_nan_ops",
    "external_nondeterministic_ops",
    "schedule_nondeterministic_ops",
    "unknown_semantics",
)


def _fact_key(fact: SemanticFact) -> tuple[Tuple[str, ...], str]:
    return fact.provenance_atoms, fact.opcode


def _contract_json(fact: SemanticFact) -> str:
    return json.dumps(fact.contract.as_json(), sort_keys=True, separators=(",", ":"))


class SemanticAssuredPassManager:
    """Add machine-semantics promotion obligations after base assurance."""

    def __init__(
        self,
        *,
        base: AssuredPassManager | None = None,
        auditor: ModuleSemanticAuditor | None = None,
        policy: SemanticPassPolicy | None = None,
    ) -> None:
        self.base = base or AssuredPassManager()
        self.auditor = auditor or ModuleSemanticAuditor()
        self.policy = policy or SemanticPassPolicy()

    @staticmethod
    def _risk_delta(source: SemanticAuditReport, candidate: SemanticAuditReport) -> Mapping[str, int]:
        return {
            field: int(getattr(candidate.risk, field)) - int(getattr(source.risk, field))
            for field in _RISK_FIELDS
        }

    @staticmethod
    def _unprovenanced_facts(report: SemanticAuditReport) -> Tuple[str, ...]:
        return tuple(
            sorted(
                fact.fingerprint
                for fact in report.facts
                if not fact.provenance_atoms
            )
        )

    @staticmethod
    def _silent_mutations(
        source: SemanticAuditReport,
        candidate: SemanticAuditReport,
    ) -> Tuple[Mapping[str, Any], ...]:
        source_groups: dict[tuple[Tuple[str, ...], str], set[str]] = {}
        candidate_groups: dict[tuple[Tuple[str, ...], str], set[str]] = {}
        for fact in source.facts:
            if not fact.provenance_atoms:
                continue
            source_groups.setdefault(_fact_key(fact), set()).add(_contract_json(fact))
        for fact in candidate.facts:
            if not fact.provenance_atoms:
                continue
            candidate_groups.setdefault(_fact_key(fact), set()).add(_contract_json(fact))

        mutations = []
        for key in sorted(set(source_groups).intersection(candidate_groups), key=str):
            before = source_groups[key]
            after = candidate_groups[key]
            if before == after:
                continue
            mutations.append(
                {
                    "provenance_atoms": key[0],
                    "opcode": key[1],
                    "source_contracts": tuple(sorted(before)),
                    "candidate_contracts": tuple(sorted(after)),
                }
            )
        return tuple(mutations)

    def run_pass(
        self,
        module: IRModule,
        compiler_pass: CompilationPass,
        *,
        validation_cases: Mapping[str, Sequence[Sequence[Any]]] = {},
        external_evidence: Sequence[ExternalValidationEvidence] = (),
    ) -> Tuple[IRModule, SemanticPassCertificate, AssuranceCertificate, PassRecord]:
        source_audit = self.auditor.audit(module)
        base_result, base_certificate, base_record = self.base.run_pass(
            module,
            compiler_pass,
            validation_cases=validation_cases,
            external_evidence=external_evidence,
        )
        candidate_audit = self.auditor.audit(base_result)
        obligations: list[SemanticPassObligation] = []

        source_ok = source_audit.valid or not self.policy.require_valid_source
        obligations.append(
            SemanticPassObligation(
                SemanticObligationKind.SOURCE_CONTRACTS,
                SemanticObligationStatus.SATISFIED if source_ok else SemanticObligationStatus.FAILED,
                "source machine-semantics contracts are valid" if source_ok else "source has unresolved machine-semantics obligations",
                {"diagnostic_count": len(source_audit.diagnostics)},
            )
        )

        base_ok = bool(base_certificate.accepted)
        obligations.append(
            SemanticPassObligation(
                SemanticObligationKind.BASE_ASSURANCE,
                SemanticObligationStatus.SATISFIED if base_ok else SemanticObligationStatus.FAILED,
                "base compiler assurance accepted the candidate" if base_ok else "base compiler assurance rejected the candidate",
                {"base_certificate": base_certificate.certificate_fingerprint},
            )
        )

        candidate_ok = candidate_audit.valid or not self.policy.require_valid_candidate
        obligations.append(
            SemanticPassObligation(
                SemanticObligationKind.CANDIDATE_CONTRACTS,
                SemanticObligationStatus.SATISFIED if candidate_ok else SemanticObligationStatus.FAILED,
                "candidate machine-semantics contracts are valid" if candidate_ok else "candidate has unresolved machine-semantics obligations",
                {"diagnostic_count": len(candidate_audit.diagnostics)},
            )
        )

        unprovenanced = self._unprovenanced_facts(candidate_audit)
        provenance_ok = not self.policy.require_contract_provenance or not unprovenanced
        obligations.append(
            SemanticPassObligation(
                SemanticObligationKind.CONTRACT_PROVENANCE,
                SemanticObligationStatus.SATISFIED if provenance_ok else SemanticObligationStatus.FAILED,
                "semantic contracts retain source provenance" if provenance_ok else "candidate semantic contracts lack source provenance",
                {"unprovenanced": unprovenanced[:32], "count": len(unprovenanced)},
            )
        )

        risk_delta = self._risk_delta(source_audit, candidate_audit)
        escalated = {key: value for key, value in risk_delta.items() if value > 0}
        risk_ok = not self.policy.reject_risk_escalation or not escalated
        obligations.append(
            SemanticPassObligation(
                SemanticObligationKind.NO_RISK_ESCALATION,
                SemanticObligationStatus.SATISFIED if risk_ok else SemanticObligationStatus.FAILED,
                "candidate does not increase forbidden semantic risk" if risk_ok else "candidate increases semantic risk surface",
                {"delta": dict(risk_delta), "escalated": escalated},
            )
        )

        mutations = self._silent_mutations(source_audit, candidate_audit)
        mutation_ok = self.policy.allow_silent_contract_change or not mutations
        obligations.append(
            SemanticPassObligation(
                SemanticObligationKind.NO_SILENT_CONTRACT_MUTATION,
                SemanticObligationStatus.SATISFIED if mutation_ok else SemanticObligationStatus.FAILED,
                "provenance-bound contracts are stable" if mutation_ok else "pass silently changed a provenance-bound semantic contract",
                {"mutations": mutations[:32], "count": len(mutations)},
            )
        )

        accepted = base_ok and not any(
            obligation.status is SemanticObligationStatus.FAILED for obligation in obligations
        )
        final = base_result if accepted else module
        payload = {
            "pass": compiler_pass.contract.pass_id,
            "source": module.fingerprint,
            "base_committed": base_result.fingerprint,
            "final": final.fingerprint,
            "accepted": accepted,
            "base_certificate": base_certificate.certificate_fingerprint,
            "source_semantics": source_audit.semantic_fingerprint,
            "candidate_semantics": candidate_audit.semantic_fingerprint,
            "obligations": [
                (item.kind.value, item.status.value, item.message, dict(item.metadata))
                for item in obligations
            ],
        }
        certificate_fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        certificate = SemanticPassCertificate(
            pass_id=compiler_pass.contract.pass_id,
            source_fingerprint=module.fingerprint,
            base_committed_fingerprint=base_result.fingerprint,
            final_fingerprint=final.fingerprint,
            accepted=accepted,
            base_certificate_fingerprint=base_certificate.certificate_fingerprint,
            source_semantic_fingerprint=source_audit.semantic_fingerprint,
            candidate_semantic_fingerprint=candidate_audit.semantic_fingerprint,
            obligations=tuple(obligations),
            certificate_fingerprint=certificate_fingerprint,
        )
        return final, certificate, base_certificate, base_record