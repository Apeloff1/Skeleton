"""Evidence-bearing decompilation for the Jeeves semantic IR.

A decompiler cannot generally reconstruct information erased by compilation.
This module therefore follows a strict rule: unknown source facts remain
unknown.  It emits behavior-preserving SSA-oriented pseudocode, reconstructs
only types supported by evidence, and records every known information loss.

That stance mirrors modern deductive type-recovery work: recover a type that
faithfully describes observed behavior rather than inventing an original source
type that may be unrecoverable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .ir import Effect, FunctionIR, IRModule, IRType, IRVerifier, Instruction, TerminatorKind


class RecoveryConfidence(str, Enum):
    EXACT = "exact"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class LossKind(str, Enum):
    SOURCE_NAME = "source_name"
    SOURCE_TYPE = "source_type"
    SOURCE_SPAN = "source_span"
    CONTROL_STRUCTURE = "control_structure"
    ALIASING = "aliasing"
    OPTIMIZATION_HISTORY = "optimization_history"
    PROVENANCE = "provenance"
    UNSUPPORTED_SEMANTICS = "unsupported_semantics"
    NONDETERMINISM = "nondeterminism"
    REPLAY = "replay"
    UNDEFINED_BEHAVIOR = "undefined_behavior"
    ASSUMPTION = "assumption"
    SAFETY_CONTRACT = "safety_contract"
    DEBUG_INFORMATION = "debug_information"


@dataclass(frozen=True)
class RecoveredType:
    value_id: str
    behavior_type: IRType
    confidence: RecoveryConfidence
    evidence: Tuple[str, ...]
    original_source_type_known: bool = False
    alternatives: Tuple[IRType, ...] = ()


@dataclass(frozen=True)
class LossRecord:
    kind: LossKind
    subject: str
    reason: str
    confidence: RecoveryConfidence = RecoveryConfidence.HIGH
    recoverable: bool = False
    evidence: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DecompilationArtifact:
    text: str
    recovered_types: Tuple[RecoveredType, ...]
    losses: Tuple[LossRecord, ...]
    source_module_fingerprint: str
    semantic_fingerprint: str
    structurally_valid_source: bool
    exact_source_recovery_claimed: bool = False

    @property
    def lossless(self) -> bool:
        return not self.losses

    @property
    def fingerprint(self) -> str:
        payload = {
            "text": self.text,
            "types": [
                {
                    "value_id": item.value_id,
                    "type": item.behavior_type.as_json(),
                    "confidence": item.confidence.value,
                    "evidence": list(item.evidence),
                    "source_known": item.original_source_type_known,
                    "alternatives": [alt.as_json() for alt in item.alternatives],
                }
                for item in self.recovered_types
            ],
            "losses": [
                {
                    "kind": item.kind.value,
                    "subject": item.subject,
                    "reason": item.reason,
                    "confidence": item.confidence.value,
                    "recoverable": item.recoverable,
                    "evidence": list(item.evidence),
                }
                for item in self.losses
            ],
            "source": self.source_module_fingerprint,
            "semantic": self.semantic_fingerprint,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class TypeRecoveryEngine:
    """Recover behavior-capturing types and retain ambiguity explicitly."""

    NUMERIC_OPS = frozenset({"add", "sub", "mul", "div", "floordiv", "mod", "neg", "min", "max"})
    BOOLEAN_OPS = frozenset({"eq", "ne", "lt", "le", "gt", "ge", "and", "or", "not"})

    def recover_function(self, function: FunctionIR) -> Tuple[RecoveredType, ...]:
        recovered: Dict[str, RecoveredType] = {}
        for parameter in function.parameters:
            recovered[parameter.value_id] = RecoveredType(
                parameter.value_id,
                parameter.value_type,
                RecoveryConfidence.HIGH,
                ("typed IR function signature",),
                bool(function.attributes.get("source_type_fidelity") == "exact"),
            )
        for block in function.blocks:
            for argument in block.arguments:
                recovered[argument.value_id] = RecoveredType(
                    argument.value_id,
                    argument.value_type,
                    RecoveryConfidence.HIGH,
                    ("typed IR block argument",),
                    False,
                )
            for instruction in block.instructions:
                for result in instruction.results:
                    evidence = ["typed IR result annotation"]
                    confidence = RecoveryConfidence.HIGH
                    alternatives = []
                    inferred = self._behavior_constraint(instruction)
                    if inferred is not None:
                        evidence.append("opcode behavior constraint: " + instruction.opcode)
                        if inferred == result.value_type:
                            confidence = RecoveryConfidence.EXACT
                        else:
                            alternatives.append(inferred)
                            confidence = RecoveryConfidence.MEDIUM
                    source_exact = any(
                        provenance.confidence == 1.0 and provenance.start is not None
                        for provenance in instruction.provenance
                    ) and bool(instruction.attributes.get("source_type_exact", False))
                    recovered[result.value_id] = RecoveredType(
                        result.value_id,
                        result.value_type,
                        confidence,
                        tuple(evidence),
                        source_exact,
                        tuple(alternatives),
                    )
        return tuple(recovered[key] for key in sorted(recovered))

    def _behavior_constraint(self, instruction: Instruction) -> Optional[IRType]:
        if instruction.opcode in self.BOOLEAN_OPS:
            return IRType("bool")
        if instruction.opcode in self.NUMERIC_OPS:
            if instruction.results:
                # Preserve the concrete IR numeric type; opcode alone cannot
                # distinguish signedness, width, integer-vs-float semantics.
                return instruction.results[0].value_type
        if instruction.opcode == "const" and instruction.results:
            return instruction.results[0].value_type
        return None


class Decompiler:
    """Render semantic IR without fabricating erased source information."""

    def __init__(
        self,
        *,
        verifier: Optional[IRVerifier] = None,
        type_recovery: Optional[TypeRecoveryEngine] = None,
    ) -> None:
        self.verifier = verifier or IRVerifier()
        self.type_recovery = type_recovery or TypeRecoveryEngine()

    def decompile(self, module: IRModule) -> DecompilationArtifact:
        report = self.verifier.verify(module)
        losses = []
        recovered = []
        chunks = [
            "// Jeeves semantic decompilation",
            "// exact source recovery: false",
            "// source module: " + module.fingerprint,
        ]
        if not report.valid:
            losses.append(
                LossRecord(
                    LossKind.UNSUPPORTED_SEMANTICS,
                    "module",
                    "input IR is structurally invalid; rendering is forensic only",
                    RecoveryConfidence.EXACT,
                    False,
                )
            )

        for function in module.functions:
            function_types = self.type_recovery.recover_function(function)
            recovered.extend(function_types)
            text, function_losses = self._decompile_function(function)
            chunks.append(text)
            losses.extend(function_losses)
            losses.extend(self._source_information_losses(function, function_types))

        semantic_payload = {
            "module_fingerprint": module.fingerprint,
            "function_fingerprints": [function.fingerprint for function in module.functions],
            "valid": report.valid,
        }
        semantic_fingerprint = hashlib.sha256(
            json.dumps(semantic_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return DecompilationArtifact(
            text="\n\n".join(chunks) + "\n",
            recovered_types=tuple(recovered),
            losses=tuple(self._deduplicate_losses(losses)),
            source_module_fingerprint=module.fingerprint,
            semantic_fingerprint=semantic_fingerprint,
            structurally_valid_source=report.valid,
            exact_source_recovery_claimed=False,
        )

    def _decompile_function(self, function: FunctionIR) -> Tuple[str, Tuple[LossRecord, ...]]:
        losses = []
        parameters = ", ".join(
            "%s: %s" % (parameter.value_id, self._render_type(parameter.value_type))
            for parameter in function.parameters
        )
        returns = ", ".join(self._render_type(item) for item in function.return_types) or "void"
        effects = ",".join(sorted(effect.value for effect in function.declared_effects))
        lines = ["fn %s(%s) -> (%s) effects[%s] {" % (function.name, parameters, returns, effects)]
        for block in function.blocks:
            arguments = ", ".join(
                "%s: %s" % (item.value_id, self._render_type(item.value_type))
                for item in block.arguments
            )
            lines.append("  %s(%s):" % (block.label, arguments))
            for instruction in block.instructions:
                rendered, instruction_losses = self._render_instruction(instruction)
                lines.append("    " + rendered)
                losses.extend(instruction_losses)
            lines.extend("    " + line for line in self._render_terminator(block.terminator))
        lines.append("}")

        if any(block.terminator.kind in (TerminatorKind.JUMP, TerminatorKind.BRANCH) for block in function.blocks):
            losses.append(
                LossRecord(
                    LossKind.CONTROL_STRUCTURE,
                    function.name,
                    "CFG is rendered explicitly; original high-level loop/if syntax is not asserted without recovery evidence",
                    RecoveryConfidence.EXACT,
                    True,
                    ("semantic CFG",),
                )
            )
        return "\n".join(lines), tuple(losses)

    def _render_instruction(self, instruction: Instruction) -> Tuple[str, Tuple[LossRecord, ...]]:
        losses = []
        lhs = ", ".join("%" + item.value_id for item in instruction.results)
        operands = ", ".join("%" + item for item in instruction.operands)
        attributes = ""
        if instruction.attributes:
            attributes = " " + json.dumps(
                dict(instruction.attributes), sort_keys=True, separators=(",", ":"), default=str
            )
        effect_text = ""
        if instruction.effects != frozenset({Effect.PURE}):
            effect_text = " effects[" + ",".join(sorted(item.value for item in instruction.effects)) + "]"
        prefix = (lhs + " = ") if lhs else ""
        if not instruction.provenance:
            losses.append(
                LossRecord(
                    LossKind.PROVENANCE,
                    lhs or instruction.opcode,
                    "instruction has no source/evidence provenance",
                    RecoveryConfidence.EXACT,
                    False,
                )
            )
        if Effect.NONDETERMINISTIC in instruction.effects:
            nondeterminism_source = instruction.attributes.get("nondeterminism_source")
            replay_policy = instruction.attributes.get("replay_policy")
            if not isinstance(nondeterminism_source, str) or not nondeterminism_source.strip():
                losses.append(
                    LossRecord(
                        LossKind.NONDETERMINISM,
                        lhs or instruction.opcode,
                        "nondeterministic behavior is explicit but its source is not recoverable",
                        RecoveryConfidence.EXACT,
                        False,
                    )
                )
            if not isinstance(replay_policy, str) or not replay_policy.strip():
                losses.append(
                    LossRecord(
                        LossKind.REPLAY,
                        lhs or instruction.opcode,
                        "nondeterministic instruction has no recovered replay policy",
                        RecoveryConfidence.EXACT,
                        False,
                    )
                )
        if bool(instruction.attributes.get("may_poison", False)) and not bool(
            instruction.attributes.get("freeze_guarded", False)
        ):
            losses.append(
                LossRecord(
                    LossKind.UNDEFINED_BEHAVIOR,
                    lhs or instruction.opcode,
                    "poison-like state may affect behavior without a recovered freeze/guard contract",
                    RecoveryConfidence.EXACT,
                    False,
                )
            )
        if instruction.opcode in {"div", "floordiv", "mod"} and instruction.attributes.get(
            "division_by_zero"
        ) not in {"reject", "trap", "defined", "guarded"}:
            losses.append(
                LossRecord(
                    LossKind.UNDEFINED_BEHAVIOR,
                    lhs or instruction.opcode,
                    "zero-divisor behavior is not explicitly represented",
                    RecoveryConfidence.EXACT,
                    True,
                )
            )
        if bool(instruction.attributes.get("assumption", False)) or instruction.opcode == "assume":
            losses.append(
                LossRecord(
                    LossKind.ASSUMPTION,
                    lhs or instruction.opcode,
                    "behavior depends on an assumption that cannot be promoted to source fact",
                    RecoveryConfidence.EXACT,
                    True,
                )
            )
        if (
            instruction.effects
            & frozenset({Effect.NETWORK, Effect.FILESYSTEM, Effect.PROCESS, Effect.PRIVILEGED})
            and "risk" not in instruction.attributes
        ):
            losses.append(
                LossRecord(
                    LossKind.SAFETY_CONTRACT,
                    lhs or instruction.opcode,
                    "effectful operation is recoverable but its risk contract is absent",
                    RecoveryConfidence.EXACT,
                    True,
                )
            )
        known = instruction.opcode in {
            "const", "identity", "add", "sub", "mul", "div", "floordiv", "mod", "neg",
            "eq", "ne", "lt", "le", "gt", "ge", "and", "or", "not", "select", "min", "max",
        }
        opcode = instruction.opcode if known else "opaque[" + instruction.opcode + "]"
        if not known:
            losses.append(
                LossRecord(
                    LossKind.UNSUPPORTED_SEMANTICS,
                    lhs or instruction.opcode,
                    "opcode is preserved as opaque rather than guessed",
                    RecoveryConfidence.EXACT,
                    True,
                    (instruction.opcode,),
                )
            )
        return prefix + opcode + "(" + operands + ")" + attributes + effect_text, tuple(losses)

    @staticmethod
    def _render_terminator(terminator: Any) -> Sequence[str]:
        if terminator.kind == TerminatorKind.RETURN:
            return ("return " + ", ".join("%" + item for item in terminator.operands),)
        if terminator.kind == TerminatorKind.JUMP:
            return ("goto " + terminator.targets[0],)
        if terminator.kind == TerminatorKind.BRANCH:
            condition = "%" + terminator.operands[0] if terminator.operands else "<unknown>"
            target_text = " : ".join(terminator.targets)
            return ("branch " + condition + " ? " + target_text,)
        if terminator.kind == TerminatorKind.FAIL:
            return ("fail",)
        return ("unreachable",)

    @staticmethod
    def _source_information_losses(
        function: FunctionIR,
        recovered_types: Sequence[RecoveredType],
    ) -> Sequence[LossRecord]:
        losses = []
        if not function.attributes.get("source_names_exact", False):
            losses.append(
                LossRecord(
                    LossKind.SOURCE_NAME,
                    function.name,
                    "SSA identifiers are preserved; original local variable names are not known",
                    RecoveryConfidence.EXACT,
                    False,
                )
            )
        uncertain_types = [item for item in recovered_types if not item.original_source_type_known]
        if uncertain_types:
            losses.append(
                LossRecord(
                    LossKind.SOURCE_TYPE,
                    function.name,
                    "%d behavior types are known but original source-level type identity is not proven" % len(uncertain_types),
                    RecoveryConfidence.EXACT,
                    False,
                    tuple(item.value_id for item in uncertain_types[:32]),
                )
            )
        provenance_items = [
            provenance
            for block in function.blocks
            for instruction in block.instructions
            for provenance in instruction.provenance
        ]
        if not provenance_items or any(item.start is None or item.end is None for item in provenance_items):
            losses.append(
                LossRecord(
                    LossKind.SOURCE_SPAN,
                    function.name,
                    "complete original source spans are not available",
                    RecoveryConfidence.EXACT,
                    False,
                )
            )
        if not function.attributes.get("optimization_history_complete", False):
            losses.append(
                LossRecord(
                    LossKind.OPTIMIZATION_HISTORY,
                    function.name,
                    "the exact historical sequence of compiler transformations is not asserted",
                    RecoveryConfidence.EXACT,
                    False,
                )
            )
        return losses

    @staticmethod
    def _deduplicate_losses(losses: Sequence[LossRecord]) -> Sequence[LossRecord]:
        seen = set()
        result = []
        for item in losses:
            key = (item.kind.value, item.subject, item.reason)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    @staticmethod
    def _render_type(value_type: IRType) -> str:
        base = value_type.name
        if value_type.parameters:
            base += "<" + ",".join(Decompiler._render_type(item) for item in value_type.parameters) + ">"
        if value_type.nullable:
            base += "?"
        return base
