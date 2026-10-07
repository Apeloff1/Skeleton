from dataclasses import replace

from skeleton.jeeves.agent.compiler_assurance import (
    CompilerSemanticAssurance,
    PassAnalysisDeclaration,
)
from skeleton.jeeves.agent.compiler_validation import (
    PassContract,
    StageLoweringPass,
    TransactionalPassManager,
)
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


def _verified_model_module(*, declared_nondeterminism: bool, poison: bool = False):
    result = ValueRef("answer", IRType.STRING)
    attrs = {"model": "fixture"}
    if declared_nondeterminism:
        attrs.update(
            {
                "nondeterminism_source": "model-sampling",
                "replay_policy": "record-observation",
            }
        )
    if poison:
        attrs["may_poison"] = True
    infer = Operation(
        op_id="infer",
        opcode=OpCode.MODEL_INFER,
        dialect=Dialect.JEEVES_MODEL,
        results=(result,),
        effects=(Effect.NONDETERMINISTIC,),
        attributes=attrs,
    )
    ret = Operation(
        op_id="return",
        opcode=OpCode.RETURN,
        dialect=Dialect.CORE,
        operands=("answer",),
        effects=(Effect.CONTROL,),
    )
    function = IRFunction(
        function_id="verified-model",
        arguments=(),
        return_types=(IRType.STRING,),
        blocks=(BasicBlock("entry", (infer, ret)),),
        entry_block="entry",
        stage=IRStage.VERIFIED_EXECUTION,
        dialects=(Dialect.CORE, Dialect.JEEVES_MODEL),
    )
    return IRModule("verified-module", (function,))


def _source_module():
    value = ValueRef("x", IRType.INT)
    const = Operation(
        op_id="const",
        opcode=OpCode.CONST,
        dialect=Dialect.CORE,
        results=(value,),
        effects=(Effect.PURE,),
        attributes={"value": 1},
    )
    ret = Operation(
        op_id="ret",
        opcode=OpCode.RETURN,
        dialect=Dialect.CORE,
        operands=("x",),
        effects=(Effect.CONTROL,),
    )
    function = IRFunction(
        function_id="f",
        arguments=(),
        return_types=(IRType.INT,),
        blocks=(BasicBlock("entry", (const, ret)),),
        entry_block="entry",
        stage=IRStage.SOURCE_SEMANTIC,
        dialects=(Dialect.CORE,),
    )
    return IRModule("m", (function,))


def test_verified_nondeterminism_requires_named_source_and_replay_policy():
    report = CompilerSemanticAssurance().inspect(
        _verified_model_module(declared_nondeterminism=False)
    )
    assert report.accepted is False
    assert "undeclared-nondeterminism" in {item.code for item in report.errors}


def test_declared_nondeterminism_is_accepted_but_poison_like_state_is_not():
    checker = CompilerSemanticAssurance()
    declared = checker.inspect(_verified_model_module(declared_nondeterminism=True))
    assert declared.accepted is True
    poison = checker.inspect(
        _verified_model_module(declared_nondeterminism=True, poison=True)
    )
    assert poison.accepted is False
    assert "unfrozen-poison" in {item.code for item in poison.errors}


class _ClaimedDeterministicButIsNot:
    contract = PassContract(
        name="stateful-pass",
        source_stage=IRStage.SOURCE_SEMANTIC,
        target_stage=IRStage.SOURCE_SEMANTIC,
        analysis=PassAnalysisDeclaration(deterministic=True),
    )

    def __init__(self):
        self.counter = 0

    def transform(self, module):
        self.counter += 1
        return replace(module, metadata={**dict(module.metadata), "counter": self.counter})


def test_pass_manager_replays_declared_deterministic_pass_and_rolls_back_on_drift():
    source = _source_module()
    committed, record = TransactionalPassManager(clock=lambda: 10.0).apply(
        source, _ClaimedDeterministicButIsNot()
    )
    assert committed.fingerprint == source.fingerprint
    assert record.rolled_back is True
    assert "declared deterministic" in record.error
    assert record.reproducer is not None
    assert record.source_assurance is not None
    assert record.candidate_assurance is not None


def test_pass_identity_is_content_derived_not_timestamp_derived():
    source = _source_module()
    first_pass = StageLoweringPass(
        IRStage.SOURCE_SEMANTIC,
        IRStage.CANONICAL,
        target_dialect=Dialect.CORE,
        name="clock-independent-pass",
    )
    second_pass = StageLoweringPass(
        IRStage.SOURCE_SEMANTIC,
        IRStage.CANONICAL,
        target_dialect=Dialect.CORE,
        name="clock-independent-pass",
    )
    _, first = TransactionalPassManager(clock=lambda: 1.0).apply(source, first_pass)
    _, second = TransactionalPassManager(clock=lambda: 9999.0).apply(source, second_pass)
    assert first.committed is True
    assert second.committed is True
    assert first.pass_id == second.pass_id
    assert first.created_at != second.created_at


def test_successful_pass_records_source_and_candidate_assurance():
    source = _source_module()
    lowered, record = TransactionalPassManager(clock=lambda: 3.0).apply(
        source,
        StageLoweringPass(
            IRStage.SOURCE_SEMANTIC,
            IRStage.CANONICAL,
            target_dialect=Dialect.CORE,
        ),
    )
    assert lowered.functions[0].stage is IRStage.CANONICAL
    assert record.committed is True
    assert record.source_assurance is not None
    assert record.source_assurance.accepted is True
    assert record.candidate_assurance is not None
    assert record.candidate_assurance.accepted is True
    assert record.metadata["determinism_verified"] is True
