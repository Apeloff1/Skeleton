"""Loss-accounted semantic decompiler for Jeeves IR.

Decompilation is reconstruction, not inversion.  The compiler may erase names,
source grouping, parallel intent, types or high-level structure.  This module
therefore returns a reconstructed object *and* a loss ledger describing what
was exact, inferred, approximate or unavailable.

For modules produced by :mod:`semantic_compiler`, provenance and plan metadata
allow an exact Plan round-trip when no information-bearing compiler policy has
removed fields.  For arbitrary IR the decompiler remains useful as a semantic
summary but refuses to fabricate an exact source plan.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .semantic_ir import (
    Dialect,
    Effect,
    IRFunction,
    IRModule,
    IRStage,
    IRType,
    OpCode,
    Operation,
    SourceOrigin,
)
from .types import (
    Plan,
    PlanStep,
    RiskTier,
    StepStatus,
    json_safe,
    stable_fingerprint,
    stable_id,
)


class RecoveryConfidence(str, Enum):
    EXACT = "exact"
    STRUCTURAL = "structural"
    HEURISTIC = "heuristic"
    UNKNOWN = "unknown"


class LossKind(str, Enum):
    IDENTIFIER = "identifier"
    TYPE = "type"
    CONTROL_STRUCTURE = "control_structure"
    DEPENDENCY = "dependency"
    CONCURRENCY = "concurrency"
    SOURCE_TEXT = "source_text"
    SOURCE_GROUPING = "source_grouping"
    EFFECT_DETAIL = "effect_detail"
    PROVENANCE = "provenance"
    INTENT = "intent"
    VERIFICATION = "verification"
    DYNAMIC_VALUE = "dynamic_value"
    UNKNOWN_OPERATION = "unknown_operation"
    NONDETERMINISM = "nondeterminism"
    REPLAY = "replay"
    ASSUMPTION = "assumption"
    UNDEFINED_SEMANTICS = "undefined_semantics"
    POISON_STATE = "poison_state"
    MEMORY_MODEL = "memory_model"
    SAFETY_CONTRACT = "safety_contract"
    ROUND_TRIP_MISMATCH = "round_trip_mismatch"


@dataclass(frozen=True, slots=True)
class DecompilationLoss:
    kind: LossKind
    message: str
    confidence: RecoveryConfidence
    function_id: str | None = None
    block_id: str | None = None
    op_id: str | None = None
    source_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LossKind):
            object.__setattr__(self, "kind", LossKind(str(self.kind)))
        if not isinstance(self.confidence, RecoveryConfidence):
            object.__setattr__(self, "confidence", RecoveryConfidence(str(self.confidence)))
        object.__setattr__(self, "message", str(self.message)[:8192])
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class RecoveryMapping:
    source_kind: str
    source_ref: str
    operation_ids: tuple[str, ...]
    block_ids: tuple[str, ...]
    confidence: float
    reconstructed: bool
    fingerprint: str


@dataclass(frozen=True, slots=True)
class RecoveredOperation:
    operation_id: str
    opcode: str
    dialect: str
    effects: tuple[str, ...]
    attributes: Mapping[str, Any]
    source_refs: tuple[str, ...]
    information_loss: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecoveredFunction:
    function_id: str
    stage: str
    operations: tuple[RecoveredOperation, ...]
    cfg: Mapping[str, tuple[str, ...]]
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DecompilationReport:
    module_fingerprint: str
    recovered_plan: Plan | None
    recovered_functions: tuple[RecoveredFunction, ...]
    mappings: tuple[RecoveryMapping, ...]
    losses: tuple[DecompilationLoss, ...]
    exact_round_trip: bool
    overall_confidence: float
    source_plan_fingerprint: str | None
    reconstructed_plan_fingerprint: str | None
    fingerprint: str

    @property
    def lossy(self) -> bool:
        return bool(self.losses)


class SemanticDecompiler:
    def decompile(self, module: IRModule) -> DecompilationReport:
        if not isinstance(module, IRModule):
            raise TypeError("module must be IRModule")
        losses: list[DecompilationLoss] = []
        recovered_functions = tuple(self._recover_function(function, losses) for function in module.functions)
        mappings = self._mappings(module)
        plan = self._recover_plan(module, losses)
        source_plan_fingerprint = self._source_plan_fingerprint(module)
        reconstructed_plan_fingerprint = stable_fingerprint(plan.to_dict()) if plan is not None else None
        exact = bool(
            plan is not None
            and source_plan_fingerprint
            and reconstructed_plan_fingerprint == source_plan_fingerprint
            and not any(
                loss.kind in {
                    LossKind.DEPENDENCY,
                    LossKind.INTENT,
                    LossKind.VERIFICATION,
                    LossKind.PROVENANCE,
                    LossKind.NONDETERMINISM,
                    LossKind.REPLAY,
                    LossKind.ASSUMPTION,
                    LossKind.UNDEFINED_SEMANTICS,
                    LossKind.POISON_STATE,
                    LossKind.MEMORY_MODEL,
                    LossKind.SAFETY_CONTRACT,
                    LossKind.ROUND_TRIP_MISMATCH,
                }
                for loss in losses
            )
        )
        if (
            plan is not None
            and source_plan_fingerprint
            and reconstructed_plan_fingerprint != source_plan_fingerprint
        ):
            losses.append(
                DecompilationLoss(
                    LossKind.ROUND_TRIP_MISMATCH,
                    "reconstructed plan fingerprint differs from compiler-recorded source plan",
                    RecoveryConfidence.STRUCTURAL,
                    metadata={
                        "source": source_plan_fingerprint,
                        "reconstructed": reconstructed_plan_fingerprint,
                    },
                )
            )
            exact = False

        overall_confidence = self._confidence(plan, mappings, losses, exact)
        fingerprint = stable_fingerprint(
            {
                "module": module.fingerprint,
                "plan": reconstructed_plan_fingerprint,
                "functions": [
                    {
                        "id": function.function_id,
                        "stage": function.stage,
                        "operations": [
                            {
                                "id": operation.operation_id,
                                "opcode": operation.opcode,
                                "dialect": operation.dialect,
                                "effects": operation.effects,
                                "attributes": operation.attributes,
                                "source_refs": operation.source_refs,
                                "loss": operation.information_loss,
                            }
                            for operation in function.operations
                        ],
                        "cfg": function.cfg,
                        "source_refs": function.source_refs,
                    }
                    for function in recovered_functions
                ],
                "mappings": [mapping.fingerprint for mapping in mappings],
                "losses": [
                    {
                        "kind": loss.kind.value,
                        "message": loss.message,
                        "confidence": loss.confidence.value,
                        "function": loss.function_id,
                        "block": loss.block_id,
                        "op": loss.op_id,
                        "source_ref": loss.source_ref,
                        "metadata": loss.metadata,
                    }
                    for loss in losses
                ],
                "exact": exact,
                "confidence": overall_confidence,
            }
        )
        return DecompilationReport(
            module_fingerprint=module.fingerprint,
            recovered_plan=plan,
            recovered_functions=recovered_functions,
            mappings=mappings,
            losses=tuple(losses),
            exact_round_trip=exact,
            overall_confidence=overall_confidence,
            source_plan_fingerprint=source_plan_fingerprint,
            reconstructed_plan_fingerprint=reconstructed_plan_fingerprint,
            fingerprint=fingerprint,
        )

    def pseudo_source(self, report: DecompilationReport) -> str:
        """Human-readable JSON reconstruction; never presented as original source."""
        if report.recovered_plan is not None:
            payload = {
                "reconstruction": "jeeves_plan",
                "exact_round_trip": report.exact_round_trip,
                "confidence": report.overall_confidence,
                "plan": report.recovered_plan.to_dict(),
                "losses": [
                    {
                        "kind": loss.kind.value,
                        "message": loss.message,
                        "confidence": loss.confidence.value,
                    }
                    for loss in report.losses
                ],
            }
        else:
            payload = {
                "reconstruction": "semantic_ir_summary",
                "exact_round_trip": False,
                "confidence": report.overall_confidence,
                "functions": [
                    {
                        "function_id": function.function_id,
                        "stage": function.stage,
                        "cfg": {key: list(value) for key, value in function.cfg.items()},
                        "operations": [
                            {
                                "operation_id": operation.operation_id,
                                "opcode": operation.opcode,
                                "dialect": operation.dialect,
                                "effects": list(operation.effects),
                                "attributes": dict(operation.attributes),
                                "source_refs": list(operation.source_refs),
                            }
                            for operation in function.operations
                        ],
                    }
                    for function in report.recovered_functions
                ],
                "losses": [
                    {
                        "kind": loss.kind.value,
                        "message": loss.message,
                        "confidence": loss.confidence.value,
                    }
                    for loss in report.losses
                ],
            }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)

    def _recover_plan(
        self,
        module: IRModule,
        losses: list[DecompilationLoss],
    ) -> Plan | None:
        if len(module.functions) != 1:
            losses.append(
                DecompilationLoss(
                    LossKind.SOURCE_GROUPING,
                    "module has multiple functions; no unique Plan reconstruction",
                    RecoveryConfidence.UNKNOWN,
                )
            )
            return None
        function = module.functions[0]
        metadata = dict(function.metadata)
        if metadata.get("source_kind") != "jeeves_plan":
            losses.append(
                DecompilationLoss(
                    LossKind.INTENT,
                    "IR does not declare a Jeeves Plan source; refusing to invent a Plan",
                    RecoveryConfidence.UNKNOWN,
                    function_id=function.function_id,
                )
            )
            return None

        plan_id = metadata.get("plan_id")
        goal_id = metadata.get("goal_id")
        version = metadata.get("plan_version")
        created_at = metadata.get("plan_created_at")
        rationale = metadata.get("plan_rationale", "")
        if not isinstance(plan_id, str) or not isinstance(goal_id, str):
            losses.append(
                DecompilationLoss(
                    LossKind.IDENTIFIER,
                    "plan_id or goal_id missing from IR metadata",
                    RecoveryConfidence.UNKNOWN,
                    function_id=function.function_id,
                )
            )
            return None
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            losses.append(
                DecompilationLoss(
                    LossKind.INTENT,
                    "plan version missing; defaulting to version 1",
                    RecoveryConfidence.HEURISTIC,
                    function_id=function.function_id,
                )
            )
            version = 1
        if not isinstance(created_at, (int, float)) or isinstance(created_at, bool) or created_at < 0:
            losses.append(
                DecompilationLoss(
                    LossKind.SOURCE_TEXT,
                    "original plan creation timestamp unavailable; using zero",
                    RecoveryConfidence.HEURISTIC,
                    function_id=function.function_id,
                )
            )
            created_at = 0.0

        step_ops: dict[str, Operation] = {}
        verification: dict[str, str] = {}
        schedule: list[str] = []
        for block in function.blocks:
            for operation in block.operations:
                step_id = operation.attributes.get("step_id")
                if (
                    isinstance(step_id, str)
                    and operation.opcode in {OpCode.TOOL_CALL, OpCode.MODEL_INFER}
                ):
                    if step_id in step_ops:
                        losses.append(
                            DecompilationLoss(
                                LossKind.SOURCE_GROUPING,
                                f"multiple execution operations map to plan step {step_id}",
                                RecoveryConfidence.HEURISTIC,
                                function_id=function.function_id,
                                block_id=block.block_id,
                                op_id=operation.op_id,
                                source_ref=step_id,
                            )
                        )
                        return None
                    step_ops[step_id] = operation
                    schedule.append(step_id)
                if isinstance(step_id, str) and operation.opcode is OpCode.ASSERT:
                    directive = operation.attributes.get("verification")
                    if isinstance(directive, str):
                        verification[step_id] = directive

        declared_schedule = metadata.get("topological_schedule")
        if isinstance(declared_schedule, list) and all(isinstance(value, str) for value in declared_schedule):
            ordered_ids = list(declared_schedule)
        else:
            ordered_ids = schedule
            losses.append(
                DecompilationLoss(
                    LossKind.CONTROL_STRUCTURE,
                    "compiler schedule metadata missing; using block operation order",
                    RecoveryConfidence.STRUCTURAL,
                    function_id=function.function_id,
                )
            )
        if set(ordered_ids) != set(step_ops):
            losses.append(
                DecompilationLoss(
                    LossKind.SOURCE_GROUPING,
                    "plan step set does not match declared schedule",
                    RecoveryConfidence.UNKNOWN,
                    function_id=function.function_id,
                )
            )
            return None

        declared_dependencies = metadata.get("dependency_graph")
        if not isinstance(declared_dependencies, dict):
            declared_dependencies = {}
            losses.append(
                DecompilationLoss(
                    LossKind.DEPENDENCY,
                    "original dependency DAG missing; serialized execution order is not used as a substitute",
                    RecoveryConfidence.UNKNOWN,
                    function_id=function.function_id,
                )
            )

        steps: list[PlanStep] = []
        for step_id in ordered_ids:
            operation = step_ops[step_id]
            attrs = operation.attributes
            dependencies_raw = declared_dependencies.get(step_id, attrs.get("dependencies"))
            if not isinstance(dependencies_raw, list) or not all(isinstance(value, str) for value in dependencies_raw):
                dependencies = ()
                losses.append(
                    DecompilationLoss(
                        LossKind.DEPENDENCY,
                        f"dependencies unavailable for step {step_id}; leaving empty rather than inferring from serial schedule",
                        RecoveryConfidence.UNKNOWN,
                        function_id=function.function_id,
                        op_id=operation.op_id,
                        source_ref=step_id,
                    )
                )
            else:
                dependencies = tuple(dependencies_raw)

            tool = attrs.get("tool")
            if tool is not None and not isinstance(tool, str):
                tool = None
                losses.append(
                    DecompilationLoss(
                        LossKind.INTENT,
                        f"tool identity malformed for step {step_id}",
                        RecoveryConfidence.UNKNOWN,
                        function_id=function.function_id,
                        op_id=operation.op_id,
                        source_ref=step_id,
                    )
                )
            arguments = attrs.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}
                losses.append(
                    DecompilationLoss(
                        LossKind.INTENT,
                        f"tool arguments unavailable for step {step_id}",
                        RecoveryConfidence.UNKNOWN,
                        function_id=function.function_id,
                        op_id=operation.op_id,
                        source_ref=step_id,
                    )
                )

            try:
                risk = RiskTier(str(attrs.get("risk", RiskTier.READ_ONLY.value)))
            except ValueError:
                risk = RiskTier.READ_ONLY
                losses.append(
                    DecompilationLoss(
                        LossKind.EFFECT_DETAIL,
                        f"risk tier unavailable for step {step_id}; defaulted to read_only",
                        RecoveryConfidence.HEURISTIC,
                        function_id=function.function_id,
                        op_id=operation.op_id,
                        source_ref=step_id,
                    )
                )
            try:
                status = StepStatus(str(attrs.get("status", StepStatus.PENDING.value)))
            except ValueError:
                status = StepStatus.PENDING
                losses.append(
                    DecompilationLoss(
                        LossKind.INTENT,
                        f"step status unavailable for {step_id}; defaulted to pending",
                        RecoveryConfidence.HEURISTIC,
                        function_id=function.function_id,
                        op_id=operation.op_id,
                        source_ref=step_id,
                    )
                )
            has_assert = any(
                op.opcode is OpCode.ASSERT and op.attributes.get("step_id") == step_id
                for block in function.blocks
                for op in block.operations
            )
            if step_id in verification:
                directive = verification[step_id]
            elif "verification" in attrs:
                directive = str(attrs.get("verification", ""))
            else:
                directive = ""
                losses.append(
                    DecompilationLoss(
                        LossKind.VERIFICATION,
                        f"verification source field was not retained for step {step_id}",
                        RecoveryConfidence.UNKNOWN,
                        function_id=function.function_id,
                        op_id=operation.op_id,
                        source_ref=step_id,
                        metadata={"assert_present": has_assert},
                    )
                )

            steps.append(
                PlanStep(
                    step_id=step_id,
                    title=str(attrs.get("title", f"Recovered {step_id}")),
                    description=str(attrs.get("description", "")),
                    dependencies=dependencies,
                    tool=tool,
                    arguments=arguments,
                    expected_outcome=str(attrs.get("expected_outcome", "")),
                    verification=directive,
                    risk=risk,
                    status=status,
                    attempts=int(attrs.get("attempts", 0)),
                    max_attempts=int(attrs.get("max_attempts", 2)),
                )
            )
        try:
            return Plan(
                plan_id=plan_id,
                goal_id=goal_id,
                steps=tuple(steps),
                version=version,
                rationale=str(rationale),
                created_at=float(created_at),
            )
        except Exception as exc:
            losses.append(
                DecompilationLoss(
                    LossKind.INTENT,
                    f"recovered plan violates Plan contract: {type(exc).__name__}: {exc}",
                    RecoveryConfidence.UNKNOWN,
                    function_id=function.function_id,
                )
            )
            return None

    def _recover_function(
        self,
        function: IRFunction,
        losses: list[DecompilationLoss],
    ) -> RecoveredFunction:
        operations: list[RecoveredOperation] = []
        source_refs: set[str] = set()
        for block in function.blocks:
            for operation in block.operations:
                refs = tuple(dict.fromkeys(origin.source_ref for origin in operation.origins))
                source_refs.update(refs)
                if not operation.origins:
                    losses.append(
                        DecompilationLoss(
                            LossKind.PROVENANCE,
                            "operation has no source origin",
                            RecoveryConfidence.UNKNOWN,
                            function_id=function.function_id,
                            block_id=block.block_id,
                            op_id=operation.op_id,
                        )
                    )
                if operation.opcode is OpCode.UNKNOWN:
                    losses.append(
                        DecompilationLoss(
                            LossKind.UNKNOWN_OPERATION,
                            "unknown operation cannot be raised to source intent",
                            RecoveryConfidence.UNKNOWN,
                            function_id=function.function_id,
                            block_id=block.block_id,
                            op_id=operation.op_id,
                        )
                    )
                if operation.dialect is Dialect.UNKNOWN or Effect.UNKNOWN in operation.effects:
                    losses.append(
                        DecompilationLoss(
                            LossKind.UNDEFINED_SEMANTICS,
                            "operation carries unknown dialect/effect semantics that cannot be reconstructed safely",
                            RecoveryConfidence.UNKNOWN,
                            function_id=function.function_id,
                            block_id=block.block_id,
                            op_id=operation.op_id,
                        )
                    )
                if any(result.type is IRType.UNKNOWN for result in operation.results):
                    losses.append(
                        DecompilationLoss(
                            LossKind.TYPE,
                            "operation produces an unknown-typed value; source type intent is unavailable",
                            RecoveryConfidence.UNKNOWN,
                            function_id=function.function_id,
                            block_id=block.block_id,
                            op_id=operation.op_id,
                        )
                    )
                if Effect.NONDETERMINISTIC in operation.effects:
                    source = operation.attributes.get("nondeterminism_source")
                    replay = operation.attributes.get("replay_policy")
                    if not isinstance(source, str) or not source.strip():
                        losses.append(
                            DecompilationLoss(
                                LossKind.NONDETERMINISM,
                                "nondeterministic behavior is present but its source is not recoverable",
                                RecoveryConfidence.UNKNOWN,
                                function_id=function.function_id,
                                block_id=block.block_id,
                                op_id=operation.op_id,
                            )
                        )
                    if not isinstance(replay, str) or not replay.strip():
                        losses.append(
                            DecompilationLoss(
                                LossKind.REPLAY,
                                "nondeterministic operation has no recoverable replay policy",
                                RecoveryConfidence.UNKNOWN,
                                function_id=function.function_id,
                                block_id=block.block_id,
                                op_id=operation.op_id,
                            )
                        )
                if operation.opcode is OpCode.ASSUME:
                    losses.append(
                        DecompilationLoss(
                            LossKind.ASSUMPTION,
                            "source semantics depend on an unresolved assumption",
                            RecoveryConfidence.STRUCTURAL,
                            function_id=function.function_id,
                            block_id=block.block_id,
                            op_id=operation.op_id,
                            metadata={"attributes": dict(operation.attributes)},
                        )
                    )
                if bool(operation.attributes.get("may_poison", False)) and not bool(
                    operation.attributes.get("freeze_guarded", False)
                ):
                    losses.append(
                        DecompilationLoss(
                            LossKind.POISON_STATE,
                            "poison-like/undefined state may flow into reconstructed semantics without a recovered guard",
                            RecoveryConfidence.UNKNOWN,
                            function_id=function.function_id,
                            block_id=block.block_id,
                            op_id=operation.op_id,
                        )
                    )
                if operation.opcode is OpCode.DIV and operation.attributes.get("division_by_zero") not in {
                    "reject",
                    "trap",
                    "defined",
                    "guarded",
                }:
                    losses.append(
                        DecompilationLoss(
                            LossKind.UNDEFINED_SEMANTICS,
                            "division-by-zero semantics were not explicit in the IR",
                            RecoveryConfidence.UNKNOWN,
                            function_id=function.function_id,
                            block_id=block.block_id,
                            op_id=operation.op_id,
                        )
                    )
                if Effect.EXTERNAL_MUTATION in operation.effects and "risk" not in operation.attributes:
                    losses.append(
                        DecompilationLoss(
                            LossKind.SAFETY_CONTRACT,
                            "external mutation is recoverable but its risk contract is missing",
                            RecoveryConfidence.UNKNOWN,
                            function_id=function.function_id,
                            block_id=block.block_id,
                            op_id=operation.op_id,
                        )
                    )
                for note in operation.information_loss:
                    losses.append(
                        DecompilationLoss(
                            LossKind.SOURCE_TEXT,
                            note,
                            RecoveryConfidence.STRUCTURAL,
                            function_id=function.function_id,
                            block_id=block.block_id,
                            op_id=operation.op_id,
                        )
                    )
                operations.append(
                    RecoveredOperation(
                        operation_id=operation.op_id,
                        opcode=operation.opcode.value,
                        dialect=operation.dialect.value,
                        effects=tuple(effect.value for effect in operation.effects),
                        attributes=dict(operation.attributes),
                        source_refs=refs,
                        information_loss=operation.information_loss,
                    )
                )
        cfg = {block.block_id: block.successors() for block in function.blocks}
        return RecoveredFunction(
            function_id=function.function_id,
            stage=function.stage.name.casefold(),
            operations=tuple(operations),
            cfg=cfg,
            source_refs=tuple(sorted(source_refs)),
        )

    @staticmethod
    def _mappings(module: IRModule) -> tuple[RecoveryMapping, ...]:
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for function in module.functions:
            for block in function.blocks:
                for operation in block.operations:
                    for origin in operation.origins:
                        key = (origin.source_kind, origin.source_ref)
                        record = grouped.setdefault(
                            key,
                            {
                                "ops": set(),
                                "blocks": set(),
                                "confidence": 1.0,
                                "reconstructed": False,
                            },
                        )
                        record["ops"].add(operation.op_id)
                        record["blocks"].add(block.block_id)
                        record["confidence"] = min(record["confidence"], origin.confidence)
                        record["reconstructed"] = record["reconstructed"] or origin.reconstructed
        values: list[RecoveryMapping] = []
        for (source_kind, source_ref), record in sorted(grouped.items()):
            operation_ids = tuple(sorted(record["ops"]))
            block_ids = tuple(sorted(record["blocks"]))
            fingerprint = stable_fingerprint(
                {
                    "source_kind": source_kind,
                    "source_ref": source_ref,
                    "operations": operation_ids,
                    "blocks": block_ids,
                    "confidence": record["confidence"],
                    "reconstructed": record["reconstructed"],
                }
            )
            values.append(
                RecoveryMapping(
                    source_kind=source_kind,
                    source_ref=source_ref,
                    operation_ids=operation_ids,
                    block_ids=block_ids,
                    confidence=record["confidence"],
                    reconstructed=record["reconstructed"],
                    fingerprint=fingerprint,
                )
            )
        return tuple(values)

    @staticmethod
    def _source_plan_fingerprint(module: IRModule) -> str | None:
        value = module.metadata.get("source_plan_fingerprint")
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _confidence(
        plan: Plan | None,
        mappings: Sequence[RecoveryMapping],
        losses: Sequence[DecompilationLoss],
        exact: bool,
    ) -> float:
        if exact:
            return 1.0
        base = 0.70 if plan is not None else 0.40
        if mappings:
            base = base * 0.70 + (
                sum(mapping.confidence for mapping in mappings) / len(mappings)
            ) * 0.30
        penalties = {
            RecoveryConfidence.EXACT: 0.0,
            RecoveryConfidence.STRUCTURAL: 0.025,
            RecoveryConfidence.HEURISTIC: 0.07,
            RecoveryConfidence.UNKNOWN: 0.13,
        }
        base -= sum(penalties[loss.confidence] for loss in losses)
        return max(0.0, min(0.99, base))


__all__ = [
    "DecompilationLoss",
    "DecompilationReport",
    "LossKind",
    "RecoveredFunction",
    "RecoveredOperation",
    "RecoveryConfidence",
    "RecoveryMapping",
    "SemanticDecompiler",
]
