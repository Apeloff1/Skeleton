from __future__ import annotations

import json

import pytest

from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from skeleton.jeeves.game_engine_runtime import (
    ExecutableGameEngineLab,
)
from skeleton.jeeves.game_engine_scripts import (
    ERA_SCRIPT_POLICIES,
    EraScriptCompiler,
    ScriptAdversary,
    ScriptInstruction,
    ScriptOp,
    ScriptSource,
    ScriptVM,
    attach_script_build,
    canonical_script_patches,
    canonical_script_sources,
    compile_script_build,
    script_policy,
)


def _ins(
    op: ScriptOp,
    *args,
) -> ScriptInstruction:
    return ScriptInstruction(
        op,
        tuple(args),
    )


def test_every_engine_era_has_script_policy() -> None:
    assert set(
        ERA_SCRIPT_POLICIES
    ) == set(EngineEra)


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_canonical_scripts_compile_attach_and_pass_adversary(
    era: EngineEra,
) -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        era,
        "action_adventure",
    )
    sources = canonical_script_sources(
        era
    )

    first = compile_script_build(
        era,
        sources,
    )
    second = compile_script_build(
        era,
        sources,
    )

    assert first == second
    assert len(
        first.manifest_digest
    ) == 64
    assert first.scripts

    attached = attach_script_build(
        sandbox,
        sources,
    )
    report = ScriptAdversary().evaluate(
        attached,
        sources,
    )

    assert report.passed
    assert report.score == 1.0
    assert {
        "manifest",
        "inventory",
        "integrity",
        "determinism",
        "gas",
    } == {
        probe.name
        for probe
        in report.probes
    }


def test_pong_vm_is_tiny_integer_rule_machine() -> None:
    policy = script_policy(
        EngineEra.PONG
    )
    source = ScriptSource(
        "score_rule",
        (
            _ins(
                ScriptOp.CONST,
                0,
                1.4,
            ),
            _ins(
                ScriptOp.CONST,
                1,
                2.2,
            ),
            _ins(
                ScriptOp.ADD,
                2,
                0,
                1,
            ),
            _ins(
                ScriptOp.STORE_STATE,
                0,
                2,
            ),
            _ins(
                ScriptOp.EMIT,
                "score",
                2,
            ),
            _ins(
                ScriptOp.HALT,
            ),
        ),
    )
    compiled = EraScriptCompiler().compile(
        EngineEra.PONG,
        source,
    )
    result = ScriptVM(
        EngineEra.PONG
    ).run(compiled)

    assert policy.registers == 4
    assert result.halted
    assert not result.exhausted
    assert result.state[0] == 3.0
    assert result.events[0].name == "score"
    assert result.events[0].value == 3.0


