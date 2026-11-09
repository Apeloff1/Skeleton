"""A provenance-bearing multi-level intermediate representation for Jeeves.

This is not a text prompt format.  It is the compiler substrate for plans,
reasoning programs, tool workflows, learned rules, causal decisions, and
reconstructed artifacts.

The design borrows durable compiler ideas rather than copying one implementation:

* SSA-like single definitions and explicit block arguments/phi nodes;
* control-flow graphs with explicit terminators;
* typed values and a conservative ``UNKNOWN`` type;
* effect summaries so transformations cannot move external mutations as if they
  were pure arithmetic;
* dialect/stage information so high-level semantics can be lowered through
  multiple representations instead of flattened in one step;
* source/provenance records and information-loss markers;
* deterministic fingerprints suitable for replay and translation validation.

A model may propose IR.  Host validation decides whether it is structurally
admissible.  Unknown operations and uncertain reconstructions remain explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum, IntEnum
from typing import Any, Iterable, Mapping, Sequence

from .types import AgentContractError, bounded_text, json_safe, require_id, stable_fingerprint


class IRValidationError(AgentContractError):
    pass


class IRStage(IntEnum):
    SOURCE_SEMANTIC = 0
    CANONICAL = 1
    CONTROL = 2
    EXECUTION = 3
    VERIFIED_EXECUTION = 4


class Dialect(str, Enum):
    JEEVES_SEMANTIC = "jeeves.semantic"
    JEEVES_CONTROL = "jeeves.control"
    JEEVES_MEMORY = "jeeves.memory"
    JEEVES_EVIDENCE = "jeeves.evidence"
    JEEVES_CAUSAL = "jeeves.causal"
    JEEVES_TOOL = "jeeves.tool"
    JEEVES_MODEL = "jeeves.model"
    CORE = "core"
    UNKNOWN = "unknown"


class IRType(str, Enum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    JSON = "json"
    UNIT = "unit"
    EVIDENCE = "evidence"
    MEMORY = "memory"
    BELIEF = "belief"
    ACTION = "action"
    PLAN = "plan"
    DISTRIBUTION = "distribution"
    EFFECT_TOKEN = "effect_token"
    UNKNOWN = "unknown"


class Effect(str, Enum):
    PURE = "pure"
    CONTROL = "control"
    READ_MEMORY = "read_memory"
    WRITE_MEMORY = "write_memory"
    READ_CONTEXT = "read_context"
    READ_EVIDENCE = "read_evidence"
    WRITE_EVIDENCE = "write_evidence"
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    EXTERNAL_MUTATION = "external_mutation"
    NONDETERMINISTIC = "nondeterministic"
    ASSERTION = "assertion"
    UNKNOWN = "unknown"


class OpCode(str, Enum):
    CONST = "const"
    COPY = "copy"
    PHI = "phi"
    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    DIV = "div"
    AND = "and"
    OR = "or"
    NOT = "not"
    EQ = "eq"
    LT = "lt"
    LE = "le"
    GT = "gt"
    GE = "ge"
    SELECT = "select"
    PACK = "pack"
    UNPACK = "unpack"
    READ_CONTEXT = "read_context"
    READ_MEMORY = "read_memory"
    WRITE_MEMORY = "write_memory"
    QUERY_EVIDENCE = "query_evidence"
    EMIT_EVIDENCE = "emit_evidence"
    CAUSAL_QUERY = "causal_query"
    MODEL_INFER = "model_infer"
    TOOL_CALL = "tool_call"
    ASSERT = "assert"
    ASSUME = "assume"
    BRANCH = "branch"
    JUMP = "jump"
    RETURN = "return"
    EFFECT_FENCE = "effect_fence"
    UNKNOWN = "unknown"


TERMINATORS = frozenset({OpCode.BRANCH, OpCode.JUMP, OpCode.RETURN})


@dataclass(frozen=True, slots=True)
class SourceOrigin:
    origin_id: str
    source_kind: str
    source_ref: str
    start: int | None = None
    end: int | None = None
    confidence: float = 1.0
    reconstructed: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "origin_id", require_id("origin_id", self.origin_id))
        object.__setattr__(self, "source_kind", bounded_text("source_kind", self.source_kind, maximum=128))
        object.__setattr__(self, "source_ref", bounded_text("source_ref", self.source_ref, maximum=4096))
        if self.start is not None and (isinstance(self.start, bool) or not isinstance(self.start, int) or self.start < 0):
            raise IRValidationError("origin start must be non-negative integer")
        if self.end is not None and (isinstance(self.end, bool) or not isinstance(self.end, int) or self.end < 0):
            raise IRValidationError("origin end must be non-negative integer")
        if self.start is not None and self.end is not None and self.end < self.start:
            raise IRValidationError("origin range is reversed")
        confidence = float(self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise IRValidationError("origin confidence must be in [0,1]")
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ValueRef:
    value_id: str
    type: IRType

    def __post_init__(self) -> None:
        object.__setattr__(self, "value_id", require_id("value_id", self.value_id))
        if not isinstance(self.type, IRType):
            object.__setattr__(self, "type", IRType(str(self.type)))


@dataclass(frozen=True, slots=True)
class Operation:
    op_id: str
    opcode: OpCode
    dialect: Dialect
    operands: tuple[str, ...] = ()
    results: tuple[ValueRef, ...] = ()
    effects: tuple[Effect, ...] = (Effect.PURE,)
    attributes: Mapping[str, Any] = field(default_factory=dict)
    origins: tuple[SourceOrigin, ...] = ()
    information_loss: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "op_id", require_id("op_id", self.op_id))
        if not isinstance(self.opcode, OpCode):
            object.__setattr__(self, "opcode", OpCode(str(self.opcode)))
        if not isinstance(self.dialect, Dialect):
            object.__setattr__(self, "dialect", Dialect(str(self.dialect)))
        operands = tuple(require_id("operand", operand) for operand in self.operands)
        object.__setattr__(self, "operands", operands)
        results = tuple(self.results)
        if any(not isinstance(result, ValueRef) for result in results):
            raise IRValidationError("operation results must be ValueRef values")
        if len({result.value_id for result in results}) != len(results):
            raise IRValidationError("operation defines duplicate result ids")
        object.__setattr__(self, "results", results)
        effects = tuple(effect if isinstance(effect, Effect) else Effect(str(effect)) for effect in self.effects)
        if not effects:
            effects = (Effect.PURE,)
        if Effect.PURE in effects and len(effects) > 1:
            raise IRValidationError("pure cannot be combined with side effects")
        object.__setattr__(self, "effects", tuple(sorted(set(effects), key=lambda item: item.value)))
        object.__setattr__(self, "attributes", json_safe(dict(self.attributes)))
        origins = tuple(self.origins)
        if any(not isinstance(origin, SourceOrigin) for origin in origins):
            raise IRValidationError("operation origins must be SourceOrigin values")
        object.__setattr__(self, "origins", origins)
        object.__setattr__(self, "information_loss", tuple(str(item) for item in self.information_loss if str(item)))
        if self.opcode in TERMINATORS and self.results:
            raise IRValidationError("terminator cannot define SSA results")
        if self.opcode is OpCode.CONST and "value" not in self.attributes:
            raise IRValidationError("const operation requires value attribute")
        if self.opcode is OpCode.PHI:
            incoming = self.attributes.get("incoming")
            if not isinstance(incoming, list) or not incoming:
                raise IRValidationError("phi operation requires non-empty incoming attribute")

    @property
    def is_pure(self) -> bool:
        return self.effects == (Effect.PURE,)

    @property
    def is_terminator(self) -> bool:
        return self.opcode in TERMINATORS

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "id": self.op_id,
                "opcode": self.opcode.value,
                "dialect": self.dialect.value,
                "operands": self.operands,
                "results": [(result.value_id, result.type.value) for result in self.results],
                "effects": [effect.value for effect in self.effects],
                "attributes": self.attributes,
                "origins": [
                    {
                        "id": origin.origin_id,
                        "kind": origin.source_kind,
                        "ref": origin.source_ref,
                        "start": origin.start,
                        "end": origin.end,
                        "confidence": origin.confidence,
                        "reconstructed": origin.reconstructed,
                    }
                    for origin in self.origins
                ],
                "loss": self.information_loss,
            }
        )


@dataclass(frozen=True, slots=True)
class BasicBlock:
    block_id: str
    operations: tuple[Operation, ...]
    predecessors_hint: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_id", require_id("block_id", self.block_id))
        operations = tuple(self.operations)
        if not operations:
            raise IRValidationError("basic block must contain at least a terminator")
        if any(not isinstance(operation, Operation) for operation in operations):
            raise IRValidationError("basic block operations must be Operation values")
        if not operations[-1].is_terminator:
            raise IRValidationError(f"block {self.block_id} lacks terminator")
        if any(operation.is_terminator for operation in operations[:-1]):
            raise IRValidationError(f"block {self.block_id} has non-final terminator")
        object.__setattr__(self, "operations", operations)
        object.__setattr__(self, "predecessors_hint", tuple(sorted({require_id("predecessor", item) for item in self.predecessors_hint})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def terminator(self) -> Operation:
        return self.operations[-1]

    def successors(self) -> tuple[str, ...]:
        term = self.terminator
        if term.opcode is OpCode.RETURN:
            return ()
        if term.opcode is OpCode.JUMP:
            target = term.attributes.get("target")
            if not isinstance(target, str) or not target:
                raise IRValidationError(f"jump {term.op_id} lacks target")
            return (target,)
        if term.opcode is OpCode.BRANCH:
            true_target = term.attributes.get("true_target")
            false_target = term.attributes.get("false_target")
            if not isinstance(true_target, str) or not isinstance(false_target, str) or not true_target or not false_target:
                raise IRValidationError(f"branch {term.op_id} lacks targets")
            if len(term.operands) != 1:
                raise IRValidationError(f"branch {term.op_id} requires one condition operand")
            return (true_target, false_target)
        raise IRValidationError(f"unsupported terminator {term.opcode.value}")

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "id": self.block_id,
                "operations": [operation.fingerprint for operation in self.operations],
                "pred_hint": self.predecessors_hint,
                "metadata": self.metadata,
            }
        )


@dataclass(frozen=True, slots=True)
class IRFunction:
    function_id: str
    arguments: tuple[ValueRef, ...]
    return_types: tuple[IRType, ...]
    blocks: tuple[BasicBlock, ...]
    entry_block: str
    stage: IRStage = IRStage.SOURCE_SEMANTIC
    dialects: tuple[Dialect, ...] = (Dialect.CORE,)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "function_id", require_id("function_id", self.function_id))
        arguments = tuple(self.arguments)
        if any(not isinstance(argument, ValueRef) for argument in arguments):
            raise IRValidationError("function arguments must be ValueRef values")
        if len({argument.value_id for argument in arguments}) != len(arguments):
            raise IRValidationError("duplicate function argument ids")
        object.__setattr__(self, "arguments", arguments)
        return_types = tuple(item if isinstance(item, IRType) else IRType(str(item)) for item in self.return_types)
        object.__setattr__(self, "return_types", return_types)
        blocks = tuple(self.blocks)
        if not blocks:
            raise IRValidationError("function requires blocks")
        if any(not isinstance(block, BasicBlock) for block in blocks):
            raise IRValidationError("function blocks must be BasicBlock values")
        if len({block.block_id for block in blocks}) != len(blocks):
            raise IRValidationError("duplicate block ids")
        object.__setattr__(self, "blocks", blocks)
        object.__setattr__(self, "entry_block", require_id("entry_block", self.entry_block))
        if not isinstance(self.stage, IRStage):
            object.__setattr__(self, "stage", IRStage(int(self.stage)))
        dialects = tuple(dialect if isinstance(dialect, Dialect) else Dialect(str(dialect)) for dialect in self.dialects)
        object.__setattr__(self, "dialects", tuple(sorted(set(dialects), key=lambda item: item.value)))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))
        self.validate()

    def block_map(self) -> dict[str, BasicBlock]:
        return {block.block_id: block for block in self.blocks}

    def predecessors(self) -> dict[str, tuple[str, ...]]:
        result: dict[str, list[str]] = {block.block_id: [] for block in self.blocks}
        for block in self.blocks:
            for successor in block.successors():
                if successor not in result:
                    raise IRValidationError(f"block {block.block_id} targets unknown block {successor}")
                result[successor].append(block.block_id)
        return {key: tuple(sorted(values)) for key, values in result.items()}

    def definition_map(self) -> dict[str, tuple[str, str, IRType]]:
        definitions: dict[str, tuple[str, str, IRType]] = {
            argument.value_id: ("<argument>", "<argument>", argument.type) for argument in self.arguments
        }
        for block in self.blocks:
            for operation in block.operations:
                for result in operation.results:
                    if result.value_id in definitions:
                        raise IRValidationError(f"SSA value {result.value_id} defined more than once")
                    definitions[result.value_id] = (block.block_id, operation.op_id, result.type)
        return definitions

    def validate(self) -> None:
        block_map = self.block_map()
        if self.entry_block not in block_map:
            raise IRValidationError("entry block is missing")
        definitions = self.definition_map()
        predecessors = self.predecessors()
        operation_ids: set[str] = set()
        for block in self.blocks:
            if block.predecessors_hint and tuple(sorted(block.predecessors_hint)) != predecessors[block.block_id]:
                raise IRValidationError(f"predecessor hint mismatch for block {block.block_id}")
            seen_non_phi = False
            for operation in block.operations:
                if operation.op_id in operation_ids:
                    raise IRValidationError(f"duplicate operation id {operation.op_id}")
                operation_ids.add(operation.op_id)
                if operation.opcode is OpCode.PHI:
                    if seen_non_phi:
                        raise IRValidationError("phi operations must appear before non-phi operations")
                    incoming = operation.attributes["incoming"]
                    incoming_blocks = {str(item[0]) for item in incoming if isinstance(item, list) and len(item) == 2}
                    if incoming_blocks != set(predecessors[block.block_id]):
                        raise IRValidationError(f"phi predecessor set mismatch in {operation.op_id}")
                    incoming_values = [str(item[1]) for item in incoming if isinstance(item, list) and len(item) == 2]
                    if any(value not in definitions for value in incoming_values):
                        raise IRValidationError(f"phi {operation.op_id} references undefined value")
                else:
                    seen_non_phi = True
                for operand in operation.operands:
                    if operand not in definitions:
                        raise IRValidationError(f"operation {operation.op_id} references undefined value {operand}")
            term = block.terminator
            if term.opcode is OpCode.RETURN:
                if len(term.operands) != len(self.return_types):
                    raise IRValidationError(f"return arity mismatch in block {block.block_id}")
                for operand, expected in zip(term.operands, self.return_types):
                    actual = definitions[operand][2]
                    if expected is not IRType.UNKNOWN and actual not in {expected, IRType.UNKNOWN}:
                        raise IRValidationError(f"return type mismatch: expected {expected.value}, got {actual.value}")

        # Reachability is an invariant. Unreachable blocks often indicate a bad
        # reconstruction or an incomplete transform and must be explicitly
        # retained as loss metadata instead of silently ignored.
        reachable: set[str] = set()
        frontier = [self.entry_block]
        while frontier:
            current = frontier.pop()
            if current in reachable:
                continue
            reachable.add(current)
            frontier.extend(block_map[current].successors())
        unreachable = set(block_map) - reachable
        if unreachable:
            raise IRValidationError(f"function contains unreachable blocks: {sorted(unreachable)}")

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "id": self.function_id,
                "arguments": [(arg.value_id, arg.type.value) for arg in self.arguments],
                "returns": [item.value for item in self.return_types],
                "blocks": [block.fingerprint for block in self.blocks],
                "entry": self.entry_block,
                "stage": int(self.stage),
                "dialects": [dialect.value for dialect in self.dialects],
                "metadata": self.metadata,
            }
        )

    def with_blocks(self, blocks: Sequence[BasicBlock], *, stage: IRStage | None = None, metadata: Mapping[str, Any] | None = None) -> "IRFunction":
        return replace(
            self,
            blocks=tuple(blocks),
            stage=self.stage if stage is None else stage,
            metadata=dict(self.metadata) if metadata is None else dict(metadata),
        )


@dataclass(frozen=True, slots=True)
class IRModule:
    module_id: str
    functions: tuple[IRFunction, ...]
    ir_version: str = "2026.1"
    target_profile: str = "jeeves-host"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "module_id", require_id("module_id", self.module_id))
        functions = tuple(self.functions)
        if not functions:
            raise IRValidationError("module requires functions")
        if any(not isinstance(function, IRFunction) for function in functions):
            raise IRValidationError("module functions must be IRFunction values")
        if len({function.function_id for function in functions}) != len(functions):
            raise IRValidationError("duplicate function ids")
        object.__setattr__(self, "functions", functions)
        object.__setattr__(self, "ir_version", bounded_text("ir_version", self.ir_version, maximum=64))
        object.__setattr__(self, "target_profile", bounded_text("target_profile", self.target_profile, maximum=256))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "module": self.module_id,
                "functions": [function.fingerprint for function in self.functions],
                "version": self.ir_version,
                "target": self.target_profile,
                "metadata": self.metadata,
            }
        )

    def function(self, function_id: str) -> IRFunction:
        for function in self.functions:
            if function.function_id == function_id:
                return function
        raise KeyError(function_id)


def replace_operation(function: IRFunction, op_id: str, replacement: Sequence[Operation]) -> IRFunction:
    """Pure utility used by compiler passes; validation occurs on construction."""
    found = False
    blocks: list[BasicBlock] = []
    for block in function.blocks:
        operations: list[Operation] = []
        for operation in block.operations:
            if operation.op_id == op_id:
                if operation.is_terminator and (not replacement or not replacement[-1].is_terminator):
                    raise IRValidationError("terminator replacement must end in terminator")
                operations.extend(replacement)
                found = True
            else:
                operations.append(operation)
        blocks.append(replace(block, operations=tuple(operations)))
    if not found:
        raise KeyError(op_id)
    return function.with_blocks(blocks)
