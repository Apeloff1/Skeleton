"""High-assurance wrapper for the Jeeves semantic compiler/decompiler.

The base compiler already supplies typed SSA, CFG/dominance verification,
effect tracking, abstract interpretation, transactional pass rollback and a
bounded translation validator.  This module tightens the *promotion standard*:

* verifier-valid is necessary but never confused with semantic equivalence;
* a changed EXACT/REFINEMENT pass needs behavioral validation or matching
  external proof evidence -- structural-only validation is insufficient;
* provenance is checked by source atoms, not merely by counting how many target
  instructions still carry *some* provenance;
* provenance confidence loss is budgeted explicitly;
* side-effect deltas and UNKNOWN effects are audited;
* test-case coverage is recorded per function;
* external SMT/translation-validation results are fingerprint-bound;
* decompilation information loss is classified and policy-gated instead of
  pretending that recovered pseudocode is the original program.

The wrapper is fail closed: if assurance rejects a candidate, the returned
module is the original immutable source module even when the lower-level pass
manager would otherwise have committed the transform.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, FrozenSet, Mapping, Sequence, Tuple

from .decompiler import DecompilationArtifact, LossKind, RecoveryConfidence
from .ir import Effect, IRModule, SourceProvenance
from .pipeline import (
    CompilationPass,
    PassManager,
    PassRecord,
    PassSemantics,
    ValidationStatus,
)


class AssuranceError(RuntimeError):
    pass


class ObligationKind(str, Enum):
    STRUCTURAL_VALIDITY = "structural_validity"
    BEHAVIORAL_EQUIVALENCE = "behavioral_equivalence"
    REFINEMENT = "refinement"
    TEST_COVERAGE = "test_coverage"
    PROVENANCE_COVERAGE = "provenance_coverage"
    PROVENANCE_CONFIDENCE = "provenance_confidence"
    EFFECT_CONTAINMENT = "effect_containment"
    UNKNOWN_EFFECT_ABSENCE = "unknown_effect_absence"
    EXTERNAL_PROOF_BINDING = "external_proof_binding"
    DECOMPILATION_LOSS_BUDGET = "decompilation_loss_budget"


class ObligationStatus(str, Enum):
    SATISFIED = "satisfied"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"
    INCONCLUSIVE = "inconclusive"


class ExternalProofStatus(str, Enum):
    PROVED = "proved"
    REFUTED = "refuted"
    UNKNOWN = "unknown"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ExternalValidationEvidence:
    checker: str
    checker_version: str
    source_fingerprint: str
    target_fingerprint: str
    status: ExternalProofStatus
    property: str
    proof_artifact_hash: str | None = None
    assumptions: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.checker.strip() or not self.checker_version.strip():
            raise AssuranceError("external validation requires checker identity/version")
        if not self.source_fingerprint or not self.target_fingerprint:
            raise AssuranceError("external validation requires bound fingerprints")
        if not isinstance(self.status, ExternalProofStatus):
            object.__setattr__(self, "status", ExternalProofStatus(str(self.status)))
        if self.proof_artifact_hash is not None and len(self.proof_artifact_hash) < 16:
            raise AssuranceError("proof artifact hash is suspiciously short")

    @property
    def fingerprint(self) -> str:
        payload = {
            "checker": self.checker,
            "version": self.checker_version,
            "source": self.source_fingerprint,
            "target": self.target_fingerprint,
            "status": self.status.value,
            "property": self.property,
            "proof": self.proof_artifact_hash,
            "assumptions": list(self.assumptions),
            "metadata": dict(self.metadata),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def proves(self, source: IRModule, target: IRModule, *, property: str) -> bool:
        return (
            self.status is ExternalProofStatus.PROVED
            and self.source_fingerprint == source.fingerprint
            and self.target_fingerprint == target.fingerprint
            and self.property == property
        )


@dataclass(frozen=True, slots=True)
class ProvenanceAtom:
    artifact_id: str
    start: int | None
    end: int | None
    evidence_ids: Tuple[str, ...]

    @classmethod
    def from_provenance(cls, provenance: SourceProvenance) -> "ProvenanceAtom":
        return cls(
            provenance.artifact_id,
            provenance.start,
            provenance.end,
            tuple(sorted(provenance.evidence_ids)),
        )


@dataclass(frozen=True, slots=True)
class ProvenanceAudit:
    source_atoms: int
    covered_atoms: int
    coverage: float
    source_confidence_mass: float
    retained_confidence_mass: float
    confidence_retention: float
    missing_atoms: Tuple[ProvenanceAtom, ...]
    weakened_atoms: Tuple[Tuple[ProvenanceAtom, float, float], ...]


@dataclass(frozen=True, slots=True)
class EffectAudit:
    source_effects: FrozenSet[Effect]
    target_effects: FrozenSet[Effect]
    added: FrozenSet[Effect]
    removed: FrozenSet[Effect]
    contains_unknown: bool


@dataclass(frozen=True, slots=True)
class CoverageAudit:
    functions: Tuple[str, ...]
    tested_functions: Tuple[str, ...]
    untested_parameterized_functions: Tuple[str, ...]
    total_cases: int
    per_function_cases: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class AssuranceObligation:
    kind: ObligationKind
    status: ObligationStatus
    message: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AssuranceCertificate:
    pass_id: str
    source_fingerprint: str
    candidate_fingerprint: str | None
    committed_fingerprint: str
    accepted: bool
    base_record_fingerprint: str
    obligations: Tuple[AssuranceObligation, ...]
    provenance: ProvenanceAudit | None
    effects: EffectAudit | None
    coverage: CoverageAudit | None
    external_evidence_fingerprints: Tuple[str, ...]
    certificate_fingerprint: str

    @property
    def failures(self) -> Tuple[AssuranceObligation, ...]:
        return tuple(item for item in self.obligations if item.status is ObligationStatus.FAILED)


@dataclass(frozen=True, slots=True)
class CompilerAssurancePolicy:
    require_behavioral_validation_for_changed_exact: bool = True
    require_behavioral_validation_for_changed_refinement: bool = True
    minimum_cases_per_parameterized_function: int = 1
    minimum_provenance_coverage: float = 1.0
    minimum_provenance_confidence_retention: float = 0.98
    reject_unknown_effect: bool = True
    allow_external_proof_substitution: bool = True

    def __post_init__(self) -> None:
        if self.minimum_cases_per_parameterized_function < 0:
            raise AssuranceError("minimum cases cannot be negative")
        for name in ("minimum_provenance_coverage", "minimum_provenance_confidence_retention"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise AssuranceError(name + " must lie in [0,1]")


class CompilerAssuranceEngine:
    def __init__(self, policy: CompilerAssurancePolicy | None = None) -> None:
        self.policy = policy or CompilerAssurancePolicy()

    @staticmethod
    def _provenance_map(module: IRModule) -> Mapping[ProvenanceAtom, float]:
        atoms: dict[ProvenanceAtom, float] = {}
        for function in module.functions:
            for block in function.blocks:
                for instruction in block.instructions:
                    for provenance in instruction.provenance:
                        atom = ProvenanceAtom.from_provenance(provenance)
                        atoms[atom] = max(atoms.get(atom, 0.0), float(provenance.confidence))
                for provenance in block.terminator.provenance:
                    atom = ProvenanceAtom.from_provenance(provenance)
                    atoms[atom] = max(atoms.get(atom, 0.0), float(provenance.confidence))
        return atoms

    def provenance_audit(self, source: IRModule, target: IRModule) -> ProvenanceAudit:
        old = self._provenance_map(source)
        new = self._provenance_map(target)
        missing = tuple(sorted((atom for atom in old if atom not in new), key=repr))
        covered = len(old) - len(missing)
        coverage = 1.0 if not old else covered / len(old)
        source_mass = sum(old.values())
        retained_mass = sum(min(confidence, new.get(atom, 0.0)) for atom, confidence in old.items())
        retention = 1.0 if source_mass <= 0 else retained_mass / source_mass
        weakened = tuple(
            sorted(
                (
                    (atom, confidence, new.get(atom, 0.0))
                    for atom, confidence in old.items()
                    if atom in new and new[atom] + 1e-12 < confidence
                ),
                key=lambda item: repr(item[0]),
            )
        )
        return ProvenanceAudit(
            source_atoms=len(old),
            covered_atoms=covered,
            coverage=coverage,
            source_confidence_mass=source_mass,
            retained_confidence_mass=retained_mass,
            confidence_retention=retention,
            missing_atoms=missing,
            weakened_atoms=weakened,
        )

    @staticmethod
    def effect_audit(source: IRModule, target: IRModule) -> EffectAudit:
        def effects(module: IRModule) -> FrozenSet[Effect]:
            values: set[Effect] = set()
            for function in module.functions:
                values.update(effect for effect in function.declared_effects if effect is not Effect.PURE)
                for block in function.blocks:
                    for instruction in block.instructions:
                        values.update(effect for effect in instruction.effects if effect is not Effect.PURE)
            return frozenset(values)

        source_effects = effects(source)
        target_effects = effects(target)
        return EffectAudit(
            source_effects=source_effects,
            target_effects=target_effects,
            added=frozenset(target_effects - source_effects),
            removed=frozenset(source_effects - target_effects),
            contains_unknown=Effect.UNKNOWN in target_effects,
        )

    def coverage_audit(
        self,
        module: IRModule,
        validation_cases: Mapping[str, Sequence[Sequence[Any]]],
    ) -> CoverageAudit:
        per_function = {function.name: len(tuple(validation_cases.get(function.name, ()))) for function in module.functions}
        untested = tuple(
            sorted(
                function.name
                for function in module.functions
                if function.parameters
                and per_function[function.name] < self.policy.minimum_cases_per_parameterized_function
            )
        )
        return CoverageAudit(
            functions=tuple(sorted(per_function)),
            tested_functions=tuple(sorted(name for name, count in per_function.items() if count > 0)),
            untested_parameterized_functions=untested,
            total_cases=sum(per_function.values()),
            per_function_cases=per_function,
        )

    @staticmethod
    def _external_proves(
        source: IRModule,
        target: IRModule,
        semantics: PassSemantics,
        evidence: Sequence[ExternalValidationEvidence],
    ) -> bool:
        property_name = "equivalence" if semantics is PassSemantics.EXACT else "refinement"
        return any(item.proves(source, target, property=property_name) for item in evidence)

    def certify(
        self,
        source: IRModule,
        candidate: IRModule,
        compiler_pass: CompilationPass,
        base_record: PassRecord,
        *,
        validation_cases: Mapping[str, Sequence[Sequence[Any]]],
        external_evidence: Sequence[ExternalValidationEvidence] = (),
    ) -> Tuple[bool, Tuple[AssuranceObligation, ...], ProvenanceAudit, EffectAudit, CoverageAudit]:
        obligations: list[AssuranceObligation] = []
        changed = source.fingerprint != candidate.fingerprint
        contract = compiler_pass.contract
        output_valid = bool(base_record.output_verification and base_record.output_verification.valid)
        obligations.append(
            AssuranceObligation(
                ObligationKind.STRUCTURAL_VALIDITY,
                ObligationStatus.SATISFIED if output_valid else ObligationStatus.FAILED,
                "candidate IR is verifier-valid" if output_valid else "candidate IR failed structural verification",
            )
        )

        coverage = self.coverage_audit(source, validation_cases)
        enough_cases = not coverage.untested_parameterized_functions
        obligations.append(
            AssuranceObligation(
                ObligationKind.TEST_COVERAGE,
                ObligationStatus.SATISFIED if enough_cases else ObligationStatus.FAILED,
                "validation observations cover parameterized functions" if enough_cases else "parameterized functions lack validation observations",
                {"untested": coverage.untested_parameterized_functions, "total_cases": coverage.total_cases},
            )
        )

        external_proof = self._external_proves(source, candidate, contract.semantics, external_evidence)
        bounded_validated = bool(
            base_record.validation is not None
            and base_record.validation.status is ValidationStatus.VALIDATED
            and base_record.validation.tested_cases > 0
        )
        needs_behavior = changed and (
            (contract.semantics is PassSemantics.EXACT and self.policy.require_behavioral_validation_for_changed_exact)
            or (contract.semantics is PassSemantics.REFINEMENT and self.policy.require_behavioral_validation_for_changed_refinement)
        )
        behavior_ok = (not needs_behavior) or bounded_validated or (
            self.policy.allow_external_proof_substitution and external_proof
        )
        kind = ObligationKind.BEHAVIORAL_EQUIVALENCE if contract.semantics is PassSemantics.EXACT else ObligationKind.REFINEMENT
        obligations.append(
            AssuranceObligation(
                kind,
                ObligationStatus.SATISFIED if behavior_ok else ObligationStatus.FAILED,
                "semantic obligation has validation evidence" if behavior_ok else "changed exact/refinement candidate lacks accepted behavioral/proof evidence",
                {
                    "changed": changed,
                    "bounded_validated": bounded_validated,
                    "external_proof": external_proof,
                    "base_validation": base_record.validation.status.value if base_record.validation else None,
                    "tested_cases": base_record.validation.tested_cases if base_record.validation else 0,
                },
            )
        )

        provenance = self.provenance_audit(source, candidate)
        obligations.append(
            AssuranceObligation(
                ObligationKind.PROVENANCE_COVERAGE,
                ObligationStatus.SATISFIED if provenance.coverage + 1e-12 >= self.policy.minimum_provenance_coverage else ObligationStatus.FAILED,
                "source provenance atoms are retained" if provenance.coverage + 1e-12 >= self.policy.minimum_provenance_coverage else "candidate lost source provenance atoms",
                {"coverage": provenance.coverage, "missing": len(provenance.missing_atoms)},
            )
        )
        obligations.append(
            AssuranceObligation(
                ObligationKind.PROVENANCE_CONFIDENCE,
                ObligationStatus.SATISFIED if provenance.confidence_retention + 1e-12 >= self.policy.minimum_provenance_confidence_retention else ObligationStatus.FAILED,
                "provenance confidence remains within budget" if provenance.confidence_retention + 1e-12 >= self.policy.minimum_provenance_confidence_retention else "provenance confidence degraded beyond budget",
                {"confidence_retention": provenance.confidence_retention, "weakened": len(provenance.weakened_atoms)},
            )
        )

        effects = self.effect_audit(source, candidate)
        allowed = set(contract.allowed_new_effects)
        unexpected = set(effects.added) - allowed
        obligations.append(
            AssuranceObligation(
                ObligationKind.EFFECT_CONTAINMENT,
                ObligationStatus.SATISFIED if not unexpected else ObligationStatus.FAILED,
                "effect delta is permitted" if not unexpected else "candidate adds effects outside pass contract",
                {"added": tuple(sorted(effect.value for effect in effects.added)), "unexpected": tuple(sorted(effect.value for effect in unexpected))},
            )
        )
        unknown_ok = not self.policy.reject_unknown_effect or not effects.contains_unknown
        obligations.append(
            AssuranceObligation(
                ObligationKind.UNKNOWN_EFFECT_ABSENCE,
                ObligationStatus.SATISFIED if unknown_ok else ObligationStatus.FAILED,
                "target contains no forbidden UNKNOWN effect" if unknown_ok else "target contains UNKNOWN effect",
            )
        )

        if external_evidence:
            all_bound = all(
                item.source_fingerprint == source.fingerprint and item.target_fingerprint == candidate.fingerprint
                for item in external_evidence
            )
            obligations.append(
                AssuranceObligation(
                    ObligationKind.EXTERNAL_PROOF_BINDING,
                    ObligationStatus.SATISFIED if all_bound else ObligationStatus.FAILED,
                    "external proof evidence is fingerprint-bound" if all_bound else "external evidence references a different source/target pair",
                )
            )

        accepted = base_record.committed and not any(item.status is ObligationStatus.FAILED for item in obligations)
        return accepted, tuple(obligations), provenance, effects, coverage


class AssuredPassManager:
    """Production-facing pass manager with a stricter commit boundary."""

    def __init__(
        self,
        *,
        base: PassManager | None = None,
        assurance: CompilerAssuranceEngine | None = None,
    ) -> None:
        self.base = base or PassManager()
        self.assurance = assurance or CompilerAssuranceEngine()

    def run_pass(
        self,
        module: IRModule,
        compiler_pass: CompilationPass,
        *,
        validation_cases: Mapping[str, Sequence[Sequence[Any]]] = {},
        external_evidence: Sequence[ExternalValidationEvidence] = (),
    ) -> Tuple[IRModule, AssuranceCertificate, PassRecord]:
        candidate, base_record = self.base.run_pass(
            module,
            compiler_pass,
            validation_cases=validation_cases,
        )
        # If the base manager rejected, it already returned ``module`` and there
        # is no candidate to promote.  Preserve that result and still emit an
        # auditable certificate.
        candidate_for_audit = candidate
        accepted, obligations, provenance, effects, coverage = self.assurance.certify(
            module,
            candidate_for_audit,
            compiler_pass,
            base_record,
            validation_cases=validation_cases,
            external_evidence=external_evidence,
        )
        result = candidate_for_audit if accepted else module
        payload = {
            "pass": compiler_pass.contract.pass_id,
            "source": module.fingerprint,
            "candidate": base_record.candidate_fingerprint,
            "committed": result.fingerprint,
            "accepted": accepted,
            "base_record": base_record.fingerprint,
            "obligations": [(item.kind.value, item.status.value, item.message, dict(item.metadata)) for item in obligations],
            "external": [item.fingerprint for item in external_evidence],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        certificate = AssuranceCertificate(
            pass_id=compiler_pass.contract.pass_id,
            source_fingerprint=module.fingerprint,
            candidate_fingerprint=base_record.candidate_fingerprint,
            committed_fingerprint=result.fingerprint,
            accepted=accepted,
            base_record_fingerprint=base_record.fingerprint,
            obligations=obligations,
            provenance=provenance,
            effects=effects,
            coverage=coverage,
            external_evidence_fingerprints=tuple(item.fingerprint for item in external_evidence),
            certificate_fingerprint=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        )
        return result, certificate, base_record


@dataclass(frozen=True, slots=True)
class DecompilationAssurancePolicy:
    require_structurally_valid_ir: bool = True
    reject_exact_source_recovery_claim: bool = True
    maximum_weighted_loss: float = 8.0
    forbidden_losses: FrozenSet[LossKind] = frozenset()

    def __post_init__(self) -> None:
        if self.maximum_weighted_loss < 0:
            raise AssuranceError("maximum_weighted_loss must be non-negative")


@dataclass(frozen=True, slots=True)
class DecompilationAssuranceReport:
    accepted: bool
    weighted_loss: float
    losses_by_kind: Mapping[str, int]
    forbidden_present: Tuple[str, ...]
    unknown_or_low_confidence_types: Tuple[str, ...]
    reasons: Tuple[str, ...]
    artifact_fingerprint: str
    report_fingerprint: str


class DecompilationAssurance:
    """Quantify reconstruction loss without pretending loss is probability."""

    LOSS_WEIGHTS: Mapping[LossKind, float] = {
        LossKind.SOURCE_NAME: 0.5,
        LossKind.SOURCE_TYPE: 1.5,
        LossKind.SOURCE_SPAN: 0.75,
        LossKind.CONTROL_STRUCTURE: 1.0,
        LossKind.ALIASING: 2.0,
        LossKind.OPTIMIZATION_HISTORY: 0.75,
        LossKind.PROVENANCE: 3.0,
        LossKind.UNSUPPORTED_SEMANTICS: 4.0,
        LossKind.NONDETERMINISM: 3.0,
        LossKind.REPLAY: 3.0,
        LossKind.UNDEFINED_BEHAVIOR: 4.0,
        LossKind.ASSUMPTION: 2.0,
        LossKind.SAFETY_CONTRACT: 4.0,
        LossKind.DEBUG_INFORMATION: 0.5,
    }

    def __init__(self, policy: DecompilationAssurancePolicy | None = None) -> None:
        self.policy = policy or DecompilationAssurancePolicy()

    def audit(self, artifact: DecompilationArtifact) -> DecompilationAssuranceReport:
        counts: dict[str, int] = {}
        weighted = 0.0
        for loss in artifact.losses:
            counts[loss.kind.value] = counts.get(loss.kind.value, 0) + 1
            weighted += self.LOSS_WEIGHTS.get(loss.kind, 1.0)
        forbidden = tuple(sorted(kind.value for kind in self.policy.forbidden_losses if counts.get(kind.value, 0)))
        uncertain_types = tuple(
            sorted(
                item.value_id
                for item in artifact.recovered_types
                if item.confidence in {RecoveryConfidence.LOW, RecoveryConfidence.UNKNOWN}
            )
        )
        reasons: list[str] = []
        if self.policy.require_structurally_valid_ir and not artifact.structurally_valid_source:
            reasons.append("source IR is structurally invalid")
        if self.policy.reject_exact_source_recovery_claim and artifact.exact_source_recovery_claimed:
            reasons.append("decompiler claimed exact source recovery")
        if weighted > self.policy.maximum_weighted_loss:
            reasons.append("weighted information loss exceeds policy")
        if forbidden:
            reasons.append("forbidden information-loss kinds are present")
        payload = {
            "artifact": artifact.fingerprint,
            "weighted_loss": weighted,
            "counts": counts,
            "forbidden": forbidden,
            "uncertain_types": uncertain_types,
            "reasons": reasons,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return DecompilationAssuranceReport(
            accepted=not reasons,
            weighted_loss=weighted,
            losses_by_kind=counts,
            forbidden_present=forbidden,
            unknown_or_low_confidence_types=uncertain_types,
            reasons=tuple(reasons),
            artifact_fingerprint=artifact.fingerprint,
            report_fingerprint=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        )
