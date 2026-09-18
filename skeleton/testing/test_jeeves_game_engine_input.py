from __future__ import annotations

import json
import math

import pytest

from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.game_engine_input import (
    INPUT_POLICIES,
    HapticMode,
    HapticRequest,
    InputDevice,
    InputNormalizer,
    RawInputSample,
    build_input_normalizer,
    input_policy,
    input_policy_document,
    normalize_haptic,
)
from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from skeleton.jeeves.game_engine_legacy import (
    InputButton,
)
from skeleton.jeeves.game_engine_runtime import (
    ExecutableGameEngineLab,
)


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_every_era_has_historical_input_policy(
    era: EngineEra,
) -> None:
    policy = input_policy(
        era
    )

    assert policy.era is era
    assert era in INPUT_POLICIES
    assert policy.devices
    assert policy.max_players >= 1


def test_input_capabilities_progress_across_eras() -> None:
    pong = input_policy(
        EngineEra.PONG
    )
    arcade = input_policy(
        EngineEra.ARCADE
    )
    fixed = input_policy(
        EngineEra.FIXED_3D
    )
    hd = input_policy(
        EngineEra.HD
    )
    modern = input_policy(
        EngineEra.MODERN
    )
    nxt = input_policy(
        EngineEra.NEXT
    )

    assert pong.devices == (
        InputDevice.PADDLE,
    )
    assert (
        arcade.devices
        == (
            InputDevice.ARCADE_STICK,
        )
    )
    assert fixed.move_axis_bits == 8
    assert (
        fixed.haptic_mode
        is HapticMode.RUMBLE
    )
    assert hd.motion
    assert modern.touch
    assert (
        nxt.haptic_mode
        is HapticMode.ADAPTIVE
    )
    assert (
        nxt.max_players
        > hd.max_players
    )


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_every_routed_sandbox_attests_input_policy(
    era: EngineEra,
) -> None:
    sandbox = (
        ExecutableGameEngineLab()
        .create(
            era
        )
    )
    document = json.loads(
        sandbox.tree.read(
            "engine/input_policy.json"
        )
    )

    assert (
        document
        == input_policy_document(
            era
        )
    )
    assert (
        ExecutableGameEngineLab()
        .evaluate(
            sandbox
        )
        .passed
    )


def test_corrupt_input_policy_is_contract_failure_and_repairable() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.MODERN
    )
    path = (
        "engine/input_policy.json"
    )
    document = json.loads(
        sandbox.tree.read(
            path
        )
    )
    document[
        "max_players"
    ] = 999
    broken = sandbox.apply(
        (
            SandboxPatch(
                path,
                json.dumps(
                    document
                ),
                sandbox.tree.file_digest(
                    path
                ),
            ),
        )
    )

    before = lab.evaluate(
        broken
    )
    assert not before.passed
    assert "contract" in before.failed
    assert (
        path
        in before.contract_mismatches
    )

    repaired = broken.apply(
        lab.canonical_repair(
            broken,
            before,
        )
    )

    assert lab.evaluate(
        repaired
    ).passed
    assert (
        json.loads(
            repaired.tree.read(
                path
            )
        )
        == input_policy_document(
            EngineEra.MODERN
        )
    )


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_normalized_input_drives_actual_historical_machine_deterministically(
    era: EngineEra,
) -> None:
    policy = input_policy(
        era
    )
    sample = RawInputSample(
        tick=0,
        player=0,
        device=policy.devices[0],
        move_y=-0.85,
    )
    normalizer = InputNormalizer(
        era
    )

    first_input = normalizer.normalize(
        sample
    )
    second_input = normalizer.normalize(
        sample
    )

    assert first_input == second_input
    assert len(
        first_input.digest
    ) == 64

    lab = ExecutableGameEngineLab()
    first_machine = (
        lab.create(
            era
        )
        .machine()
    )
    second_machine = (
        lab.create(
            era
        )
        .machine()
    )

    first_frame = first_machine.step(
        first_input.compatibility
    )
    second_frame = second_machine.step(
        second_input.compatibility
    )

    assert first_frame == second_frame
    assert (
        first_machine.fingerprint()
        == second_machine.fingerprint()
    )


