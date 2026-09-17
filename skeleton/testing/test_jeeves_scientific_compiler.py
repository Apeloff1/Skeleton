from __future__ import annotations

from dataclasses import replace

from skeleton.jeeves.compiler import (
    AbstractValue,
    BasicBlock,
    CompilationPass,
    Decompiler,
    Effect,
    FunctionIR,
    IRModule,
    IRType,
    IRVerifier,
    Instruction,
    PassContract,
    PassManager,
    SSAValue,
    SourceProvenance,
    Terminator,
    TerminatorKind,
)
from skeleton.jeeves.compiler.pipeline import NumericAbstractInterpreter, PassSemantics
from skeleton.jeeves.science.lineage import (
    ArchitectureObservation,
    LineageDomain,
    PromotionCriterion,
    PromotionStatus,
    default_lineage,
)


I64 = IRType("i64")


def _arithmetic_module(*, add_opcode: str = "add", with_effect: bool = False) -> IRModule:
    x = SSAValue("x", I64)
    one = SSAValue("one", I64)
    out = SSAValue("out", I64)
    provenance = (SourceProvenance("unit", 0, 4, 1.0, ("ev:1",)),)
    instructions = [
        Instruction("const", (one,), (), {"value": 1}, provenance=provenance),
        Instruction(add_opcode, (out,), ("x", "one"), provenance=provenance),
    ]
    effects = frozenset({Effect.PURE})
    declared = frozenset({Effect.PURE})
    if with_effect:
        instructions.append(
            Instruction(
                "emit",
                (),
                ("out",),
                effects=frozenset({Effect.NETWORK}),
                provenance=provenance,
            )
        )
        declared = frozenset({Effect.NETWORK})
    block = BasicBlock(
        "entry",
        instructions=tuple(instructions),
        terminator=Terminator(TerminatorKind.RETURN, ("out",)),
    )
    function = FunctionIR(
        "f",
        (x,),
        (I64,),
        (block,),
        "entry",
        declared_effects=declared,
    )
    return IRModule((function,))


class IdentityPass(CompilationPass):
    contract = PassContract("identity")

    def apply(self, module: IRModule) -> IRModule:
        return module


class SemanticCorruptionPass(CompilationPass):
    contract = PassContract("corrupt")

    def apply(self, module: IRModule) -> IRModule:
        function = module.functions[0]
        block = function.blocks[0]
        instructions = list(block.instructions)
        instructions[1] = replace(instructions[1], opcode="sub")
        new_block = replace(block, instructions=tuple(instructions))
        return replace(module, functions=(replace(function, blocks=(new_block,)),))


class EffectEscalationPass(CompilationPass):
    contract = PassContract("effect-escalation", require_translation_validation=False)

    def apply(self, module: IRModule) -> IRModule:
        function = module.functions[0]
        block = function.blocks[0]
        effectful = Instruction(
            "emit",
            (),
            ("out",),
            effects=frozenset({Effect.NETWORK}),
            provenance=block.instructions[-1].provenance,
        )
        new_block = replace(block, instructions=block.instructions + (effectful,))
        new_function = replace(
            function,
            blocks=(new_block,),
            declared_effects=frozenset({Effect.NETWORK}),
        )
        return replace(module, functions=(new_function,))


class AllowedEffectPass(CompilationPass):
    contract = PassContract(
        "allowed-effect",
        require_translation_validation=False,
        allowed_new_effects=frozenset({Effect.NETWORK}),
    )

    def apply(self, module: IRModule) -> IRModule:
        function = module.functions[0]
        block = function.blocks[0]
        effectful = Instruction(
            "emit",
            (),
            ("out",),
            effects=frozenset({Effect.NETWORK}),
            provenance=block.instructions[-1].provenance,
        )
        new_block = replace(block, instructions=block.instructions + (effectful,))
        return replace(
            module,
            functions=(
                replace(
                    function,
                    blocks=(new_block,),
                    declared_effects=frozenset({Effect.NETWORK}),
                ),
            ),
        )


def test_default_lineage_is_deterministic_and_chronological() -> None:
    lineage = default_lineage()
    ordered = lineage.ordered()
    assert ordered
    assert [record.year for record in ordered] == sorted(record.year for record in ordered)
    assert lineage.fingerprint == default_lineage().fingerprint
    compiler_ids = {record.theory_id for record in lineage.ordered(domain=LineageDomain.COMPILERS)}
    assert {"ssa_1991", "llvm_2004", "egg_2021", "mlir_2021", "llvm22_2026"} <= compiler_ids


