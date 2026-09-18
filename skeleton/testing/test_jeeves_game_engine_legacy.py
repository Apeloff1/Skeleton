from __future__ import annotations

import json

import pytest

from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from skeleton.jeeves.game_engine_legacy import (
    AudioEvent,
    AudioMixer,
    CommandRenderer,
    DrawCommand,
    EightBitTileMachine,
    InputButton,
    InputFrame,
    LEGACY_ERAS,
    LegacyEngineAdversary,
    LegacyEngineLab,
    PongMachine,
    SixteenBitRasterMachine,
    VectorArcadeMachine,
    build_legacy_engine_tree,
    compile_legacy_tuning,
    create_legacy_machine,
    default_legacy_tuning,
    legacy_hardware,
)


@pytest.mark.parametrize("era", LEGACY_ERAS)
def test_legacy_adversary_passes_canonical_machine(era: EngineEra) -> None:
    report = LegacyEngineAdversary().evaluate(era)
    assert report.passed
    assert report.score == 1.0
    assert report.failed == ()
    assert {
        "file_tree",
        "tuning",
        "determinism",
        "draw_budget",
        "audio_budget",
        "snapshot",
    } == {probe.name for probe in report.probes}


@pytest.mark.parametrize(
    ("era", "machine_type"),
    [
        (EngineEra.PONG, PongMachine),
        (EngineEra.ARCADE, VectorArcadeMachine),
        (EngineEra.EIGHT_BIT, EightBitTileMachine),
        (EngineEra.SIXTEEN_BIT, SixteenBitRasterMachine),
    ],
)
def test_factory_builds_period_specific_machine(
    era: EngineEra,
    machine_type: type,
) -> None:
    assert isinstance(
        create_legacy_machine(era),
        machine_type,
    )


def test_nonlegacy_machine_request_fails_closed() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="not implemented",
    ):
        create_legacy_machine(EngineEra.EARLY_3D)


def test_input_tick_mismatch_fails_closed() -> None:
    machine = PongMachine()
    with pytest.raises(
        GameEngineLabError,
        match="input tick mismatch",
    ):
        machine.step(InputFrame(2))


def test_pong_scores_resets_ball_and_emits_score_tone() -> None:
    machine = PongMachine()
    machine.ball_x = 1
    machine.ball_vx = -3
    machine.ball_y = 200
    machine.left_y = 20

    packet = machine.step(InputFrame(0))

    assert machine.right_score == 1
    assert machine.ball_x == machine.spec.width // 2
    assert any(
        event.frequency_hz == 220
        for event in packet.audio_events
    )


def test_vector_arcade_world_wrap_and_fire() -> None:
    machine = VectorArcadeMachine()
    machine.ship_x = 319.9
    machine.vx = 3

    packet = machine.step(
        InputFrame(
            0,
            InputButton.FIRE | InputButton.UP,
        )
    )

    assert 0 <= machine.ship_x < machine.spec.width
    assert machine.shots
    assert any(
        command.kind == "line"
        for command in packet.draw_commands
    )


def test_eight_bit_tile_collision_and_jump() -> None:
    machine = EightBitTileMachine()
    for tick in range(120):
        machine.step(InputFrame(tick))

    assert machine.on_ground
    prior_y = machine.y
    machine.step(
        InputFrame(120, InputButton.A)
    )
    assert machine.y <= prior_y
    assert machine.vy < 0


def test_sixteen_bit_multiplane_and_actor_pool() -> None:
    machine = SixteenBitRasterMachine()
    packet = machine.step(
        InputFrame(0, InputButton.RIGHT)
    )

    assert sum(
        command.kind == "plane"
        for command in packet.draw_commands
    ) == 3
    assert len(machine.actors) == 48


def test_machine_snapshot_rejects_tamper() -> None:
    machine = PongMachine()
    machine.step(InputFrame(0))
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


