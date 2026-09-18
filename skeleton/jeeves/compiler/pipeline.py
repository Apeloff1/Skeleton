"""Transactional compiler pipeline with bounded translation validation.

This is deliberately stricter than a conventional optimizer.  Every pass has a
contract, runs against immutable IR, is structurally re-verified, is checked for
unexpected effect escalation, and can be translation-validated on a deterministic
semantic subset before commit.  Failure returns the previous module unchanged.

The translation validator is *bounded*, not a theorem prover.  It reports that
fact explicitly.  Proof-carrying or SMT-backed validators can be installed later
behind the same contract without weakening current fail-closed behavior.
"""

from __future__ import annotations

import hashlib
import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Iterable, Mapping, Optional, Sequence, Set, Tuple

from .ir import (
    BasicBlock,
    ControlFlowGraph,
    Effect,
    FunctionIR,
    IRModule,
    IRVerifier,
    Instruction,
    TerminatorKind,
    VerificationReport,
)


class PassSemantics(str, Enum):
    EXACT = "exact"
    REFINEMENT = "refinement"
    APPROXIMATE = "approximate"


class ValidationStatus(str, Enum):
    VALIDATED = "validated"
    STRUCTURAL_ONLY = "structural_only"
    INCONCLUSIVE = "inconclusive"
    REJECTED = "rejected"


class AnalysisDomain(str, Enum):
    CFG = "cfg"
    DOMINANCE = "dominance"
    SSA = "ssa"
    TYPES = "types"
    EFFECTS = "effects"
    PROVENANCE = "provenance"
    ABSTRACT_INTERPRETATION = "abstract_interpretation"
    ALIAS = "alias"
    CAPABILITIES = "capabilities"
    NONDETERMINISM = "nondeterminism"


@dataclass(frozen=True)
class PassContract:
    pass_id: str
    semantics: PassSemantics = PassSemantics.EXACT
    requires_verified_input: bool = True
    require_translation_validation: bool = True
    allowed_new_effects: FrozenSet[Effect] = frozenset()
    preserve_provenance: bool = True
    maximum_validation_steps: int = 10_000
    required_analyses: FrozenSet[AnalysisDomain] = frozenset()
    preserved_analyses: FrozenSet[AnalysisDomain] = frozenset()
    invalidated_analyses: FrozenSet[AnalysisDomain] = frozenset()
    deterministic: bool = True
    replay_safe: bool = False
    thread_safe: bool = True

    def __post_init__(self) -> None:
        if not self.pass_id:
            raise ValueError("pass_id must be non-empty")
        if self.maximum_validation_steps <= 0:
            raise ValueError("maximum_validation_steps must be positive")
        required = frozenset(
            item if isinstance(item, AnalysisDomain) else AnalysisDomain(str(item))
            for item in self.required_analyses
        )
        preserved = frozenset(
            item if isinstance(item, AnalysisDomain) else AnalysisDomain(str(item))
            for item in self.preserved_analyses
        )
        invalidated = frozenset(
            item if isinstance(item, AnalysisDomain) else AnalysisDomain(str(item))
            for item in self.invalidated_analyses
        )
        if preserved & invalidated:
            raise ValueError("an analysis cannot be both preserved and invalidated")
        if not isinstance(self.deterministic, bool):
            raise TypeError("deterministic must be bool")
        if not isinstance(self.replay_safe, bool):
            raise TypeError("replay_safe must be bool")
        if not isinstance(self.thread_safe, bool):
            raise TypeError("thread_safe must be bool")
        object.__setattr__(self, "required_analyses", required)
        object.__setattr__(self, "preserved_analyses", preserved)
        object.__setattr__(self, "invalidated_analyses", invalidated)


class CompilationPass(ABC):
    """Pure transformation interface.  Implementations must not mutate input IR."""

    contract: PassContract

    @abstractmethod
    def apply(self, module: IRModule) -> IRModule:
        raise NotImplementedError


@dataclass(frozen=True)
class TranslationValidation:
    status: ValidationStatus
    source_fingerprint: str
    target_fingerprint: str
    tested_cases: int
    mismatches: Tuple[str, ...] = ()
    unsupported: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.status in (ValidationStatus.VALIDATED, ValidationStatus.STRUCTURAL_ONLY)