def test_newer_architecture_is_not_promoted_when_invariant_regresses() -> None:
    lineage = default_lineage()
    incumbent = ArchitectureObservation(
        "old",
        {"semantic_correctness": 1.0, "throughput": 0.5},
        evidence_count=100,
        independent_runs=10,
        verified=True,
        adversarially_tested=True,
        reproduction_id="old-r1",
    )
    candidate = ArchitectureObservation(
        "new",
        {"semantic_correctness": 0.99, "throughput": 0.9},
        evidence_count=100,
        independent_runs=10,
        verified=True,
        adversarially_tested=True,
        reproduction_id="new-r1",
    )
    decision = lineage.evaluate_promotion(
        incumbent=incumbent,
        candidate=candidate,
        criteria=(
            PromotionCriterion(
                "semantic_correctness",
                weight=10.0,
                minimum_candidate=1.0,
                maximum_regression=0.0,
                mandatory=True,
            ),
            PromotionCriterion("throughput", weight=1.0, maximum_regression=0.2),
        ),
        require_verification=True,
        require_adversarial_test=True,
    )
    assert decision.status == PromotionStatus.REJECT
    assert any(item.startswith("semantic_correctness") for item in decision.mandatory_failures)


def test_promotion_requires_evidence_before_recency_can_matter() -> None:
    lineage = default_lineage()
    incumbent = ArchitectureObservation("incumbent", {"quality": 0.7}, 50, 8)
    candidate = ArchitectureObservation("candidate", {"quality": 0.9}, 1, 1)
    decision = lineage.evaluate_promotion(
        incumbent=incumbent,
        candidate=candidate,
        criteria=(PromotionCriterion("quality", weight=1.0),),
        minimum_evidence=3,
        minimum_independent_runs=2,
    )
    assert decision.status == PromotionStatus.SHADOW
    assert decision.insufficient_evidence


def test_ir_verifier_checks_ssa_and_effect_contracts() -> None:
    module = _arithmetic_module()
    report = IRVerifier().verify(module)
    assert report.valid

    function = module.functions[0]
    bad_instruction = Instruction("add", (SSAValue("bad", I64),), ("missing", "x"))
    bad_block = replace(
        function.blocks[0],
        instructions=(bad_instruction,),
        terminator=Terminator(TerminatorKind.RETURN, ("bad",)),
    )
    bad = replace(module, functions=(replace(function, blocks=(bad_block,)),))
    bad_report = IRVerifier().verify(bad)
    assert not bad_report.valid
    assert "undefined_value" in {item.code for item in bad_report.errors}


def test_translation_validation_commits_equivalent_pass() -> None:
    module = _arithmetic_module()
    result, record = PassManager().run_pass(
        module,
        IdentityPass(),
        validation_cases={"f": ((0,), (1,), (-5,), (100,))},
    )
    assert record.committed
    assert result.fingerprint == module.fingerprint
    assert record.validation is not None
    assert record.validation.tested_cases == 4


def test_semantics_changing_pass_rolls_back_transactionally() -> None:
    module = _arithmetic_module()
    result, record = PassManager().run_pass(
        module,
        SemanticCorruptionPass(),
        validation_cases={"f": ((0,), (1,), (5,))},
    )
    assert not record.committed
    assert result.fingerprint == module.fingerprint
    assert record.candidate_fingerprint != module.fingerprint
    assert record.validation is not None
    assert record.validation.mismatches


def test_effect_escalation_is_rejected_unless_contract_explicitly_allows_it() -> None:
    module = _arithmetic_module()
    manager = PassManager()
    rolled_back, rejected = manager.run_pass(module, EffectEscalationPass())
    assert not rejected.committed
    assert rolled_back.fingerprint == module.fingerprint
    assert any("effect escalation" in reason for reason in rejected.rejected_reasons)

    promoted, accepted = manager.run_pass(module, AllowedEffectPass())
    assert accepted.committed
    assert promoted.fingerprint != module.fingerprint


def test_abstract_interpreter_propagates_sound_intervals() -> None:
    module = _arithmetic_module()
    states = NumericAbstractInterpreter().analyze(
        module.functions[0],
        parameter_ranges={"x": AbstractValue.interval(2, 4)},
    )
    assert "entry" in states
    # Entry state intentionally represents facts *before* executing the block.
    assert states["entry"].get("x") == AbstractValue.interval(2, 4)


def test_decompiler_never_claims_exact_source_recovery() -> None:
    module = _arithmetic_module()
    artifact = Decompiler().decompile(module)
    assert artifact.structurally_valid_source
    assert not artifact.exact_source_recovery_claimed
    assert "exact source recovery: false" in artifact.text
    assert artifact.losses
    assert any(loss.kind.value == "source_type" for loss in artifact.losses)
    assert "%out = add(%x, %one)" in artifact.text


def test_provenance_contributes_to_ir_fingerprint() -> None:
    module = _arithmetic_module()
    function = module.functions[0]
    block = function.blocks[0]
    instruction = block.instructions[0]
    changed_provenance = (SourceProvenance("different", 0, 4, 1.0),)
    changed_instruction = replace(instruction, provenance=changed_provenance)
    changed_block = replace(block, instructions=(changed_instruction,) + block.instructions[1:])
    changed = replace(module, functions=(replace(function, blocks=(changed_block,)),))
    assert changed.fingerprint != module.fingerprint
