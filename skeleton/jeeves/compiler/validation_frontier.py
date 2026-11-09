"""Independent, adversarial validation consensus for Jeeves compilation.

The existing compiler is deliberately fail-closed and already provides typed
SSA, structural verification, abstract interpretation, bounded differential
execution and external proof binding. This module answers a different question:

    How much *independent* evidence supports a source -> target transform?

It prevents assurance inflation. Five variants of the same checker do not count
as five independent confirmations. Evidence is fingerprint-bound, grouped by an
explicit methodological independence group, contradiction is dominant, and
bounded execution is never relabeled as proof.

The consensus layer is intentionally checker-agnostic. It can ingest internal
Jeeves checks and external SMT/backend validators without claiming that any
individual checker is infallible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .ir import IRModule, IRVerifier
from .pipeline import (
    PassSemantics,
    SemanticExecutor,
    TranslationValidator,
    UnsupportedSemantics,
    ValidationStatus,
)


class ValidationFrontierError(RuntimeError):
    pass


class ValidatorKind(str, Enum):
    STRUCTURAL = "structural"
    ABSTRACT_INTERPRETATION = "abstract_interpretation"
    DIFFERENTIAL_EXECUTION = "differential_execution"
    METAMORPHIC = "metamorphic"
    EXTERNAL_SMT = "external_smt"
    EXTERNAL_BACKEND = "external_backend"
    PROOF_ASSISTANT = "proof_assistant"
    DECOMPILATION_AUDIT = "decompilation_audit"
    DECOMPILATION_ROUNDTRIP = "decompilation_roundtrip"
    EFFECT_AUDIT = "effect_audit"
    PROVENANCE_AUDIT = "provenance_audit"


class ValidationVerdict(str, Enum):
    SUPPORTS = "supports"
    REFUTES = "refutes"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"
    ERROR = "error"


class AssuranceConsensusStatus(str, Enum):
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"
    SINGLE_METHOD = "single_method"
    MULTIMETHOD = "multimethod"
    HIGH_ASSURANCE = "high_assurance"
    EXTERNALLY_PROVED = "externally_proved"


@dataclass(frozen=True, slots=True)
class ValidationEvidence:
    evidence_id: str
    kind: ValidatorKind
    checker: str
    checker_version: str
    independence_group: str
    source_fingerprint: str
    target_fingerprint: str
    property: str
    verdict: ValidationVerdict
    tested_cases: int = 0
    coverage: float | None = None
    assumptions: tuple[str, ...] = ()
    counterexamples: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    artifact_hash: str | None = None
    machine_checked: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "evidence_id",
            "checker",
            "checker_version",
            "independence_group",
            "source_fingerprint",
            "target_fingerprint",
            "property",
        ):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValidationFrontierError(f"{name} is required")
            object.__setattr__(
                self,
                name,
                value.casefold() if name == "independence_group" else value,
            )
        if not isinstance(self.kind, ValidatorKind):
            object.__setattr__(self, "kind", ValidatorKind(str(self.kind)))
        if not isinstance(self.verdict, ValidationVerdict):
            object.__setattr__(self, "verdict", ValidationVerdict(str(self.verdict)))
        if (
            isinstance(self.tested_cases, bool)
            or not isinstance(self.tested_cases, int)
            or self.tested_cases < 0
        ):
            raise ValidationFrontierError("tested_cases must be non-negative integer")
        if self.coverage is not None:
            coverage = float(self.coverage)
            if not 0.0 <= coverage <= 1.0:
                raise ValidationFrontierError("coverage must lie in [0,1]")
            object.__setattr__(self, "coverage", coverage)
        object.__setattr__(
            self,
            "assumptions",
            tuple(sorted({str(item) for item in self.assumptions if str(item)})),
        )
        object.__setattr__(
            self,
            "counterexamples",
            tuple(str(item) for item in self.counterexamples if str(item)),
        )
        object.__setattr__(
            self,
            "notes",
            tuple(str(item) for item in self.notes if str(item)),
        )
        if self.artifact_hash is not None and len(str(self.artifact_hash)) < 16:
            raise ValidationFrontierError("artifact_hash is suspiciously short")
        # Canonical JSON check without coupling the compiler to agent helpers.
        try:
            json.dumps(dict(self.metadata), sort_keys=True, default=str)
        except TypeError as exc:  # pragma: no cover - defensive
            raise ValidationFrontierError("metadata is not serializable") from exc

    @property
    def fingerprint(self) -> str:
        payload = {
            "id": self.evidence_id,
            "kind": self.kind.value,
            "checker": self.checker,
            "version": self.checker_version,
            "group": self.independence_group,
            "source": self.source_fingerprint,
            "target": self.target_fingerprint,
            "property": self.property,
            "verdict": self.verdict.value,
            "cases": self.tested_cases,
            "coverage": self.coverage,
            "assumptions": self.assumptions,
            "counterexamples": self.counterexamples,
            "notes": self.notes,
            "artifact": self.artifact_hash,
            "machine_checked": self.machine_checked,
            "metadata": dict(self.metadata),
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), default=str
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def bound_to(self, source: IRModule, target: IRModule) -> bool:
        return (
            self.source_fingerprint == source.fingerprint
            and self.target_fingerprint == target.fingerprint
        )


@dataclass(frozen=True, slots=True)
class IndependenceGroupAssessment:
    group: str
    evidence_ids: tuple[str, ...]
    supporting_ids: tuple[str, ...]
    refuting_ids: tuple[str, ...]
    inconclusive_ids: tuple[str, ...]
    kinds: tuple[ValidatorKind, ...]
    effective_support: bool
    machine_checked_support: bool


@dataclass(frozen=True, slots=True)
class AssuranceConsensusPolicy:
    minimum_independent_semantic_groups: int = 2
    minimum_high_assurance_groups: int = 3
    require_structural_support: bool = True
    reject_any_bound_refutation: bool = True
    reject_fingerprint_mismatch: bool = True
    require_semantic_evidence_for_changed_exact: bool = True
    require_semantic_evidence_for_changed_refinement: bool = True
    minimum_coverage_for_differential: float = 0.0
    proof_kinds: tuple[ValidatorKind, ...] = (
        ValidatorKind.EXTERNAL_SMT,
        ValidatorKind.EXTERNAL_BACKEND,
        ValidatorKind.PROOF_ASSISTANT,
    )
    semantic_kinds: tuple[ValidatorKind, ...] = (
        ValidatorKind.ABSTRACT_INTERPRETATION,
        ValidatorKind.DIFFERENTIAL_EXECUTION,
        ValidatorKind.METAMORPHIC,
        ValidatorKind.EXTERNAL_SMT,
        ValidatorKind.EXTERNAL_BACKEND,
        ValidatorKind.PROOF_ASSISTANT,
        ValidatorKind.DECOMPILATION_ROUNDTRIP,
    )

    def __post_init__(self) -> None:
        for name in (
            "minimum_independent_semantic_groups",
            "minimum_high_assurance_groups",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValidationFrontierError(f"{name} must be non-negative integer")
        if self.minimum_high_assurance_groups < self.minimum_independent_semantic_groups:
            raise ValidationFrontierError(
                "high-assurance threshold cannot be below multimethod threshold"
            )
        if not 0.0 <= float(self.minimum_coverage_for_differential) <= 1.0:
            raise ValidationFrontierError(
                "minimum_coverage_for_differential must lie in [0,1]"
            )


@dataclass(frozen=True, slots=True)
class AssuranceConsensus:
    status: AssuranceConsensusStatus
    source_fingerprint: str
    target_fingerprint: str
    property: str
    accepted: bool
    independent_groups: tuple[IndependenceGroupAssessment, ...]
    supporting_semantic_groups: tuple[str, ...]
    structural_groups: tuple[str, ...]
    proof_groups: tuple[str, ...]
    rejected_evidence_ids: tuple[str, ...]
    ignored_evidence_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    fingerprint: str


class AssuranceConsensusEngine:
    """Aggregate validation evidence without pretending correlation is independence."""

    def __init__(self, policy: AssuranceConsensusPolicy | None = None) -> None:
        self.policy = policy or AssuranceConsensusPolicy()

    def evaluate(
        self,
        source: IRModule,
        target: IRModule,
        *,
        semantics: PassSemantics,
        evidence: Sequence[ValidationEvidence],
    ) -> AssuranceConsensus:
        if not isinstance(source, IRModule) or not isinstance(target, IRModule):
            raise TypeError("source and target must be IRModule")
        if not isinstance(semantics, PassSemantics):
            semantics = PassSemantics(str(semantics))

        property_name = (
            "equivalence"
            if semantics is PassSemantics.EXACT
            else "refinement"
            if semantics is PassSemantics.REFINEMENT
            else "approximation"
        )
        rejected: list[str] = []
        ignored: list[str] = []
        bound: list[ValidationEvidence] = []
        reasons: list[str] = []

        for item in evidence:
            if not isinstance(item, ValidationEvidence):
                raise TypeError("evidence must contain ValidationEvidence")
            if not item.bound_to(source, target):
                if self.policy.reject_fingerprint_mismatch:
                    rejected.append(item.evidence_id)
                else:
                    ignored.append(item.evidence_id)
                continue
            if item.property != property_name and item.kind not in {
                ValidatorKind.STRUCTURAL,
                ValidatorKind.EFFECT_AUDIT,
                ValidatorKind.PROVENANCE_AUDIT,
                ValidatorKind.DECOMPILATION_AUDIT,
            }:
                ignored.append(item.evidence_id)
                continue
            if (
                item.kind is ValidatorKind.DIFFERENTIAL_EXECUTION
                and item.coverage is not None
                and item.coverage < self.policy.minimum_coverage_for_differential
            ):
                ignored.append(item.evidence_id)
                continue
            bound.append(item)

        groups: dict[str, list[ValidationEvidence]] = {}
        for item in bound:
            groups.setdefault(item.independence_group, []).append(item)

        assessments: list[IndependenceGroupAssessment] = []
        for group, items in sorted(groups.items()):
            supporting = tuple(
                sorted(
                    item.evidence_id
                    for item in items
                    if item.verdict is ValidationVerdict.SUPPORTS
                )
            )
            refuting = tuple(
                sorted(
                    item.evidence_id
                    for item in items
                    if item.verdict is ValidationVerdict.REFUTES
                )
            )
            inconclusive = tuple(
                sorted(
                    item.evidence_id
                    for item in items
                    if item.verdict
                    in {
                        ValidationVerdict.INCONCLUSIVE,
                        ValidationVerdict.ERROR,
                    }
                )
            )
            assessments.append(
                IndependenceGroupAssessment(
                    group=group,
                    evidence_ids=tuple(sorted(item.evidence_id for item in items)),
                    supporting_ids=supporting,
                    refuting_ids=refuting,
                    inconclusive_ids=inconclusive,
                    kinds=tuple(
                        sorted({item.kind for item in items}, key=lambda x: x.value)
                    ),
                    effective_support=bool(supporting) and not bool(refuting),
                    machine_checked_support=any(
                        item.machine_checked
                        and item.verdict is ValidationVerdict.SUPPORTS
                        for item in items
                    )
                    and not bool(refuting),
                )
            )

        bound_refutations = [
            item.evidence_id
            for item in bound
            if item.verdict is ValidationVerdict.REFUTES
        ]
        if rejected:
            reasons.append("fingerprint-mismatched evidence was supplied")
        if bound_refutations:
            reasons.append("a bound validator produced a counterexample/refutation")

        structural_groups = tuple(
            assessment.group
            for assessment in assessments
            if assessment.effective_support
            and ValidatorKind.STRUCTURAL in assessment.kinds
        )
        semantic_groups = tuple(
            assessment.group
            for assessment in assessments
            if assessment.effective_support
            and any(kind in self.policy.semantic_kinds for kind in assessment.kinds)
        )
        proof_groups = tuple(
            assessment.group
            for assessment in assessments
            if assessment.machine_checked_support
            and any(kind in self.policy.proof_kinds for kind in assessment.kinds)
        )

        changed = source.fingerprint != target.fingerprint
        need_semantic = changed and (
            (
                semantics is PassSemantics.EXACT
                and self.policy.require_semantic_evidence_for_changed_exact
            )
            or (
                semantics is PassSemantics.REFINEMENT
                and self.policy.require_semantic_evidence_for_changed_refinement
            )
        )

        if self.policy.reject_any_bound_refutation and bound_refutations:
            status = AssuranceConsensusStatus.REJECTED
            accepted = False
        elif self.policy.reject_fingerprint_mismatch and rejected:
            status = AssuranceConsensusStatus.REJECTED
            accepted = False
        elif self.policy.require_structural_support and not structural_groups:
            status = AssuranceConsensusStatus.INCONCLUSIVE
            accepted = False
            reasons.append("no independent structural support")
        elif need_semantic and not semantic_groups:
            status = AssuranceConsensusStatus.INCONCLUSIVE
            accepted = False
            reasons.append("changed transform lacks semantic support")
        elif proof_groups:
            status = AssuranceConsensusStatus.EXTERNALLY_PROVED
            accepted = True
        elif len(set(semantic_groups)) >= self.policy.minimum_high_assurance_groups:
            status = AssuranceConsensusStatus.HIGH_ASSURANCE
            accepted = True
        elif len(set(semantic_groups)) >= self.policy.minimum_independent_semantic_groups:
            status = AssuranceConsensusStatus.MULTIMETHOD
            accepted = True
        elif semantic_groups:
            status = AssuranceConsensusStatus.SINGLE_METHOD
            accepted = not need_semantic or self.policy.minimum_independent_semantic_groups <= 1
            if not accepted:
                reasons.append("semantic support lacks independent methodological replication")
        else:
            status = AssuranceConsensusStatus.INCONCLUSIVE
            accepted = not changed and bool(structural_groups)

        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "status": status.value,
                    "source": source.fingerprint,
                    "target": target.fingerprint,
                    "property": property_name,
                    "accepted": accepted,
                    "groups": [
                        {
                            "group": item.group,
                            "evidence": item.evidence_ids,
                            "support": item.supporting_ids,
                            "refute": item.refuting_ids,
                            "kinds": [kind.value for kind in item.kinds],
                        }
                        for item in assessments
                    ],
                    "rejected": sorted(rejected),
                    "ignored": sorted(ignored),
                    "reasons": reasons,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return AssuranceConsensus(
            status=status,
            source_fingerprint=source.fingerprint,
            target_fingerprint=target.fingerprint,
            property=property_name,
            accepted=accepted,
            independent_groups=tuple(assessments),
            supporting_semantic_groups=tuple(sorted(set(semantic_groups))),
            structural_groups=tuple(sorted(set(structural_groups))),
            proof_groups=tuple(sorted(set(proof_groups))),
            rejected_evidence_ids=tuple(sorted(set(rejected))),
            ignored_evidence_ids=tuple(sorted(set(ignored))),
            reasons=tuple(reasons),
            fingerprint=fingerprint,
        )


class InternalValidationFactory:
    """Create fingerprint-bound evidence from existing Jeeves validators."""

    def __init__(
        self,
        *,
        verifier: IRVerifier | None = None,
        translator: TranslationValidator | None = None,
        executor: SemanticExecutor | None = None,
    ) -> None:
        self.verifier = verifier or IRVerifier()
        self.executor = executor or SemanticExecutor()
        self.translator = translator or TranslationValidator(self.executor)

    def structural(
        self,
        source: IRModule,
        target: IRModule,
        *,
        checker_version: str = "jeeves-ir-v1",
    ) -> ValidationEvidence:
        source_report = self.verifier.verify(source)
        target_report = self.verifier.verify(target)
        supports = source_report.valid and target_report.valid
        return ValidationEvidence(
            evidence_id=self._id(
                "structural", source.fingerprint, target.fingerprint, checker_version
            ),
            kind=ValidatorKind.STRUCTURAL,
            checker="jeeves.IRVerifier",
            checker_version=checker_version,
            independence_group="jeeves-structural-verifier",
            source_fingerprint=source.fingerprint,
            target_fingerprint=target.fingerprint,
            property="structure",
            verdict=(
                ValidationVerdict.SUPPORTS
                if supports
                else ValidationVerdict.REFUTES
            ),
            counterexamples=tuple(
                diagnostic.message
                for diagnostic in (*source_report.diagnostics, *target_report.diagnostics)
                if getattr(diagnostic, "severity", None)
                and str(getattr(diagnostic.severity, "value", diagnostic.severity))
                == "error"
            ),
            notes=("structural validity is necessary but not semantic equivalence",),
        )

    def differential(
        self,
        source: IRModule,
        target: IRModule,
        *,
        cases: Mapping[str, Sequence[Sequence[Any]]],
        semantics: PassSemantics,
        maximum_steps: int = 10_000,
        checker_version: str = "jeeves-bounded-diff-v1",
    ) -> ValidationEvidence:
        result = self.translator.validate(
            source,
            target,
            cases=cases,
            semantics=semantics,
            maximum_steps=maximum_steps,
        )
        if result.status is ValidationStatus.VALIDATED:
            verdict = ValidationVerdict.SUPPORTS
        elif result.status is ValidationStatus.REJECTED:
            verdict = ValidationVerdict.REFUTES
        else:
            verdict = ValidationVerdict.INCONCLUSIVE
        parameterized = sum(1 for fn in source.functions if fn.parameters)
        tested_functions = sum(
            1
            for fn in source.functions
            if tuple(cases.get(fn.name, ())) or not fn.parameters
        )
        coverage = 1.0 if parameterized == 0 else min(
            1.0, tested_functions / max(1, len(source.functions))
        )
        return ValidationEvidence(
            evidence_id=self._id(
                "differential",
                source.fingerprint,
                target.fingerprint,
                checker_version,
                str(result.tested_cases),
            ),
            kind=ValidatorKind.DIFFERENTIAL_EXECUTION,
            checker="jeeves.TranslationValidator",
            checker_version=checker_version,
            independence_group="jeeves-bounded-differential-execution",
            source_fingerprint=source.fingerprint,
            target_fingerprint=target.fingerprint,
            property=(
                "equivalence"
                if semantics is PassSemantics.EXACT
                else "refinement"
                if semantics is PassSemantics.REFINEMENT
                else "approximation"
            ),
            verdict=verdict,
            tested_cases=result.tested_cases,
            coverage=coverage,
            counterexamples=result.mismatches,
            notes=tuple(result.notes) + tuple(result.unsupported),
        )

    def metamorphic(
        self,
        source: IRModule,
        target: IRModule,
        *,
        relation_id: str,
        cases: Mapping[str, Sequence[Sequence[Any]]],
        relation: Callable[[tuple[Any, ...], tuple[Any, ...], Sequence[Any]], bool],
        maximum_steps: int = 10_000,
        checker_version: str = "jeeves-metamorphic-v1",
    ) -> ValidationEvidence:
        """Test a declared source/target relation on explicit observations.

        The relation is user- or pass-defined. This is adversarial property
        testing, not a proof that the relation holds outside the tested cases.
        """
        if not relation_id.strip() or not callable(relation):
            raise ValidationFrontierError("metamorphic relation id/callable required")
        source_functions = {fn.name: fn for fn in source.functions}
        target_functions = {fn.name: fn for fn in target.functions}
        if set(source_functions) != set(target_functions):
            return ValidationEvidence(
                evidence_id=self._id(
                    "metamorphic", relation_id, source.fingerprint, target.fingerprint
                ),
                kind=ValidatorKind.METAMORPHIC,
                checker="jeeves.MetamorphicValidator",
                checker_version=checker_version,
                independence_group="jeeves-metamorphic-properties",
                source_fingerprint=source.fingerprint,
                target_fingerprint=target.fingerprint,
                property="equivalence",
                verdict=ValidationVerdict.REFUTES,
                counterexamples=("function set changed",),
            )

        tested = 0
        failures: list[str] = []
        unsupported: list[str] = []
        for name in sorted(source_functions):
            function_cases = tuple(cases.get(name, ()))
            if not function_cases and not source_functions[name].parameters:
                function_cases = ((),)
            for index, arguments in enumerate(function_cases):
                try:
                    old = self.executor.execute_function(
                        source_functions[name], arguments, maximum_steps=maximum_steps
                    )
                    new = self.executor.execute_function(
                        target_functions[name], arguments, maximum_steps=maximum_steps
                    )
                except UnsupportedSemantics as exc:
                    unsupported.append(f"{name}: {exc}")
                    break
                except Exception as exc:
                    failures.append(
                        f"{name}[{index}]: execution failure {type(exc).__name__}"
                    )
                    continue
                tested += 1
                try:
                    holds = bool(relation(old, new, arguments))
                except Exception as exc:
                    failures.append(
                        f"{name}[{index}]: relation failure {type(exc).__name__}"
                    )
                    continue
                if not holds:
                    failures.append(f"{name}[{index}]: metamorphic relation violated")

        verdict = (
            ValidationVerdict.REFUTES
            if failures
            else ValidationVerdict.INCONCLUSIVE
            if unsupported or tested == 0
            else ValidationVerdict.SUPPORTS
        )
        return ValidationEvidence(
            evidence_id=self._id(
                "metamorphic",
                relation_id,
                source.fingerprint,
                target.fingerprint,
                str(tested),
            ),
            kind=ValidatorKind.METAMORPHIC,
            checker="jeeves.MetamorphicValidator",
            checker_version=checker_version,
            independence_group="jeeves-metamorphic-properties",
            source_fingerprint=source.fingerprint,
            target_fingerprint=target.fingerprint,
            property="equivalence",
            verdict=verdict,
            tested_cases=tested,
            counterexamples=tuple(failures),
            notes=tuple(unsupported)
            + ("bounded metamorphic testing is evidence, not proof",),
            metadata={"relation_id": relation_id},
        )

    @staticmethod
    def _id(*parts: str) -> str:
        encoded = json.dumps(parts, separators=(",", ":"))
        return "val:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:28]
