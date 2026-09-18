from __future__ import annotations

from dataclasses import replace

import pytest

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
from skeleton.jeeves.compiler.semantics import (
    AliasRelation,
    DivisionByZeroSemantics,
    FloatMode,
    FloatSemanticContract,
    InstructionSemanticContract,
    IntegerSemanticContract,
    MemoryAccessKind,
    MemoryOrdering,
    MemorySemanticContract,
    ModuleSemanticAuditor,
    NaNSemantics,
    NondeterminismContract,
    NondeterminismKind,
    OverflowSemantics,
    RoundingMode,
    SemanticContractCodec,
    SemanticContractError,
    SemanticDecompiler,
    SemanticSafetyProfile,
    semantic_contract_attributes,
)


I37 = IRType("i37")
F32 = IRType("f32")
PROV = (SourceProvenance("unit", 0, 8, 1.0, ("ev:semantics",)),)


def _module(instruction: Instruction, *, parameters: tuple[SSAValue, ...] = ()) -> IRModule:
    result_ids = tuple(item.value_id for item in instruction.results)
    terminator = (
        Terminator(TerminatorKind.RETURN, result_ids[:1], provenance=PROV)
        if result_ids
        else Terminator(TerminatorKind.RETURN, (), provenance=PROV)
    )
    declared = instruction.effects
    block = BasicBlock("entry", instructions=(instruction,), terminator=terminator)
    function = FunctionIR(
        "f",
        parameters,
        tuple(item.value_type for item in instruction.results[:1]),
        (block,),
        "entry",
        declared_effects=declared,
    )
    return IRModule((function,))


def _codes(module: IRModule, *, profile: SemanticSafetyProfile | None = None) -> set[str]:
    return {item.code for item in ModuleSemanticAuditor(profile).audit(module).diagnostics}


def test_fixed_width_integer_requires_explicit_overflow_contract() -> None:
    out = SSAValue("out", I37)
    instruction = Instruction("add", (out,), (), provenance=PROV)
    assert "SEM.INTEGER.MISSING" in _codes(_module(instruction))


def test_arbitrary_integer_width_is_recognized_and_wrap_contract_is_valid() -> None:
    out = SSAValue("out", I37)
    contract = InstructionSemanticContract(
        integer=IntegerSemanticContract(OverflowSemantics.WRAP)
    )
    instruction = Instruction(
        "add",
        (out,),
        (),
        semantic_contract_attributes(contract),
        provenance=PROV,
    )
    report = ModuleSemanticAuditor().audit(_module(instruction))
    assert report.valid
    assert report.facts[0].contract.integer is not None
    assert report.facts[0].contract.integer.overflow is OverflowSemantics.WRAP


def test_integer_division_requires_divide_by_zero_semantics() -> None:
    out = SSAValue("out", I37)
    contract = InstructionSemanticContract(
        integer=IntegerSemanticContract(OverflowSemantics.WRAP)
    )
    instruction = Instruction(
        "div",
        (out,),
        (),
        semantic_contract_attributes(contract),
        provenance=PROV,
    )
    assert "SEM.INTEGER.DIVZERO" in _codes(_module(instruction))

    complete = replace(
        contract,
        integer=IntegerSemanticContract(
            OverflowSemantics.WRAP,
            DivisionByZeroSemantics.TRAP,
        ),
    )
    valid = replace(instruction, attributes=semantic_contract_attributes(complete))
    assert ModuleSemanticAuditor().audit(_module(valid)).valid


def test_undefined_integer_behavior_fails_closed() -> None:
    out = SSAValue("out", I37)
    contract = InstructionSemanticContract(
        integer=IntegerSemanticContract(OverflowSemantics.UNDEFINED)
    )
    instruction = Instruction(
        "add",
        (out,),
        (),
        semantic_contract_attributes(contract),
        provenance=PROV,
    )
    report = ModuleSemanticAuditor().audit(_module(instruction))
    assert not report.valid
    assert report.risk.undefined_integer_ops == 1
    assert "SEM.INTEGER.UNDEFINED" in {item.code for item in report.diagnostics}


def test_memory_effect_requires_contract_and_unknown_alias_rejected() -> None:
    out = SSAValue("out", I37)
    bare = Instruction(
        "load",
        (out,),
        (),
        effects=frozenset({Effect.READ_MEMORY}),
        provenance=PROV,
    )
    assert "SEM.MEMORY.MISSING" in _codes(_module(bare))

    unknown_alias = InstructionSemanticContract(
        memory=MemorySemanticContract(
            "heap:users",
            access=MemoryAccessKind.PLAIN,
            alias=AliasRelation.UNKNOWN,
        )
    )
    instruction = replace(
        bare,
        attributes=semantic_contract_attributes(unknown_alias),
    )
    strict = ModuleSemanticAuditor().audit(_module(instruction))
    assert not strict.valid
    assert strict.risk.unknown_alias_accesses == 1

    relaxed = ModuleSemanticAuditor(
        SemanticSafetyProfile(reject_unknown_alias=False)
    ).audit(_module(instruction))
    assert relaxed.valid


