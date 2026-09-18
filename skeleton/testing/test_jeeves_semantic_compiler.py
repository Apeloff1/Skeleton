from dataclasses import replace

from skeleton.jeeves.agent.compiler_validation import (
    PassContract,
    TransactionalPassManager,
    TranslationValidationStatus,
    TranslationValidator,
)
from skeleton.jeeves.agent.semantic_compiler import SemanticCompiler
from skeleton.jeeves.agent.semantic_decompiler import LossKind, SemanticDecompiler
from skeleton.jeeves.agent.semantic_ir import (
    BasicBlock,
    Dialect,
    Effect,
    IRFunction,
    IRModule,
    IRStage,
    IRType,
    OpCode,
    Operation,
    ValueRef,
)
from skeleton.jeeves.agent.types import Plan, PlanStep, RiskTier


def _plan():
    return Plan(
        plan_id="plan-semantic-1",
        goal_id="goal-semantic-1",
        steps=(
            PlanStep(
                step_id="reason",
                title="Reason",
                description="Form a candidate.",
                expected_outcome="Candidate exists.",
                verification="candidate_present",
            ),
            PlanStep(
                step_id="read",
                title="Read",
                description="Read external state.",
                dependencies=("reason",),
                tool="repo.read",
                arguments={"path": "x"},
                expected_outcome="State observed.",
                verification="observation_present",
                risk=RiskTier.READ_ONLY,
            ),
            PlanStep(
                step_id="write",
                title="Write",
                description="Apply a reversible change.",
                dependencies=("read",),
                tool="repo.write",
                arguments={"path": "x", "value": 2},
                expected_outcome="Change applied.",
                verification="write_verified",
                risk=RiskTier.REVERSIBLE,
            ),
        ),
        version=7,
        rationale="Compiler regression fixture.",
        created_at=123.5,
    )


def test_compiler_keeps_every_level_and_translation_validates_lowering():
    artifact = SemanticCompiler(clock=lambda: 200.0).compile_plan(_plan())
    assert artifact.valid is True
    assert artifact.source.functions[0].stage is IRStage.SOURCE_SEMANTIC
    assert artifact.canonical.functions[0].stage is IRStage.CANONICAL
    assert artifact.control.functions[0].stage is IRStage.CONTROL
    assert artifact.execution is not None
    assert artifact.execution.functions[0].stage is IRStage.EXECUTION
    assert all(
        record.validation is not None
        and record.validation.status is TranslationValidationStatus.PROVED_STRUCTURAL
        for record in artifact.passes
    )
    assert artifact.topological_schedule == ("reason", "read", "write")


def test_compiler_preserves_dependency_dag_separately_from_serial_schedule():
    plan = Plan(
        plan_id="plan-dag",
        goal_id="goal-dag",
        steps=(
            PlanStep(step_id="a", title="A", description="A"),
            PlanStep(step_id="b", title="B", description="B"),
            PlanStep(step_id="c", title="C", description="C", dependencies=("a", "b")),
        ),
        created_at=1.0,
    )
    artifact = SemanticCompiler(clock=lambda: 2.0).compile_plan(plan)
    function = artifact.execution.functions[0]
    assert function.metadata["dependency_graph"]["c"] == ["a", "b"]
    assert function.metadata["serialization_is_not_original_dependency_semantics"] is True


def test_mutating_tool_effect_survives_all_lowerings():
    artifact = SemanticCompiler(clock=lambda: 2.0).compile_plan(_plan())
    for module in (artifact.source, artifact.canonical, artifact.control, artifact.execution):
        function = module.functions[0]
        write_ops = [
            op
            for block in function.blocks
            for op in block.operations
            if op.attributes.get("step_id") == "write" and op.opcode is OpCode.TOOL_CALL
        ]
        assert len(write_ops) == 1
        assert Effect.TOOL_CALL in write_ops[0].effects
        assert Effect.EXTERNAL_MUTATION in write_ops[0].effects


