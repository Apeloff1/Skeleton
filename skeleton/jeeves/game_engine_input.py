"""Deterministic historical input and haptic normalization for Jeeves engines.

The executable machines keep one small compatibility boundary: InputFrame.
This module evolves the device side from Pong paddles through digital pads,
mouse/keyboard, analog sticks, motion, touch and next-era XR, then lowers those
samples into the existing compatibility frame plus attested analog metadata.

Godot controller generators and the input/haptics knowledge seed remain
separate authoring/reference surfaces. This module is runtime authority:
no host device polling, wall clock, random source, or platform API is used.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

from .game_engine_lab import EngineEra, GameEngineLabError
from .game_engine_legacy import InputButton, InputFrame

INPUT_SCHEMA_VERSION = 1
MAX_INPUT_PLAYERS = 16
MAX_HAPTIC_TICKS = 60 * 30


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        _canonical(value).encode("utf-8")
    ).hexdigest()


def _finite(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise GameEngineLabError(
            f"{label} must be finite"
        )
    return result


def _unit_signed(value: float, label: str) -> float:
    result = _finite(value, label)
    if not -1.0 <= result <= 1.0:
        raise GameEngineLabError(
            f"{label} must be within [-1, 1]"
        )
    return result


def _unit_unsigned(value: float, label: str) -> float:
    result = _finite(value, label)
    if not 0.0 <= result <= 1.0:
        raise GameEngineLabError(
            f"{label} must be within [0, 1]"
        )
    return result


class InputDevice(str, Enum):
    PADDLE = "paddle"
    ARCADE_STICK = "arcade_stick"
    DPAD_PAD = "dpad_pad"
    SIX_BUTTON_PAD = "six_button_pad"
    KEYBOARD_MOUSE = "keyboard_mouse"
    ANALOG_PAD = "analog_pad"
    DUAL_ANALOG_PAD = "dual_analog_pad"
    MOTION_PAD = "motion_pad"
    TOUCH = "touch"
    XR = "xr"


class HapticMode(str, Enum):
    NONE = "none"
    RUMBLE = "rumble"
    DUAL_MOTOR = "dual_motor"
    HD_HAPTIC = "hd_haptic"
    ADAPTIVE = "adaptive"


@dataclass(frozen=True, slots=True)
class EraInputPolicy:
    era: EngineEra
    devices: tuple[InputDevice, ...]
    button_mask: InputButton
    move_axis_bits: int
    aim_axis_bits: int
    trigger_bits: int
    deadzone: float
    pointer: bool
    motion: bool
    touch: bool
    max_players: int
    haptic_mode: HapticMode
    haptic_amplitude_bits: int
    haptic_frequency_min: int
    haptic_frequency_max: int

    def __post_init__(self) -> None:
        if not self.devices:
            raise GameEngineLabError(
                "input policy requires a device"
            )
        if (
            not 0 <= self.move_axis_bits <= 16
            or not 0 <= self.aim_axis_bits <= 16
            or not 0 <= self.trigger_bits <= 16
            or not 0 <= self.haptic_amplitude_bits <= 16
        ):
            raise GameEngineLabError(
                "input quantization bits outside range"
            )
        if not 0.0 <= self.deadzone < 1.0:
            raise GameEngineLabError(
                "input deadzone outside [0, 1)"
            )
        if not 1 <= self.max_players <= MAX_INPUT_PLAYERS:
            raise GameEngineLabError(
                "input player budget outside range"
            )
        if self.haptic_mode is HapticMode.NONE:
            if self.haptic_amplitude_bits != 0:
                raise GameEngineLabError(
                    "non-haptic era cannot expose amplitude bits"
                )
        elif (
            self.haptic_amplitude_bits <= 0
            or self.haptic_frequency_min <= 0
            or self.haptic_frequency_max
            < self.haptic_frequency_min
        ):
            raise GameEngineLabError(
                "haptic policy range invalid"
            )


MOVE_BUTTONS = (
    InputButton.UP
    | InputButton.DOWN
    | InputButton.LEFT
    | InputButton.RIGHT
)
PONG_BUTTONS = (
    InputButton.UP
    | InputButton.DOWN
    | InputButton.START
    | InputButton.A
    | InputButton.B
)
ARCADE_BUTTONS = (
    MOVE_BUTTONS
    | InputButton.FIRE
    | InputButton.START
)
EIGHT_BIT_BUTTONS = (
    MOVE_BUTTONS
    | InputButton.START
    | InputButton.A
    | InputButton.B
)
SIXTEEN_BIT_BUTTONS = (
    EIGHT_BIT_BUTTONS
    | InputButton.C
    | InputButton.FIRE
)
FULL_BUTTONS = SIXTEEN_BIT_BUTTONS


def _policy(
    era: EngineEra,
    devices: tuple[InputDevice, ...],
    button_mask: InputButton,
    move_bits: int,
    aim_bits: int,
    trigger_bits: int,
    deadzone: float,
    *,
    pointer: bool,
    motion: bool,
    touch: bool,
    players: int,
    haptic: HapticMode,
    haptic_bits: int = 0,
    haptic_min: int = 0,
    haptic_max: int = 0,
) -> EraInputPolicy:
    return EraInputPolicy(
        era,
        devices,
        button_mask,
        move_bits,
        aim_bits,
        trigger_bits,
        deadzone,
        pointer,
        motion,
        touch,
        players,
        haptic,
        haptic_bits,
        haptic_min,
        haptic_max,
    )


INPUT_POLICIES: Mapping[EngineEra, EraInputPolicy] = {
    EngineEra.PONG: _policy(
        EngineEra.PONG,
        (InputDevice.PADDLE,),
        PONG_BUTTONS,
        6,
        0,
        0,
        0.0,
        pointer=False,
        motion=False,
        touch=False,
        players=2,
        haptic=HapticMode.NONE,
    ),
    EngineEra.ARCADE: _policy(
        EngineEra.ARCADE,
        (InputDevice.ARCADE_STICK,),
        ARCADE_BUTTONS,
        0,
        0,
        0,
        0.25,
        pointer=False,
        motion=False,
        touch=False,
        players=2,
        haptic=HapticMode.NONE,
    ),
    EngineEra.EIGHT_BIT: _policy(
        EngineEra.EIGHT_BIT,
        (InputDevice.DPAD_PAD,),
        EIGHT_BIT_BUTTONS,
        0,
        0,
        0,
        0.25,
        pointer=False,
        motion=False,
        touch=False,
        players=2,
        haptic=HapticMode.NONE,
    ),
    EngineEra.SIXTEEN_BIT: _policy(
        EngineEra.SIXTEEN_BIT,
        (InputDevice.SIX_BUTTON_PAD,),
        SIXTEEN_BIT_BUTTONS,
        0,
        0,
        0,
        0.22,
        pointer=False,
        motion=False,
        touch=False,
        players=4,
        haptic=HapticMode.NONE,
    ),
    EngineEra.EARLY_3D: _policy(
        EngineEra.EARLY_3D,
        (
            InputDevice.KEYBOARD_MOUSE,
            InputDevice.DPAD_PAD,
        ),
        FULL_BUTTONS,
        0,
        8,
        0,
        0.20,
        pointer=True,
        motion=False,
        touch=False,
        players=4,
        haptic=HapticMode.NONE,
    ),
    EngineEra.FIXED_3D: _policy(
        EngineEra.FIXED_3D,
        (
            InputDevice.ANALOG_PAD,
            InputDevice.KEYBOARD_MOUSE,
        ),
        FULL_BUTTONS,
        8,
        8,
        8,
        0.18,
        pointer=True,
        motion=False,
        touch=False,
        players=4,
        haptic=HapticMode.RUMBLE,
        haptic_bits=8,
        haptic_min=20,
        haptic_max=180,
    ),
    EngineEra.SHADER: _policy(
        EngineEra.SHADER,
        (
            InputDevice.DUAL_ANALOG_PAD,
            InputDevice.KEYBOARD_MOUSE,
        ),
        FULL_BUTTONS,
        8,
        8,
        8,
        0.16,
        pointer=True,
        motion=False,
        touch=False,
        players=4,
        haptic=HapticMode.DUAL_MOTOR,
        haptic_bits=8,
        haptic_min=20,
        haptic_max=250,
    ),
    EngineEra.HD: _policy(
        EngineEra.HD,
        (
            InputDevice.DUAL_ANALOG_PAD,
            InputDevice.KEYBOARD_MOUSE,
            InputDevice.MOTION_PAD,
        ),
        FULL_BUTTONS,
        10,
        10,
        10,
        0.14,
        pointer=True,
        motion=True,
        touch=False,
        players=4,
        haptic=HapticMode.DUAL_MOTOR,
        haptic_bits=10,
        haptic_min=20,
        haptic_max=320,
    ),
    EngineEra.OPEN_WORLD: _policy(
        EngineEra.OPEN_WORLD,
        (
            InputDevice.DUAL_ANALOG_PAD,
            InputDevice.KEYBOARD_MOUSE,
            InputDevice.MOTION_PAD,
            InputDevice.TOUCH,
        ),
        FULL_BUTTONS,
        12,
        12,
        12,
        0.12,
        pointer=True,
        motion=True,
        touch=True,
        players=4,
        haptic=HapticMode.HD_HAPTIC,
        haptic_bits=12,
        haptic_min=15,
        haptic_max=400,
    ),
    EngineEra.MODERN: _policy(
        EngineEra.MODERN,
        (
            InputDevice.DUAL_ANALOG_PAD,
            InputDevice.KEYBOARD_MOUSE,
            InputDevice.MOTION_PAD,
            InputDevice.TOUCH,
            InputDevice.XR,
        ),
        FULL_BUTTONS,
        16,
        16,
        16,
        0.10,
        pointer=True,
        motion=True,
        touch=True,
        players=8,
        haptic=HapticMode.HD_HAPTIC,
        haptic_bits=16,
        haptic_min=10,
        haptic_max=500,
    ),
    EngineEra.NEXT: _policy(
        EngineEra.NEXT,
        (
            InputDevice.DUAL_ANALOG_PAD,
            InputDevice.KEYBOARD_MOUSE,
            InputDevice.MOTION_PAD,
            InputDevice.TOUCH,
            InputDevice.XR,
        ),
        FULL_BUTTONS,
        16,
        16,
        16,
        0.08,
        pointer=True,
        motion=True,
        touch=True,
        players=16,
        haptic=HapticMode.ADAPTIVE,
        haptic_bits=16,
        haptic_min=5,
        haptic_max=1000,
    ),
}


def input_policy(era: EngineEra | str) -> EraInputPolicy:
    try:
        key = (
            era
            if isinstance(era, EngineEra)
            else EngineEra(str(era))
        )
    except ValueError as exc:
        raise GameEngineLabError(
            f"unknown engine era: {era!r}"
        ) from exc
    return INPUT_POLICIES[key]


def input_policy_document(
    era: EngineEra | str,
) -> dict[str, object]:
    policy = input_policy(
        era
    )
    return {
        "schema_version":
            INPUT_SCHEMA_VERSION,
        "engine_era":
            policy.era.value,
        "devices": [
            device.value
            for device
            in policy.devices
        ],
        "button_mask":
            int(
                policy.button_mask
            ),
        "move_axis_bits":
            policy.move_axis_bits,
        "aim_axis_bits":
            policy.aim_axis_bits,
        "trigger_bits":
            policy.trigger_bits,
        "deadzone":
            policy.deadzone,
        "pointer":
            policy.pointer,
        "motion":
            policy.motion,
        "touch":
            policy.touch,
        "max_players":
            policy.max_players,
        "haptic_mode":
            policy.haptic_mode.value,
        "haptic_amplitude_bits":
            policy.haptic_amplitude_bits,
        "haptic_frequency_hz": [
            policy.haptic_frequency_min,
            policy.haptic_frequency_max,
        ],
        "host_device_polling":
            False,
    }


@dataclass(frozen=True, slots=True)
class RawInputSample:
    tick: int
    player: int
    device: InputDevice
    buttons: InputButton = InputButton.NONE
    move_x: float = 0.0
    move_y: float = 0.0
    aim_x: float = 0.0
    aim_y: float = 0.0
    left_trigger: float = 0.0
    right_trigger: float = 0.0
    pointer_x: float = 0.0
    pointer_y: float = 0.0
    motion_x: float = 0.0
    motion_y: float = 0.0
    motion_z: float = 0.0
    touch_active: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.tick) is not int
            or self.tick < 0
        ):
            raise GameEngineLabError(
                "input tick must be a non-negative integer"
            )
        if (
            type(self.player) is not int
            or not 0 <= self.player < MAX_INPUT_PLAYERS
        ):
            raise GameEngineLabError(
                "input player outside global bounds"
            )
        if not isinstance(self.device, InputDevice):
            try:
                coerced_device = InputDevice(
                    str(self.device)
                )
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise GameEngineLabError(
                    "input device is unknown"
                ) from exc
            object.__setattr__(
                self,
                "device",
                coerced_device,
            )
        if not isinstance(self.buttons, InputButton):
            try:
                coerced_buttons = InputButton(
                    int(self.buttons)
                )
            except (
                TypeError,
                ValueError,
                OverflowError,
            ) as exc:
                raise GameEngineLabError(
                    "input button encoding is invalid"
                ) from exc
            object.__setattr__(
                self,
                "buttons",
                coerced_buttons,
            )
        for name in (
            "move_x",
            "move_y",
            "aim_x",
            "aim_y",
            "pointer_x",
            "pointer_y",
            "motion_x",
            "motion_y",
            "motion_z",
        ):
            _unit_signed(
                getattr(self, name),
                name,
            )
        _unit_unsigned(
            self.left_trigger,
            "left_trigger",
        )
        _unit_unsigned(
            self.right_trigger,
            "right_trigger",
        )
        if type(self.touch_active) is not bool:
            raise GameEngineLabError(
                "touch_active must be boolean"
            )


@dataclass(frozen=True, slots=True)
class NormalizedInput:
    schema_version: int
    era: EngineEra
    tick: int
    player: int
    device: InputDevice
    compatibility: InputFrame
    move: tuple[float, float]
    aim: tuple[float, float]
    triggers: tuple[float, float]
    pointer: tuple[float, float]
    motion: tuple[
        float,
        float,
        float,
    ]
    touch_active: bool
    digest: str


def _deadzone(
    value: float,
    deadzone: float,
) -> float:
    magnitude = abs(value)
    if magnitude <= deadzone:
        return 0.0
    scaled = (
        magnitude - deadzone
    ) / (
        1.0 - deadzone
    )
    return math.copysign(
        min(1.0, scaled),
        value,
    )


def _quantize_signed(
    value: float,
    bits: int,
) -> float:
    if bits <= 0:
        return 0.0
    levels = (
        (1 << (bits - 1))
        - 1
    )
    if levels <= 0:
        return 0.0
    return round(
        max(-1.0, min(1.0, value))
        * levels
    ) / levels


def _quantize_unsigned(
    value: float,
    bits: int,
) -> float:
    if bits <= 0:
        return 0.0
    levels = (1 << bits) - 1
    return round(
        max(0.0, min(1.0, value))
        * levels
    ) / levels


def _direction_buttons(
    move_x: float,
    move_y: float,
) -> InputButton:
    buttons = InputButton.NONE
    if move_x < -0.25:
        buttons |= InputButton.LEFT
    elif move_x > 0.25:
        buttons |= InputButton.RIGHT
    if move_y < -0.25:
        buttons |= InputButton.UP
    elif move_y > 0.25:
        buttons |= InputButton.DOWN
    return buttons


class InputNormalizer:
    """Pure deterministic device-to-era lowering."""

    def __init__(
        self,
        era: EngineEra | str,
    ) -> None:
        self.policy = input_policy(era)

    @property
    def era(self) -> EngineEra:
        return self.policy.era

    def normalize(
        self,
        sample: RawInputSample,
    ) -> NormalizedInput:
        if (
            sample.player
            >= self.policy.max_players
        ):
            raise GameEngineLabError(
                "input player exceeds era player budget"
            )
        if sample.device not in self.policy.devices:
            raise GameEngineLabError(
                (
                    f"{sample.device.value} unavailable "
                    f"for {self.era.value}"
                )
            )
        unsupported_bits = (
            int(sample.buttons)
            & ~int(
                self.policy.button_mask
            )
        )
        if unsupported_bits:
            raise GameEngineLabError(
                "input sample contains buttons unavailable in era"
            )
        if (
            self.era
            is EngineEra.PONG
        ):
            player_mask = (
                (
                    InputButton.UP
                    | InputButton.DOWN
                    | InputButton.START
                )
                if sample.player == 0
                else (
                    InputButton.A
                    | InputButton.B
                    | InputButton.START
                )
            )
            if (
                int(sample.buttons)
                & ~int(
                    player_mask
                )
            ):
                raise GameEngineLabError(
                    "Pong paddle sample contains controls for the other player"
                )
            if sample.move_x != 0.0:
                raise GameEngineLabError(
                    "Pong paddle exposes only the vertical movement axis"
                )
        if (
            not self.policy.pointer
            and (
                sample.pointer_x != 0.0
                or sample.pointer_y != 0.0
            )
        ):
            raise GameEngineLabError(
                "pointer input unavailable in era"
            )
        if (
            not self.policy.motion
            and (
                sample.motion_x != 0.0
                or sample.motion_y != 0.0
                or sample.motion_z != 0.0
            )
        ):
            raise GameEngineLabError(
                "motion input unavailable in era"
            )
        if (
            not self.policy.touch
            and sample.touch_active
        ):
            raise GameEngineLabError(
                "touch input unavailable in era"
            )
        if (
            self.policy.trigger_bits == 0
            and (
                sample.left_trigger != 0.0
                or sample.right_trigger != 0.0
            )
        ):
            raise GameEngineLabError(
                "analog triggers unavailable in era"
            )

        move_x = _deadzone(
            sample.move_x,
            self.policy.deadzone,
        )
        move_y = _deadzone(
            sample.move_y,
            self.policy.deadzone,
        )
        aim_x = _deadzone(
            sample.aim_x,
            self.policy.deadzone,
        )
        aim_y = _deadzone(
            sample.aim_y,
            self.policy.deadzone,
        )

        move = (
            (
                _quantize_signed(
                    move_x,
                    self.policy.move_axis_bits,
                ),
                _quantize_signed(
                    move_y,
                    self.policy.move_axis_bits,
                ),
            )
            if self.policy.move_axis_bits > 0
            else (0.0, 0.0)
        )
        if self.policy.aim_axis_bits > 0:
            aim = (
                _quantize_signed(
                    aim_x,
                    self.policy.aim_axis_bits,
                ),
                _quantize_signed(
                    aim_y,
                    self.policy.aim_axis_bits,
                ),
            )
        else:
            if (
                aim_x != 0.0
                or aim_y != 0.0
            ):
                raise GameEngineLabError(
                    "aim axes unavailable in era"
                )
            aim = (0.0, 0.0)

        triggers = (
            _quantize_unsigned(
                sample.left_trigger,
                self.policy.trigger_bits,
            ),
            _quantize_unsigned(
                sample.right_trigger,
                self.policy.trigger_bits,
            ),
        )
        pointer = (
            (
                _quantize_signed(
                    sample.pointer_x,
                    max(
                        8,
                        self.policy.aim_axis_bits,
                    ),
                ),
                _quantize_signed(
                    sample.pointer_y,
                    max(
                        8,
                        self.policy.aim_axis_bits,
                    ),
                ),
            )
            if self.policy.pointer
            else (0.0, 0.0)
        )
        motion = (
            (
                _quantize_signed(
                    sample.motion_x,
                    max(
                        10,
                        self.policy.aim_axis_bits,
                    ),
                ),
                _quantize_signed(
                    sample.motion_y,
                    max(
                        10,
                        self.policy.aim_axis_bits,
                    ),
                ),
                _quantize_signed(
                    sample.motion_z,
                    max(
                        10,
                        self.policy.aim_axis_bits,
                    ),
                ),
            )
            if self.policy.motion
            else (0.0, 0.0, 0.0)
        )

        compatibility_buttons = sample.buttons
        compatibility_buttons |= (
            _direction_buttons(
                move_x,
                move_y,
            )
            & self.policy.button_mask
        )

        if self.era is EngineEra.PONG:
            player_mask = (
                (
                    InputButton.UP
                    | InputButton.DOWN
                    | InputButton.START
                )
                if sample.player == 0
                else (
                    InputButton.A
                    | InputButton.B
                    | InputButton.START
                )
            )
            compatibility_buttons &= (
                player_mask
            )
            vertical = move_y
            if vertical < -0.25:
                compatibility_buttons |= (
                    InputButton.UP
                    if sample.player == 0
                    else InputButton.A
                )
            elif vertical > 0.25:
                compatibility_buttons |= (
                    InputButton.DOWN
                    if sample.player == 0
                    else InputButton.B
                )

        compatibility = InputFrame(
            sample.tick,
            compatibility_buttons,
        )
        payload = {
            "schema_version":
                INPUT_SCHEMA_VERSION,
            "engine_era":
                self.era.value,
            "tick":
                sample.tick,
            "player":
                sample.player,
            "device":
                sample.device.value,
            "buttons":
                int(
                    compatibility.buttons
                ),
            "move":
                move,
            "aim":
                aim,
            "triggers":
                triggers,
            "pointer":
                pointer,
            "motion":
                motion,
            "touch_active":
                (
                    sample.touch_active
                    if self.policy.touch
                    else False
                ),
        }
        return NormalizedInput(
            INPUT_SCHEMA_VERSION,
            self.era,
            sample.tick,
            sample.player,
            sample.device,
            compatibility,
            move,
            aim,
            triggers,
            pointer,
            motion,
            (
                sample.touch_active
                if self.policy.touch
                else False
            ),
            _digest(payload),
        )

    def normalize_many(
        self,
        samples: Iterable[
            RawInputSample
        ],
    ) -> tuple[
        NormalizedInput,
        ...,
    ]:
        values = tuple(
            self.normalize(sample)
            for sample in samples
        )
        identities = {
            (
                item.tick,
                item.player,
            )
            for item in values
        }
        if len(identities) != len(values):
            raise GameEngineLabError(
                "duplicate input sample for tick/player"
            )
        return tuple(
            sorted(
                values,
                key=lambda item: (
                    item.tick,
                    item.player,
                ),
            )
        )


@dataclass(frozen=True, slots=True)
class HapticRequest:
    tick: int
    player: int
    amplitude: float
    frequency_hz: float
    duration_ticks: int
    channel: int = 0

    def __post_init__(self) -> None:
        if (
            type(self.tick) is not int
            or self.tick < 0
            or type(self.player) is not int
            or not 0
            <= self.player
            < MAX_INPUT_PLAYERS
            or type(self.duration_ticks)
            is not int
            or not 1
            <= self.duration_ticks
            <= MAX_HAPTIC_TICKS
            or type(self.channel) is not int
            or not 0 <= self.channel <= 3
        ):
            raise GameEngineLabError(
                "haptic request integer field outside bounds"
            )
        _unit_unsigned(
            self.amplitude,
            "haptic amplitude",
        )
        frequency = _finite(
            self.frequency_hz,
            "haptic frequency",
        )
        if frequency <= 0:
            raise GameEngineLabError(
                "haptic frequency must be positive"
            )


@dataclass(frozen=True, slots=True)
class HapticCommand:
    era: EngineEra
    mode: HapticMode
    tick: int
    player: int
    amplitude: float
    frequency_hz: int
    duration_ticks: int
    channel: int
    digest: str


def normalize_haptic(
    era: EngineEra | str,
    request: HapticRequest,
) -> HapticCommand:
    policy = input_policy(era)
    if (
        policy.haptic_mode
        is HapticMode.NONE
    ):
        raise GameEngineLabError(
            "haptic output unavailable in era"
        )
    if (
        request.player
        >= policy.max_players
    ):
        raise GameEngineLabError(
            "haptic player exceeds era player budget"
        )
    levels = (
        (1 << (
            policy.haptic_amplitude_bits
        ))
        - 1
    )
    amplitude = round(
        request.amplitude
        * levels
    ) / levels
    frequency = int(
        round(
            min(
                float(
                    policy.haptic_frequency_max
                ),
                max(
                    float(
                        policy.haptic_frequency_min
                    ),
                    request.frequency_hz,
                ),
            )
        )
    )
    if (
        policy.haptic_mode
        is HapticMode.RUMBLE
        and request.channel != 0
    ):
        raise GameEngineLabError(
            "single-motor rumble era exposes only channel 0"
        )
    if (
        policy.haptic_mode
        is HapticMode.DUAL_MOTOR
        and request.channel > 1
    ):
        raise GameEngineLabError(
            "dual-motor era exposes channels 0 and 1"
        )
    payload = {
        "engine_era":
            policy.era.value,
        "mode":
            policy.haptic_mode.value,
        "tick":
            request.tick,
        "player":
            request.player,
        "amplitude":
            amplitude,
        "frequency_hz":
            frequency,
        "duration_ticks":
            request.duration_ticks,
        "channel":
            request.channel,
    }
    return HapticCommand(
        policy.era,
        policy.haptic_mode,
        request.tick,
        request.player,
        amplitude,
        frequency,
        request.duration_ticks,
        request.channel,
        _digest(payload),
    )


def build_input_normalizer(
    era: EngineEra | str,
) -> InputNormalizer:
    return InputNormalizer(era)
