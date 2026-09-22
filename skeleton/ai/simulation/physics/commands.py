"""Deterministic gameplay input commands for physics replay and rollback."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..ecs.canonical import digest
from .body import BodyType
from .errors import PhysicsReplayError, PhysicsValidationError
from .math3d import Vec3
from .world import PhysicsWorld

MAX_COMMANDS_PER_TICK = 100_000
MAX_COMMAND_FRAMES = 1_000_000


class PhysicsCommandKind(str, Enum):
    APPLY_FORCE = "apply_force"
    APPLY_TORQUE = "apply_torque"
    APPLY_IMPULSE = "apply_impulse"
    SET_LINEAR_VELOCITY = "set_linear_velocity"
    SET_ANGULAR_VELOCITY = "set_angular_velocity"


@dataclass(frozen=True, slots=True)
class PhysicsCommand:
    sequence: int
    body_id: str
    kind: PhysicsCommandKind
    vector: Vec3
    point: Vec3 | None = None

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise PhysicsValidationError("command sequence must be non-negative integer")
        if not isinstance(self.body_id, str) or not self.body_id:
            raise PhysicsValidationError("command body_id must be non-empty")
        if not isinstance(self.kind, PhysicsCommandKind):
            raise PhysicsValidationError("command kind must be PhysicsCommandKind")
        if not isinstance(self.vector, Vec3):
            raise PhysicsValidationError("command vector must be Vec3")
        if self.point is not None and not isinstance(self.point, Vec3):
            raise PhysicsValidationError("command point must be Vec3 or None")
        if self.kind not in (
            PhysicsCommandKind.APPLY_FORCE,
            PhysicsCommandKind.APPLY_IMPULSE,
        ) and self.point is not None:
            raise PhysicsValidationError(
                f"{self.kind.value} does not accept a world-space point"
            )

    @property
    def fingerprint(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.physics.command.v1",
                "sequence": self.sequence,
                "body_id": self.body_id,
                "kind": self.kind.value,
                "vector": self.vector.to_tuple(),
                "point": None if self.point is None else self.point.to_tuple(),
            }
        )


@dataclass(frozen=True, slots=True)
class PhysicsCommandFrame:
    tick: int
    commands: tuple[PhysicsCommand, ...]
    frame_digest: str

    def __post_init__(self) -> None:
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick <= 0:
            raise PhysicsReplayError("command frame tick must be positive integer")
        try:
            commands = tuple(self.commands)
        except TypeError as exc:
            raise PhysicsReplayError("command frame commands must be iterable") from exc
        if len(commands) > MAX_COMMANDS_PER_TICK:
            raise PhysicsReplayError("command frame exceeds per-tick command bound")
        if not all(isinstance(command, PhysicsCommand) for command in commands):
            raise PhysicsReplayError("command frame contains invalid command")
        sequences = tuple(command.sequence for command in commands)
        if sequences != tuple(range(len(commands))):
            raise PhysicsReplayError("command sequences must be contiguous from zero")
        object.__setattr__(self, "commands", commands)
        expected = digest(
            {
                "domain": "skeleton.simulation.physics.command_frame.v1",
                "tick": self.tick,
                "commands": [command.fingerprint for command in commands],
            }
        )
        if self.frame_digest != expected:
            raise PhysicsReplayError("command frame digest mismatch")

    @classmethod
    def build(
        cls,
        tick: int,
        commands: tuple[PhysicsCommand, ...] | list[PhysicsCommand],
    ) -> "PhysicsCommandFrame":
        commands = tuple(commands)
        frame_digest = digest(
            {
                "domain": "skeleton.simulation.physics.command_frame.v1",
                "tick": tick,
                "commands": [command.fingerprint for command in commands],
            }
        )
        return cls(tick=tick, commands=commands, frame_digest=frame_digest)


class PhysicsCommandTape:
    """Bounded ordered command frames keyed by the tick they precede."""

    def __init__(self, *, max_frames: int = 65_536) -> None:
        if (
            isinstance(max_frames, bool)
            or not isinstance(max_frames, int)
            or not 1 <= max_frames <= MAX_COMMAND_FRAMES
        ):
            raise PhysicsReplayError("command tape max_frames outside supported range")
        self.max_frames = max_frames
        self._frames: dict[int, PhysicsCommandFrame] = {}

    def append(self, frame: PhysicsCommandFrame) -> PhysicsCommandFrame:
        if not isinstance(frame, PhysicsCommandFrame):
            raise PhysicsReplayError("command tape requires PhysicsCommandFrame")
        existing = self._frames.get(frame.tick)
        if existing is not None and existing != frame:
            raise PhysicsReplayError("command tape tick already contains different frame")
        if existing is None and len(self._frames) >= self.max_frames:
            raise PhysicsReplayError("command tape frame bound exceeded")
        self._frames[frame.tick] = frame
        return frame

    def remove(self, tick: int) -> PhysicsCommandFrame:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick <= 0:
            raise PhysicsReplayError("command tape tick must be positive integer")
        try:
            return self._frames.pop(tick)
        except KeyError as exc:
            raise PhysicsReplayError("cannot remove missing command frame") from exc

    def replace(self, frame: PhysicsCommandFrame) -> PhysicsCommandFrame:
        if not isinstance(frame, PhysicsCommandFrame):
            raise PhysicsReplayError("command tape requires PhysicsCommandFrame")
        if frame.tick not in self._frames:
            raise PhysicsReplayError("cannot replace missing command frame")
        self._frames[frame.tick] = frame
        return frame

    def frame(self, tick: int) -> PhysicsCommandFrame:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick <= 0:
            raise PhysicsReplayError("command tape tick must be positive integer")
        return self._frames.get(tick, PhysicsCommandFrame.build(tick, ()))

    def ticks(self) -> tuple[int, ...]:
        return tuple(sorted(self._frames))

    def truncate_after(self, tick: int) -> int:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise PhysicsReplayError("command tape tick must be non-negative integer")
        future = [value for value in self._frames if value > tick]
        for value in sorted(future):
            del self._frames[value]
        return len(future)

    @property
    def tape_digest(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.physics.command_tape.v1",
                "frames": [
                    {
                        "tick": tick,
                        "frame_digest": self._frames[tick].frame_digest,
                    }
                    for tick in self.ticks()
                ],
            }
        )


def _apply_physics_commands_unchecked(
    world: PhysicsWorld,
    frame: PhysicsCommandFrame,
) -> None:
    if not isinstance(world, PhysicsWorld):
        raise PhysicsValidationError("command application requires PhysicsWorld")
    if not isinstance(frame, PhysicsCommandFrame):
        raise PhysicsValidationError("command application requires PhysicsCommandFrame")
    if frame.tick != world.tick + 1:
        raise PhysicsValidationError(
            "command frame tick must target the world's next simulation tick"
        )

    for command in frame.commands:
        body = world.get_body(command.body_id)
        if command.kind is PhysicsCommandKind.APPLY_FORCE:
            if body.body_type is not BodyType.DYNAMIC:
                raise PhysicsValidationError("force command requires dynamic body")
            body.apply_force(command.vector, point=command.point)
        elif command.kind is PhysicsCommandKind.APPLY_TORQUE:
            if body.body_type is not BodyType.DYNAMIC:
                raise PhysicsValidationError("torque command requires dynamic body")
            body.apply_torque(command.vector)
        elif command.kind is PhysicsCommandKind.APPLY_IMPULSE:
            if body.body_type is not BodyType.DYNAMIC:
                raise PhysicsValidationError("impulse command requires dynamic body")
            body.apply_impulse(command.vector, point=command.point)
        elif command.kind is PhysicsCommandKind.SET_LINEAR_VELOCITY:
            if body.body_type is BodyType.STATIC:
                raise PhysicsValidationError("velocity command cannot target static body")
            body.linear_velocity = command.vector
            body.wake()
        elif command.kind is PhysicsCommandKind.SET_ANGULAR_VELOCITY:
            if body.body_type is BodyType.STATIC:
                raise PhysicsValidationError("velocity command cannot target static body")
            body.angular_velocity = command.vector
            body.wake()
        else:
            raise PhysicsValidationError(f"unsupported command kind: {command.kind}")



def apply_physics_commands(
    world: PhysicsWorld,
    frame: PhysicsCommandFrame,
) -> None:
    """Apply one command frame atomically without advancing simulation."""

    if not isinstance(world, PhysicsWorld):
        raise PhysicsValidationError("command application requires PhysicsWorld")
    if not isinstance(frame, PhysicsCommandFrame):
        raise PhysicsValidationError("command application requires PhysicsCommandFrame")
    before = world.capture_snapshot()
    try:
        _apply_physics_commands_unchecked(world, frame)
    except Exception:
        world.restore_snapshot(before)
        raise


def step_physics_with_commands(
    world: PhysicsWorld,
    frame: PhysicsCommandFrame,
):
    """Atomically apply commands and execute exactly one fixed physics tick."""

    if not isinstance(world, PhysicsWorld):
        raise PhysicsValidationError("command step requires PhysicsWorld")
    if not isinstance(frame, PhysicsCommandFrame):
        raise PhysicsValidationError("command step requires PhysicsCommandFrame")
    before = world.capture_snapshot()
    try:
        _apply_physics_commands_unchecked(world, frame)
        return world.step()[0]
    except Exception:
        world.restore_snapshot(before)
        raise
