"""Independent original-game controller remapping, axis calibration and input replay.

A deterministic input translator for controller/device observations, not a claim
of USB access. A source-bound profile is immutable; remaps produce new versions.
Digital events and analog thresholds share an ordered, bounded audit trail.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from .game_frontier_expedition import ExpeditionError, _digest
from .game_frontier_expedition_controllers import (
    ControllerEvent, ControllerProfile, ControllerTransition, ButtonBinding,
    replay_controller,
)

_ACTIONS = frozenset((
    "navigate_up", "navigate_down", "travel", "rest", "inspect",
    "pause", "inventory",
))


@dataclass(frozen=True, slots=True)
class AxisCalibration:
    axis: int
    deadzone: float = 0.25
    engage: float = 0.65
    release: float = 0.35
    invert: bool = False

    def __post_init__(self):
        if type(self.axis) is not int or not 0 <= self.axis < 16:
            raise ExpeditionError("axis must be a physical controller index")
        for name in ("deadzone", "engage", "release"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not 0 <= value <= 1:
                raise ExpeditionError("calibration must be a finite unit fraction")
        if not 0 <= self.deadzone < self.release < self.engage <= 1:
            raise ExpeditionError("axis hysteresis thresholds are inconsistent")
        if type(self.invert) is not bool:
            raise ExpeditionError("axis inversion must be explicit")


@dataclass(frozen=True, slots=True)
class AxisBinding:
    calibration: AxisCalibration
    direction: int
    action: str

    def __post_init__(self):
        if not isinstance(self.calibration, AxisCalibration):
            raise ExpeditionError("axis binding requires verified calibration")
        if type(self.direction) is not int or self.direction not in (-1, 1):
            raise ExpeditionError("axis direction must be negative or positive")
        if self.action not in _ACTIONS:
            raise ExpeditionError("axis action is not supported")


@dataclass(frozen=True, slots=True)
class AnalogSample:
    frame: int
    axis: int
    value: float
    device: int = 0

    def __post_init__(self):
        if type(self.frame) is not int or not 0 <= self.frame <= 10_000_000_000:
            raise ExpeditionError("analog sample frame invalid")
        if type(self.axis) is not int or not 0 <= self.axis < 16:
            raise ExpeditionError("analog device axis invalid")
        if type(self.value) not in (int, float) or not -1 <= self.value <= 1:
            raise ExpeditionError("analog value must be finite -1..1")
        if type(self.device) is not int or not 0 <= self.device < 8:
            raise ExpeditionError("analog device scope invalid")


@dataclass(frozen=True, slots=True)
class GameInput:
    sequence: int
    frame: int
    action: str
    device: int
    source: str
    receipt: str
    prior_receipt: str


def remap_controller(profile: ControllerProfile, *, action: str,
                     button_index: int) -> ControllerProfile:
    """Atomically remap a real original game action to a free device button."""
    if not isinstance(profile, ControllerProfile) or action not in _ACTIONS:
        raise ExpeditionError("known source profile/action required")
    if type(button_index) is not int or not 0 <= button_index <= 31:
        raise ExpeditionError("game button index must be supported")
    old = next((b for b in profile.buttons if b.action == action), None)
    if old is None:
        raise ExpeditionError("controller action not defined by source profile")
    if any(b.godot_button == button_index and b.action != action
           for b in profile.buttons):
        raise ExpeditionError("button remap collides with another game action")
    return replace(profile, buttons=tuple(
        replace(b, godot_button=button_index) if b.action == action else b
        for b in profile.buttons
    ))


def translate_analog(samples: Iterable[AnalogSample],
                     bindings: tuple[AxisBinding, ...], *,
                     device: int = 0, max_samples: int = 100_000) -> tuple[tuple[int, str], ...]:
    """Hysteretic analog-to-discrete translation suppresses stick jitter."""
    if (type(bindings) is not tuple or not 1 <= len(bindings) <= 16
            or any(not isinstance(x, AxisBinding) for x in bindings)):
        raise ExpeditionError("analog source bindings must be typed and bounded")
    if len({(b.calibration.axis, b.direction) for b in bindings}) != len(bindings):
        raise ExpeditionError("duplicate axis direction binding")
    if type(device) is not int or not 0 <= device < 8:
        raise ExpeditionError("foreign device scope")
    if type(max_samples) is not int or not 1 <= max_samples <= 100_000:
        raise ExpeditionError("analog replay budget invalid")
    engaged: set[tuple[int, int]] = set()
    result: list[tuple[int, str]] = []
    prev = -1
    for count, sample in enumerate(samples):
        if count >= max_samples:
            raise ExpeditionError("analog sample stream exceeds replay budget")
        if not isinstance(sample, AnalogSample) or sample.device != device:
            raise ExpeditionError("analog observation from foreign device")
        if sample.frame < prev:
            raise ExpeditionError("analog samples out of frame order")
        prev = sample.frame
        for binding in bindings:
            if binding.calibration.axis != sample.axis:
                continue
            calibration = binding.calibration
            raw = -sample.value if calibration.invert else sample.value
            v = binding.direction * raw
            identity = (sample.axis, binding.direction)
            if identity in engaged:
                if v < calibration.release:
                    engaged.remove(identity)
            elif v >= calibration.engage:
                engaged.add(identity)
                result.append((sample.frame, binding.action))
    return tuple(result)


def merge_input_replays(
    profile: ControllerProfile, digital: tuple[ControllerEvent, ...],
    analog: tuple[AnalogSample, ...], bindings: tuple[AxisBinding, ...], *,
    world_digest: str, device: int = 0,
) -> tuple[GameInput, ...]:
    """Combine two verified input sources without inventing timestamps."""
    if not isinstance(profile, ControllerProfile):
        raise ExpeditionError("typed source controller required")
    if type(world_digest) is not str or len(world_digest) != 64:
        raise ExpeditionError("input observations need source world hash")
    digits = replay_controller(profile, digital, world_digest=world_digest,
                               device=device)
    analog_actions = translate_analog(analog, bindings, device=device)
    events = [(x.frame, 0, x.sequence, x.action) for x in digits]
    events.extend((frame, 1, index, action)
                  for index, (frame, action) in enumerate(analog_actions))
    events.sort()
    receipt = _digest({"profile": profile.digest, "world": world_digest,
                       "device": device, "plane": "merged_game_input_v1"})
    result: list[GameInput] = []
    for frame, plane, index, action in events:
        prior = receipt
        source = "digital" if plane == 0 else "analog"
        receipt = _digest({
            "previous": prior, "sequence": len(result) + 1,
            "frame": frame, "action": action, "device": device,
            "source": source, "profile": profile.digest,
            "world": world_digest,
        })
        result.append(GameInput(len(result) + 1, frame, action, device,
                                source, receipt, prior))
    return tuple(result)


def verify_input_replay(profile: ControllerProfile,
                        digital: tuple[ControllerEvent, ...],
                        analog: tuple[AnalogSample, ...],
                        bindings: tuple[AxisBinding, ...],
                        evidence: tuple[GameInput, ...], *,
                        world_digest: str, device: int = 0) -> None:
    expected = merge_input_replays(profile, digital, analog, bindings,
                                   world_digest=world_digest, device=device)
    if evidence != expected:
        raise ExpeditionError("game input replay differs from real controller data")
