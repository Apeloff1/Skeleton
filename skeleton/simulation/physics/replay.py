"""Tamper-evident deterministic replay for autonomous physics steps.

The initial replay contract records deterministic fixed steps from an initial
snapshot. External gameplay inputs/commands are intentionally not fabricated:
input-bearing replay will layer an explicit command tape on this foundation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from ..ecs.canonical import chained_digest, digest
from .errors import PhysicsReplayDivergenceError, PhysicsReplayError
from .snapshots import PhysicsSnapshot
from .world import PhysicsStepReceipt, PhysicsWorld

_ZERO_CHAIN = "0" * 64


@dataclass(frozen=True, slots=True)
class PhysicsReplayFrame:
    index: int
    tick: int
    before_digest: str
    after_digest: str
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class PhysicsReplayTape:
    initial: PhysicsSnapshot
    frames: tuple[PhysicsReplayFrame, ...]
    chain_digest: str


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
    def __init__(self, world: PhysicsWorld) -> None:
        if not isinstance(world, PhysicsWorld):
            raise PhysicsReplayError("recorder requires PhysicsWorld")
        self.world = world
        self.initial = world.capture_snapshot()
        self._frames: list[PhysicsReplayFrame] = []
        self._chain = _ZERO_CHAIN

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

    chain = _ZERO_CHAIN
    for expected in tape.frames:
        if expected.index < 0:
            raise PhysicsReplayError("replay frame index must be non-negative")
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