def test_pong_paddle_maps_player_one_to_up_down() -> None:
    normalizer = InputNormalizer(
        EngineEra.PONG
    )

    up = normalizer.normalize(
        RawInputSample(
            tick=0,
            player=0,
            device=InputDevice.PADDLE,
            move_y=-1.0,
        )
    )
    down = normalizer.normalize(
        RawInputSample(
            tick=1,
            player=0,
            device=InputDevice.PADDLE,
            move_y=1.0,
        )
    )

    assert up.compatibility.pressed(
        InputButton.UP
    )
    assert down.compatibility.pressed(
        InputButton.DOWN
    )
    assert not up.compatibility.pressed(
        InputButton.A
    )


def test_pong_second_paddle_maps_to_a_b() -> None:
    normalizer = InputNormalizer(
        EngineEra.PONG
    )

    up = normalizer.normalize(
        RawInputSample(
            tick=0,
            player=1,
            device=InputDevice.PADDLE,
            move_y=-1.0,
        )
    )
    down = normalizer.normalize(
        RawInputSample(
            tick=1,
            player=1,
            device=InputDevice.PADDLE,
            move_y=1.0,
        )
    )

    assert up.compatibility.pressed(
        InputButton.A
    )
    assert down.compatibility.pressed(
        InputButton.B
    )


def test_digital_era_synthesizes_direction_from_normalized_axis() -> None:
    normalizer = InputNormalizer(
        EngineEra.EIGHT_BIT
    )

    value = normalizer.normalize(
        RawInputSample(
            tick=0,
            player=0,
            device=InputDevice.DPAD_PAD,
            move_x=0.9,
            move_y=-0.9,
        )
    )

    assert value.move == (
        0.0,
        0.0,
    )
    assert value.compatibility.pressed(
        InputButton.RIGHT
    )
    assert value.compatibility.pressed(
        InputButton.UP
    )


def test_modern_deadzone_removes_small_drift() -> None:
    normalizer = InputNormalizer(
        EngineEra.MODERN
    )

    value = normalizer.normalize(
        RawInputSample(
            tick=0,
            player=0,
            device=InputDevice.DUAL_ANALOG_PAD,
            move_x=0.05,
        )
    )

    assert value.move[0] == 0.0
    assert not value.compatibility.pressed(
        InputButton.RIGHT
    )


def test_analog_quantization_is_deterministic_and_era_specific() -> None:
    fixed = InputNormalizer(
        EngineEra.FIXED_3D
    ).normalize(
        RawInputSample(
            tick=0,
            player=0,
            device=InputDevice.ANALOG_PAD,
            move_x=0.333333,
        )
    )
    modern = InputNormalizer(
        EngineEra.MODERN
    ).normalize(
        RawInputSample(
            tick=0,
            player=0,
            device=InputDevice.DUAL_ANALOG_PAD,
            move_x=0.333333,
        )
    )

    assert fixed.move[0] != modern.move[0]
    assert (
        abs(
            modern.move[0]
            - 0.259259
        )
        < abs(
            fixed.move[0]
            - 0.259259
        )
    )


def test_unsupported_device_fails_closed() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="unavailable",
    ):
        InputNormalizer(
            EngineEra.PONG
        ).normalize(
            RawInputSample(
                tick=0,
                player=0,
                device=InputDevice.XR,
            )
        )


def test_unsupported_button_fails_closed() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="buttons unavailable",
    ):
        InputNormalizer(
            EngineEra.EIGHT_BIT
        ).normalize(
            RawInputSample(
                tick=0,
                player=0,
                device=InputDevice.DPAD_PAD,
                buttons=InputButton.FIRE,
            )
        )


def test_pointer_input_is_gated_by_era() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="pointer input unavailable",
    ):
        InputNormalizer(
            EngineEra.SIXTEEN_BIT
        ).normalize(
            RawInputSample(
                tick=0,
                player=0,
                device=InputDevice.SIX_BUTTON_PAD,
                pointer_x=0.5,
            )
        )

    value = InputNormalizer(
        EngineEra.EARLY_3D
    ).normalize(
        RawInputSample(
            tick=0,
            player=0,
            device=InputDevice.KEYBOARD_MOUSE,
            pointer_x=0.5,
            pointer_y=-0.25,
        )
    )
    assert value.pointer != (
        0.0,
        0.0,
    )


