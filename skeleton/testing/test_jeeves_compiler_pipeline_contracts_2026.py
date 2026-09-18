from __future__ import annotations

from dataclasses import replace

from skeleton.jeeves.compiler.decompiler import Decompiler, LossKind
from skeleton.jeeves.compiler.ir import (
    BasicBlock,
    Effect,
    FunctionIR,
    IRModule,
    IRType,
    Instruction,
    SourceProvenance,
    SSAValue,
    Terminator,
    TerminatorKind,
)
from skeleton.jeeves.compiler.pipeline import (
    AnalysisDomain,
    CompilationPass,
    PassContract,
    PassManager,
)


I64 = IRType("i64")
PROV = (SourceProvenance("unit", 0, 8, 1.0, ("ev:compiler-contract",)),)


def _base_module() -> IRModule:
    x = SSAValue("x", I64)
    one = SSAValue("one", I64)
    out = SSAValue("out", I64)
    block = BasicBlock(
        "entry",
        instructions=(
            Instruction("const", (one,), (), {"value": 1}, provenance=PROV),
            Instruction("add", (out,), ("x", "one"), provenance=PROV),
        ),
        terminator=Terminator(TerminatorKind.RETURN, ("out",), provenance=PROV),
    )
    return IRModule((FunctionIR("f", (x,), (I64,), (block,), "entry"),))


class _StatefulClaimedDeterministicPass(CompilationPass):
    contract = PassContract(
        "stateful-deterministic",
        require_translation_validation=False,
        deterministic=True,
        replay_safe=True,
    )

    def __init__(self) -> None:
        self.counter = 0

    def apply(self, module: IRModule) -> IRModule:
        self.counter += 1
        function = module.functions[0]
        block = function.blocks[0]
        first = replace(
            block.instructions[0],
            attributes={
                **dict(block.instructions[0].attributes),
                "replay_counter": self.counter,
            },
        )
        updated = replace(block, instructions=(first, *block.instructions[1:]))
        return replace(module, functions=(replace(function, blocks=(updated,)),))


class _AnalysisDeclaringNoopPass(CompilationPass):
    contract = PassContract(
        "analysis-contract",
        require_translation_validation=False,
        required_analyses=frozenset({AnalysisDomain.CFG, AnalysisDomain.TYPES}),
        preserved_analyses=frozenset({AnalysisDomain.CFG}),
        invalidated_analyses=frozenset({AnalysisDomain.ALIAS}),
        deterministic=True,
        thread_safe=True,
    )

    def apply(self, module: IRModule) -> IRModule:
        return module




class _ReplayUnsafePass(CompilationPass):
    contract = PassContract(
        "replay-unsafe",
        require_translation_validation=False,
        deterministic=True,
    )

    def __init__(self) -> None:
        self.calls = 0

    def apply(self, module: IRModule) -> IRModule:
        self.calls += 1
        return module


def test_declared_determinism_requires_explicit_replay_safety_before_execution() -> None:
    source = _base_module()
    compiler_pass = _ReplayUnsafePass()

    result, record = PassManager().run_pass(source, compiler_pass)

    assert result.fingerprint == source.fingerprint
    assert record.committed is False
    assert compiler_pass.calls == 0
    assert record.determinism_verified is False
    assert record.analysis_contract["replay_safe"] == ("false",)
    assert any(
        "replay_safe=True" in reason and "not executed" in reason
        for reason in record.rejected_reasons
    )


def test_declared_deterministic_pass_rolls_back_when_replay_changes() -> None:
    source = _base_module()
    result, record = PassManager().run_pass(
        source,
        _StatefulClaimedDeterministicPass(),
    )

    assert result.fingerprint == source.fingerprint
    assert record.committed is False
    assert record.determinism_verified is False
    assert record.determinism_replay_fingerprint is not None
    assert any(
        "declared deterministic but replay fingerprint changed" in reason
        for reason in record.rejected_reasons
    )


def test_pass_record_persists_analysis_contract_and_determinism_result() -> None:
    source = _base_module()
    result, record = PassManager().run_pass(
        source,
        _AnalysisDeclaringNoopPass(),
    )

    assert result.fingerprint == source.fingerprint
    assert record.committed is True
    assert record.determinism_verified is True
    assert record.determinism_replay_fingerprint == source.fingerprint
    assert record.analysis_contract == {
        "required": ("cfg", "types"),
        "preserved": ("cfg",),
        "invalidated": ("alias",),
    }


def _hazard_module() -> IRModule:
    left = SSAValue("left", I64)
    right = SSAValue("right", I64)
    out = SSAValue("out", I64)
    risky = Instruction(
        "div",
        (out,),
        ("left", "right"),
        {
            "may_poison": True,
            "assumption": True,
        },
        effects=frozenset({Effect.NONDETERMINISTIC, Effect.NETWORK}),
        provenance=PROV,
    )
    block = BasicBlock(
        "entry",
        instructions=(risky,),
        terminator=Terminator(TerminatorKind.RETURN, ("out",), provenance=PROV),
    )
    return IRModule(
        (
            FunctionIR(
                "hazard",
                (left, right),
                (I64,),
                (block,),
                "entry",
                declared_effects=frozenset(
                    {Effect.NONDETERMINISTIC, Effect.NETWORK}
                ),
            ),
        )
    )


def test_decompiler_records_unrecoverable_runtime_contracts_explicitly() -> None:
    artifact = Decompiler().decompile(_hazard_module())
    kinds = {loss.kind for loss in artifact.losses}

    assert LossKind.NONDETERMINISM in kinds
    assert LossKind.REPLAY in kinds
    assert LossKind.UNDEFINED_BEHAVIOR in kinds
    assert LossKind.ASSUMPTION in kinds
    assert LossKind.SAFETY_CONTRACT in kinds
    assert artifact.lossless is False
    assert artifact.exact_source_recovery_claimed is False
