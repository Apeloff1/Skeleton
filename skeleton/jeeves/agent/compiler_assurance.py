"""2026 semantic-assurance plane for the Jeeves compiler.

The design adopts durable compiler assurance principles without overstating
proof strength:

* legality is explicit rather than implied by successful construction;
* UNKNOWN semantics may exist in early/recovery IR but are forbidden in
  VERIFIED_EXECUTION unless policy explicitly permits them;
* nondeterminism requires a named source and replay policy;
* side effects remain explicit and cannot masquerade as PURE;
* assumptions and information loss are tracked as proof debt;
* every inspection emits a deterministic fingerprint suitable for a crash/
  failure reproducer and CI artifact.

This module does not claim a mechanically verified compiler.  It supplies
machine-checkable obligations that sit beside translation validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .semantic_ir import Dialect, Effect, IRFunction, IRModule, IRStage, IRType, OpCode, Operation
from .types import AgentContractError, json_safe, stable_fingerprint, stable_id


class FindingSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AnalysisDomain(str, Enum):
    CFG = "cfg"
    SSA = "ssa"
    TYPES = "types"
    EFFECTS = "effects"
    PROVENANCE = "provenance"
    MEMORY = "memory"
    ALIAS = "alias"
    CAPABILITIES = "capabilities"
    EVIDENCE = "evidence"
    NONDETERMINISM = "nondeterminism"


class ProofScope(str, Enum):
    NONE = "none"
    STRUCTURAL = "structural"
    SYMBOLIC = "symbolic"
    DIFFERENTIAL = "differential"
    TRANSLATION_VALIDATED = "translation_validated"
    MECHANIZED = "mechanized"


@dataclass(frozen=True, slots=True)
class AssurancePolicy:
    """Legality policy for semantic IR.

    Early stages are allowed to carry explicit uncertainty.  The final verified
    stage is deliberately much stricter.
    """

    reject_unknown_at_verified_execution: bool = True
    reject_information_loss_at_verified_execution: bool = True
    require_nondeterminism_contract: bool = True
    require_external_mutation_risk: bool = True
    require_tool_identity: bool = True
    require_division_semantics: bool = True
    allow_assume_before_verified_execution: bool = True
    allowed_verified_dialects: tuple[Dialect, ...] = (
        Dialect.CORE,
        Dialect.JEEVES_CONTROL,
        Dialect.JEEVES_MEMORY,
        Dialect.JEEVES_EVIDENCE,
        Dialect.JEEVES_CAUSAL,
        Dialect.JEEVES_TOOL,
        Dialect.JEEVES_MODEL,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "allowed_verified_dialects",
            tuple(
                value if isinstance(value, Dialect) else Dialect(str(value))
                for value in self.allowed_verified_dialects
            ),
        )


@dataclass(frozen=True, slots=True)
class SemanticAssuranceFinding:
    finding_id: str
    severity: FindingSeverity
    code: str
    message: str
    function_id: str | None = None
    block_id: str | None = None
    operation_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.severity, FindingSeverity):
            object.__setattr__(self, "severity", FindingSeverity(str(self.severity)))
        if not str(self.code).strip():
            raise AgentContractError("assurance finding code is required")
        if not str(self.message).strip():
            raise AgentContractError("assurance finding message is required")
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class SemanticAssuranceReport:
    module_fingerprint: str
    findings: tuple[SemanticAssuranceFinding, ...]
    checked_domains: tuple[AnalysisDomain, ...]
    proof_scope: ProofScope
    accepted: bool
    proof_debt: tuple[str, ...]
    fingerprint: str

    @property
    def errors(self) -> tuple[SemanticAssuranceFinding, ...]:
        return tuple(item for item in self.findings if item.severity is FindingSeverity.ERROR)

    @property
    def warnings(self) -> tuple[SemanticAssuranceFinding, ...]:
        return tuple(item for item in self.findings if item.severity is FindingSeverity.WARNING)

    def as_json(self) -> dict[str, Any]:
        return {
            "module_fingerprint": self.module_fingerprint,
            "accepted": self.accepted,
            "proof_scope": self.proof_scope.value,
            "checked_domains": [item.value for item in self.checked_domains],
            "proof_debt": list(self.proof_debt),
            "findings": [
                {
                    "finding_id": item.finding_id,
                    "severity": item.severity.value,
                    "code": item.code,
                    "message": item.message,
                    "function_id": item.function_id,
                    "block_id": item.block_id,
                    "operation_id": item.operation_id,
                    "metadata": dict(item.metadata),
                }
                for item in self.findings
            ],
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class PassAnalysisDeclaration:
    """MLIR-like declaration of analysis dependencies and invalidation."""

    requires: tuple[AnalysisDomain, ...] = ()
    preserves: tuple[AnalysisDomain, ...] = ()
    invalidates: tuple[AnalysisDomain, ...] = ()
    deterministic: bool = True
    thread_safe: bool = True
    proof_scope: ProofScope = ProofScope.TRANSLATION_VALIDATED

    def __post_init__(self) -> None:
        for name in ("requires", "preserves", "invalidates"):
            values = tuple(
                item if isinstance(item, AnalysisDomain) else AnalysisDomain(str(item))
                for item in getattr(self, name)
            )
            object.__setattr__(self, name, tuple(sorted(set(values), key=lambda x: x.value)))
        if set(self.preserves) & set(self.invalidates):
            raise AgentContractError("an analysis cannot be both preserved and invalidated")
        if not isinstance(self.proof_scope, ProofScope):
            object.__setattr__(self, "proof_scope", ProofScope(str(self.proof_scope)))


@dataclass(frozen=True, slots=True)
class FailureReproducer:
    reproducer_id: str
    pass_name: str
    source_fingerprint: str
    candidate_fingerprint: str | None
    source_assurance_fingerprint: str
    candidate_assurance_fingerprint: str | None
    validation_fingerprint: str | None
    reason: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "id": self.reproducer_id,
                "pass": self.pass_name,
                "source": self.source_fingerprint,
                "candidate": self.candidate_fingerprint,
                "source_assurance": self.source_assurance_fingerprint,
                "candidate_assurance": self.candidate_assurance_fingerprint,
                "validation": self.validation_fingerprint,
                "reason": self.reason,
                "metadata": self.metadata,
            }
        )


class CompilerSemanticAssurance:
    """Static semantic legality checker for Jeeves IR."""

    _CHECKED = (
        AnalysisDomain.CFG,
        AnalysisDomain.SSA,
        AnalysisDomain.TYPES,
        AnalysisDomain.EFFECTS,
        AnalysisDomain.PROVENANCE,
        AnalysisDomain.NONDETERMINISM,
        AnalysisDomain.CAPABILITIES,
    )

    def __init__(self, *, policy: AssurancePolicy | None = None) -> None:
        self.policy = policy or AssurancePolicy()

    def inspect(self, module: IRModule) -> SemanticAssuranceReport:
        if not isinstance(module, IRModule):
            raise TypeError("module must be IRModule")
        findings: list[SemanticAssuranceFinding] = []
        debt: list[str] = []

        # IRModule validates module-level identity on construction and every
        # IRFunction exposes a full CFG/SSA validator. Re-run function
        # validation at the assurance boundary so future pass implementations
        # cannot rely only on a stale construction-time check.
        for function in module.functions:
            try:
                function.validate()
            except Exception as exc:
                findings.append(self._finding(
                    FindingSeverity.ERROR,
                    "invalid-ir",
                    f"IR validation failed: {type(exc).__name__}: {exc}",
                    function_id=function.function_id,
                ))

        for function in module.functions:
            verified = function.stage is IRStage.VERIFIED_EXECUTION
            if verified and any(dialect not in self.policy.allowed_verified_dialects for dialect in function.dialects):
                findings.append(self._finding(
                    FindingSeverity.ERROR,
                    "illegal-verified-dialect",
                    "verified execution contains a dialect outside the configured legality target",
                    function_id=function.function_id,
                    metadata={"dialects": [d.value for d in function.dialects]},
                ))
            if verified and Dialect.UNKNOWN in function.dialects and self.policy.reject_unknown_at_verified_execution:
                findings.append(self._finding(
                    FindingSeverity.ERROR,
                    "unknown-dialect",
                    "UNKNOWN dialect cannot cross the verified-execution boundary",
                    function_id=function.function_id,
                ))

            for block in function.blocks:
                for operation in block.operations:
                    self._inspect_operation(function, block.block_id, operation, findings, debt)

        accepted = not any(item.severity is FindingSeverity.ERROR for item in findings)
        proof_scope = ProofScope.STRUCTURAL
        fingerprint = stable_fingerprint(
            {
                "module": module.fingerprint,
                "accepted": accepted,
                "findings": [
                    (
                        item.severity.value,
                        item.code,
                        item.function_id,
                        item.block_id,
                        item.operation_id,
                        item.metadata,
                    )
                    for item in findings
                ],
                "debt": sorted(set(debt)),
                "policy": {
                    "reject_unknown_verified": self.policy.reject_unknown_at_verified_execution,
                    "reject_loss_verified": self.policy.reject_information_loss_at_verified_execution,
                    "nondeterminism_contract": self.policy.require_nondeterminism_contract,
                },
            }
        )
        return SemanticAssuranceReport(
            module_fingerprint=module.fingerprint,
            findings=tuple(findings),
            checked_domains=self._CHECKED,
            proof_scope=proof_scope,
            accepted=accepted,
            proof_debt=tuple(sorted(set(debt))),
            fingerprint=fingerprint,
        )

    def _inspect_operation(
        self,
        function: IRFunction,
        block_id: str,
        operation: Operation,
        findings: list[SemanticAssuranceFinding],
        debt: list[str],
    ) -> None:
        verified = function.stage is IRStage.VERIFIED_EXECUTION
        location = {
            "function_id": function.function_id,
            "block_id": block_id,
            "operation_id": operation.op_id,
        }

        if operation.opcode is OpCode.UNKNOWN or operation.dialect is Dialect.UNKNOWN or Effect.UNKNOWN in operation.effects:
            severity = FindingSeverity.ERROR if verified and self.policy.reject_unknown_at_verified_execution else FindingSeverity.WARNING
            findings.append(self._finding(
                severity,
                "unknown-semantics",
                "operation carries UNKNOWN opcode, dialect, or effect",
                **location,
            ))
            debt.append(f"{operation.op_id}: unknown semantics")

        if any(result.type is IRType.UNKNOWN for result in operation.results):
            severity = FindingSeverity.ERROR if verified and self.policy.reject_unknown_at_verified_execution else FindingSeverity.WARNING
            findings.append(self._finding(
                severity,
                "unknown-result-type",
                "operation produces UNKNOWN typed SSA value",
                **location,
            ))
            debt.append(f"{operation.op_id}: unknown result type")

        if operation.information_loss:
            severity = (
                FindingSeverity.ERROR
                if verified and self.policy.reject_information_loss_at_verified_execution
                else FindingSeverity.WARNING
            )
            findings.append(self._finding(
                severity,
                "information-loss",
                "operation carries declared information loss",
                **location,
                metadata={"loss": list(operation.information_loss)},
            ))
            debt.extend(f"{operation.op_id}: {value}" for value in operation.information_loss)

        if Effect.NONDETERMINISTIC in operation.effects and self.policy.require_nondeterminism_contract:
            source = operation.attributes.get("nondeterminism_source")
            replay = operation.attributes.get("replay_policy")
            if not isinstance(source, str) or not source.strip() or not isinstance(replay, str) or not replay.strip():
                findings.append(self._finding(
                    FindingSeverity.ERROR,
                    "undeclared-nondeterminism",
                    "nondeterministic operation requires nondeterminism_source and replay_policy",
                    **location,
                ))
            else:
                findings.append(self._finding(
                    FindingSeverity.INFO,
                    "declared-nondeterminism",
                    "nondeterminism is explicit and replay policy is declared",
                    **location,
                    metadata={"source": source, "replay_policy": replay},
                ))

        if operation.opcode is OpCode.TOOL_CALL and self.policy.require_tool_identity:
            tool = operation.attributes.get("tool")
            if not isinstance(tool, str) or not tool.strip():
                findings.append(self._finding(
                    FindingSeverity.ERROR,
                    "missing-tool-identity",
                    "tool call lacks stable tool identity",
                    **location,
                ))

        if (
            Effect.EXTERNAL_MUTATION in operation.effects
            and self.policy.require_external_mutation_risk
            and "risk" not in operation.attributes
        ):
            findings.append(self._finding(
                FindingSeverity.ERROR,
                "unbounded-external-mutation",
                "external mutation lacks explicit risk metadata",
                **location,
            ))

        if operation.opcode is OpCode.DIV and self.policy.require_division_semantics:
            behavior = operation.attributes.get("division_by_zero")
            if behavior not in {"reject", "trap", "defined", "guarded"}:
                findings.append(self._finding(
                    FindingSeverity.ERROR if verified else FindingSeverity.WARNING,
                    "division-semantics-implicit",
                    "division must declare division_by_zero semantics",
                    **location,
                ))
                debt.append(f"{operation.op_id}: division-by-zero behavior unspecified")

        # LLVM-style poison/freeze semantics are represented explicitly as
        # attributes in Jeeves IR rather than implicitly copied from LLVM IR.
        if bool(operation.attributes.get("may_poison", False)):
            guarded = bool(operation.attributes.get("freeze_guarded", False))
            if not guarded:
                findings.append(self._finding(
                    FindingSeverity.ERROR if verified else FindingSeverity.WARNING,
                    "unfrozen-poison",
                    "operation may produce poison-like state without freeze/guard contract",
                    **location,
                ))
                debt.append(f"{operation.op_id}: poison-like state not stabilized")

        if operation.opcode is OpCode.ASSUME:
            if verified or not self.policy.allow_assume_before_verified_execution:
                findings.append(self._finding(
                    FindingSeverity.ERROR,
                    "unresolved-assumption",
                    "ASSUME cannot cross the verified-execution boundary",
                    **location,
                ))
            else:
                debt.append(f"{operation.op_id}: unresolved assumption")

        if not operation.origins:
            findings.append(self._finding(
                FindingSeverity.WARNING,
                "missing-provenance",
                "operation has no source origin; reverse mapping and auditability are weakened",
                **location,
            ))

    @staticmethod
    def _finding(
        severity: FindingSeverity,
        code: str,
        message: str,
        *,
        function_id: str | None = None,
        block_id: str | None = None,
        operation_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> SemanticAssuranceFinding:
        payload = {
            "severity": severity.value,
            "code": code,
            "function": function_id,
            "block": block_id,
            "operation": operation_id,
            "metadata": dict(metadata or {}),
        }
        return SemanticAssuranceFinding(
            finding_id=stable_id("semantic-assurance", payload, length=28),
            severity=severity,
            code=code,
            message=message,
            function_id=function_id,
            block_id=block_id,
            operation_id=operation_id,
            metadata=metadata or {},
        )

    def make_reproducer(
        self,
        *,
        pass_name: str,
        source: IRModule,
        source_report: SemanticAssuranceReport,
        candidate: IRModule | None,
        candidate_report: SemanticAssuranceReport | None,
        validation_fingerprint: str | None,
        reason: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> FailureReproducer:
        payload = {
            "pass": pass_name,
            "source": source.fingerprint,
            "candidate": candidate.fingerprint if candidate is not None else None,
            "source_assurance": source_report.fingerprint,
            "candidate_assurance": candidate_report.fingerprint if candidate_report else None,
            "validation": validation_fingerprint,
            "reason": reason,
        }
        return FailureReproducer(
            reproducer_id=stable_id("compiler-reproducer", payload, length=32),
            pass_name=str(pass_name),
            source_fingerprint=source.fingerprint,
            candidate_fingerprint=candidate.fingerprint if candidate is not None else None,
            source_assurance_fingerprint=source_report.fingerprint,
            candidate_assurance_fingerprint=candidate_report.fingerprint if candidate_report else None,
            validation_fingerprint=validation_fingerprint,
            reason=str(reason)[:8192],
            metadata=metadata or {},
        )


STANDARD_REFERENCES: tuple[Mapping[str, str], ...] = (
    {
        "system": "LLVM IR",
        "profile": "2026",
        "principle": "poison and freeze semantics must be explicit when relevant",
    },
    {
        "system": "MLIR",
        "profile": "2026",
        "principle": "dialect conversion legality, analysis preservation, pass failure, and reproducibility are explicit",
    },
    {
        "system": "CompCert",
        "profile": "3.18/2026",
        "principle": "semantic preservation is the correctness target; failure is preferable to unsound code generation",
    },
    {
        "system": "Alive2",
        "profile": "translation validation",
        "principle": "optimization correctness can be checked per transformation within a defined proof envelope",
    },
)


__all__ = [
    "AnalysisDomain",
    "AssurancePolicy",
    "CompilerSemanticAssurance",
    "FailureReproducer",
    "FindingSeverity",
    "PassAnalysisDeclaration",
    "ProofScope",
    "SemanticAssuranceFinding",
    "SemanticAssuranceReport",
    "STANDARD_REFERENCES",
]