def test_decompiler_round_trips_compiled_plan_exactly():
    plan = _plan()
    artifact = SemanticCompiler(clock=lambda: 200.0).compile_plan(plan)
    report = SemanticDecompiler().decompile(artifact.execution)
    assert report.recovered_plan is not None
    assert report.recovered_plan.to_dict() == plan.to_dict()
    assert report.exact_round_trip is True
    assert report.losses == ()
    assert report.source_plan_fingerprint == report.reconstructed_plan_fingerprint


class _BadToolRewrite:
    contract = PassContract(
        name="bad-tool-rewrite",
        source_stage=IRStage.EXECUTION,
        target_stage=IRStage.EXECUTION,
        must_change=True,
        preserve_observable_effects=True,
        preserve_tool_targets=True,
        preserve_returns=True,
    )

    def transform(self, module):
        functions = []
        changed = False
        for function in module.functions:
            blocks = []
            for block in function.blocks:
                operations = []
                for operation in block.operations:
                    if operation.opcode is OpCode.TOOL_CALL and not changed:
                        attrs = dict(operation.attributes)
                        attrs["tool"] = "attacker.retargeted"
                        operation = replace(operation, attributes=attrs)
                        changed = True
                    operations.append(operation)
                blocks.append(replace(block, operations=tuple(operations)))
            functions.append(replace(function, blocks=tuple(blocks)))
        return replace(module, functions=tuple(functions))


def test_translation_validator_rejects_retargeted_tool_call_and_rolls_back():
    artifact = SemanticCompiler(clock=lambda: 2.0).compile_plan(_plan())
    source = artifact.execution
    manager = TransactionalPassManager(clock=lambda: 3.0)
    committed, record = manager.apply(source, _BadToolRewrite())
    assert committed.fingerprint == source.fingerprint
    assert record.rolled_back is True
    assert record.validation is not None
    assert record.validation.status is TranslationValidationStatus.REJECTED
    assert any("tool-call target" in item.reason for item in record.validation.counterexamples)


class _NoOpPass:
    contract = PassContract(
        name="claimed-change",
        source_stage=IRStage.EXECUTION,
        target_stage=IRStage.EXECUTION,
        must_change=True,
    )

    def transform(self, module):
        return module


def test_must_change_pass_cannot_silently_commit_identical_fingerprint():
    artifact = SemanticCompiler(clock=lambda: 2.0).compile_plan(_plan())
    source = artifact.execution
    committed, record = TransactionalPassManager(clock=lambda: 3.0).apply(source, _NoOpPass())
    assert committed.fingerprint == source.fingerprint
    assert record.rolled_back is True
    assert "identical fingerprint" in record.error


def _pure_module(swapped=False):
    left = ValueRef("a", IRType.INT)
    right = ValueRef("b", IRType.INT)
    out = ValueRef("sum", IRType.INT)
    add = Operation(
        op_id="add-op",
        opcode=OpCode.ADD,
        dialect=Dialect.CORE,
        operands=("b", "a") if swapped else ("a", "b"),
        results=(out,),
        effects=(Effect.PURE,),
    )
    ret = Operation(
        op_id="ret-op",
        opcode=OpCode.RETURN,
        dialect=Dialect.CORE,
        operands=("sum",),
        effects=(Effect.CONTROL,),
    )
    block = BasicBlock("entry", (add, ret))
    function = IRFunction(
        function_id="pure-add",
        arguments=(left, right),
        return_types=(IRType.INT,),
        blocks=(block,),
        entry_block="entry",
        stage=IRStage.CANONICAL,
        dialects=(Dialect.CORE,),
    )
    return IRModule("pure-module", (function,))


def test_symbolic_validator_proves_commutative_add_reordering():
    source = _pure_module(False)
    target = _pure_module(True)
    report = TranslationValidator().validate(
        source,
        target,
        contract=PassContract(
            name="commute-add",
            source_stage=IRStage.CANONICAL,
            target_stage=IRStage.CANONICAL,
            must_change=True,
        ),
    )
    assert report.status is TranslationValidationStatus.PROVED_SYMBOLIC
    assert report.accepted is True


def test_decompiler_refuses_to_invent_plan_for_generic_ir():
    report = SemanticDecompiler().decompile(_pure_module(False))
    assert report.recovered_plan is None
    assert report.exact_round_trip is False
    assert any(loss.kind is LossKind.INTENT for loss in report.losses)
