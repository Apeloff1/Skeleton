from __future__ import annotations

from dataclasses import replace

from skeleton.jeeves.compiler.assurance import (
    AssuredPassManager,
    CompilerAssuranceEngine,
    CompilerAssurancePolicy,
    DecompilationAssurance,
    DecompilationAssurancePolicy,
    ExternalProofStatus,
    ExternalValidationEvidence,
    ObligationKind,
    ObligationStatus,
)
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
from skeleton.jeeves.compiler.pipeline import CompilationPass, PassContract, PassManager


I64 = IRType("i64")


def _module(*, provenance_confidence: float = 1.0, artifact_id: str = "unit") -> IRModule:
    x = SSAValue("x", I64)
    one = SSAValue("one", I64)
    out = SSAValue("out", I64)
    provenance = (SourceProvenance(artifact_id, 0, 4, provenance_confidence, ("ev:1",)),)
    block = BasicBlock(
        "entry",
        instructions=(
            Instruction("const", (one,), (), {"value": 1}, provenance=provenance),
            Instruction("add", (out,), ("x", "one"), provenance=provenance),
        ),
        terminator=Terminator(TerminatorKind.RETURN, ("out",), provenance=provenance),
    )
    return IRModule((FunctionIR("f", (x,), (I64,), (block,), "entry"),))


class AnnotatingEquivalentPass(CompilationPass):
    contract = PassContract("annotate-equivalent", replay_safe=True)

    def apply(self, module: IRModule) -> IRModule:
        function = module.functions[0]
        block = function.blocks[0]
        instructions = list(block.instructions)
        instructions[1] = replace(instructions[1], attributes={"optimization_note": "semantic-noop"})
        return replace(module, functions=(replace(function, blocks=(replace(block, instructions=tuple(instructions)),)),))


class CorruptingPass(CompilationPass):
    contract = PassContract("corrupt", replay_safe=True)

    def apply(self, module: IRModule) -> IRModule:
        function = module.functions[0]
        block = function.blocks[0]
        instructions = list(block.instructions)
        instructions[1] = replace(instructions[1], opcode="sub")
        return replace(module, functions=(replace(function, blocks=(replace(block, instructions=tuple(instructions)),)),))


class ReplaceProvenancePass(CompilationPass):
    contract = PassContract("replace-provenance", replay_safe=True)

    def apply(self, module: IRModule) -> IRModule:
        function = module.functions[0]
        block = function.blocks[0]
        replacement = (SourceProvenance("unrelated-artifact", 0, 4, 1.0, ("ev:other",)),)
        instructions = tuple(replace(instruction, provenance=replacement) for instruction in block.instructions)
        terminator = replace(block.terminator, provenance=replacement)
        new_block = replace(block, instructions=instructions, terminator=terminator)
        return replace(module, functions=(replace(function, blocks=(new_block,)),))


class WeakenProvenancePass(CompilationPass):
    contract = PassContract("weaken-provenance", replay_safe=True)

    def apply(self, module: IRModule) -> IRModule:
        function = module.functions[0]
        block = function.blocks[0]
        weakened = tuple(replace(item, confidence=0.40) for item in block.instructions[0].provenance)
        instructions = tuple(replace(instruction, provenance=weakened) for instruction in block.instructions)
        terminator = replace(block.terminator, provenance=weakened)
        new_block = replace(block, instructions=instructions, terminator=terminator)
        return replace(module, functions=(replace(function, blocks=(new_block,)),))


class AddUnknownEffectPass(CompilationPass):
    contract = PassContract(
        "unknown-effect",
        allowed_new_effects=frozenset({Effect.UNKNOWN}),
        require_translation_validation=False,
        replay_safe=True,
    )

    def apply(self, module: IRModule) -> IRModule:
        function = module.functions[0]
        block = function.blocks[0]
        opaque = Instruction(
            "opaque_effect",
            (),
            (),
            effects=frozenset({Effect.UNKNOWN}),
            provenance=block.instructions[0].provenance,
        )
        new_block = replace(block, instructions=block.instructions + (opaque,))
        new_function = replace(function, blocks=(new_block,), declared_effects=frozenset({Effect.UNKNOWN}))
        return replace(module, functions=(new_function,))


def _cases():
    return {"f": ((-10,), (0,), (1,), (7,), (1000,))}


def test_semantically_equivalent_changed_pass_can_be_assured_with_bounded_evidence() -> None:
    module = _module()
    result, certificate, base_record = AssuredPassManager().run_pass(
        module,
        AnnotatingEquivalentPass(),
        validation_cases=_cases(),
    )
    assert base_record.committed
    assert certificate.accepted
    assert result.fingerprint != module.fingerprint
    assert not certificate.failures
    kinds = {item.kind: item.status for item in certificate.obligations}
    assert kinds[ObligationKind.STRUCTURAL_VALIDITY] is ObligationStatus.SATISFIED
    assert kinds[ObligationKind.BEHAVIORAL_EQUIVALENCE] is ObligationStatus.SATISFIED
    assert certificate.coverage is not None
    assert certificate.coverage.total_cases == 5