def test_atomic_order_legality_is_checked_by_access_direction() -> None:
    out = SSAValue("out", I37)
    bad_contract = InstructionSemanticContract(
        memory=MemorySemanticContract(
            "shared:counter",
            access=MemoryAccessKind.ATOMIC,
            ordering=MemoryOrdering.RELEASE,
            alias=AliasRelation.MUST_ALIAS,
        )
    )
    read = Instruction(
        "atomic_load",
        (out,),
        (),
        semantic_contract_attributes(bad_contract),
        effects=frozenset({Effect.READ_MEMORY}),
        provenance=PROV,
    )
    assert "SEM.ATOMIC.ORDER" in _codes(_module(read))

    good_contract = replace(
        bad_contract,
        memory=replace(
            bad_contract.memory,
            ordering=MemoryOrdering.ACQUIRE,
        ),
    )
    good = replace(read, attributes=semantic_contract_attributes(good_contract))
    assert ModuleSemanticAuditor().audit(_module(good)).valid


def test_float_contract_distinguishes_strict_ieee_from_fast_math() -> None:
    out = SSAValue("out", F32)
    fast = InstructionSemanticContract(
        floating=FloatSemanticContract(
            mode=FloatMode.FAST_MATH,
            rounding=RoundingMode.NEAREST_EVEN,
            nan=NaNSemantics.ASSUME_ABSENT,
            preserve_signed_zero=False,
        )
    )
    instruction = Instruction(
        "add",
        (out,),
        (),
        semantic_contract_attributes(fast),
        provenance=PROV,
    )
    report = ModuleSemanticAuditor().audit(_module(instruction))
    assert not report.valid
    assert report.risk.fast_math_ops == 1
    assert report.risk.assume_no_nan_ops == 1

    strict = replace(
        instruction,
        attributes=semantic_contract_attributes(
            InstructionSemanticContract(
                floating=FloatSemanticContract(
                    mode=FloatMode.STRICT_IEEE,
                    rounding=RoundingMode.NEAREST_EVEN,
                    nan=NaNSemantics.PRESERVE,
                    preserve_signed_zero=True,
                )
            )
        ),
    )
    assert ModuleSemanticAuditor().audit(_module(strict)).valid


def test_nondeterminism_requires_source_and_seed_contract() -> None:
    out = SSAValue("out", I37)
    bare = Instruction(
        "random",
        (out,),
        (),
        effects=frozenset({Effect.NONDETERMINISTIC}),
        provenance=PROV,
    )
    assert "SEM.NONDET.MISSING" in _codes(_module(bare))

    seeded = InstructionSemanticContract(
        nondeterminism=NondeterminismContract(
            NondeterminismKind.SEEDED,
            seed_source="run.seed",
        )
    )
    valid = replace(bare, attributes=semantic_contract_attributes(seeded))
    assert ModuleSemanticAuditor().audit(_module(valid)).valid


def test_codec_rejects_string_boolean_and_string_schema_version() -> None:
    out = SSAValue("out", F32)
    string_bool = Instruction(
        "add",
        (out,),
        (),
        {
            "semantic_contract": {
                "schema_version": 1,
                "memory": None,
                "integer": None,
                "floating": {
                    "mode": "strict_ieee",
                    "rounding": "nearest_even",
                    "nan": "preserve",
                    "preserve_signed_zero": "false",
                },
                "nondeterminism": None,
            }
        },
        provenance=PROV,
    )
    with pytest.raises(SemanticContractError):
        SemanticContractCodec.from_instruction(string_bool)

    string_schema = replace(
        string_bool,
        attributes={
            "semantic_contract": {
                "schema_version": "1",
                "memory": None,
                "integer": None,
                "floating": {
                    "mode": "strict_ieee",
                    "rounding": "nearest_even",
                    "nan": "preserve",
                    "preserve_signed_zero": True,
                },
                "nondeterminism": None,
            }
        },
    )
    with pytest.raises(SemanticContractError):
        SemanticContractCodec.from_instruction(string_schema)


def test_semantic_decompiler_marks_under_specified_ir_unsafe() -> None:
    out = SSAValue("out", I37)
    bare = Instruction("add", (out,), (), provenance=PROV)
    unsafe = SemanticDecompiler().decompile(_module(bare))
    assert not unsafe.safe_for_reasoning
    assert "unresolved machine-semantics" in unsafe.reasons[0]

    explicit = replace(
        bare,
        attributes=semantic_contract_attributes(
            InstructionSemanticContract(
                integer=IntegerSemanticContract(OverflowSemantics.WRAP)
            )
        ),
    )
    safe = SemanticDecompiler().decompile(_module(explicit))
    assert safe.safe_for_reasoning
    assert '"semantic_contract"' in safe.artifact.text
    assert safe.source_audit.valid
