"""Tamper-evident deterministic replay for physics simulation."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from ..ecs.canonical import chained_digest, digest
from .commands import PhysicsCommand, PhysicsCommandFrame, step_physics_with_commands
from .errors import PhysicsReplayDivergenceError, PhysicsReplayError
from .snapshots import PhysicsSnapshot
from .world import PhysicsStepReceipt, PhysicsWorld

_ZERO_CHAIN = "0" * 64


def _sha256_text(value: str, *, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise PhysicsReplayError(f"{name} must be sha256 text")
    try:
        int(value, 16)
    except ValueError as exc:
        raise PhysicsReplayError(f"{name} must be sha256 text") from exc
    return value


def _initial_chain(snapshot: PhysicsSnapshot) -> str:
    return chained_digest(
        _ZERO_CHAIN,
        {"initial_snapshot_digest": snapshot.snapshot_digest},
    )


@dataclass(frozen=True, slots=True)
class PhysicsReplayFrame:
    """One autonomous fixed-step transition."""

    index: int
    tick: int
    before_digest: str
    after_digest: str
    receipt_digest: str

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int) or self.index < 0:
            raise PhysicsReplayError("replay frame index must be non-negative integer")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise PhysicsReplayError("replay frame tick must be non-negative integer")
        _sha256_text(self.before_digest, name="before_digest")
        _sha256_text(self.after_digest, name="after_digest")
        _sha256_text(self.receipt_digest, name="receipt_digest")


@dataclass(frozen=True, slots=True)
class PhysicsReplayTape:
    initial: PhysicsSnapshot
    frames: tuple[PhysicsReplayFrame, ...]
    chain_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.initial, PhysicsSnapshot):
            raise PhysicsReplayError("replay tape initial must be PhysicsSnapshot")
        try:
            frames = tuple(self.frames)
        except TypeError as exc:
            raise PhysicsReplayError("replay tape frames must be iterable") from exc
        object.__setattr__(self, "frames", frames)
        _sha256_text(self.chain_digest, name="chain_digest")

        previous_digest = self.initial.state_digest
        for index, frame in enumerate(frames):
            if not isinstance(frame, PhysicsReplayFrame):
                raise PhysicsReplayError("replay tape contains invalid frame")
            if frame.index != index:
                raise PhysicsReplayError("replay frame indices must be contiguous")
            if frame.tick != self.initial.tick + index + 1:
                raise PhysicsReplayError("replay frame ticks must be contiguous")
            if frame.before_digest != previous_digest:
                raise PhysicsReplayError("replay frame state chain must be contiguous")
            previous_digest = frame.after_digest


@dataclass(frozen=True, slots=True)
class PhysicsReplayVerification:
    frames: int
    final_digest: str
    chain_digest: str
    ok: bool


def _frame_from_receipt(index: int, receipt: PhysicsStepReceipt) -> PhysicsReplayFrame:
    return PhysicsReplayFrame(
        index=index,
        tick=receipt.tick,
        before_digest=receipt.before_digest,
        after_digest=receipt.after_digest,
        receipt_digest=digest(asdict(receipt)),
    )


class PhysicsReplayRecorder:
    """Record autonomous deterministic fixed steps."""

    def __init__(self, world: PhysicsWorld) -> None:
        if not isinstance(world, PhysicsWorld):
            raise PhysicsReplayError("recorder requires PhysicsWorld")
        self.world = world
        self.initial = world.capture_snapshot()
        self._frames: list[PhysicsReplayFrame] = []
        self._chain = _initial_chain(self.initial)

    def step(self) -> PhysicsStepReceipt:
        receipt = self.world.step()[0]
        frame = _frame_from_receipt(len(self._frames), receipt)
        self._chain = chained_digest(self._chain, asdict(frame))
        self._frames.append(frame)
        return receipt

    def tape(self) -> PhysicsReplayTape:
        return PhysicsReplayTape(
            initial=self.initial,
            frames=tuple(self._frames),
            chain_digest=self._chain,
        )


def replay_physics(
    world_factory: Callable[[], PhysicsWorld],
    tape: PhysicsReplayTape,
) -> PhysicsReplayVerification:
    if not callable(world_factory):
        raise PhysicsReplayError("world_factory must be callable")
    if not isinstance(tape, PhysicsReplayTape):
        raise PhysicsReplayError("tape must be PhysicsReplayTape")

    world = world_factory()
    if not isinstance(world, PhysicsWorld):
        raise PhysicsReplayError("world_factory must return PhysicsWorld")
    world.restore_snapshot(tape.initial)

    chain = _initial_chain(tape.initial)
    for expected in tape.frames:
        receipt = world.step()[0]
        actual = _frame_from_receipt(expected.index, receipt)
        if actual != expected:
            raise PhysicsReplayDivergenceError(
                f"physics replay diverged at frame {expected.index}"
            )
        chain = chained_digest(chain, asdict(actual))

    if chain != tape.chain_digest:
        raise PhysicsReplayDivergenceError("physics replay chain digest mismatch")

    return PhysicsReplayVerification(
        frames=len(tape.frames),
        final_digest=world.state_digest,
        chain_digest=chain,
        ok=True,
    )


@dataclass(frozen=True, slots=True)
class PhysicsCommandReplayFrame:
    """One complete gameplay-input → physics-step transition."""

    index: int
    tick: int
    commands: PhysicsCommandFrame
    before_digest: str
    simulation_before_digest: str
    after_digest: str
    receipt_digest: str

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int) or self.index < 0:
            raise PhysicsReplayError("command replay index must be non-negative integer")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick <= 0:
            raise PhysicsReplayError("command replay tick must be positive integer")
        if not isinstance(self.commands, PhysicsCommandFrame):
            raise PhysicsReplayError("command replay frame requires PhysicsCommandFrame")
        if self.commands.tick != self.tick:
            raise PhysicsReplayError("command replay frame/tick mismatch")
        _sha256_text(self.before_digest, name="before_digest")
        _sha256_text(
            self.simulation_before_digest,
            name="simulation_before_digest",
        )
        _sha256_text(self.after_digest, name="after_digest")
        _sha256_text(self.receipt_digest, name="receipt_digest")


@dataclass(frozen=True, slots=True)
class PhysicsCommandReplayTape:
    initial: PhysicsSnapshot
    frames: tuple[PhysicsCommandReplayFrame, ...]
    chain_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.initial, PhysicsSnapshot):
            raise PhysicsReplayError("command replay initial must be PhysicsSnapshot")
        try:
            frames = tuple(self.frames)
        except TypeError as exc:
            raise PhysicsReplayError("command replay frames must be iterable") from exc
        object.__setattr__(self, "frames", frames)
        _sha256_text(self.chain_digest, name="chain_digest")

        previous_digest = self.initial.state_digest
        for index, frame in enumerate(frames):
            if not isinstance(frame, PhysicsCommandReplayFrame):
                raise PhysicsReplayError("command replay contains invalid frame")
            if frame.index != index:
                raise PhysicsReplayError("command replay indices must be contiguous")
            if frame.tick != self.initial.tick + index + 1:
                raise PhysicsReplayError("command replay ticks must be contiguous")
            if frame.before_digest != previous_digest:
                raise PhysicsReplayError("command replay state chain must be contiguous")
            previous_digest = frame.after_digest


def _command_chain_material(frame: PhysicsCommandReplayFrame) -> dict[str, object]:
    return {
        "index": frame.index,
        "tick": frame.tick,
        "command_frame_digest": frame.commands.frame_digest,
        "before_digest": frame.before_digest,
        "simulation_before_digest": frame.simulation_before_digest,
        "after_digest": frame.after_digest,
        "receipt_digest": frame.receipt_digest,
    }


def _command_frame_from_receipt(
    index: int,
    commands: PhysicsCommandFrame,
    receipt: PhysicsStepReceipt,
    *,
    before_digest: str,
) -> PhysicsCommandReplayFrame:
    return PhysicsCommandReplayFrame(
        index=index,
        tick=receipt.tick,
        commands=commands,
        before_digest=before_digest,
        simulation_before_digest=receipt.before_digest,
        after_digest=receipt.after_digest,
        receipt_digest=digest(asdict(receipt)),
    )


class PhysicsCommandReplayRecorder:
    """Record deterministic gameplay commands and resulting physics evidence."""

    def __init__(self, world: PhysicsWorld) -> None:
        if not isinstance(world, PhysicsWorld):
            raise PhysicsReplayError("command replay recorder requires PhysicsWorld")
        self.world = world
        self.initial = world.capture_snapshot()
        self._frames: list[PhysicsCommandReplayFrame] = []
        self._chain = _initial_chain(self.initial)

    def step(
        self,
        commands: tuple[PhysicsCommand, ...] | list[PhysicsCommand] = (),
    ) -> PhysicsStepReceipt:
        frame = PhysicsCommandFrame.build(self.world.tick + 1, tuple(commands))
        before_digest = self.world.state_digest
        receipt = step_physics_with_commands(self.world, frame)
        replay_frame = _command_frame_from_receipt(
            len(self._frames),
            frame,
            receipt,
            before_digest=before_digest,
        )
        self._chain = chained_digest(
            self._chain,
            _command_chain_material(replay_frame),
        )
        self._frames.append(replay_frame)
        return receipt

    def tape(self) -> PhysicsCommandReplayTape:
        return PhysicsCommandReplayTape(
            initial=self.initial,
            frames=tuple(self._frames),
            chain_digest=self._chain,
        )


def replay_physics_commands(
    world_factory: Callable[[], PhysicsWorld],
    tape: PhysicsCommandReplayTape,
) -> PhysicsReplayVerification:
    if not callable(world_factory):
        raise PhysicsReplayError("world_factory must be callable")
    if not isinstance(tape, PhysicsCommandReplayTape):
        raise PhysicsReplayError("tape must be PhysicsCommandReplayTape")

    world = world_factory()
    if not isinstance(world, PhysicsWorld):
        raise PhysicsReplayError("world_factory must return PhysicsWorld")
    world.restore_snapshot(tape.initial)

    chain = _initial_chain(tape.initial)
    for expected in tape.frames:
        before_digest = world.state_digest
        receipt = step_physics_with_commands(world, expected.commands)
        actual = _command_frame_from_receipt(
            expected.index,
            expected.commands,
            receipt,
            before_digest=before_digest,
        )
        if actual != expected:
            raise PhysicsReplayDivergenceError(
                f"physics command replay diverged at frame {expected.index}"
            )
        chain = chained_digest(chain, _command_chain_material(actual))

    if chain != tape.chain_digest:
        raise PhysicsReplayDivergenceError(
            "physics command replay chain digest mismatch"
        )

    return PhysicsReplayVerification(
        frames=len(tape.frames),
        final_digest=world.state_digest,
        chain_digest=chain,
        ok=True,
    )
