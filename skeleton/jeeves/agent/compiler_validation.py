"""Translation validation and transactional compiler passes for Jeeves semantic IR.

The pass manager is intentionally fail-closed:
* source and target IR must validate;
* a pass that declares it should change the module may not silently no-op;
* observable effects, tool targets, confirmation boundaries and returns are
  translation-validation obligations;
* exact structural semantic equality is accepted;
* a small straight-line pure fragment also supports symbolic normalization;
* anything outside the validator's proof envelope is INCONCLUSIVE, not "true";
* strict passes roll back on rejection or inconclusive validation.

This is translation validation, not a claim of a fully mechanically verified
compiler.  The distinction is recorded in every report.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, Sequence

from .compiler_assurance import (
    CompilerSemanticAssurance,
    FailureReproducer,
    PassAnalysisDeclaration,
    SemanticAssuranceReport,
)
from .semantic_ir import (
    Dialect,
    Effect,
    IRFunction,
    IRModule,
    IRStage,
    IRType,
    OpCode,
    Operation,
)
from .types import AgentContractError, bounded_text, json_safe, stable_fingerprint, stable_id


class TranslationValidationStatus(str, Enum):
    PROVED_STRUCTURAL = "proved_structural"
    PROVED_SYMBOLIC = "proved_symbolic"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class TranslationCounterexample:
    function_id: str
    reason: str
    source_observation: Any = None
    target_observation: Any = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "function_id", str(self.function_id))
        object.__setattr__(self, "reason", bounded_text("counterexample reason", self.reason, maximum=4096))
        object.__setattr__(self, "source_observation", json_safe(self.source_observation))
        object.__setattr__(self, "target_observation", json_safe(self.target_observation))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class TranslationValidationReport:
    source_fingerprint: str
    target_fingerprint: str
    status: TranslationValidationStatus
    validator: str
    obligations: tuple[str, ...]
    discharged: tuple[str, ...]
    unresolved: tuple[str, ...]
    counterexamples: tuple[TranslationCounterexample, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return self.status in {
            TranslationValidationStatus.PROVED_STRUCTURAL,
            TranslationValidationStatus.PROVED_SYMBOLIC,
        }

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "source": self.source_fingerprint,
                "target": self.target_fingerprint,
                "status": self.status.value,
                "validator": self.validator,
                "obligations": self.obligations,
                "discharged": self.discharged,
                "unresolved": self.unresolved,
                "counterexamples": [
                    {
                        "function": value.function_id,
                        "reason": value.reason,
                        "source": value.source_observation,
                        "target": value.target_observation,
                        "metadata": value.metadata,
                    }
                    for value in self.counterexamples
                ],
                "metadata": self.metadata,
                "source_assurance": self.source_assurance.fingerprint if self.source_assurance else None,
                "candidate_assurance": self.candidate_assurance.fingerprint if self.candidate_assurance else None,
                "reproducer": self.reproducer.fingerprint if self.reproducer else None,
            }
        )


@dataclass(frozen=True, slots=True)
class PassContract:
    name: str
    source_stage: IRStage | None = None
    target_stage: IRStage | None = None
    must_change: bool = True
    preserve_observable_effects: bool = True
    preserve_tool_targets: bool = True
    preserve_returns: bool = True
    allow_inconclusive: bool = False
    analysis: PassAnalysisDeclaration = field(default_factory=PassAnalysisDeclaration)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", bounded_text("pass name", self.name, maximum=256))
        if self.source_stage is not None and not isinstance(self.source_stage, IRStage):
            object.__setattr__(self, "source_stage", IRStage(int(self.source_stage)))
        if self.target_stage is not None and not isinstance(self.target_stage, IRStage):
            object.__setattr__(self, "target_stage", IRStage(int(self.target_stage)))
        if not isinstance(self.analysis, PassAnalysisDeclaration):
            raise TypeError("analysis must be PassAnalysisDeclaration")


class CompilerPass(Protocol):
    contract: PassContract

    def transform(self, module: IRModule) -> IRModule:
        ...


@dataclass(frozen=True, slots=True)
class PassApplication:
    pass_id: str
    contract: PassContract
    source_fingerprint: str
    candidate_fingerprint: str | None
    committed_fingerprint: str
    changed: bool
    committed: bool
    rolled_back: bool
    validation: TranslationValidationReport | None
    error: str | None
    created_at: float
    metadata: Mapping[str, Any] = field(default_factory=dict)
    source_assurance: SemanticAssuranceReport | None = None
    candidate_assurance: SemanticAssuranceReport | None = None
    reproducer: FailureReproducer | None = None

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "pass_id": self.pass_id,
                "contract": self.contract.name,
                "source": self.source_fingerprint,
                "candidate": self.candidate_fingerprint,
                "committed": self.committed_fingerprint,
                "changed": self.changed,
                "did_commit": self.committed,
                "rolled_back": self.rolled_back,
                "validation": self.validation.fingerprint if self.validation else None,
                "error": self.error,
                "created_at": self.created_at,
                "metadata": self.metadata,
            }
        )


class TranslationValidator:
    """Scoped refinement validator for semantic IR.

    The strongest fast path checks a normalized semantic skeleton which ignores
    lowering-only stage/dialect differences but preserves operation semantics,
    dataflow identities, CFG, attributes and non-control effects.

    A secondary proof path handles straight-line pure arithmetic/boolean
    functions via symbolic normalization.  It intentionally does not claim
    equivalence for unsupported control/effects.
    """

    _IGNORABLE_LOWERING_EFFECTS = {Effect.PURE, Effect.CONTROL}
    _SYMBOLIC_OPS = {
        OpCode.CONST,
        OpCode.COPY,
        OpCode.ADD,
        OpCode.SUB,
        OpCode.MUL,
        OpCode.AND,
        OpCode.OR,
        OpCode.NOT,
        OpCode.EQ,
        OpCode.LT,
        OpCode.LE,
        OpCode.GT,
        OpCode.GE,
        OpCode.SELECT,
        OpCode.RETURN,
    }

    def validate(
        self,
        source: IRModule,
        target: IRModule,
        *,
        contract: PassContract | None = None,
    ) -> TranslationValidationReport:
        contract = contract or PassContract(name="translation-validation", must_change=False)
        obligations = [
            "module/function interface preservation",
            "valid source and target IR",
        ]
        discharged = [
            "source IR construction validation",
            "target IR construction validation",
        ]
        unresolved: list[str] = []
        counterexamples: list[TranslationCounterexample] = []

        if contract.preserve_observable_effects:
            obligations.append("observable effect preservation")
        if contract.preserve_tool_targets:
            obligations.append("tool target preservation")
        if contract.preserve_returns:
            obligations.append("return behavior preservation")

        if len(source.functions) != len(target.functions):
            counterexamples.append(
                TranslationCounterexample(
                    function_id="<module>",
                    reason="function count changed",
                    source_observation=len(source.functions),
                    target_observation=len(target.functions),
                )
            )
            return self._report(source, target, TranslationValidationStatus.REJECTED, obligations, discharged, unresolved, counterexamples)

        source_by_id = {value.function_id: value for value in source.functions}
        target_by_id = {value.function_id: value for value in target.functions}
        if set(source_by_id) != set(target_by_id):
            counterexamples.append(
                TranslationCounterexample(
                    function_id="<module>",
                    reason="function identity set changed",
                    source_observation=sorted(source_by_id),
                    target_observation=sorted(target_by_id),
                )
            )
            return self._report(source, target, TranslationValidationStatus.REJECTED, obligations, discharged, unresolved, counterexamples)

        structural_equal = True
        symbolic_possible = True
        for function_id in sorted(source_by_id):
            before = source_by_id[function_id]
            after = target_by_id[function_id]
            interface_problem = self._interface_difference(before, after)
            if interface_problem:
                counterexamples.append(
                    TranslationCounterexample(
                        function_id=function_id,
                        reason=interface_problem,
                        source_observation=self._interface(before),
                        target_observation=self._interface(after),
                    )
                )
                structural_equal = False
                symbolic_possible = False
                continue

            if contract.source_stage is not None and before.stage != contract.source_stage:
                counterexamples.append(
                    TranslationCounterexample(
                        function_id=function_id,
                        reason="source stage violates pass contract",
                        source_observation=int(before.stage),
                        target_observation=int(contract.source_stage),
                    )
                )
                structural_equal = False
                symbolic_possible = False
                continue
            if contract.target_stage is not None and after.stage != contract.target_stage:
                counterexamples.append(
                    TranslationCounterexample(
                        function_id=function_id,
                        reason="target stage violates pass contract",
                        source_observation=int(after.stage),
                        target_observation=int(contract.target_stage),
                    )
                )
                structural_equal = False
                symbolic_possible = False
                continue

            if contract.preserve_observable_effects:
                before_effects = self._observable_effect_trace(before)
                after_effects = self._observable_effect_trace(after)
                if before_effects != after_effects:
                    counterexamples.append(
                        TranslationCounterexample(
                            function_id=function_id,
                            reason="observable effect trace changed",
                            source_observation=before_effects,
                            target_observation=after_effects,
                        )
                    )
                    structural_equal = False
                    symbolic_possible = False
                    continue
            if contract.preserve_tool_targets:
                before_tools = self._tool_targets(before)
                after_tools = self._tool_targets(after)
                if before_tools != after_tools:
                    counterexamples.append(
                        TranslationCounterexample(
                            function_id=function_id,
                            reason="tool-call target/arguments changed",
                            source_observation=before_tools,
                            target_observation=after_tools,
                        )
                    )
                    structural_equal = False
                    symbolic_possible = False
                    continue

            before_skeleton = self._semantic_skeleton(before)
            after_skeleton = self._semantic_skeleton(after)
            if before_skeleton != after_skeleton:
                structural_equal = False
                if not self._can_symbolically_compare(before, after):
                    symbolic_possible = False
                    unresolved.append(f"{function_id}: structural semantics differ outside symbolic proof fragment")

        if counterexamples:
            return self._report(source, target, TranslationValidationStatus.REJECTED, obligations, discharged, unresolved, counterexamples)

        if structural_equal:
            discharged.extend(
                value
                for value in (
                    "normalized operation/dataflow/CFG semantics preserved",
                    "observable effect trace preserved" if contract.preserve_observable_effects else "",
                    "tool targets preserved" if contract.preserve_tool_targets else "",
                    "return interface preserved" if contract.preserve_returns else "",
                )
                if value
            )
            return self._report(source, target, TranslationValidationStatus.PROVED_STRUCTURAL, obligations, discharged, unresolved, ())

        if symbolic_possible:
            for function_id in sorted(source_by_id):
                before = source_by_id[function_id]
                after = target_by_id[function_id]
                if self._semantic_skeleton(before) == self._semantic_skeleton(after):
                    continue
                symbolic_before = self._symbolic_returns(before)
                symbolic_after = self._symbolic_returns(after)
                if symbolic_before is None or symbolic_after is None:
                    unresolved.append(f"{function_id}: symbolic normalizer could not construct proof")
                    continue
                if symbolic_before != symbolic_after:
                    counterexamples.append(
                        TranslationCounterexample(
                            function_id=function_id,
                            reason="symbolic return expression changed",
                            source_observation=symbolic_before,
                            target_observation=symbolic_after,
                        )
                    )
            if counterexamples:
                return self._report(source, target, TranslationValidationStatus.REJECTED, obligations, discharged, unresolved, counterexamples)
            if not unresolved:
                discharged.append("straight-line pure return expressions symbolically normalized to identical forms")
                return self._report(source, target, TranslationValidationStatus.PROVED_SYMBOLIC, obligations, discharged, unresolved, ())

        return self._report(source, target, TranslationValidationStatus.INCONCLUSIVE, obligations, discharged, unresolved, ())

    def _report(
        self,
        source: IRModule,
        target: IRModule,
        status: TranslationValidationStatus,
        obligations: Sequence[str],
        discharged: Sequence[str],
        unresolved: Sequence[str],
        counterexamples: Sequence[TranslationCounterexample],
    ) -> TranslationValidationReport:
        return TranslationValidationReport(
            source_fingerprint=source.fingerprint,
            target_fingerprint=target.fingerprint,
            status=status,
            validator="jeeves.translation-validator.v1",
            obligations=tuple(dict.fromkeys(obligations)),
            discharged=tuple(dict.fromkeys(discharged)),
            unresolved=tuple(dict.fromkeys(unresolved)),
            counterexamples=tuple(counterexamples),
            metadata={"proof_scope": "structural + straight-line symbolic subset"},
        )

    @staticmethod
    def _interface(function: IRFunction) -> dict[str, Any]:
        return {
            "arguments": [(value.value_id, value.type.value) for value in function.arguments],
            "return_types": [value.value for value in function.return_types],
        }

    def _interface_difference(self, source: IRFunction, target: IRFunction) -> str | None:
        if [(v.value_id, v.type.value) for v in source.arguments] != [(v.value_id, v.type.value) for v in target.arguments]:
            return "function arguments changed"
        if source.return_types != target.return_types:
            return "function return types changed"
        return None

    def _semantic_skeleton(self, function: IRFunction) -> Any:
        blocks = []
        for block in function.blocks:
            operations = []
            for operation in block.operations:
                effects = tuple(
                    effect.value
                    for effect in operation.effects
                    if effect not in self._IGNORABLE_LOWERING_EFFECTS
                )
                operations.append(
                    (
                        operation.opcode.value,
                        operation.operands,
                        tuple((result.value_id, result.type.value) for result in operation.results),
                        effects,
                        self._semantic_attributes(operation),
                        tuple(
                            (
                                origin.source_kind,
                                origin.source_ref,
                                origin.start,
                                origin.end,
                                origin.reconstructed,
                            )
                            for origin in operation.origins
                        ),
                    )
                )
            blocks.append((block.block_id, tuple(operations), block.successors()))
        return tuple(blocks)

    @staticmethod
    def _semantic_attributes(operation: Operation) -> Any:
        ignored = {"lowering_stage", "dialect_lowering", "debug_label", "pass_note"}
        return tuple(
            sorted(
                (key, stable_fingerprint(value))
                for key, value in operation.attributes.items()
                if key not in ignored
            )
        )

    def _observable_effect_trace(self, function: IRFunction) -> tuple[tuple[str, tuple[str, ...]], ...]:
        trace = []
        for block in function.blocks:
            for operation in block.operations:
                effects = tuple(
                    effect.value
                    for effect in operation.effects
                    if effect not in self._IGNORABLE_LOWERING_EFFECTS
                )
                if effects:
                    trace.append((operation.opcode.value, effects))
        return tuple(trace)

    @staticmethod
    def _tool_targets(function: IRFunction) -> tuple[Any, ...]:
        values = []
        for block in function.blocks:
            for operation in block.operations:
                if operation.opcode is OpCode.TOOL_CALL:
                    values.append(
                        (
                            operation.attributes.get("tool"),
                            stable_fingerprint(operation.attributes.get("arguments", {})),
                            operation.attributes.get("risk"),
                            bool(operation.attributes.get("confirmation_required", False)),
                        )
                    )
        return tuple(values)

    def _can_symbolically_compare(self, source: IRFunction, target: IRFunction) -> bool:
        for function in (source, target):
            if len(function.blocks) != 1:
                return False
            for operation in function.blocks[0].operations:
                if operation.opcode not in self._SYMBOLIC_OPS:
                    return False
                if operation.opcode is OpCode.RETURN:
                    if any(effect not in {Effect.PURE, Effect.CONTROL} for effect in operation.effects):
                        return False
                elif not operation.is_pure:
                    return False
        return True

    def _symbolic_returns(self, function: IRFunction) -> tuple[Any, ...] | None:
        if not self._can_symbolically_compare(function, function):
            return None
        environment: dict[str, Any] = {
            argument.value_id: ("arg", index, argument.type.value)
            for index, argument in enumerate(function.arguments)
        }
        for operation in function.blocks[0].operations:
            if operation.opcode is OpCode.RETURN:
                return tuple(environment.get(value, ("undefined", value)) for value in operation.operands)
            expressions = self._symbolic_operation(operation, environment)
            if expressions is None:
                return None
            for result, expression in zip(operation.results, expressions):
                environment[result.value_id] = expression
        return None

    def _symbolic_operation(self, operation: Operation, env: Mapping[str, Any]) -> tuple[Any, ...] | None:
        opcode = operation.opcode
        if opcode is OpCode.CONST:
            return (("const", stable_fingerprint(operation.attributes.get("value"))),)
        operands = [env.get(value, ("undefined", value)) for value in operation.operands]
        if opcode is OpCode.COPY and len(operands) == 1:
            return (operands[0],)
        if opcode in {OpCode.ADD, OpCode.MUL, OpCode.AND, OpCode.OR, OpCode.EQ} and len(operands) == 2:
            ordered = tuple(sorted(operands, key=repr))
            return ((opcode.value, *ordered),)
        if opcode in {OpCode.SUB, OpCode.LT, OpCode.LE, OpCode.GT, OpCode.GE} and len(operands) == 2:
            return ((opcode.value, operands[0], operands[1]),)
        if opcode is OpCode.NOT and len(operands) == 1:
            return (("not", operands[0]),)
        if opcode is OpCode.SELECT and len(operands) == 3:
            return (("select", operands[0], operands[1], operands[2]),)
        return None


class TransactionalPassManager:
    def __init__(
        self,
        *,
        validator: TranslationValidator | None = None,
        assurance: CompilerSemanticAssurance | None = None,
        verify_declared_determinism: bool = True,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.validator = validator or TranslationValidator()
        self.assurance = assurance or CompilerSemanticAssurance()
        self.verify_declared_determinism = bool(verify_declared_determinism)
        self._clock = clock

    @staticmethod
    def _analysis_metadata(contract: PassContract) -> dict[str, Any]:
        declaration = contract.analysis
        return {
            "analysis_requires": [item.value for item in declaration.requires],
            "analysis_preserves": [item.value for item in declaration.preserves],
            "analysis_invalidates": [item.value for item in declaration.invalidates],
            "declared_deterministic": declaration.deterministic,
            "declared_thread_safe": declaration.thread_safe,
            "declared_proof_scope": declaration.proof_scope.value,
        }

    def apply(self, module: IRModule, compiler_pass: CompilerPass) -> tuple[IRModule, PassApplication]:
        contract = compiler_pass.contract
        source_fingerprint = module.fingerprint
        # Replay identity is content-derived. Wall time is audit metadata only.
        pass_id = stable_id(
            "pass",
            {
                "name": contract.name,
                "source": source_fingerprint,
                "source_stage": int(contract.source_stage) if contract.source_stage is not None else None,
                "target_stage": int(contract.target_stage) if contract.target_stage is not None else None,
                "analysis": self._analysis_metadata(contract),
            },
            length=28,
        )
        candidate: IRModule | None = None
        candidate_assurance: SemanticAssuranceReport | None = None
        report: TranslationValidationReport | None = None
        reproducer: FailureReproducer | None = None
        error: str | None = None
        source_assurance: SemanticAssuranceReport | None = None
        metadata = self._analysis_metadata(contract)
        try:
            source_assurance = self.assurance.inspect(module)
            if not source_assurance.accepted:
                error = (
                    "source semantic assurance rejected; "
                    f"errors={[item.code for item in source_assurance.errors]}"
                )
                reproducer = self.assurance.make_reproducer(
                    pass_name=contract.name,
                    source=module,
                    source_report=source_assurance,
                    candidate=None,
                    candidate_report=None,
                    validation_fingerprint=None,
                    reason=error,
                    metadata=metadata,
                )
                return module, PassApplication(
                    pass_id=pass_id,
                    contract=contract,
                    source_fingerprint=source_fingerprint,
                    candidate_fingerprint=None,
                    committed_fingerprint=source_fingerprint,
                    changed=False,
                    committed=False,
                    rolled_back=True,
                    validation=None,
                    error=error,
                    created_at=self._clock(),
                    metadata=metadata,
                    source_assurance=source_assurance,
                    candidate_assurance=None,
                    reproducer=reproducer,
                )

            candidate = compiler_pass.transform(module)
            if not isinstance(candidate, IRModule):
                raise TypeError("compiler pass did not return IRModule")
            changed = candidate.fingerprint != source_fingerprint
            if contract.must_change and not changed:
                raise AgentContractError(
                    f"pass {contract.name} declared must_change but produced identical fingerprint"
                )

            if self.verify_declared_determinism and contract.analysis.deterministic:
                replay_candidate = compiler_pass.transform(module)
                if not isinstance(replay_candidate, IRModule):
                    raise TypeError("compiler pass determinism replay did not return IRModule")
                if replay_candidate.fingerprint != candidate.fingerprint:
                    error = (
                        "pass declared deterministic but repeated transformation "
                        "produced a different candidate fingerprint"
                    )
                    candidate_assurance = self.assurance.inspect(candidate)
                    reproducer = self.assurance.make_reproducer(
                        pass_name=contract.name,
                        source=module,
                        source_report=source_assurance,
                        candidate=candidate,
                        candidate_report=candidate_assurance,
                        validation_fingerprint=None,
                        reason=error,
                        metadata={
                            **metadata,
                            "first_candidate": candidate.fingerprint,
                            "replay_candidate": replay_candidate.fingerprint,
                        },
                    )
                    return module, PassApplication(
                        pass_id=pass_id,
                        contract=contract,
                        source_fingerprint=source_fingerprint,
                        candidate_fingerprint=candidate.fingerprint,
                        committed_fingerprint=source_fingerprint,
                        changed=changed,
                        committed=False,
                        rolled_back=True,
                        validation=None,
                        error=error,
                        created_at=self._clock(),
                        metadata={
                            **metadata,
                            "determinism_replay_fingerprint": replay_candidate.fingerprint,
                        },
                        source_assurance=source_assurance,
                        candidate_assurance=candidate_assurance,
                        reproducer=reproducer,
                    )
                metadata["determinism_replay_fingerprint"] = replay_candidate.fingerprint
                metadata["determinism_verified"] = True

            candidate_assurance = self.assurance.inspect(candidate)
            report = self.validator.validate(module, candidate, contract=contract)
            translation_accepted = report.accepted or (
                report.status is TranslationValidationStatus.INCONCLUSIVE
                and contract.allow_inconclusive
            )
            assurance_accepted = candidate_assurance.accepted
            if not translation_accepted or not assurance_accepted:
                reasons: list[str] = []
                if not translation_accepted:
                    reasons.append(
                        f"translation validation {report.status.value}; "
                        f"unresolved={list(report.unresolved)}; "
                        f"counterexamples={[value.reason for value in report.counterexamples]}"
                    )
                if not assurance_accepted:
                    reasons.append(
                        "candidate semantic assurance rejected; "
                        f"errors={[item.code for item in candidate_assurance.errors]}"
                    )
                error = " | ".join(reasons)
                reproducer = self.assurance.make_reproducer(
                    pass_name=contract.name,
                    source=module,
                    source_report=source_assurance,
                    candidate=candidate,
                    candidate_report=candidate_assurance,
                    validation_fingerprint=report.fingerprint,
                    reason=error,
                    metadata=metadata,
                )
                return module, PassApplication(
                    pass_id=pass_id,
                    contract=contract,
                    source_fingerprint=source_fingerprint,
                    candidate_fingerprint=candidate.fingerprint,
                    committed_fingerprint=source_fingerprint,
                    changed=changed,
                    committed=False,
                    rolled_back=True,
                    validation=report,
                    error=error,
                    created_at=self._clock(),
                    metadata=metadata,
                    source_assurance=source_assurance,
                    candidate_assurance=candidate_assurance,
                    reproducer=reproducer,
                )
            return candidate, PassApplication(
                pass_id=pass_id,
                contract=contract,
                source_fingerprint=source_fingerprint,
                candidate_fingerprint=candidate.fingerprint,
                committed_fingerprint=candidate.fingerprint,
                changed=changed,
                committed=True,
                rolled_back=False,
                validation=report,
                error=None,
                created_at=self._clock(),
                metadata=metadata,
                source_assurance=source_assurance,
                candidate_assurance=candidate_assurance,
                reproducer=None,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if source_assurance is not None:
                try:
                    reproducer = self.assurance.make_reproducer(
                        pass_name=contract.name,
                        source=module,
                        source_report=source_assurance,
                        candidate=candidate,
                        candidate_report=candidate_assurance,
                        validation_fingerprint=report.fingerprint if report else None,
                        reason=error,
                        metadata=metadata,
                    )
                except Exception:
                    reproducer = None
            return module, PassApplication(
                pass_id=pass_id,
                contract=contract,
                source_fingerprint=source_fingerprint,
                candidate_fingerprint=candidate.fingerprint if candidate is not None else None,
                committed_fingerprint=source_fingerprint,
                changed=(candidate is not None and candidate.fingerprint != source_fingerprint),
                committed=False,
                rolled_back=True,
                validation=report,
                error=error,
                created_at=self._clock(),
                metadata=metadata,
                source_assurance=source_assurance,
                candidate_assurance=candidate_assurance,
                reproducer=reproducer,
            )

    def run(
        self,
        module: IRModule,
        passes: Sequence[CompilerPass],
        *,
        stop_on_rollback: bool = True,
    ) -> tuple[IRModule, tuple[PassApplication, ...]]:
        current = module
        records: list[PassApplication] = []
        for compiler_pass in passes:
            candidate, record = self.apply(current, compiler_pass)
            records.append(record)
            current = candidate
            if record.rolled_back and stop_on_rollback:
                break
        return current, tuple(records)


class StageLoweringPass:
    """Semantics-preserving stage/dialect lowering.

    It intentionally leaves opcodes, operands, results, attributes and
    observable effects unchanged. Only stage and dialect identities move.
    """

    def __init__(
        self,
        source_stage: IRStage,
        target_stage: IRStage,
        *,
        target_dialect: Dialect,
        name: str | None = None,
    ) -> None:
        if target_stage <= source_stage:
            raise ValueError("target_stage must be later than source_stage")
        self.target_dialect = target_dialect
        self.contract = PassContract(
            name=name or f"lower-{source_stage.name.casefold()}-to-{target_stage.name.casefold()}",
            source_stage=source_stage,
            target_stage=target_stage,
            must_change=True,
            preserve_observable_effects=True,
            preserve_tool_targets=True,
            preserve_returns=True,
            allow_inconclusive=False,
        )

    def transform(self, module: IRModule) -> IRModule:
        functions: list[IRFunction] = []
        for function in module.functions:
            if function.stage != self.contract.source_stage:
                raise AgentContractError(
                    f"function {function.function_id} at {function.stage.name}, expected {self.contract.source_stage.name}"
                )
            blocks = []
            for block in function.blocks:
                operations = tuple(
                    replace(
                        operation,
                        dialect=(
                            operation.dialect
                            if operation.dialect is Dialect.CORE
                            else self.target_dialect
                        ),
                        attributes={
                            **dict(operation.attributes),
                            "lowering_stage": self.contract.target_stage.name.casefold(),
                        },
                    )
                    for operation in block.operations
                )
                blocks.append(replace(block, operations=operations))
            metadata = {
                **dict(function.metadata),
                "lowered_from_stage": function.stage.name.casefold(),
                "lowering_pass": self.contract.name,
            }
            functions.append(
                replace(
                    function,
                    blocks=tuple(blocks),
                    stage=self.contract.target_stage,
                    dialects=tuple(
                        sorted(
                            {
                                Dialect.CORE,
                                self.target_dialect,
                                *(
                                    dialect
                                    for dialect in function.dialects
                                    if dialect is Dialect.CORE
                                ),
                            },
                            key=lambda item: item.value,
                        )
                    ),
                    metadata=metadata,
                )
            )
        return replace(
            module,
            functions=tuple(functions),
            metadata={
                **dict(module.metadata),
                "last_lowering_pass": self.contract.name,
                "parent_fingerprint": module.fingerprint,
            },
        )


__all__ = [
    "CompilerPass",
    "PassApplication",
    "PassContract",
    "StageLoweringPass",
    "TransactionalPassManager",
    "TranslationCounterexample",
    "TranslationValidationReport",
    "TranslationValidationStatus",
    "TranslationValidator",
]
