"""Jeeves semantic compiler.

The compiler turns host-validated plan objects into a provenance-bearing,
multi-level IR and keeps every lowering product instead of discarding earlier
levels.

Pipeline:
    Plan -> SOURCE_SEMANTIC -> CANONICAL -> CONTROL -> EXECUTION

Each lowering is transactional and translation-validated.  The compiler chooses
one deterministic serial schedule that is a topological extension of the plan's
partial order; the original dependency DAG remains explicit metadata so a
scheduler/decompiler never confuses serialization with original intent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Sequence

from .compiler_validation import (
    PassApplication,
    PassContract,
    StageLoweringPass,
    TransactionalPassManager,
)
from .semantic_ir import (
    BasicBlock,
    Dialect,
    Effect,
    IRFunction,
    IRModule,
    IRStage,
    IRType,
    OpCode,
    Operation,
    SourceOrigin,
    ValueRef,
)
from .types import (
    AgentContractError,
    Plan,
    PlanStep,
    RiskTier,
    stable_fingerprint,
    stable_id,
)


@dataclass(frozen=True, slots=True)
class CompilationPolicy:
    preserve_source_metadata: bool = True
    include_verification_ops: bool = True
    lower_to_execution: bool = True
    strict_translation_validation: bool = True


@dataclass(frozen=True, slots=True)
class CompilationArtifact:
    plan_fingerprint: str
    source: IRModule
    canonical: IRModule
    control: IRModule
    execution: IRModule | None
    passes: tuple[PassApplication, ...]
    topological_schedule: tuple[str, ...]
    fingerprint: str

    @property
    def valid(self) -> bool:
        return all(record.committed for record in self.passes)


class ExecutionDialectLoweringPass:
    contract = PassContract(
        name="lower-control-to-execution",
        source_stage=IRStage.CONTROL,
        target_stage=IRStage.EXECUTION,
        must_change=True,
        preserve_observable_effects=True,
        preserve_tool_targets=True,
        preserve_returns=True,
        allow_inconclusive=False,
    )

    @staticmethod
    def _dialect(operation: Operation) -> Dialect:
        if operation.dialect is Dialect.CORE:
            return Dialect.CORE
        if operation.opcode is OpCode.TOOL_CALL:
            return Dialect.JEEVES_TOOL
        if operation.opcode is OpCode.MODEL_INFER:
            return Dialect.JEEVES_MODEL
        if operation.opcode in {OpCode.READ_MEMORY, OpCode.WRITE_MEMORY}:
            return Dialect.JEEVES_MEMORY
        if operation.opcode in {OpCode.QUERY_EVIDENCE, OpCode.EMIT_EVIDENCE}:
            return Dialect.JEEVES_EVIDENCE
        if operation.opcode is OpCode.CAUSAL_QUERY:
            return Dialect.JEEVES_CAUSAL
        return Dialect.JEEVES_CONTROL

    def transform(self, module: IRModule) -> IRModule:
        functions: list[IRFunction] = []
        for function in module.functions:
            if function.stage is not IRStage.CONTROL:
                raise AgentContractError("execution lowering requires CONTROL stage")
            blocks = []
            for block in function.blocks:
                operations = tuple(
                    replace(
                        operation,
                        dialect=self._dialect(operation),
                        attributes={
                            **dict(operation.attributes),
                            "lowering_stage": "execution",
                        },
                    )
                    for operation in block.operations
                )
                blocks.append(replace(block, operations=operations))
            dialects = {
                operation.dialect
                for block in blocks
                for operation in block.operations
            }
            functions.append(
                replace(
                    function,
                    blocks=tuple(blocks),
                    stage=IRStage.EXECUTION,
                    dialects=tuple(sorted(dialects, key=lambda value: value.value)),
                    metadata={
                        **dict(function.metadata),
                        "lowered_from_stage": "control",
                        "lowering_pass": self.contract.name,
                    },
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


class SemanticCompiler:
    def __init__(
        self,
        *,
        policy: CompilationPolicy | None = None,
        pass_manager: TransactionalPassManager | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.policy = policy or CompilationPolicy()
        self.pass_manager = pass_manager or TransactionalPassManager(clock=clock)
        self._clock = clock

    def compile_plan(self, plan: Plan) -> CompilationArtifact:
        if not isinstance(plan, Plan):
            raise TypeError("plan must be Plan")
        plan_fingerprint = stable_fingerprint(plan.to_dict())
        schedule = self._topological_schedule(plan)
        source = self._source_module(plan, plan_fingerprint, schedule)

        canonical_pass = StageLoweringPass(
            IRStage.SOURCE_SEMANTIC,
            IRStage.CANONICAL,
            target_dialect=Dialect.JEEVES_SEMANTIC,
            name="canonicalize-plan-semantics",
        )
        canonical, canonical_record = self.pass_manager.apply(source, canonical_pass)
        if not canonical_record.committed and self.policy.strict_translation_validation:
            raise AgentContractError(f"canonical lowering rejected: {canonical_record.error}")

        control_pass = StageLoweringPass(
            IRStage.CANONICAL,
            IRStage.CONTROL,
            target_dialect=Dialect.JEEVES_CONTROL,
            name="lower-canonical-to-control",
        )
        control, control_record = self.pass_manager.apply(canonical, control_pass)
        if not control_record.committed and self.policy.strict_translation_validation:
            raise AgentContractError(f"control lowering rejected: {control_record.error}")

        execution: IRModule | None = None
        records = [canonical_record, control_record]
        if self.policy.lower_to_execution:
            execution, execution_record = self.pass_manager.apply(control, ExecutionDialectLoweringPass())
            records.append(execution_record)
            if not execution_record.committed and self.policy.strict_translation_validation:
                raise AgentContractError(f"execution lowering rejected: {execution_record.error}")

        artifact_fingerprint = stable_fingerprint(
            {
                "plan": plan_fingerprint,
                "source": source.fingerprint,
                "canonical": canonical.fingerprint,
                "control": control.fingerprint,
                "execution": execution.fingerprint if execution else None,
                "passes": [record.fingerprint for record in records],
                "schedule": schedule,
            }
        )
        return CompilationArtifact(
            plan_fingerprint=plan_fingerprint,
            source=source,
            canonical=canonical,
            control=control,
            execution=execution,
            passes=tuple(records),
            topological_schedule=schedule,
            fingerprint=artifact_fingerprint,
        )

    def _source_module(
        self,
        plan: Plan,
        plan_fingerprint: str,
        schedule: tuple[str, ...],
    ) -> IRModule:
        step_by_id = {step.step_id: step for step in plan.steps}
        block_ids = {
            step_id: stable_id("bb", {"plan": plan.plan_id, "step": step_id}, length=24)
            for step_id in schedule
        }
        entry_id = stable_id("bb", {"plan": plan.plan_id, "kind": "entry"}, length=24)
        exit_id = stable_id("bb", {"plan": plan.plan_id, "kind": "exit"}, length=24)
        predecessor_for: dict[str, str] = {}
        previous = entry_id
        for step_id in schedule:
            predecessor_for[block_ids[step_id]] = previous
            previous = block_ids[step_id]
        predecessor_for[exit_id] = previous

        first_target = block_ids[schedule[0]] if schedule else exit_id
        entry_jump = Operation(
            op_id=stable_id("op", {"plan": plan.plan_id, "entry": first_target}, length=24),
            opcode=OpCode.JUMP,
            dialect=Dialect.CORE,
            effects=(Effect.CONTROL,),
            attributes={"target": first_target, "schedule_kind": "deterministic_topological_extension"},
            origins=(self._plan_origin(plan, plan_fingerprint),),
        )
        blocks: list[BasicBlock] = [
            BasicBlock(
                block_id=entry_id,
                operations=(entry_jump,),
                predecessors_hint=(),
                metadata={"role": "entry"},
            )
        ]

        for index, step_id in enumerate(schedule):
            step = step_by_id[step_id]
            block_id = block_ids[step_id]
            next_target = block_ids[schedule[index + 1]] if index + 1 < len(schedule) else exit_id
            origin = self._step_origin(plan, step)
            result = ValueRef(
                stable_id("value", {"plan": plan.plan_id, "step": step.step_id, "kind": "result"}, length=24),
                IRType.JSON,
            )
            main = Operation(
                op_id=stable_id("op", {"plan": plan.plan_id, "step": step.step_id, "kind": "execute"}, length=24),
                opcode=OpCode.TOOL_CALL if step.tool else OpCode.MODEL_INFER,
                dialect=Dialect.JEEVES_SEMANTIC,
                operands=(),
                results=(result,),
                effects=self._effects(step),
                attributes={
                    "step_id": step.step_id,
                    "title": step.title,
                    "description": step.description,
                    "dependencies": list(step.dependencies),
                    "tool": step.tool,
                    "arguments": dict(step.arguments),
                    "expected_outcome": step.expected_outcome,
                    "verification": step.verification,
                    "risk": step.risk.value,
                    "status": step.status.value,
                    "attempts": step.attempts,
                    "max_attempts": step.max_attempts,
                    "confirmation_required": step.risk in {
                        RiskTier.EXTERNAL,
                        RiskTier.HIGH_IMPACT,
                    },
                    "dependency_semantics": "partial_order_source_serialized_for_host_execution",
                },
                origins=(origin,),
            )
            operations: list[Operation] = [main]
            if self.policy.include_verification_ops and step.verification:
                operations.append(
                    Operation(
                        op_id=stable_id("op", {"plan": plan.plan_id, "step": step.step_id, "kind": "verify"}, length=24),
                        opcode=OpCode.ASSERT,
                        dialect=Dialect.JEEVES_SEMANTIC,
                        operands=(result.value_id,),
                        results=(),
                        effects=(Effect.ASSERTION,),
                        attributes={
                            "step_id": step.step_id,
                            "verification": step.verification,
                            "expected_outcome": step.expected_outcome,
                        },
                        origins=(origin,),
                    )
                )
            operations.append(
                Operation(
                    op_id=stable_id("op", {"plan": plan.plan_id, "step": step.step_id, "kind": "jump"}, length=24),
                    opcode=OpCode.JUMP,
                    dialect=Dialect.CORE,
                    effects=(Effect.CONTROL,),
                    attributes={"target": next_target},
                    origins=(origin,),
                )
            )
            blocks.append(
                BasicBlock(
                    block_id=block_id,
                    operations=tuple(operations),
                    predecessors_hint=(predecessor_for[block_id],),
                    metadata={
                        "role": "plan_step",
                        "step_id": step.step_id,
                        "schedule_index": index,
                    },
                )
            )

        blocks.append(
            BasicBlock(
                block_id=exit_id,
                operations=(
                    Operation(
                        op_id=stable_id("op", {"plan": plan.plan_id, "kind": "return"}, length=24),
                        opcode=OpCode.RETURN,
                        dialect=Dialect.CORE,
                        operands=(),
                        effects=(Effect.CONTROL,),
                        attributes={},
                        origins=(self._plan_origin(plan, plan_fingerprint),),
                    ),
                ),
                predecessors_hint=(predecessor_for[exit_id],),
                metadata={"role": "exit"},
            )
        )

        function = IRFunction(
            function_id=stable_id("function", {"plan": plan.plan_id}, length=24),
            arguments=(),
            return_types=(),
            blocks=tuple(blocks),
            entry_block=entry_id,
            stage=IRStage.SOURCE_SEMANTIC,
            dialects=(Dialect.CORE, Dialect.JEEVES_SEMANTIC),
            metadata={
                "source_kind": "jeeves_plan",
                "plan_id": plan.plan_id,
                "goal_id": plan.goal_id,
                "plan_version": plan.version,
                "plan_rationale": plan.rationale,
                "plan_created_at": plan.created_at,
                "plan_fingerprint": plan_fingerprint,
                "dependency_graph": {
                    step.step_id: list(step.dependencies)
                    for step in plan.steps
                },
                "topological_schedule": list(schedule),
                "serialization_is_not_original_dependency_semantics": True,
            },
        )
        return IRModule(
            module_id=stable_id("module", {"plan": plan.plan_id, "fingerprint": plan_fingerprint}, length=24),
            functions=(function,),
            ir_version="2026.1",
            target_profile="jeeves-host",
            metadata={
                "compiler": "jeeves.semantic-compiler.v1",
                "compiled_at": self._clock(),
                "source_plan_fingerprint": plan_fingerprint,
                "preserves_dependency_graph": True,
            },
        )

    @staticmethod
    def _effects(step: PlanStep) -> tuple[Effect, ...]:
        if step.tool is None:
            return (Effect.MODEL_CALL, Effect.NONDETERMINISTIC)
        effects = [Effect.TOOL_CALL]
        if step.risk in {
            RiskTier.REVERSIBLE,
            RiskTier.MUTATING,
            RiskTier.EXTERNAL,
            RiskTier.HIGH_IMPACT,
        }:
            effects.append(Effect.EXTERNAL_MUTATION)
        return tuple(sorted(set(effects), key=lambda value: value.value))

    @staticmethod
    def _plan_origin(plan: Plan, fingerprint: str) -> SourceOrigin:
        return SourceOrigin(
            origin_id=stable_id("origin", {"plan": plan.plan_id}, length=24),
            source_kind="jeeves_plan",
            source_ref=plan.plan_id,
            confidence=1.0,
            metadata={
                "goal_id": plan.goal_id,
                "plan_fingerprint": fingerprint,
            },
        )

    @staticmethod
    def _step_origin(plan: Plan, step: PlanStep) -> SourceOrigin:
        fingerprint = stable_fingerprint(
            {
                "plan_id": plan.plan_id,
                "step_id": step.step_id,
                "title": step.title,
                "description": step.description,
                "dependencies": step.dependencies,
                "tool": step.tool,
                "arguments": step.arguments,
                "expected_outcome": step.expected_outcome,
                "verification": step.verification,
                "risk": step.risk.value,
                "status": step.status.value,
                "attempts": step.attempts,
                "max_attempts": step.max_attempts,
            }
        )
        return SourceOrigin(
            origin_id=stable_id("origin", {"plan": plan.plan_id, "step": step.step_id}, length=24),
            source_kind="plan_step",
            source_ref=step.step_id,
            confidence=1.0,
            metadata={
                "plan_id": plan.plan_id,
                "step_fingerprint": fingerprint,
            },
        )

    @staticmethod
    def _topological_schedule(plan: Plan) -> tuple[str, ...]:
        order = {step.step_id: index for index, step in enumerate(plan.steps)}
        dependencies = {step.step_id: set(step.dependencies) for step in plan.steps}
        children: dict[str, set[str]] = {step.step_id: set() for step in plan.steps}
        for step in plan.steps:
            for parent in step.dependencies:
                children[parent].add(step.step_id)
        ready = sorted(
            (step_id for step_id, deps in dependencies.items() if not deps),
            key=lambda value: (order[value], value),
        )
        result: list[str] = []
        while ready:
            current = ready.pop(0)
            result.append(current)
            for child in sorted(children[current], key=lambda value: (order[value], value)):
                dependencies[child].discard(current)
                if not dependencies[child] and child not in result and child not in ready:
                    ready.append(child)
            ready.sort(key=lambda value: (order[value], value))
        if len(result) != len(plan.steps):
            raise AgentContractError("plan dependency graph could not be topologically scheduled")
        return tuple(result)


__all__ = [
    "CompilationArtifact",
    "CompilationPolicy",
    "ExecutionDialectLoweringPass",
    "SemanticCompiler",
]