@pytest.mark.parametrize(
    "op",
    [
        ScriptOp.MUL,
        ScriptOp.DIV,
        ScriptOp.JUMP,
        ScriptOp.CALL,
    ],
)
def test_pong_rejects_later_era_opcodes(
    op: ScriptOp,
) -> None:
    if op in {
        ScriptOp.JUMP,
        ScriptOp.CALL,
    }:
        instruction = _ins(
            op,
            1,
        )
    else:
        instruction = _ins(
            op,
            0,
            1,
            2,
        )
    source = ScriptSource(
        "too_modern",
        (
            instruction,
            _ins(
                ScriptOp.HALT
            ),
        ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="unavailable",
    ):
        EraScriptCompiler().compile(
            EngineEra.PONG,
            source,
        )


def test_sixteen_bit_fixed_point_arithmetic_is_replay_stable() -> None:
    source = ScriptSource(
        "fixed_math",
        (
            _ins(
                ScriptOp.CONST,
                0,
                1.1,
            ),
            _ins(
                ScriptOp.CONST,
                1,
                2.2,
            ),
            _ins(
                ScriptOp.MUL,
                2,
                0,
                1,
            ),
            _ins(
                ScriptOp.HALT,
            ),
        ),
    )
    compiled = EraScriptCompiler().compile(
        EngineEra.SIXTEEN_BIT,
        source,
    )
    vm = ScriptVM(
        EngineEra.SIXTEEN_BIT
    )

    first = vm.run(compiled)
    second = vm.run(compiled)

    assert first == second
    assert (
        first.registers[2]
        == round(
            first.registers[2]
            * 65_536
        )
        / 65_536
    )


@pytest.mark.parametrize(
    "era",
    [
        EngineEra.EARLY_3D,
        EngineEra.FIXED_3D,
        EngineEra.SHADER,
        EngineEra.HD,
        EngineEra.OPEN_WORLD,
        EngineEra.MODERN,
        EngineEra.NEXT,
    ],
)
def test_call_capable_eras_return_deterministically(
    era: EngineEra,
) -> None:
    source = ScriptSource(
        "subroutine",
        (
            _ins(
                ScriptOp.CALL,
                3,
            ),
            _ins(
                ScriptOp.EMIT,
                "return",
                0,
            ),
            _ins(
                ScriptOp.HALT,
            ),
            _ins(
                ScriptOp.CONST,
                0,
                7,
            ),
            _ins(
                ScriptOp.RET,
            ),
            _ins(
                ScriptOp.HALT,
            ),
        ),
    )
    compiled = EraScriptCompiler().compile(
        era,
        source,
    )
    result = ScriptVM(
        era
    ).run(compiled)

    assert result.halted
    assert not result.exhausted
    assert result.registers[0] == 7
    assert result.events[0].value == 7


def test_vm_gas_stops_infinite_arcade_loop() -> None:
    source = ScriptSource(
        "loop",
        (
            _ins(
                ScriptOp.JUMP,
                0,
            ),
            _ins(
                ScriptOp.HALT,
            ),
        ),
    )
    compiled = EraScriptCompiler().compile(
        EngineEra.ARCADE,
        source,
    )
    result = ScriptVM(
        EngineEra.ARCADE
    ).run(compiled)

    assert not result.halted
    assert result.exhausted
    assert (
        result.steps
        == script_policy(
            EngineEra.ARCADE
        ).max_steps
    )


def test_vm_division_by_zero_is_defined_not_host_exception() -> None:
    source = ScriptSource(
        "safe_div",
        (
            _ins(
                ScriptOp.CONST,
                0,
                8,
            ),
            _ins(
                ScriptOp.CONST,
                1,
                0,
            ),
            _ins(
                ScriptOp.DIV,
                2,
                0,
                1,
            ),
            _ins(
                ScriptOp.HALT,
            ),
        ),
    )
    compiled = EraScriptCompiler().compile(
        EngineEra.SIXTEEN_BIT,
        source,
    )
    result = ScriptVM(
        EngineEra.SIXTEEN_BIT
    ).run(compiled)

    assert result.halted
    assert result.registers[2] == 0.0


def test_compile_rejects_out_of_range_jump_target() -> None:
    source = ScriptSource(
        "bad_jump",
        (
            _ins(
                ScriptOp.JUMP,
                99,
            ),
            _ins(
                ScriptOp.HALT,
            ),
        ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="outside program",
    ):
        EraScriptCompiler().compile(
            EngineEra.EIGHT_BIT,
            source,
        )


def test_compile_rejects_register_outside_era_limit() -> None:
    policy = script_policy(
        EngineEra.PONG
    )
    source = ScriptSource(
        "bad_register",
        (
            _ins(
                ScriptOp.CONST,
                policy.registers,
                1,
            ),
            _ins(
                ScriptOp.HALT,
            ),
        ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="register",
    ):
        EraScriptCompiler().compile(
            EngineEra.PONG,
            source,
        )


def test_compile_rejects_duplicate_script_ids() -> None:
    source = ScriptSource(
        "same",
        (
            _ins(
                ScriptOp.HALT
            ),
        ),
    )
    with pytest.raises(
        GameEngineLabError,
        match="unique",
    ):
        EraScriptCompiler().compile_all(
            EngineEra.PONG,
            (
                source,
                source,
            ),
        )


def test_compiled_script_documents_declare_no_host_code_execution() -> None:
    build = compile_script_build(
        EngineEra.NEXT,
        canonical_script_sources(
            EngineEra.NEXT
        ),
    )

    assert (
        build.manifest()[
            "host_code_execution"
        ]
        is False
    )
    assert all(
        script.document()[
            "executable_host_code"
        ]
        is False
        for script in build.scripts
    )


def test_script_manifest_tamper_is_detected_and_repaired() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.EIGHT_BIT
    )
    sources = canonical_script_sources(
        EngineEra.EIGHT_BIT
    )
    attached = attach_script_build(
        sandbox,
        sources,
    )
    path = (
        "scripts/compiled/"
        "manifest.json"
    )
    manifest = json.loads(
        attached.tree.read(path)
    )
    manifest["script_count"] += 1
    broken = attached.apply(
        (
            SandboxPatch(
                path,
                json.dumps(
                    manifest,
                    sort_keys=True,
                ),
                attached.tree.file_digest(
                    path
                ),
            ),
        )
    )

    before = ScriptAdversary().evaluate(
        broken,
        sources,
    )
    assert not before.passed
    assert "manifest" in before.failed

    repaired = broken.apply(
        canonical_script_patches(
            broken,
            sources,
        )
    )

    assert ScriptAdversary().evaluate(
        repaired,
        sources,
    ).passed


def test_untracked_compiled_script_is_quality_failure_and_removed() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.MODERN
    )
    sources = canonical_script_sources(
        EngineEra.MODERN
    )
    attached = attach_script_build(
        sandbox,
        sources,
    )
    rogue_path = (
        "scripts/compiled/"
        "rogue.script.json"
    )
    broken = attached.apply(
        (
            SandboxPatch(
                rogue_path,
                "{}",
            ),
        )
    )

    before = ScriptAdversary().evaluate(
        broken,
        sources,
    )
    assert not before.passed
    assert "inventory" in before.failed

    repaired = broken.apply(
        canonical_script_patches(
            broken,
            sources,
        )
    )

    assert (
        rogue_path
        not in repaired.tree.files
    )
    assert ScriptAdversary().evaluate(
        repaired,
        sources,
    ).passed


def test_runtime_quality_accepts_attested_compiled_script_plane() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.SHADER
    )
    attached = attach_script_build(
        sandbox,
        canonical_script_sources(
            EngineEra.SHADER
        ),
    )

    assert lab.evaluate(
        attached
    ).passed



def test_jeeves_compiles_evaluates_and_executes_era_scripts() -> None:
    jeeves = Jeeves()
    sandbox = jeeves.build_game_engine(
        EngineEra.EIGHT_BIT,
        gameplay_dialect="platformer",
    )
    sources = canonical_script_sources(
        EngineEra.EIGHT_BIT
    )

    compiled = jeeves.compile_game_scripts(
        sandbox,
        sources,
    )
    report = jeeves.evaluate_game_scripts(
        compiled,
        sources,
    )
    result = jeeves.execute_game_script(
        compiled,
        sources[0],
        state=(4.0,),
    )

    assert report.passed
    assert result.halted
    assert not result.exhausted
    assert result.state[0] == 5.0
    assert result.events[0].name == "moved"
    assert (
        jeeves.evaluate_game_engine(
            compiled
        ).passed
    )
