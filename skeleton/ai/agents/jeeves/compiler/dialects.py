"""Legality-driven dialects and progressive lowering for Jeeves IR.

The design follows the durable ideas in modern multi-level compiler systems:
operations belong to explicit dialects, conversion has a target legality model,
types can be converted independently of rewrites, and a lowering succeeds only
when its requested legality condition is satisfied.  Rewrites are transactional:
the input module is immutable and is returned unchanged on failure.

This is not an MLIR binding.  It is a small semantic substrate specialized for
Jeeves plans, rules, tools, and learned programs while preserving the same
engineering invariants.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from .ir import BasicBlock, FunctionIR, IRModule, IRType, IRVerifier, Instruction


class OperationTrait(str, Enum):
    PURE = "pure"
    TERMINATOR_LIKE = "terminator_like"
    COMMUTATIVE = "commutative"
    ASSOCIATIVE = "associative"
    IDEMPOTENT = "idempotent"
    CONSTANT_LIKE = "constant_like"
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
    SIDE_EFFECTING = "side_effecting"
    NONDETERMINISTIC = "nondeterministic"


@dataclass(frozen=True)
class OperationSchema:
    name: str
    dialect: str
    minimum_operands: int = 0
    maximum_operands: Optional[int] = None
    minimum_results: int = 0
    maximum_results: Optional[int] = None
    traits: frozenset[OperationTrait] = frozenset()
    required_attributes: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.name or not self.dialect:
            raise ValueError("operation name and dialect are required")
        if self.minimum_operands < 0 or self.minimum_results < 0:
            raise ValueError("minimum arities cannot be negative")
        if self.maximum_operands is not None and self.maximum_operands < self.minimum_operands:
            raise ValueError("maximum_operands is below minimum_operands")
        if self.maximum_results is not None and self.maximum_results < self.minimum_results:
            raise ValueError("maximum_results is below minimum_results")

    @property
    def qualified_name(self) -> str:
        return self.dialect + "." + self.name

    def verify(self, instruction: Instruction) -> Tuple[str, ...]:
        failures = []
        operand_count = len(instruction.operands)
        result_count = len(instruction.results)
        if operand_count < self.minimum_operands:
            failures.append("too_few_operands")
        if self.maximum_operands is not None and operand_count > self.maximum_operands:
            failures.append("too_many_operands")
        if result_count < self.minimum_results:
            failures.append("too_few_results")
        if self.maximum_results is not None and result_count > self.maximum_results:
            failures.append("too_many_results")
        missing = self.required_attributes - frozenset(instruction.attributes)
        if missing:
            failures.append("missing_attributes:" + ",".join(sorted(missing)))
        return tuple(failures)


@dataclass(frozen=True)
class Dialect:
    namespace: str
    operations: Tuple[OperationSchema, ...]
    version: int = 1

    def __post_init__(self) -> None:
        if not self.namespace:
            raise ValueError("dialect namespace is required")
        if self.version <= 0:
            raise ValueError("dialect version must be positive")
        names = [item.name for item in self.operations]
        if len(names) != len(set(names)):
            raise ValueError("operation names must be unique within a dialect")
        if any(item.dialect != self.namespace for item in self.operations):
            raise ValueError("operation dialect does not match registry namespace")


class DialectRegistry:
    def __init__(self, dialects: Iterable[Dialect] = ()) -> None:
        self._dialects: Dict[str, Dialect] = {}
        self._schemas: Dict[str, OperationSchema] = {}
        for dialect in dialects:
            self.register(dialect)

    def register(self, dialect: Dialect) -> None:
        previous = self._dialects.get(dialect.namespace)
        if previous is not None and previous != dialect:
            raise ValueError("dialect namespace already registered")
        self._dialects[dialect.namespace] = dialect
        for operation in dialect.operations:
            self._schemas[operation.qualified_name] = operation

    def schema(self, opcode: str) -> Optional[OperationSchema]:
        return self._schemas.get(opcode)

    def verify_instruction(self, instruction: Instruction) -> Tuple[str, ...]:
        schema = self.schema(instruction.opcode)
        if schema is None:
            return ("unregistered_operation",)
        return schema.verify(instruction)

    @property
    def namespaces(self) -> Tuple[str, ...]:
        return tuple(sorted(self._dialects))


class Legality(str, Enum):
    LEGAL = "legal"
    ILLEGAL = "illegal"
    DYNAMIC = "dynamic"
    UNKNOWN = "unknown"


class ConversionMode(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    ANALYSIS = "analysis"


DynamicLegality = Callable[[Instruction], bool]


class ConversionTarget:
    """Explicit operation/dialect legality policy."""

    def __init__(self) -> None:
        self._operations: Dict[str, Legality] = {}
        self._dialects: Dict[str, Legality] = {}
        self._dynamic_operations: Dict[str, DynamicLegality] = {}
        self._dynamic_dialects: Dict[str, DynamicLegality] = {}

    def legal_operation(self, opcode: str) -> "ConversionTarget":
        self._operations[opcode] = Legality.LEGAL
        return self

    def illegal_operation(self, opcode: str) -> "ConversionTarget":
        self._operations[opcode] = Legality.ILLEGAL
        return self

    def dynamic_operation(self, opcode: str, predicate: DynamicLegality) -> "ConversionTarget":
        self._operations[opcode] = Legality.DYNAMIC
        self._dynamic_operations[opcode] = predicate
        return self

    def legal_dialect(self, namespace: str) -> "ConversionTarget":
        self._dialects[namespace] = Legality.LEGAL
        return self

    def illegal_dialect(self, namespace: str) -> "ConversionTarget":
        self._dialects[namespace] = Legality.ILLEGAL
        return self

    def dynamic_dialect(self, namespace: str, predicate: DynamicLegality) -> "ConversionTarget":
        self._dialects[namespace] = Legality.DYNAMIC
        self._dynamic_dialects[namespace] = predicate
        return self

    def classify(self, instruction: Instruction) -> Legality:
        operation_state = self._operations.get(instruction.opcode)
        if operation_state is not None:
            if operation_state == Legality.DYNAMIC:
                predicate = self._dynamic_operations[instruction.opcode]
                return Legality.LEGAL if bool(predicate(instruction)) else Legality.ILLEGAL
            return operation_state
        namespace = instruction.opcode.partition(".")[0]
        dialect_state = self._dialects.get(namespace)
        if dialect_state is None:
            return Legality.UNKNOWN
        if dialect_state == Legality.DYNAMIC:
            predicate = self._dynamic_dialects[namespace]
            return Legality.LEGAL if bool(predicate(instruction)) else Legality.ILLEGAL
        return dialect_state


TypeRule = Callable[[IRType], Optional[IRType]]


class TypeConverter:
    """Ordered type conversion rules with explicit failure."""

    def __init__(self, rules: Sequence[TypeRule] = ()) -> None:
        self._rules = list(rules)

    def add_rule(self, rule: TypeRule) -> None:
        self._rules.append(rule)

    def convert(self, source: IRType) -> Optional[IRType]:
        for rule in reversed(self._rules):
            result = rule(source)
            if result is not None:
                return result
        return source

    def is_legal(self, source: IRType) -> bool:
        converted = self.convert(source)
        return converted is not None and converted == source


@dataclass(frozen=True)
class RewriteResult:
    instructions: Tuple[Instruction, ...]
    rationale: str
    evidence_ids: Tuple[str, ...] = ()


RewriteFunction = Callable[[Instruction, TypeConverter], Optional[RewriteResult]]


@dataclass(frozen=True)
class RewritePattern:
    pattern_id: str
    source_opcode: str
    benefit: int
    rewrite: RewriteFunction = field(compare=False, repr=False)
    evidence_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.pattern_id or not self.source_opcode:
            raise ValueError("pattern id and source opcode are required")


@dataclass(frozen=True)
class ConversionFailure:
    function: str
    block: str
    opcode: str
    reason: str


@dataclass(frozen=True)
class AppliedRewrite:
    pattern_id: str
    source_opcode: str
    replacement_opcodes: Tuple[str, ...]
    function: str
    block: str
    rationale: str
    evidence_ids: Tuple[str, ...]


@dataclass(frozen=True)
class ConversionReport:
    mode: ConversionMode
    input_fingerprint: str
    output_fingerprint: str
    committed: bool
    rewrites: Tuple[AppliedRewrite, ...]
    failures: Tuple[ConversionFailure, ...]
    illegal_remaining: Tuple[Tuple[str, str, str], ...]
    unknown_remaining: Tuple[Tuple[str, str, str], ...]

    @property
    def successful(self) -> bool:
        return self.committed and not self.failures


class DialectConversionEngine:
    """Bounded legalization search with immutable rollback semantics."""

    def __init__(
        self,
        registry: DialectRegistry,
        *,
        verifier: Optional[IRVerifier] = None,
        maximum_pattern_depth: int = 8,
        maximum_generated_instructions: int = 100_000,
    ) -> None:
        if maximum_pattern_depth <= 0 or maximum_generated_instructions <= 0:
            raise ValueError("conversion bounds must be positive")
        self.registry = registry
        self.verifier = verifier or IRVerifier()
        self.maximum_pattern_depth = maximum_pattern_depth
        self.maximum_generated_instructions = maximum_generated_instructions

    def convert(
        self,
        module: IRModule,
        *,
        target: ConversionTarget,
        patterns: Sequence[RewritePattern],
        type_converter: Optional[TypeConverter] = None,
        mode: ConversionMode = ConversionMode.FULL,
    ) -> Tuple[IRModule, ConversionReport]:
        converter = type_converter or TypeConverter()
        input_report = self.verifier.verify(module)
        if not input_report.valid:
            failure = ConversionFailure("<module>", "<module>", "<verify>", "input IR is invalid")
            return module, self._report(module, module, mode, False, (), (failure,), target)

        pattern_map: Dict[str, list[RewritePattern]] = {}
        for pattern in patterns:
            pattern_map.setdefault(pattern.source_opcode, []).append(pattern)
        for values in pattern_map.values():
            values.sort(key=lambda item: (-item.benefit, item.pattern_id))

        if mode == ConversionMode.ANALYSIS:
            failures = self._analysis_failures(module, target, pattern_map)
            committed = not failures
            return module, self._report(module, module, mode, committed, (), failures, target)

        rewrites = []
        failures = []
        generated = 0
        new_functions = []
        for function in module.functions:
            new_blocks = []
            for block in function.blocks:
                instructions = []
                for instruction in block.instructions:
                    legalized, applied, failure = self._legalize_instruction(
                        instruction,
                        target=target,
                        pattern_map=pattern_map,
                        type_converter=converter,
                        function=function.name,
                        block=block.label,
                        depth=0,
                    )
                    if failure is not None:
                        failures.append(failure)
                        if mode == ConversionMode.PARTIAL and target.classify(instruction) == Legality.UNKNOWN:
                            legalized = (instruction,)
                        else:
                            legalized = (instruction,)
                    instructions.extend(legalized)
                    rewrites.extend(applied)
                    generated += len(legalized)
                    if generated > self.maximum_generated_instructions:
                        failures.append(
                            ConversionFailure(
                                function.name,
                                block.label,
                                instruction.opcode,
                                "generated-instruction budget exceeded",
                            )
                        )
                        break
                new_blocks.append(replace(block, instructions=tuple(instructions)))
            new_functions.append(replace(function, blocks=tuple(new_blocks)))

        candidate = replace(module, functions=tuple(new_functions))
        output_report = self.verifier.verify(candidate)
        if not output_report.valid:
            failures.append(
                ConversionFailure("<module>", "<module>", "<verify>", "converted IR failed verification")
            )

        illegal, unknown = self._remaining(candidate, target)
        if illegal:
            failures.append(
                ConversionFailure("<module>", "<module>", "<legality>", "illegal operations remain")
            )
        if mode == ConversionMode.FULL and unknown:
            failures.append(
                ConversionFailure("<module>", "<module>", "<legality>", "unknown operations remain in full conversion")
            )
        committed = not failures
        result = candidate if committed else module
        return result, ConversionReport(
            mode=mode,
            input_fingerprint=module.fingerprint,
            output_fingerprint=result.fingerprint,
            committed=committed,
            rewrites=tuple(rewrites) if committed else tuple(),
            failures=tuple(failures),
            illegal_remaining=illegal,
            unknown_remaining=unknown,
        )

    def _legalize_instruction(
        self,
        instruction: Instruction,
        *,
        target: ConversionTarget,
        pattern_map: Mapping[str, Sequence[RewritePattern]],
        type_converter: TypeConverter,
        function: str,
        block: str,
        depth: int,
    ) -> Tuple[Tuple[Instruction, ...], Tuple[AppliedRewrite, ...], Optional[ConversionFailure]]:
        state = target.classify(instruction)
        if state == Legality.LEGAL:
            return (instruction,), (), None
        if state == Legality.UNKNOWN:
            return (instruction,), (), ConversionFailure(function, block, instruction.opcode, "operation legality is unknown")
        if depth >= self.maximum_pattern_depth:
            return (instruction,), (), ConversionFailure(function, block, instruction.opcode, "legalization depth exceeded")

        candidates = pattern_map.get(instruction.opcode, ())
        if not candidates:
            return (instruction,), (), ConversionFailure(function, block, instruction.opcode, "no legalization pattern")

        original_results = frozenset(item.value_id for item in instruction.results)
        for pattern in candidates:
            try:
                rewritten = pattern.rewrite(instruction, type_converter)
            except Exception:
                continue
            if rewritten is None or not rewritten.instructions:
                continue
            replacement_results = frozenset(
                result.value_id
                for replacement in rewritten.instructions
                for result in replacement.results
            )
            if not original_results.issubset(replacement_results):
                continue
            legalized = []
            applied = []
            failed = False
            for replacement in rewritten.instructions:
                child, child_applied, child_failure = self._legalize_instruction(
                    replacement,
                    target=target,
                    pattern_map=pattern_map,
                    type_converter=type_converter,
                    function=function,
                    block=block,
                    depth=depth + 1,
                )
                if child_failure is not None:
                    failed = True
                    break
                legalized.extend(child)
                applied.extend(child_applied)
            if failed:
                continue
            applied.insert(
                0,
                AppliedRewrite(
                    pattern_id=pattern.pattern_id,
                    source_opcode=instruction.opcode,
                    replacement_opcodes=tuple(item.opcode for item in rewritten.instructions),
                    function=function,
                    block=block,
                    rationale=rewritten.rationale,
                    evidence_ids=tuple(sorted(set(pattern.evidence_ids + rewritten.evidence_ids))),
                ),
            )
            return tuple(legalized), tuple(applied), None
        return (instruction,), (), ConversionFailure(function, block, instruction.opcode, "all legalization patterns failed")

    def _analysis_failures(
        self,
        module: IRModule,
        target: ConversionTarget,
        pattern_map: Mapping[str, Sequence[RewritePattern]],
    ) -> Tuple[ConversionFailure, ...]:
        failures = []
        for function in module.functions:
            for block in function.blocks:
                for instruction in block.instructions:
                    state = target.classify(instruction)
                    if state == Legality.ILLEGAL and not pattern_map.get(instruction.opcode):
                        failures.append(
                            ConversionFailure(
                                function.name,
                                block.label,
                                instruction.opcode,
                                "illegal operation has no candidate legalization pattern",
                            )
                        )
        return tuple(failures)

    @staticmethod
    def _remaining(
        module: IRModule,
        target: ConversionTarget,
    ) -> Tuple[Tuple[Tuple[str, str, str], ...], Tuple[Tuple[str, str, str], ...]]:
        illegal = []
        unknown = []
        for function in module.functions:
            for block in function.blocks:
                for instruction in block.instructions:
                    state = target.classify(instruction)
                    record = (function.name, block.label, instruction.opcode)
                    if state == Legality.ILLEGAL:
                        illegal.append(record)
                    elif state == Legality.UNKNOWN:
                        unknown.append(record)
        return tuple(illegal), tuple(unknown)

    def _report(
        self,
        source: IRModule,
        result: IRModule,
        mode: ConversionMode,
        committed: bool,
        rewrites: Sequence[AppliedRewrite],
        failures: Sequence[ConversionFailure],
        target: ConversionTarget,
    ) -> ConversionReport:
        illegal, unknown = self._remaining(result, target)
        return ConversionReport(
            mode=mode,
            input_fingerprint=source.fingerprint,
            output_fingerprint=result.fingerprint,
            committed=committed,
            rewrites=tuple(rewrites),
            failures=tuple(failures),
            illegal_remaining=illegal,
            unknown_remaining=unknown,
        )
