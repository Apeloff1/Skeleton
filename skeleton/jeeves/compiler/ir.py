"""Provenance-bearing SSA intermediate representation for Jeeves.

The IR is intentionally small.  Its purpose is to make semantic claims about
plans, learned rules, tool programs, and recovered programs explicit enough to
verify.  It borrows enduring compiler ideas -- typed SSA, CFGs, explicit
side-effects, source provenance, structural verification -- without pretending
to be a machine-code backend.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Iterable, Mapping, Optional, Sequence, Set, Tuple


class Effect(str, Enum):
    PURE = "pure"
    READ_MEMORY = "read_memory"
    WRITE_MEMORY = "write_memory"
    READ_EVIDENCE = "read_evidence"
    WRITE_EVIDENCE = "write_evidence"
    TOOL = "tool"
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    PROCESS = "process"
    NONDETERMINISTIC = "nondeterministic"
    PRIVILEGED = "privileged"
    MODEL_CALL = "model_call"
    UNKNOWN = "unknown"


class TerminatorKind(str, Enum):
    RETURN = "return"
    JUMP = "jump"
    BRANCH = "branch"
    FAIL = "fail"
    UNREACHABLE = "unreachable"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_json_value(item) for item in value)
    if hasattr(value, "as_json"):
        return _json_value(value.as_json())
    raise TypeError("value is not canonically serializable: %s" % type(value).__name__)


def _fingerprint(prefix: str, payload: Any) -> str:
    encoded = json.dumps(_json_value(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return prefix + ":" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IRType:
    name: str
    parameters: Tuple["IRType", ...] = ()
    nullable: bool = False

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 256:
            raise ValueError("IR type name must be non-empty and bounded")

    def as_json(self) -> Mapping[str, Any]:
        return {
            "name": self.name,
            "parameters": [item.as_json() for item in self.parameters],
            "nullable": self.nullable,
        }


@dataclass(frozen=True)
class SourceProvenance:
    artifact_id: str
    start: Optional[int] = None
    end: Optional[int] = None
    confidence: float = 1.0
    evidence_ids: Tuple[str, ...] = ()
    transformation_chain: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.artifact_id:
            raise ValueError("artifact_id must be non-empty")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("provenance confidence must be in [0, 1]")
        if self.start is not None and self.start < 0:
            raise ValueError("source start cannot be negative")
        if self.end is not None and self.end < 0:
            raise ValueError("source end cannot be negative")
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("source end cannot precede start")

    def transformed(self, pass_id: str, *, confidence_factor: float = 1.0) -> "SourceProvenance":
        if not 0.0 <= confidence_factor <= 1.0:
            raise ValueError("confidence_factor must be in [0, 1]")
        return SourceProvenance(
            artifact_id=self.artifact_id,
            start=self.start,
            end=self.end,
            confidence=self.confidence * confidence_factor,
            evidence_ids=self.evidence_ids,
            transformation_chain=self.transformation_chain + (pass_id,),
        )

    def as_json(self) -> Mapping[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "start": self.start,
            "end": self.end,
            "confidence": round(float(self.confidence), 12),
            "evidence_ids": list(self.evidence_ids),
            "transformation_chain": list(self.transformation_chain),
        }


@dataclass(frozen=True)
class SSAValue:
    value_id: str
    value_type: IRType

    def __post_init__(self) -> None:
        if not self.value_id or len(self.value_id) > 256:
            raise ValueError("SSA value id must be non-empty and bounded")

    def as_json(self) -> Mapping[str, Any]:
        return {"id": self.value_id, "type": self.value_type.as_json()}


@dataclass(frozen=True)
class Instruction:
    opcode: str
    results: Tuple[SSAValue, ...] = ()
    operands: Tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)
    effects: FrozenSet[Effect] = frozenset({Effect.PURE})
    provenance: Tuple[SourceProvenance, ...] = ()

    def __post_init__(self) -> None:
        if not self.opcode or len(self.opcode) > 256:
            raise ValueError("opcode must be non-empty and bounded")
        if Effect.PURE in self.effects and len(self.effects) > 1:
            raise ValueError("PURE cannot be combined with side effects")
        _json_value(self.attributes)

    def as_json(self) -> Mapping[str, Any]:
        return {
            "opcode": self.opcode,
            "results": [item.as_json() for item in self.results],
            "operands": list(self.operands),
            "attributes": _json_value(self.attributes),
            "effects": sorted(effect.value for effect in self.effects),
            "provenance": [item.as_json() for item in self.provenance],
        }


@dataclass(frozen=True)
class Terminator:
    kind: TerminatorKind
    operands: Tuple[str, ...] = ()
    targets: Tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)
    provenance: Tuple[SourceProvenance, ...] = ()

    def __post_init__(self) -> None:
        if self.kind == TerminatorKind.JUMP and len(self.targets) != 1:
            raise ValueError("jump terminator requires exactly one target")
        if self.kind == TerminatorKind.BRANCH and len(self.targets) < 2:
            raise ValueError("branch terminator requires at least two targets")
        if self.kind in (TerminatorKind.RETURN, TerminatorKind.FAIL, TerminatorKind.UNREACHABLE) and self.targets:
            raise ValueError("terminal terminator cannot have targets")
        _json_value(self.attributes)

    def as_json(self) -> Mapping[str, Any]:
        return {
            "kind": self.kind.value,
            "operands": list(self.operands),
            "targets": list(self.targets),
            "attributes": _json_value(self.attributes),
            "provenance": [item.as_json() for item in self.provenance],
        }


@dataclass(frozen=True)
class BasicBlock:
    label: str
    arguments: Tuple[SSAValue, ...] = ()
    instructions: Tuple[Instruction, ...] = ()
    terminator: Terminator = field(default_factory=lambda: Terminator(TerminatorKind.UNREACHABLE))

    def __post_init__(self) -> None:
        if not self.label or len(self.label) > 256:
            raise ValueError("block label must be non-empty and bounded")

    def as_json(self) -> Mapping[str, Any]:
        return {
            "label": self.label,
            "arguments": [item.as_json() for item in self.arguments],
            "instructions": [item.as_json() for item in self.instructions],
            "terminator": self.terminator.as_json(),
        }


@dataclass(frozen=True)
class FunctionIR:
    name: str
    parameters: Tuple[SSAValue, ...]
    return_types: Tuple[IRType, ...]
    blocks: Tuple[BasicBlock, ...]
    entry: str
    declared_effects: FrozenSet[Effect] = frozenset({Effect.PURE})
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("function name must be non-empty")
        if Effect.PURE in self.declared_effects and len(self.declared_effects) > 1:
            raise ValueError("PURE cannot be combined with declared side effects")
        _json_value(self.attributes)

    def as_json(self) -> Mapping[str, Any]:
        return {
            "name": self.name,
            "parameters": [item.as_json() for item in self.parameters],
            "return_types": [item.as_json() for item in self.return_types],
            "blocks": [item.as_json() for item in self.blocks],
            "entry": self.entry,
            "declared_effects": sorted(effect.value for effect in self.declared_effects),
            "attributes": _json_value(self.attributes),
        }

    @property
    def fingerprint(self) -> str:
        return _fingerprint("function", self.as_json())


@dataclass(frozen=True)
class IRModule:
    functions: Tuple[FunctionIR, ...]
    dialect: str = "jeeves.semantic"
    schema_version: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.dialect:
            raise ValueError("dialect must be non-empty")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive")
        _json_value(self.metadata)

    def as_json(self) -> Mapping[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dialect": self.dialect,
            "functions": [item.as_json() for item in self.functions],
            "metadata": _json_value(self.metadata),
        }

    @property
    def fingerprint(self) -> str:
        return _fingerprint("module", self.as_json())


@dataclass(frozen=True)
class IRDiagnostic:
    code: str
    message: str
    severity: Severity
    function: Optional[str] = None
    block: Optional[str] = None
    value_id: Optional[str] = None


@dataclass(frozen=True)
class VerificationReport:
    diagnostics: Tuple[IRDiagnostic, ...]
    module_fingerprint: str

    @property
    def valid(self) -> bool:
        return not any(item.severity == Severity.ERROR for item in self.diagnostics)

    @property
    def errors(self) -> Tuple[IRDiagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.severity == Severity.ERROR)


class ControlFlowGraph:
    """Deterministic CFG and dominance queries for one function."""

    def __init__(self, function: FunctionIR) -> None:
        self.function = function
        self.blocks = {block.label: block for block in function.blocks}
        self.successors: Dict[str, Tuple[str, ...]] = {
            block.label: tuple(block.terminator.targets) for block in function.blocks
        }
        predecessor_sets: Dict[str, Set[str]] = {label: set() for label in self.blocks}
        for source, targets in self.successors.items():
            for target in targets:
                if target in predecessor_sets:
                    predecessor_sets[target].add(source)
        self.predecessors: Dict[str, Tuple[str, ...]] = {
            label: tuple(sorted(items)) for label, items in predecessor_sets.items()
        }
        self.reachable = self._reachable()
        self.dominators = self._dominators()

    def _reachable(self) -> FrozenSet[str]:
        if self.function.entry not in self.blocks:
            return frozenset()
        seen: Set[str] = set()
        stack = [self.function.entry]
        while stack:
            current = stack.pop()
            if current in seen or current not in self.blocks:
                continue
            seen.add(current)
            stack.extend(reversed(self.successors.get(current, ())))
        return frozenset(seen)

    def _dominators(self) -> Mapping[str, FrozenSet[str]]:
        labels = set(self.reachable)
        if not labels:
            return {}
        dom: Dict[str, Set[str]] = {label: set(labels) for label in labels}
        dom[self.function.entry] = {self.function.entry}
        changed = True
        while changed:
            changed = False
            for label in sorted(labels):
                if label == self.function.entry:
                    continue
                preds = [pred for pred in self.predecessors.get(label, ()) if pred in labels]
                if not preds:
                    new = {label}
                else:
                    common = set(dom[preds[0]])
                    for pred in preds[1:]:
                        common.intersection_update(dom[pred])
                    new = common | {label}
                if new != dom[label]:
                    dom[label] = new
                    changed = True
        return {label: frozenset(items) for label, items in dom.items()}

    def dominates(self, candidate: str, block: str) -> bool:
        return candidate in self.dominators.get(block, frozenset())


class IRVerifier:
    """Structural, SSA, dominance, return, and effect verifier."""

    def verify(self, module: IRModule) -> VerificationReport:
        diagnostics = []
        names = set()
        for function in module.functions:
            if function.name in names:
                diagnostics.append(self._error("duplicate_function", "duplicate function name", function=function.name))
                continue
            names.add(function.name)
            diagnostics.extend(self._verify_function(function))
        return VerificationReport(tuple(diagnostics), module.fingerprint)

    def _verify_function(self, function: FunctionIR) -> Sequence[IRDiagnostic]:
        diagnostics = []
        labels = [block.label for block in function.blocks]
        label_set = set(labels)
        if len(labels) != len(label_set):
            diagnostics.append(self._error("duplicate_block", "block labels must be unique", function=function.name))
        if function.entry not in label_set:
            diagnostics.append(self._error("missing_entry", "entry block does not exist", function=function.name))
            return diagnostics

        cfg = ControlFlowGraph(function)
        for block in function.blocks:
            for target in block.terminator.targets:
                if target not in label_set:
                    diagnostics.append(self._error("invalid_target", "terminator targets missing block", function=function.name, block=block.label))
            if block.label not in cfg.reachable:
                diagnostics.append(IRDiagnostic("unreachable_block", "block is unreachable from entry", Severity.WARNING, function=function.name, block=block.label))

        definitions: Dict[str, Tuple[str, int, IRType, bool]] = {}
        for parameter in function.parameters:
            if parameter.value_id in definitions:
                diagnostics.append(self._error("duplicate_value", "duplicate SSA value", function=function.name, value_id=parameter.value_id))
            definitions[parameter.value_id] = (function.entry, -10_000, parameter.value_type, True)

        for block in function.blocks:
            for argument in block.arguments:
                if argument.value_id in definitions:
                    diagnostics.append(self._error("duplicate_value", "duplicate SSA value", function=function.name, block=block.label, value_id=argument.value_id))
                definitions[argument.value_id] = (block.label, -1, argument.value_type, False)
            for index, instruction in enumerate(block.instructions):
                for result in instruction.results:
                    if result.value_id in definitions:
                        diagnostics.append(self._error("duplicate_value", "duplicate SSA value", function=function.name, block=block.label, value_id=result.value_id))
                    definitions[result.value_id] = (block.label, index, result.value_type, False)

        for block in function.blocks:
            for index, instruction in enumerate(block.instructions):
                diagnostics.extend(self._verify_operands(function, cfg, definitions, block.label, index, instruction.operands))
            diagnostics.extend(self._verify_operands(function, cfg, definitions, block.label, len(block.instructions), block.terminator.operands))

            if block.terminator.kind == TerminatorKind.RETURN:
                actual_types = []
                for operand in block.terminator.operands:
                    definition = definitions.get(operand)
                    if definition is not None:
                        actual_types.append(definition[2])
                if len(actual_types) != len(function.return_types):
                    diagnostics.append(self._error("return_arity", "return operand count differs from function return types", function=function.name, block=block.label))
                elif tuple(actual_types) != tuple(function.return_types):
                    diagnostics.append(self._error("return_type", "return operand types differ from function return types", function=function.name, block=block.label))

        observed_effects: Set[Effect] = set()
        for block in function.blocks:
            for instruction in block.instructions:
                observed_effects.update(effect for effect in instruction.effects if effect != Effect.PURE)
        declared = set(effect for effect in function.declared_effects if effect != Effect.PURE)
        missing = observed_effects - declared
        if missing:
            diagnostics.append(self._error("undeclared_effect", "function performs undeclared effects: %s" % ",".join(sorted(item.value for item in missing)), function=function.name))
        if not observed_effects and function.declared_effects != frozenset({Effect.PURE}):
            diagnostics.append(IRDiagnostic("overdeclared_effect", "function declares effects not observed in the current IR", Severity.WARNING, function=function.name))
        return diagnostics

    def _verify_operands(
        self,
        function: FunctionIR,
        cfg: ControlFlowGraph,
        definitions: Mapping[str, Tuple[str, int, IRType, bool]],
        block_label: str,
        use_index: int,
        operands: Iterable[str],
    ) -> Sequence[IRDiagnostic]:
        diagnostics = []
        for operand in operands:
            definition = definitions.get(operand)
            if definition is None:
                diagnostics.append(self._error("undefined_value", "operand has no SSA definition", function=function.name, block=block_label, value_id=operand))
                continue
            def_block, def_index, _value_type, is_parameter = definition
            if is_parameter:
                continue
            if def_block == block_label:
                if def_index >= use_index:
                    diagnostics.append(self._error("use_before_definition", "SSA value is used before its definition", function=function.name, block=block_label, value_id=operand))
            elif not cfg.dominates(def_block, block_label):
                diagnostics.append(self._error("dominance_violation", "SSA definition does not dominate use", function=function.name, block=block_label, value_id=operand))
        return diagnostics

    @staticmethod
    def _error(
        code: str,
        message: str,
        *,
        function: Optional[str] = None,
        block: Optional[str] = None,
        value_id: Optional[str] = None,
    ) -> IRDiagnostic:
        return IRDiagnostic(code, message, Severity.ERROR, function, block, value_id)