def test_motion_input_is_gated_by_era() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="motion input unavailable",
    ):
        InputNormalizer(
            EngineEra.SHADER
        ).normalize(
            RawInputSample(
                tick=0,
                player=0,
                device=InputDevice.DUAL_ANALOG_PAD,
                motion_x=0.5,
            )
        )

    value = InputNormalizer(
        EngineEra.HD
    ).normalize(
        RawInputSample(
            tick=0,
            player=0,
            device=InputDevice.MOTION_PAD,
            motion_x=0.5,
        )
    )
    assert value.motion[0] != 0.0


def test_touch_input_is_gated_by_era() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="touch input unavailable",
    ):
        InputNormalizer(
            EngineEra.HD
        ).normalize(
            RawInputSample(
                tick=0,
                player=0,
                device=InputDevice.DUAL_ANALOG_PAD,
                touch_active=True,
            )
        )

    value = InputNormalizer(
        EngineEra.OPEN_WORLD
    ).normalize(
        RawInputSample(
            tick=0,
            player=0,
            device=InputDevice.TOUCH,
            touch_active=True,
        )
    )
    assert value.touch_active


def test_player_budget_is_era_specific() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="player budget",
    ):
        InputNormalizer(
            EngineEra.PONG
        ).normalize(
            RawInputSample(
                tick=0,
                player=2,
                device=InputDevice.PADDLE,
            )
        )


def test_batch_normalization_rejects_duplicate_tick_player_identity() -> None:
    normalizer = InputNormalizer(
        EngineEra.MODERN
    )
    sample = RawInputSample(
        tick=4,
        player=0,
        device=InputDevice.DUAL_ANALOG_PAD,
    )

    with pytest.raises(
        GameEngineLabError,
        match="duplicate input sample",
    ):
        normalizer.normalize_many(
            (
                sample,
                sample,
            )
        )


def test_batch_normalization_sorts_tick_then_player() -> None:
    normalizer = InputNormalizer(
        EngineEra.NEXT
    )
    values = normalizer.normalize_many(
        (
            RawInputSample(
                tick=2,
                player=1,
                device=InputDevice.DUAL_ANALOG_PAD,
            ),
            RawInputSample(
                tick=1,
                player=1,
                device=InputDevice.DUAL_ANALOG_PAD,
            ),
            RawInputSample(
                tick=1,
                player=0,
                device=InputDevice.DUAL_ANALOG_PAD,
            ),
        )
    )

    assert [
        (
            item.tick,
            item.player,
        )
        for item in values
    ] == [
        (1, 0),
        (1, 1),
        (2, 1),
    ]


@pytest.mark.parametrize(
    "era",
    [
        EngineEra.PONG,
        EngineEra.ARCADE,
        EngineEra.EIGHT_BIT,
        EngineEra.SIXTEEN_BIT,
        EngineEra.EARLY_3D,
    ],
)
def test_pre_haptic_eras_reject_haptic_output(
    era: EngineEra,
) -> None:
    with pytest.raises(
        GameEngineLabError,
        match="haptic output unavailable",
    ):
        normalize_haptic(
            era,
            HapticRequest(
                tick=0,
                player=0,
                amplitude=0.5,
                frequency_hz=100,
                duration_ticks=4,
            ),
        )


def test_fixed_3d_rumble_is_single_channel() -> None:
    command = normalize_haptic(
        EngineEra.FIXED_3D,
        HapticRequest(
            tick=0,
            player=0,
            amplitude=0.5,
            frequency_hz=100,
            duration_ticks=4,
            channel=0,
        ),
    )

    assert (
        command.mode
        is HapticMode.RUMBLE
    )
    assert len(
        command.digest
    ) == 64

    with pytest.raises(
        GameEngineLabError,
        match="channel 0",
    ):
        normalize_haptic(
            EngineEra.FIXED_3D,
            HapticRequest(
                tick=0,
                player=0,
                amplitude=0.5,
                frequency_hz=100,
                duration_ticks=4,
                channel=1,
            ),
        )