@dataclass(frozen=True)
class PassRecord:
    pass_id: str
    source_fingerprint: str
    candidate_fingerprint: Optional[str]
    committed_fingerprint: str
    committed: bool
    input_verification: VerificationReport
    output_verification: Optional[VerificationReport]
    validation: Optional[TranslationValidation]
    rejected_reasons: Tuple[str, ...] = ()
    determinism_replay_fingerprint: Optional[str] = None
    determinism_verified: bool = False
    analysis_contract: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    replay_safe_declared: bool = False
    thread_safe_declared: bool = False

    @property
    def fingerprint(self) -> str:
        payload = {
            "pass_id": self.pass_id,
            "source": self.source_fingerprint,
            "candidate": self.candidate_fingerprint,
            "committed": self.committed_fingerprint,
            "accepted": self.committed,
            "rejected_reasons": list(self.rejected_reasons),
            "validation_status": self.validation.status.value if self.validation else None,
            "determinism_replay": self.determinism_replay_fingerprint,
            "determinism_verified": self.determinism_verified,
            "analysis_contract": {
                key: list(value) for key, value in sorted(self.analysis_contract.items())
            },
            "replay_safe_declared": self.replay_safe_declared,
            "thread_safe_declared": self.thread_safe_declared,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ExecutionError(RuntimeError):
    pass


class UnsupportedSemantics(ExecutionError):
    pass


class SemanticExecutor:
    """Deterministic interpreter for the validation-safe semantic IR subset."""

    PURE_OPS = frozenset(
        {
            "const",
            "identity",
            "add",
            "sub",
            "mul",
            "div",
            "floordiv",
            "mod",
            "neg",
            "eq",
            "ne",
            "lt",
            "le",
            "gt",
            "ge",
            "and",
            "or",
            "not",
            "select",
            "min",
            "max",
        }
    )

    def execute_function(
        self,
        function: FunctionIR,
        arguments: Sequence[Any],
        *,
        maximum_steps: int = 10_000,
    ) -> Tuple[Any, ...]:
        if len(arguments) != len(function.parameters):
            raise ExecutionError("argument arity mismatch")
        blocks = {block.label: block for block in function.blocks}
        if function.entry not in blocks:
            raise ExecutionError("missing entry block")
        env: Dict[str, Any] = {
            parameter.value_id: value for parameter, value in zip(function.parameters, arguments)
        }
        current = function.entry
        steps = 0
        while True:
            block = blocks[current]
            if block.arguments:
                raise UnsupportedSemantics("block arguments require explicit edge-value semantics")
            for instruction in block.instructions:
                steps += 1
                if steps > maximum_steps:
                    raise ExecutionError("execution step limit exceeded")
                if instruction.effects != frozenset({Effect.PURE}):
                    raise UnsupportedSemantics("effectful instruction cannot be executed by bounded validator")
                values = [env[item] for item in instruction.operands]
                results = self._evaluate(instruction, values)
                if len(results) != len(instruction.results):
                    raise ExecutionError("instruction result arity mismatch")
                for result, value in zip(instruction.results, results):
                    env[result.value_id] = value

            term = block.terminator
            if term.kind == TerminatorKind.RETURN:
                return tuple(env[item] for item in term.operands)
            if term.kind == TerminatorKind.JUMP:
                current = term.targets[0]
                continue
            if term.kind == TerminatorKind.BRANCH:
                if len(term.operands) != 1:
                    raise UnsupportedSemantics("bounded branch validator expects one condition operand")
                condition = bool(env[term.operands[0]])
                current = term.targets[0] if condition else term.targets[1]
                continue
            if term.kind == TerminatorKind.FAIL:
                raise ExecutionError("program reached fail terminator")
            if term.kind == TerminatorKind.UNREACHABLE:
                raise ExecutionError("program reached unreachable terminator")
            raise UnsupportedSemantics("unsupported terminator")

    def _evaluate(self, instruction: Instruction, values: Sequence[Any]) -> Tuple[Any, ...]:
        op = instruction.opcode
        if op not in self.PURE_OPS:
            raise UnsupportedSemantics("unsupported opcode: %s" % op)
        if op == "const":
            return (instruction.attributes.get("value"),)
        if op == "identity":
            return (values[0],)
        if op == "add":
            return (values[0] + values[1],)
        if op == "sub":
            return (values[0] - values[1],)
        if op == "mul":
            return (values[0] * values[1],)
        if op == "div":
            return (values[0] / values[1],)
        if op == "floordiv":
            return (values[0] // values[1],)
        if op == "mod":
            return (values[0] % values[1],)
        if op == "neg":
            return (-values[0],)
        if op == "eq":
            return (values[0] == values[1],)
        if op == "ne":
            return (values[0] != values[1],)
        if op == "lt":
            return (values[0] < values[1],)
        if op == "le":
            return (values[0] <= values[1],)
        if op == "gt":
            return (values[0] > values[1],)
        if op == "ge":
            return (values[0] >= values[1],)
        if op == "and":
            return (bool(values[0]) and bool(values[1]),)
        if op == "or":
            return (bool(values[0]) or bool(values[1]),)
        if op == "not":
            return (not bool(values[0]),)
        if op == "select":
            return (values[1] if bool(values[0]) else values[2],)
        if op == "min":
            return (min(values[0], values[1]),)
        if op == "max":
            return (max(values[0], values[1]),)
        raise UnsupportedSemantics(op)


class TranslationValidator:
    """Validate source/target behavior on an explicit bounded observation set."""

    def __init__(self, executor: Optional[SemanticExecutor] = None) -> None:
        self.executor = executor or SemanticExecutor()

    def validate(
        self,
        source: IRModule,
        target: IRModule,
        *,
        cases: Mapping[str, Sequence[Sequence[Any]]],
        semantics: PassSemantics,
        maximum_steps: int,
    ) -> TranslationValidation:
        mismatches = []
        unsupported = []
        tested = 0
        source_functions = {item.name: item for item in source.functions}
        target_functions = {item.name: item for item in target.functions}
        if set(source_functions) != set(target_functions):
            return TranslationValidation(
                ValidationStatus.REJECTED,
                source.fingerprint,
                target.fingerprint,
                0,
                mismatches=("function set changed",),
            )

        for name in sorted(source_functions):
            source_function = source_functions[name]
            target_function = target_functions[name]
            if tuple(source_function.return_types) != tuple(target_function.return_types):
                mismatches.append(name + ": return type signature changed")
                continue
            if tuple(parameter.value_type for parameter in source_function.parameters) != tuple(
                parameter.value_type for parameter in target_function.parameters
            ):
                mismatches.append(name + ": parameter type signature changed")
                continue
            function_cases = tuple(cases.get(name, ()))
            if not function_cases and not source_function.parameters:
                function_cases = ((),)
            if not function_cases:
                unsupported.append(name + ": no validation observations")
                continue
            for index, arguments in enumerate(function_cases):
                try:
                    old = self.executor.execute_function(
                        source_function, arguments, maximum_steps=maximum_steps
                    )
                    new = self.executor.execute_function(
                        target_function, arguments, maximum_steps=maximum_steps
                    )
                except UnsupportedSemantics as exc:
                    unsupported.append(name + ": " + str(exc))
                    break
                except Exception as exc:
                    mismatches.append(name + "[%d]: execution failure %s" % (index, type(exc).__name__))
                    continue
                tested += 1
                if not self._compatible(old, new, semantics):
                    mismatches.append(name + "[%d]: observable output mismatch" % index)

        if mismatches:
            status = ValidationStatus.REJECTED
        elif unsupported:
            status = ValidationStatus.INCONCLUSIVE
        elif tested:
            status = ValidationStatus.VALIDATED
        else:
            status = ValidationStatus.STRUCTURAL_ONLY
        return TranslationValidation(
            status,
            source.fingerprint,
            target.fingerprint,
            tested,
            tuple(sorted(set(mismatches))),
            tuple(sorted(set(unsupported))),
            notes=("bounded validation is evidence, not a machine-checked proof",),
        )

    @staticmethod
    def _compatible(old: Tuple[Any, ...], new: Tuple[Any, ...], semantics: PassSemantics) -> bool:
        if semantics == PassSemantics.EXACT:
            return old == new
        if semantics == PassSemantics.REFINEMENT:
            # In the current scalar subset refinement means no new externally
            # visible behavior.  Rich nondeterministic traces can plug in a
            # stronger subset relation later.
            return old == new
        return True


class PassManager:
    """Fail-closed transactional pass manager."""

    def __init__(
        self,
        *,
        verifier: Optional[IRVerifier] = None,
        validator: Optional[TranslationValidator] = None,
        allow_approximate: bool = False,
        verify_declared_determinism: bool = True,
    ) -> None:
        self.verifier = verifier or IRVerifier()
        self.validator = validator or TranslationValidator()
        self.allow_approximate = bool(allow_approximate)
        self.verify_declared_determinism = bool(verify_declared_determinism)

    def run_pass(
        self,
        module: IRModule,
        compiler_pass: CompilationPass,
        *,
        validation_cases: Mapping[str, Sequence[Sequence[Any]]] = {},
    ) -> Tuple[IRModule, PassRecord]:
        contract = compiler_pass.contract
        input_report = self.verifier.verify(module)
        reasons = []
        if contract.requires_verified_input and not input_report.valid:
            reasons.append("input IR failed verification")
            return module, self._record(
                contract.pass_id, module, None, module, False, input_report, None, None, reasons,
                contract=contract,
            )
        if contract.semantics == PassSemantics.APPROXIMATE and not self.allow_approximate:
            reasons.append("approximate pass requires explicit opt-in")
            return module, self._record(
                contract.pass_id, module, None, module, False, input_report, None, None, reasons,
                contract=contract,
            )
        if (
            self.verify_declared_determinism
            and contract.deterministic
            and not contract.replay_safe
        ):
            reasons.append(
                "determinism verification requires replay_safe=True; "
                "pass was not executed"
            )
            return module, self._record(
                contract.pass_id, module, None, module, False, input_report, None, None, reasons,
                contract=contract,
            )

        try:
            candidate = compiler_pass.apply(module)
        except Exception as exc:
            reasons.append("pass raised %s" % type(exc).__name__)
            return module, self._record(
                contract.pass_id, module, None, module, False, input_report, None, None, reasons,
                contract=contract,
            )
        if not isinstance(candidate, IRModule):
            reasons.append("pass did not return IRModule")
            return module, self._record(
                contract.pass_id, module, None, module, False, input_report, None, None, reasons,
                contract=contract,
            )

        determinism_replay_fingerprint = None
        determinism_verified = False
        if self.verify_declared_determinism and contract.deterministic:
            try:
                replay_candidate = compiler_pass.apply(module)
            except Exception as exc:
                reasons.append("determinism replay raised %s" % type(exc).__name__)
            else:
                if not isinstance(replay_candidate, IRModule):
                    reasons.append("determinism replay did not return IRModule")
                else:
                    determinism_replay_fingerprint = replay_candidate.fingerprint
                    if replay_candidate.fingerprint != candidate.fingerprint:
                        reasons.append("pass declared deterministic but replay fingerprint changed")
                    else:
                        determinism_verified = True

        output_report = self.verifier.verify(candidate)
        if not output_report.valid:
            reasons.append("candidate IR failed verification")

        effect_escalations = self._unexpected_effects(module, candidate) - set(contract.allowed_new_effects)
        if effect_escalations:
            reasons.append(
                "unexpected effect escalation: "
                + ",".join(sorted(item.value for item in effect_escalations))
            )

        if contract.preserve_provenance:
            missing = self._missing_provenance(module, candidate)
            if missing:
                reasons.append("candidate dropped provenance for %d sourced instruction(s)" % missing)

        validation = None
        if contract.require_translation_validation and not reasons:
            validation = self.validator.validate(
                module,
                candidate,
                cases=validation_cases,
                semantics=contract.semantics,
                maximum_steps=contract.maximum_validation_steps,
            )
            if not validation.accepted:
                reasons.append("translation validation did not accept candidate: %s" % validation.status.value)

        committed = not reasons
        result = candidate if committed else module
        return result, self._record(
            contract.pass_id,
            module,
            candidate,
            result,
            committed,
            input_report,
            output_report,
            validation,
            reasons,
            contract=contract,
            determinism_replay_fingerprint=determinism_replay_fingerprint,
            determinism_verified=determinism_verified,
        )

    def run_pipeline(
        self,
        module: IRModule,
        passes: Sequence[CompilationPass],
        *,
        validation_cases: Mapping[str, Sequence[Sequence[Any]]] = {},
        stop_on_failure: bool = True,
    ) -> Tuple[IRModule, Tuple[PassRecord, ...]]:
        current = module
        records = []
        for compiler_pass in passes:
            current, record = self.run_pass(
                current, compiler_pass, validation_cases=validation_cases
            )
            records.append(record)
            if not record.committed and stop_on_failure:
                break
        return current, tuple(records)

    @staticmethod
    def _function_effects(module: IRModule) -> Set[Effect]:
        effects = set()
        for function in module.functions:
            for block in function.blocks:
                for instruction in block.instructions:
                    effects.update(effect for effect in instruction.effects if effect != Effect.PURE)
        return effects

    def _unexpected_effects(self, source: IRModule, candidate: IRModule) -> Set[Effect]:
        return self._function_effects(candidate) - self._function_effects(source)

    @staticmethod
    def _missing_provenance(source: IRModule, candidate: IRModule) -> int:
        sourced = 0
        for function in source.functions:
            for block in function.blocks:
                sourced += sum(1 for instruction in block.instructions if instruction.provenance)
        preserved = 0
        for function in candidate.functions:
            for block in function.blocks:
                preserved += sum(1 for instruction in block.instructions if instruction.provenance)
        return max(0, sourced - preserved)

    @staticmethod
    def _record(
        pass_id: str,
        source: IRModule,
        candidate: Optional[IRModule],
        committed: IRModule,
        accepted: bool,
        input_report: VerificationReport,
        output_report: Optional[VerificationReport],
        validation: Optional[TranslationValidation],
        reasons: Sequence[str],
        *,
        contract: Optional[PassContract] = None,
        determinism_replay_fingerprint: Optional[str] = None,
        determinism_verified: bool = False,
    ) -> PassRecord:
        return PassRecord(
            pass_id=pass_id,
            source_fingerprint=source.fingerprint,
            candidate_fingerprint=candidate.fingerprint if candidate else None,
            committed_fingerprint=committed.fingerprint,
            committed=accepted,
            input_verification=input_report,
            output_verification=output_report,
            validation=validation,
            rejected_reasons=tuple(reasons),
            determinism_replay_fingerprint=determinism_replay_fingerprint,
            determinism_verified=determinism_verified,
            analysis_contract={} if contract is None else {
                "required": tuple(sorted(item.value for item in contract.required_analyses)),
                "preserved": tuple(sorted(item.value for item in contract.preserved_analyses)),
                "invalidated": tuple(sorted(item.value for item in contract.invalidated_analyses)),
            },
            replay_safe_declared=False if contract is None else contract.replay_safe,
            thread_safe_declared=False if contract is None else contract.thread_safe,
        )


class AbstractValueKind(str, Enum):
    BOTTOM = "bottom"
    CONSTANT = "constant"
    INTERVAL = "interval"
    TOP = "top"


@dataclass(frozen=True)
class AbstractValue:
    """Tiny numeric lattice used for sound, cheap pre-pass reasoning."""

    kind: AbstractValueKind
    constant: Optional[float] = None
    lower: Optional[float] = None
    upper: Optional[float] = None

    @classmethod
    def bottom(cls) -> "AbstractValue":
        return cls(AbstractValueKind.BOTTOM)

    @classmethod
    def top(cls) -> "AbstractValue":
        return cls(AbstractValueKind.TOP)

    @classmethod
    def const(cls, value: float) -> "AbstractValue":
        value = float(value)
        if not math.isfinite(value):
            return cls.top()
        return cls(AbstractValueKind.CONSTANT, constant=value, lower=value, upper=value)

    @classmethod
    def interval(cls, lower: float, upper: float) -> "AbstractValue":
        lower = float(lower)
        upper = float(upper)
        if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
            return cls.top()
        if lower == upper:
            return cls.const(lower)
        return cls(AbstractValueKind.INTERVAL, lower=lower, upper=upper)

    def join(self, other: "AbstractValue") -> "AbstractValue":
        if self.kind == AbstractValueKind.BOTTOM:
            return other
        if other.kind == AbstractValueKind.BOTTOM:
            return self
        if self.kind == AbstractValueKind.TOP or other.kind == AbstractValueKind.TOP:
            return AbstractValue.top()
        assert self.lower is not None and self.upper is not None
        assert other.lower is not None and other.upper is not None
        return AbstractValue.interval(min(self.lower, other.lower), max(self.upper, other.upper))


@dataclass(frozen=True)
class AbstractState:
    values: Mapping[str, AbstractValue] = field(default_factory=dict)

    def get(self, value_id: str) -> AbstractValue:
        return self.values.get(value_id, AbstractValue.top())

    def with_value(self, value_id: str, value: AbstractValue) -> "AbstractState":
        updated = dict(self.values)
        updated[value_id] = value
        return AbstractState(updated)

    def join(self, other: "AbstractState") -> "AbstractState":
        keys = set(self.values) | set(other.values)
        return AbstractState({key: self.get(key).join(other.get(key)) for key in keys})


class NumericAbstractInterpreter:
    """Forward fixed-point interval analysis for the safe numeric core."""

    def analyze(
        self,
        function: FunctionIR,
        *,
        parameter_ranges: Mapping[str, AbstractValue] = {},
        maximum_iterations: int = 128,
    ) -> Mapping[str, AbstractState]:
        cfg = ControlFlowGraph(function)
        states: Dict[str, AbstractState] = {
            label: AbstractState() for label in cfg.reachable
        }
        entry = AbstractState(
            {
                parameter.value_id: parameter_ranges.get(parameter.value_id, AbstractValue.top())
                for parameter in function.parameters
            }
        )
        states[function.entry] = entry
        for _iteration in range(maximum_iterations):
            changed = False
            for label in sorted(cfg.reachable):
                block = cfg.blocks[label]
                state = states[label]
                out = self._transfer_block(block, state)
                for target in cfg.successors.get(label, ()):
                    joined = states[target].join(out)
                    if joined != states[target]:
                        states[target] = joined
                        changed = True
            if not changed:
                return states
        raise RuntimeError("abstract interpretation did not converge within iteration limit")

    def _transfer_block(self, block: BasicBlock, state: AbstractState) -> AbstractState:
        current = state
        for instruction in block.instructions:
            if len(instruction.results) != 1:
                for result in instruction.results:
                    current = current.with_value(result.value_id, AbstractValue.top())
                continue
            value = self._transfer_instruction(instruction, current)
            current = current.with_value(instruction.results[0].value_id, value)
        return current

    def _transfer_instruction(self, instruction: Instruction, state: AbstractState) -> AbstractValue:
        if instruction.opcode == "const":
            value = instruction.attributes.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return AbstractValue.const(float(value))
            return AbstractValue.top()
        operands = [state.get(item) for item in instruction.operands]
        if instruction.opcode == "identity" and operands:
            return operands[0]
        if instruction.opcode == "neg" and operands:
            operand = operands[0]
            if operand.lower is None or operand.upper is None:
                return AbstractValue.top()
            return AbstractValue.interval(-operand.upper, -operand.lower)
        if instruction.opcode in ("add", "sub", "mul") and len(operands) == 2:
            left, right = operands
            if None in (left.lower, left.upper, right.lower, right.upper):
                return AbstractValue.top()
            assert left.lower is not None and left.upper is not None
            assert right.lower is not None and right.upper is not None
            if instruction.opcode == "add":
                return AbstractValue.interval(left.lower + right.lower, left.upper + right.upper)
            if instruction.opcode == "sub":
                return AbstractValue.interval(left.lower - right.upper, left.upper - right.lower)
            products = (
                left.lower * right.lower,
                left.lower * right.upper,
                left.upper * right.lower,
                left.upper * right.upper,
            )
            return AbstractValue.interval(min(products), max(products))
        return AbstractValue.top()
