from __future__ import annotations

from dataclasses import replace

from skeleton.jeeves.compiler.ir import (
    BasicBlock,
    FunctionIR,
    IRModule,
    IRType,
    Instruction,
    SourceProvenance,
    SSAValue,
    Terminator,
    TerminatorKind,
)
from skeleton.jeeves.compiler.pipeline import CompilationPass, PassContract
from skeleton.jeeves.compiler.semantic_assurance import (
    SemanticAssuredPassManager,
    SemanticObligationKind,
    SemanticObligationStatus,
)
from skeleton.jeeves.compiler.semantics import (
    InstructionSemanticContract,
    IntegerSemanticContract,
    OverflowSemantics,
    semantic_contract_attributes,
)


I64 = IRType("i64")
PROV = (SourceProvenance("unit", 0, 12, 1.0, ("ev:semantic-pass",)),)


def _module(*, overflow: OverflowSemantics = OverflowSemantics.WRAP, provenance=PROV) -> IRModule:
    x = SSAValue("x", I64)
    one = SSAValue("one", I64)
    out = SSAValue("out", I64)
    contract = InstructionSemanticContract(
        integer=IntegerSemanticContract(overflow)
    )
    block = BasicBlock(
        "entry",
        instructions=(
            Instruction("const", (one,), (), {"value": 1}, provenance=provenance),
            Instruction(
                "add",
                (out,),
                ("x", "one"),
                semantic_contract_attributes(contract),
                provenance=provenance,
            ),
        ),
        terminator=Terminator(TerminatorKind.RETURN, ("out",), provenance=provenance),
    )
    return IRModule((FunctionIR("f", (x,), (I64,), (block,), "entry"),))


def _cases():
    return {"f": ((-10,), (0,), (1,), (7,), (1000,))}


class IdentityPass(CompilationPass):
    contract = PassContract("semantic-identity", replay_safe=True)

    def apply(self, module: IRModule) -> IRModule:
        return module


class ChangeOverflowPass(CompilationPass):
    contract = PassContract("change-overflow", replay_safe=True)

    def __init__(self, target: OverflowSemantics) -> None:
        self.target = target

    def apply(self, module: IRModule) -> IRModule:
        function = module.functions[0]
        block = function.blocks[0]
        instructions = list(block.instructions)
        original = instructions[1]
        changed = InstructionSemanticContract(
            integer=IntegerSemanticContract(self.target)
        )
        instructions[1] = replace(
            original,
            attributes=semantic_contract_attributes(changed),
        )
        new_block = replace(block, instructions=tuple(instructions))
        return replace(module, functions=(replace(function, blocks=(new_block,)),))


def _statuses(certificate):
    return {item.kind: item.status for item in certificate.obligations}


def test_semantic_identity_is_accepted_when_base_assurance_accepts() -> None:
    module = _module()
    result, certificate, base_certificate, base_record = SemanticAssuredPassManager().run_pass(
        module,
        IdentityPass(),
        validation_cases=_cases(),
    )
    assert base_record.committed
    assert base_certificate.accepted
    assert certificate.accepted
    assert result.fingerprint == module.fingerprint
    assert all(
        item.status is SemanticObligationStatus.SATISFIED
        for item in certificate.obligations
    )


def test_output_equivalent_but_contract_mutating_pass_rolls_back() -> None:
    module = _module(overflow=OverflowSemantics.WRAP)
    result, certificate, base_certificate, base_record = SemanticAssuredPassManager().run_pass(
        module,
        ChangeOverflowPass(OverflowSemantics.SATURATE),
        validation_cases=_cases(),
    )
    # The bounded executor does not model overflow, so these ordinary cases are
    # behaviorally identical. Base assurance therefore accepts the transform.
    assert base_record.committed
    assert base_certificate.accepted
    assert not certificate.accepted
    assert result.fingerprint == module.fingerprint
    statuses = _statuses(certificate)
    assert statuses[SemanticObligationKind.NO_SILENT_CONTRACT_MUTATION] is SemanticObligationStatus.FAILED


def test_risk_escalation_to_poison_is_rejected_even_if_examples_match() -> None:
    module = _module(overflow=OverflowSemantics.WRAP)
    result, certificate, base_certificate, base_record = SemanticAssuredPassManager().run_pass(
        module,
        ChangeOverflowPass(OverflowSemantics.POISON),
        validation_cases=_cases(),
    )
    assert base_record.committed
    assert base_certificate.accepted
    assert not certificate.accepted
    assert result.fingerprint == module.fingerprint
    risk = next(
        item for item in certificate.obligations
        if item.kind is SemanticObligationKind.NO_RISK_ESCALATION
    )
    assert risk.status is SemanticObligationStatus.FAILED
    assert risk.metadata["escalated"]["poison_integer_ops"] == 1


def test_candidate_with_undefined_overflow_fails_candidate_contract_gate() -> None:
    module = _module(overflow=OverflowSemantics.WRAP)
    result, certificate, base_certificate, base_record = SemanticAssuredPassManager().run_pass(
        module,
        ChangeOverflowPass(OverflowSemantics.UNDEFINED),
        validation_cases=_cases(),
    )
    assert base_record.committed
    assert base_certificate.accepted
    assert not certificate.accepted
    assert result.fingerprint == module.fingerprint
    statuses = _statuses(certificate)
    assert statuses[SemanticObligationKind.CANDIDATE_CONTRACTS] is SemanticObligationStatus.FAILED


def test_semantic_contract_without_provenance_is_not_promoted() -> None:
    module = _module(provenance=())
    result, certificate, base_certificate, base_record = SemanticAssuredPassManager().run_pass(
        module,
        IdentityPass(),
        validation_cases=_cases(),
    )
    assert base_record.committed
    assert base_certificate.accepted
    assert not certificate.accepted
    assert result.fingerprint == module.fingerprint
    provenance = next(
        item for item in certificate.obligations
        if item.kind is SemanticObligationKind.CONTRACT_PROVENANCE
    )
    assert provenance.status is SemanticObligationStatus.FAILED
    assert provenance.metadata["count"] == 1