def test_shader_dual_motor_accepts_second_channel_and_rejects_third() -> None:
    second = normalize_haptic(
        EngineEra.SHADER,
        HapticRequest(
            tick=0,
            player=0,
            amplitude=0.7,
            frequency_hz=150,
            duration_ticks=8,
            channel=1,
        ),
    )
    assert second.channel == 1

    with pytest.raises(
        GameEngineLabError,
        match="channels 0 and 1",
    ):
        normalize_haptic(
            EngineEra.SHADER,
            HapticRequest(
                tick=0,
                player=0,
                amplitude=0.7,
                frequency_hz=150,
                duration_ticks=8,
                channel=2,
            ),
        )


def test_next_haptic_clamps_frequency_and_quantizes_amplitude() -> None:
    first = normalize_haptic(
        EngineEra.NEXT,
        HapticRequest(
            tick=7,
            player=0,
            amplitude=0.333333,
            frequency_hz=5000,
            duration_ticks=12,
            channel=3,
        ),
    )
    second = normalize_haptic(
        EngineEra.NEXT,
        HapticRequest(
            tick=7,
            player=0,
            amplitude=0.333333,
            frequency_hz=5000,
            duration_ticks=12,
            channel=3,
        ),
    )

    assert first == second
    assert (
        first.mode
        is HapticMode.ADAPTIVE
    )
    assert first.frequency_hz == 1000
    assert 0.0 < first.amplitude < 1.0


def test_raw_input_rejects_nonfinite_axes() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="finite",
    ):
        RawInputSample(
            tick=0,
            player=0,
            device=InputDevice.DUAL_ANALOG_PAD,
            move_x=math.nan,
        )


def test_builder_returns_era_normalizer() -> None:
    normalizer = build_input_normalizer(
        EngineEra.HD
    )

    assert isinstance(
        normalizer,
        InputNormalizer,
    )
    assert (
        normalizer.era
        is EngineEra.HD
    )


def test_jeeves_owns_input_and_haptic_normalization() -> None:
    jeeves = Jeeves()
    sample = RawInputSample(
        tick=0,
        player=0,
        device=InputDevice.DUAL_ANALOG_PAD,
        move_x=0.8,
    )

    value = jeeves.normalize_game_input(
        EngineEra.MODERN,
        sample,
    )
    command = jeeves.normalize_game_haptic(
        EngineEra.MODERN,
        HapticRequest(
            tick=0,
            player=0,
            amplitude=0.4,
            frequency_hz=120,
            duration_ticks=5,
            channel=2,
        ),
    )

    assert (
        value.era
        is EngineEra.MODERN
    )
    assert value.compatibility.pressed(
        InputButton.RIGHT
    )
    assert (
        command.mode
        is HapticMode.HD_HAPTIC
    )



def test_pong_raw_digital_paddle_buttons_are_preserved_per_player() -> None:
    normalizer = InputNormalizer(
        EngineEra.PONG
    )

    left = normalizer.normalize(
        RawInputSample(
            tick=0,
            player=0,
            device=InputDevice.PADDLE,
            buttons=InputButton.UP,
        )
    )
    right = normalizer.normalize(
        RawInputSample(
            tick=0,
            player=1,
            device=InputDevice.PADDLE,
            buttons=InputButton.B,
        )
    )

    assert left.compatibility.pressed(
        InputButton.UP
    )
    assert right.compatibility.pressed(
        InputButton.B
    )


def test_pong_rejects_other_players_digital_controls() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="other player",
    ):
        InputNormalizer(
            EngineEra.PONG
        ).normalize(
            RawInputSample(
                tick=0,
                player=0,
                device=InputDevice.PADDLE,
                buttons=InputButton.A,
            )
        )


def test_pong_rejects_horizontal_paddle_axis() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="vertical movement axis",
    ):
        InputNormalizer(
            EngineEra.PONG
        ).normalize(
            RawInputSample(
                tick=0,
                player=0,
                device=InputDevice.PADDLE,
                move_x=0.5,
            )
        )
