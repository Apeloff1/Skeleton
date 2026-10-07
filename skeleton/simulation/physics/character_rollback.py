"""Bounded rollback and input correction for kinematic character state.

The character controller intentionally does not own rigid-body history. During
resimulation the caller supplies bodies for each tick, allowing this timeline to
be paired with PhysicsCommandRollbackSession or another authoritative scene
rollback source.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from ..ecs.canonical import digest
from .body import RigidBody
from .character import (
    CharacterControllerState,
    CharacterRuntimeResult,
    KinematicCapsuleController,
)
from .errors import (
    PhysicsReplayError,
    PhysicsSnapshotError,
    PhysicsValidationError,
)
from .math3d import Vec3

MAX_CHARACTER_HISTORY = 65_536
MAX_CHARACTER_RESIMULATION_SPAN = 10_000


def _positive_dt(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError("character input dt must be numeric")
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise PhysicsValidationError("character input dt must be positive")
    return value


def _ignore_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not all(
        isinstance(value, str) and value
        for value in values
    ):
        raise PhysicsValidationError(
            "character input ignore must be tuple of non-empty strings"
        )
    return tuple(sorted(set(values)))


@dataclass(frozen=True, slots=True)
class CharacterInputFrame:
    tick: int
    requested_velocity: Vec3
    dt: float
    ignore: tuple[str, ...] = ()
    recover_overlaps: bool = True
    carry_support: bool = True

    def __post_init__(self) -> None:
        if (
            isinstance(self.tick, bool)
            or not isinstance(self.tick, int)
            or self.tick <= 0
        ):
            raise PhysicsValidationError(
                "character input tick must be positive integer"
            )
        if not isinstance(self.requested_velocity, Vec3):
            raise PhysicsValidationError(
                "character requested_velocity must be Vec3"
            )
        object.__setattr__(self, "dt", _positive_dt(self.dt))
        object.__setattr__(self, "ignore", _ignore_tuple(self.ignore))
        if not isinstance(self.recover_overlaps, bool) or not isinstance(
            self.carry_support,
            bool,
        ):
            raise PhysicsValidationError(
                "character input flags must be boolean"
            )

    def material(self) -> dict[str, object]:
        return {
            "domain": "skeleton.simulation.physics.character_input.v1",
            "tick": self.tick,
            "requested_velocity": self.requested_velocity.to_tuple(),
            "dt": self.dt,
            "ignore": self.ignore,
            "recover_overlaps": self.recover_overlaps,
            "carry_support": self.carry_support,
        }

    @property
    def frame_digest(self) -> str:
        return digest(self.material())


@dataclass(frozen=True, slots=True)
class CharacterStepReceipt:
    tick: int
    before_digest: str
    after_digest: str
    frame_digest: str
    result: CharacterRuntimeResult


@dataclass(frozen=True, slots=True)
class CharacterRollbackReceipt:
    from_tick: int
    to_tick: int
    discarded_states: int
    restored_state_digest: str
    history_digest: str


@dataclass(frozen=True, slots=True)
class CharacterCorrectionReceipt:
    corrected_tick: int
    rollback_tick: int
    resimulated_through_tick: int
    before_digest: str
    after_digest: str
    command_digest: str
    history_digest: str


BodiesAtTick = Callable[[int], tuple[RigidBody, ...]]


class CharacterRollbackSession:
    """Bounded deterministic rollback over one character controller.

    Controller state is snapshotted after each tick. Input frames are retained
    separately as evidence and replay material. Scene rigid bodies are supplied
    by the caller during resimulation, so this class never hides or duplicates
    authoritative world state.
    """

    def __init__(
        self,
        controller: KinematicCapsuleController,
        *,
        history_capacity: int = 256,
        command_capacity: int = 65_536,
    ) -> None:
        if not isinstance(controller, KinematicCapsuleController):
            raise PhysicsSnapshotError(
                "character rollback requires KinematicCapsuleController"
            )
        for name, value in (
            ("history_capacity", history_capacity),
            ("command_capacity", command_capacity),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 2 <= value <= MAX_CHARACTER_HISTORY
            ):
                raise PhysicsSnapshotError(
                    f"{name} outside supported range"
                )

        self.controller = controller
        self.history_capacity = history_capacity
        self.command_capacity = command_capacity
        self.tick = 0
        self._states: dict[int, CharacterControllerState] = {
            0: controller.capture_state()
        }
        self._commands: dict[int, CharacterInputFrame] = {}

    def _append_state(
        self,
        tick: int,
        state: CharacterControllerState,
    ) -> None:
        existing = self._states.get(tick)
        if existing is not None and existing != state:
            raise PhysicsSnapshotError(
                "different character state already retained for tick"
            )
        self._states[tick] = state
        while len(self._states) > self.history_capacity:
            oldest = min(self._states)
            del self._states[oldest]

    def _append_command(self, frame: CharacterInputFrame) -> bool:
        existing = self._commands.get(frame.tick)
        if existing is not None:
            if existing != frame:
                raise PhysicsReplayError(
                    "different character input already retained for tick"
                )
            return False
        self._commands[frame.tick] = frame
        while len(self._commands) > self.command_capacity:
            oldest = min(self._commands)
            del self._commands[oldest]
        return True

    def _execute_frame(
        self,
        frame: CharacterInputFrame,
        bodies: tuple[RigidBody, ...],
    ) -> CharacterStepReceipt:
        if frame.tick != self.tick + 1:
            raise PhysicsReplayError(
                "character frame tick must immediately follow session tick"
            )
        before = self.controller.capture_state()
        result = self.controller.runtime_step(
            frame.requested_velocity,
            bodies,
            dt=frame.dt,
            ignore=frame.ignore,
            recover_overlaps=frame.recover_overlaps,
            carry_support=frame.carry_support,
        )
        after = self.controller.capture_state()
        self.tick = frame.tick
        self._append_state(self.tick, after)
        return CharacterStepReceipt(
            tick=self.tick,
            before_digest=before.state_digest,
            after_digest=after.state_digest,
            frame_digest=frame.frame_digest,
            result=result,
        )

    def step(
        self,
        requested_velocity: Vec3,
        bodies: tuple[RigidBody, ...],
        *,
        dt: float,
        ignore: tuple[str, ...] = (),
        recover_overlaps: bool = True,
        carry_support: bool = True,
    ) -> CharacterStepReceipt:
        frame = CharacterInputFrame(
            tick=self.tick + 1,
            requested_velocity=requested_velocity,
            dt=dt,
            ignore=ignore,
            recover_overlaps=recover_overlaps,
            carry_support=carry_support,
        )
        existing = self._commands.get(frame.tick)
        if existing is not None and existing != frame:
            raise PhysicsReplayError(
                "next character tick has different retained input; use correction"
            )

        before = self.controller.capture_state()
        previous_tick = self.tick
        states_before = dict(self._states)
        commands_before = dict(self._commands)
        try:
            self._append_command(frame)
            return self._execute_frame(frame, bodies)
        except Exception:
            self.controller.restore_state(before)
            self.tick = previous_tick
            self._states = states_before
            self._commands = commands_before
            raise

    def rollback_to(self, tick: int) -> CharacterRollbackReceipt:
        if (
            isinstance(tick, bool)
            or not isinstance(tick, int)
            or tick < 0
        ):
            raise PhysicsSnapshotError(
                "character rollback tick must be non-negative integer"
            )
        try:
            state = self._states[tick]
        except KeyError as exc:
            raise PhysicsSnapshotError(
                "character rollback state not retained"
            ) from exc

        before = self.tick
        self.controller.restore_state(state)
        discarded = sum(1 for value in self._states if value > tick)
        self._states = {
            value: snapshot
            for value, snapshot in self._states.items()
            if value <= tick
        }
        self.tick = tick
        return CharacterRollbackReceipt(
            from_tick=before,
            to_tick=tick,
            discarded_states=discarded,
            restored_state_digest=self.controller.state_digest,
            history_digest=self.history_digest,
        )

    def resimulate_to(
        self,
        tick: int,
        bodies_at_tick: BodiesAtTick,
    ) -> tuple[CharacterStepReceipt, ...]:
        if (
            isinstance(tick, bool)
            or not isinstance(tick, int)
            or tick < self.tick
        ):
            raise PhysicsReplayError(
                "character resimulation target must be at or after current tick"
            )
        if tick - self.tick > MAX_CHARACTER_RESIMULATION_SPAN:
            raise PhysicsReplayError(
                "character resimulation span exceeds supported range"
            )
        if not callable(bodies_at_tick):
            raise PhysicsValidationError(
                "bodies_at_tick must be callable"
            )

        before_state = self.controller.capture_state()
        before_tick = self.tick
        states_before = dict(self._states)
        try:
            receipts: list[CharacterStepReceipt] = []
            while self.tick < tick:
                next_tick = self.tick + 1
                try:
                    frame = self._commands[next_tick]
                except KeyError as exc:
                    raise PhysicsReplayError(
                        "character input frame not retained for resimulation"
                    ) from exc
                bodies = bodies_at_tick(next_tick)
                receipts.append(self._execute_frame(frame, bodies))
            return tuple(receipts)
        except Exception:
            self.controller.restore_state(before_state)
            self.tick = before_tick
            self._states = states_before
            raise

    def correct_and_resimulate(
        self,
        frame: CharacterInputFrame,
        *,
        bodies_at_tick: BodiesAtTick,
        through_tick: int | None = None,
    ) -> CharacterCorrectionReceipt:
        if not isinstance(frame, CharacterInputFrame):
            raise PhysicsValidationError(
                "correction frame must be CharacterInputFrame"
            )
        if frame.tick not in self._commands:
            raise PhysicsReplayError(
                "cannot correct character input that was not retained"
            )
        if frame.tick - 1 not in self._states:
            raise PhysicsSnapshotError(
                "preceding character rollback state not retained"
            )

        present = self.tick if through_tick is None else through_tick
        if (
            isinstance(present, bool)
            or not isinstance(present, int)
            or present < frame.tick
        ):
            raise PhysicsReplayError(
                "character correction through_tick must be at or after frame tick"
            )
        if present - (frame.tick - 1) > MAX_CHARACTER_RESIMULATION_SPAN:
            raise PhysicsReplayError(
                "character correction span exceeds supported range"
            )

        before_state = self.controller.capture_state()
        before_tick = self.tick
        before_digest = before_state.state_digest
        states_before = dict(self._states)
        commands_before = dict(self._commands)

        self._commands[frame.tick] = frame
        try:
            self.rollback_to(frame.tick - 1)
            self.resimulate_to(present, bodies_at_tick)
        except Exception:
            self._states = states_before
            self._commands = commands_before
            self.tick = before_tick
            self.controller.restore_state(before_state)
            raise

        return CharacterCorrectionReceipt(
            corrected_tick=frame.tick,
            rollback_tick=frame.tick - 1,
            resimulated_through_tick=present,
            before_digest=before_digest,
            after_digest=self.controller.state_digest,
            command_digest=self.command_digest,
            history_digest=self.history_digest,
        )

    def state_at(self, tick: int) -> CharacterControllerState:
        try:
            return self._states[tick]
        except KeyError as exc:
            raise PhysicsSnapshotError(
                "character state not retained"
            ) from exc

    def input_at(self, tick: int) -> CharacterInputFrame:
        try:
            return self._commands[tick]
        except KeyError as exc:
            raise PhysicsReplayError(
                "character input not retained"
            ) from exc

    def state_ticks(self) -> tuple[int, ...]:
        return tuple(sorted(self._states))

    def input_ticks(self) -> tuple[int, ...]:
        return tuple(sorted(self._commands))

    @property
    def command_digest(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.physics.character_commands.v1",
                "frames": [
                    {
                        "tick": tick,
                        "frame_digest": self._commands[tick].frame_digest,
                    }
                    for tick in self.input_ticks()
                ],
            }
        )

    @property
    def history_digest(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.physics.character_rollback_history.v1",
                "current_tick": self.tick,
                "states": [
                    {
                        "tick": tick,
                        "state_digest": self._states[tick].state_digest,
                    }
                    for tick in self.state_ticks()
                ],
                "command_digest": self.command_digest,
            }
        )