def test_semantic_corruption_is_rolled_back_before_assurance_promotion() -> None:
    module = _module()
    result, certificate, base_record = AssuredPassManager().run_pass(
        module,
        CorruptingPass(),
        validation_cases=_cases(),
    )
    assert not base_record.committed
    assert not certificate.accepted
    assert result.fingerprint == module.fingerprint
    assert base_record.validation is not None
    assert base_record.validation.mismatches


def test_provenance_substitution_is_rejected_even_when_instruction_count_is_unchanged() -> None:
    module = _module()
    # The base manager's legacy check only counts sourced instructions.  The
    # high-assurance layer must detect that the *specific source atoms* changed.
    result, certificate, base_record = AssuredPassManager().run_pass(
        module,
        ReplaceProvenancePass(),
        validation_cases=_cases(),
    )
    assert base_record.committed
    assert not certificate.accepted
    assert result.fingerprint == module.fingerprint
    assert certificate.provenance is not None
    assert certificate.provenance.coverage == 0.0
    assert certificate.provenance.missing_atoms
    failed = {item.kind for item in certificate.failures}
    assert ObligationKind.PROVENANCE_COVERAGE in failed


def test_provenance_confidence_degradation_is_budgeted_independently_of_coverage() -> None:
    module = _module(provenance_confidence=1.0)
    result, certificate, base_record = AssuredPassManager().run_pass(
        module,
        WeakenProvenancePass(),
        validation_cases=_cases(),
    )
    assert base_record.committed
    assert not certificate.accepted
    assert result.fingerprint == module.fingerprint
    assert certificate.provenance is not None
    assert certificate.provenance.coverage == 1.0
    assert certificate.provenance.confidence_retention < 0.98
    assert any(item.kind is ObligationKind.PROVENANCE_CONFIDENCE for item in certificate.failures)


def test_unknown_effect_is_rejected_even_if_pass_contract_declares_it_allowed() -> None:
    module = _module()
    result, certificate, base_record = AssuredPassManager().run_pass(module, AddUnknownEffectPass())
    # Base layer may accept because UNKNOWN was explicitly listed as an allowed
    # new effect, but production assurance treats UNKNOWN as a separate hazard.
    assert base_record.committed
    assert not certificate.accepted
    assert result.fingerprint == module.fingerprint
    assert certificate.effects is not None and certificate.effects.contains_unknown
    assert any(item.kind is ObligationKind.UNKNOWN_EFFECT_ABSENCE for item in certificate.failures)


def test_external_proof_must_be_fingerprint_bound_to_candidate() -> None:
    module = _module()
    candidate, base_record = PassManager().run_pass(
        module,
        AnnotatingEquivalentPass(),
        validation_cases=_cases(),
    )
    assert base_record.committed
    wrong = ExternalValidationEvidence(
        checker="smt-validator",
        checker_version="1.0",
        source_fingerprint=module.fingerprint,
        target_fingerprint="module:deadbeefdeadbeefdeadbeefdeadbeef",
        status=ExternalProofStatus.PROVED,
        property="equivalence",
        proof_artifact_hash="a" * 64,
    )
    accepted, obligations, *_ = CompilerAssuranceEngine().certify(
        module,
        candidate,
        AnnotatingEquivalentPass(),
        base_record,
        validation_cases=_cases(),
        external_evidence=(wrong,),
    )
    assert not accepted
    binding = next(item for item in obligations if item.kind is ObligationKind.EXTERNAL_PROOF_BINDING)
    assert binding.status is ObligationStatus.FAILED


def test_decompiler_assurance_can_forbid_specific_information_loss() -> None:
    artifact = Decompiler().decompile(_module())
    default_report = DecompilationAssurance().audit(artifact)
    assert default_report.artifact_fingerprint == artifact.fingerprint
    assert default_report.weighted_loss > 0.0

    strict = DecompilationAssurance(
        DecompilationAssurancePolicy(
            maximum_weighted_loss=100.0,
            forbidden_losses=frozenset({LossKind.SOURCE_TYPE}),
        )
    ).audit(artifact)
    assert not strict.accepted
    assert LossKind.SOURCE_TYPE.value in strict.forbidden_present
    assert "forbidden information-loss kinds are present" in strict.reasons


def test_assurance_policy_can_raise_provenance_retention_requirement() -> None:
    engine = CompilerAssuranceEngine(
        CompilerAssurancePolicy(
            minimum_provenance_coverage=1.0,
            minimum_provenance_confidence_retention=1.0,
        )
    )
    audit = engine.provenance_audit(_module(provenance_confidence=1.0), _module(provenance_confidence=0.99))
    assert audit.coverage == 1.0
    assert audit.confidence_retention < 1.0