def test_eight_bit_scanline_sprite_limit_is_enforced() -> None:
    machine = create_legacy_machine(
        EngineEra.EIGHT_BIT
    )
    renderer = CommandRenderer(
        machine.profile,
        machine.spec,
    )
    for index in range(20):
        renderer.emit(
            DrawCommand(
                "sprite",
                1,
                (index, 30, index, 0),
            )
        )

    commands = renderer.flush()

    assert (
        len(commands)
        == machine.spec.max_sprites_per_scanline
    )
    assert renderer.dropped == 12


def test_pong_audio_voice_limit_keeps_higher_priority_tone() -> None:
    spec = legacy_hardware(EngineEra.PONG)
    mixer = AudioMixer(spec)
    mixer.emit(
        AudioEvent(
            0,
            "square",
            220,
            3,
            priority=1,
        )
    )
    mixer.emit(
        AudioEvent(
            0,
            "square",
            880,
            2,
            priority=5,
        )
    )

    events = mixer.flush()

    assert len(events) == 1
    assert events[0].frequency_hz == 880


@pytest.mark.parametrize("era", LEGACY_ERAS)
def test_legacy_file_tree_contains_runtime_contracts(
    era: EngineEra,
) -> None:
    tree = build_legacy_engine_tree(
        era,
        "soulslike",
    )
    assert {
        "engine/input.json",
        "engine/audio.json",
        "engine/legacy_renderer.json",
        "engine/legacy_runtime.py",
        "engine/legacy_tuning.json",
    } <= set(tree.files)

    renderer = json.loads(
        tree.read(
            "engine/legacy_renderer.json"
        )
    )
    assert (
        renderer["renderer"]
        == legacy_hardware(era).renderer
    )


@pytest.mark.parametrize("era", LEGACY_ERAS)
def test_bounded_tuning_compiles_into_machine(
    era: EngineEra,
) -> None:
    lab = LegacyEngineLab()
    sandbox = lab.create(
        era,
        "soulslike",
    )

    assert (
        compile_legacy_tuning(
            era,
            sandbox.tree,
        )
        == default_legacy_tuning(era)
    )
    assert sandbox.machine().profile.era is era


def test_corrupt_tuning_is_repaired_by_adversarial_loop() -> None:
    lab = LegacyEngineLab()
    sandbox = lab.create(
        EngineEra.PONG,
        "arcade_golden_age",
    )
    path = "engine/legacy_tuning.json"
    payload = json.loads(
        sandbox.tree.read(path)
    )
    payload["paddle_speed"] = 999
    broken = sandbox.apply(
        [
            SandboxPatch(
                path,
                json.dumps(payload),
                sandbox.tree.file_digest(path),
            )
        ]
    )

    before = lab.evaluate(broken)
    assert not before.passed
    assert "tuning" in before.failed

    result = lab.adversarial_improve(
        broken
    )

    assert result.promoted
    assert result.report.passed
    assert len(result.rounds) == 1
    assert result.rounds[0].accepted
    assert (
        compile_legacy_tuning(
            EngineEra.PONG,
            result.sandbox.tree,
        )
        == default_legacy_tuning(
            EngineEra.PONG
        )
    )


def test_regressing_ai_candidate_is_not_promoted() -> None:
    lab = LegacyEngineLab()
    sandbox = lab.create(
        EngineEra.ARCADE
    )
    path = "engine/legacy_tuning.json"
    payload = json.loads(
        sandbox.tree.read(path)
    )
    payload["thrust"] = 999
    broken = sandbox.apply(
        [
            SandboxPatch(
                path,
                json.dumps(payload),
                sandbox.tree.file_digest(path),
            )
        ]
    )

    def worse(current, report):
        del report
        return (
            SandboxPatch(
                "engine/audio.json",
                None,
                current.tree.file_digest(
                    "engine/audio.json"
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
    assert (
        result.sandbox.tree.digest
        == broken.tree.digest
    )
