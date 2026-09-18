from __future__ import annotations

import json

import pytest

from skeleton.jeeves.game_engine_3d import (
    SHADERS,
    THREE_D_ERAS,
    Draw3DCommand,
    FixedFunctionMachine,
    ShaderConsoleMachine,
    SoftwareBspMachine,
    ThreeDEngineAdversary,
    ThreeDEngineLab,
    build_3d_engine_tree,
    compile_3d_tuning,
    create_3d_machine,
    default_3d_tuning,
)
from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)


@pytest.mark.parametrize("era", THREE_D_ERAS)
def test_3d_adversary_passes_canonical_engine(
    era: EngineEra,
) -> None:
    report = ThreeDEngineAdversary().evaluate(era)
    assert report.passed
    assert report.score == 1.0
    assert report.failed == ()


@pytest.mark.parametrize(
    ("era", "machine_type"),
    [
        (
            EngineEra.EARLY_3D,
            SoftwareBspMachine,
        ),
        (
            EngineEra.FIXED_3D,
            FixedFunctionMachine,
        ),
        (
            EngineEra.SHADER,
            ShaderConsoleMachine,
        ),
    ],
)
def test_3d_factory_builds_distinct_pipeline_machine(
    era: EngineEra,
    machine_type: type,
) -> None:
    assert isinstance(
        create_3d_machine(era),
        machine_type,
    )


def test_non_3d_runtime_request_fails_closed() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="3D runtime unavailable",
    ):
        create_3d_machine(
            EngineEra.PONG
        )


def test_software_bsp_uses_painter_depth_order() -> None:
    machine = SoftwareBspMachine()
    frame = machine.step()

    assert frame.commands
    assert all(
        frame.commands[index].depth
        >= frame.commands[
            index + 1
        ].depth
        for index
        in range(
            len(frame.commands) - 1
        )
    )
    assert not machine.spec.z_buffer


def test_fixed_function_frustum_culls_far_object() -> None:
    machine = FixedFunctionMachine()
    frame = machine.step()

    assert frame.culled >= 1
    assert machine.spec.z_buffer
    assert all(
        isinstance(
            command,
            Draw3DCommand,
        )
        and command.shader == "fixed"
        for command
        in frame.commands
    )


def test_shader_console_binds_bounded_programs_and_constants() -> None:
    machine = ShaderConsoleMachine()
    frame = machine.step()

    assert frame.commands
    assert all(
        command.shader in SHADERS
        and len(
            command.constants_digest
        )
        == 64
        for command
        in frame.commands
    )


def test_3d_snapshot_tamper_is_rejected() -> None:
    machine = ShaderConsoleMachine()
    machine.step()
    snapshot = machine.snapshot()
    forged = type(snapshot)(
        snapshot.era,
        snapshot.tick,
        snapshot.state,
        "0" * 64,
    )

    with pytest.raises(
        GameEngineLabError,
        match="digest mismatch",
    ):
        machine.restore(forged)


@pytest.mark.parametrize("era", THREE_D_ERAS)
def test_3d_tree_contains_pipeline_visibility_and_tuning(
    era: EngineEra,
) -> None:
    tree = build_3d_engine_tree(
        era,
        "boomer_shooter",
    )

    assert {
        "engine/3d_pipeline.json",
        "engine/visibility.json",
        "engine/3d_tuning.json",
        "assets/scene3d.json",
        "engine/3d_runtime.py",
    } <= set(tree.files)
    assert (
        compile_3d_tuning(
            era,
            tree,
        )
        == default_3d_tuning(era)
    )


def test_shader_tree_carries_program_manifest() -> None:
    assert (
        "engine/shaders.json"
        in build_3d_engine_tree(
            EngineEra.SHADER
        ).files
    )


def test_corrupt_3d_tuning_is_repaired() -> None:
    lab = ThreeDEngineLab()
    sandbox = lab.create(
        EngineEra.EARLY_3D
    )
    path = "engine/3d_tuning.json"
    payload = json.loads(
        sandbox.tree.read(path)
    )
    payload["near_plane"] = 999
    broken = sandbox.apply(
        [
            SandboxPatch(
                path,
                json.dumps(payload),
                sandbox.tree.file_digest(
                    path
                ),
            )
        ]
    )

    assert not lab.evaluate(
        broken
    ).passed

    result = lab.adversarial_improve(
        broken
    )

    assert result.promoted
    assert result.report.passed
    assert len(result.rounds) == 1
    assert result.rounds[0].accepted


def test_regressing_3d_candidate_is_not_promoted() -> None:
    lab = ThreeDEngineLab()
    sandbox = lab.create(
        EngineEra.FIXED_3D
    )
    path = "engine/3d_tuning.json"
    payload = json.loads(
        sandbox.tree.read(path)
    )
    payload["fov_deg"] = 999
    broken = sandbox.apply(
        [
            SandboxPatch(
                path,
                json.dumps(payload),
                sandbox.tree.file_digest(
                    path
                ),
            )
        ]
    )

    def worse(current, report):
        del report
        return (
            SandboxPatch(
                "engine/visibility.json",
                None,
                current.tree.file_digest(
                    "engine/visibility.json"
                ),
            ),
        )

    result = lab.adversarial_improve(
        broken,
        improver=worse,
    )

    assert not result.promoted
    assert len(result.rounds) == 1
    assert not result.rounds[0].accepted


def test_shader_state_identity_uses_stable_digest_not_process_hash() -> None:
    machine = ShaderConsoleMachine()
    frame = machine.step()

    by_shader = {
        command.shader: command.state_key[1]
        for command in frame.commands
    }
    expected = {
        name: int(
            __import__("hashlib").sha256(
                name.encode("utf-8")
            ).hexdigest()[:8],
            16,
        )
        for name in SHADERS
    }

    assert by_shader == expected
