"""Bounded rollback session over deterministic physics snapshots."""
from __future__ import annotations

from dataclasses import dataclass

from ..ecs.canonical import digest
from .commands import (
    PhysicsCommand,
    PhysicsCommandFrame,
    PhysicsCommandTape,
    step_physics_with_commands,
)
from .errors import PhysicsReplayError, PhysicsSnapshotError
from .snapshots import PhysicsSnapshot, PhysicsSnapshotHistory
from .world import PhysicsStepReceipt, PhysicsWorld


@dataclass(frozen=True, slots=True)
class RollbackReceipt:
    from_tick: int
    to_tick: int
    discarded_snapshots: int
    restored_state_digest: str
    history_digest: str


class PhysicsRollbackSession:
    """Own a bounded snapshot timeline without making history simulation state.

    The wrapped PhysicsWorld remains the sole authority. History is observational
    rollback infrastructure and therefore does not participate in world digests.
    Topology/configuration changes after session creation fail closed because
    retained snapshots can no longer represent the active world configuration.
    """

    def __init__(self, world: PhysicsWorld, *, capacity: int = 256) -> None:
        if not isinstance(world, PhysicsWorld):
            raise PhysicsSnapshotError("rollback session requires PhysicsWorld")
        self.world = world
        self.history = PhysicsSnapshotHistory(capacity)
        initial = world.capture_snapshot()
        self._configuration_digest = initial.configuration_digest
        self.history.append(initial)

    def _assert_configuration(self) -> None:
        if self.world.configuration_digest != self._configuration_digest:
            raise PhysicsSnapshotError(
                "physics world configuration changed during rollback session"
            )

    def step(self, steps: int = 1) -> tuple[PhysicsStepReceipt, ...]:
        self._assert_configuration()
        if (
            isinstance(steps, bool)
            or not isinstance(steps, int)
            or not 1 <= steps <= 10_000
        ):
            raise PhysicsSnapshotError("rollback session steps outside supported range")
        receipts: list[PhysicsStepReceipt] = []
        for _ in range(steps):
            receipt = self.world.step()[0]
            self.history.append(self.world.capture_snapshot())
            receipts.append(receipt)
        return tuple(receipts)

    def rollback_to(self, tick: int) -> RollbackReceipt:
        self._assert_configuration()
        before = self.world.tick
        snapshot = self.history.at_tick(tick)
        self.world.restore_snapshot(snapshot)
        discarded = self.history.truncate_after(tick)
        return RollbackReceipt(
            from_tick=before,
            to_tick=tick,
            discarded_snapshots=discarded,
            restored_state_digest=self.world.state_digest,
            history_digest=self.history_digest,
        )

    def resimulate_to(self, tick: int) -> tuple[PhysicsStepReceipt, ...]:
        self._assert_configuration()
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < self.world.tick:
            raise PhysicsSnapshotError(
                "resimulation target must be integer at or after current tick"
            )
        delta = tick - self.world.tick
        if delta > 10_000:
            raise PhysicsSnapshotError("resimulation span exceeds supported range")
        return self.step(delta) if delta > 0 else ()

    @property
    def history_digest(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.physics.rollback_history.v1",
                "configuration_digest": self._configuration_digest,
                "snapshots": [
                    {
                        "tick": tick,
                        "snapshot_digest": self.history.at_tick(tick).snapshot_digest,
                    }
                    for tick in self.history.ticks()
                ],
            }
        )

    def snapshot_at(self, tick: int) -> PhysicsSnapshot:
        return self.history.at_tick(tick)



@dataclass(frozen=True, slots=True)
class CommandCorrectionReceipt:
    corrected_tick: int
    rollback_tick: int
    resimulated_through_tick: int
    before_digest: str
    after_digest: str
    command_tape_digest: str
    history_digest: str


class PhysicsCommandRollbackSession:
    """Rollback session that retains deterministic gameplay input frames.

    A late authoritative input can replace one prior command frame, rewind to the
    snapshot immediately before it, and resimulate all retained commands through
    the previous present tick. Command history is not simulation state, but both
    history and command-tape digests are exposed as evidence.
    """

    def __init__(
        self,
        world: PhysicsWorld,
        *,
        history_capacity: int = 256,
        command_capacity: int = 65_536,
    ) -> None:
        if not isinstance(world, PhysicsWorld):
            raise PhysicsSnapshotError("command rollback requires PhysicsWorld")
        self.world = world
        self.history = PhysicsSnapshotHistory(history_capacity)
        self.commands = PhysicsCommandTape(max_frames=command_capacity)
        initial = world.capture_snapshot()
        self._configuration_digest = initial.configuration_digest
        self.history.append(initial)

    def _assert_configuration(self) -> None:
        if self.world.configuration_digest != self._configuration_digest:
            raise PhysicsSnapshotError(
                "physics world configuration changed during command rollback session"
            )

    def step(
        self,
        commands: tuple[PhysicsCommand, ...] | list[PhysicsCommand] = (),
    ) -> PhysicsStepReceipt:
        self._assert_configuration()
        frame = PhysicsCommandFrame.build(self.world.tick + 1, tuple(commands))
        existing = (
            self.commands.frame(frame.tick)
            if frame.tick in self.commands.ticks()
            else None
        )
        if existing is not None and existing != frame:
            raise PhysicsReplayError(
                "next tick already has different retained commands; use correction"
            )

        previous = self.world.capture_snapshot()
        receipt = step_physics_with_commands(self.world, frame)
        appended = False
        try:
            if existing is None:
                self.commands.append(frame)
                appended = True
            self.history.append(self.world.capture_snapshot())
        except Exception:
            self.world.restore_snapshot(previous)
            if appended:
                self.commands.remove(frame.tick)
            self.history.truncate_after(previous.tick)
            raise
        return receipt

    def rollback_to(self, tick: int) -> RollbackReceipt:
        self._assert_configuration()
        before = self.world.tick
        snapshot = self.history.at_tick(tick)
        self.world.restore_snapshot(snapshot)
        discarded = self.history.truncate_after(tick)
        return RollbackReceipt(
            from_tick=before,
            to_tick=tick,
            discarded_snapshots=discarded,
            restored_state_digest=self.world.state_digest,
            history_digest=self.history_digest,
        )

    def resimulate_to(self, tick: int) -> tuple[PhysicsStepReceipt, ...]:
        self._assert_configuration()
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < self.world.tick:
            raise PhysicsSnapshotError(
                "resimulation target must be integer at or after current tick"
            )
        delta = tick - self.world.tick
        if delta > 10_000:
            raise PhysicsSnapshotError("resimulation span exceeds supported range")

        receipts: list[PhysicsStepReceipt] = []
        while self.world.tick < tick:
            next_tick = self.world.tick + 1
            frame = self.commands.frame(next_tick)
            receipt = step_physics_with_commands(self.world, frame)
            self.history.append(self.world.capture_snapshot())
            receipts.append(receipt)
        return tuple(receipts)

    def correct_and_resimulate(
        self,
        tick: int,
        commands: tuple[PhysicsCommand, ...] | list[PhysicsCommand],
        *,
        through_tick: int | None = None,
    ) -> CommandCorrectionReceipt:
        self._assert_configuration()
        if isinstance(tick, bool) or not isinstance(tick, int) or tick <= 0:
            raise PhysicsReplayError("corrected tick must be positive integer")
        if tick not in self.commands.ticks():
            raise PhysicsReplayError("cannot correct command frame that was not retained")

        present_tick = self.world.tick if through_tick is None else through_tick
        if (
            isinstance(present_tick, bool)
            or not isinstance(present_tick, int)
            or present_tick < tick
        ):
            raise PhysicsReplayError(
                "resimulation through_tick must be at or after corrected tick"
            )
        if present_tick - (tick - 1) > 10_000:
            raise PhysicsReplayError("correction resimulation span exceeds supported range")

        corrected = PhysicsCommandFrame.build(tick, tuple(commands))
        before_snapshot = self.world.capture_snapshot()
        before_digest = before_snapshot.state_digest
        original = self.commands.frame(tick)
        retained_history = tuple(
            self.history.at_tick(value)
            for value in self.history.ticks()
        )

        self.commands.replace(corrected)
        try:
            self.rollback_to(tick - 1)
            self.resimulate_to(present_tick)
        except Exception:
            self.commands.replace(original)
            self.history.clear()
            for snapshot in retained_history:
                self.history.append(snapshot)
            self.world.restore_snapshot(before_snapshot)
            raise

        return CommandCorrectionReceipt(
            corrected_tick=tick,
            rollback_tick=tick - 1,
            resimulated_through_tick=present_tick,
            before_digest=before_digest,
            after_digest=self.world.state_digest,
            command_tape_digest=self.commands.tape_digest,
            history_digest=self.history_digest,
        )

    def snapshot_at(self, tick: int) -> PhysicsSnapshot:
        return self.history.at_tick(tick)

    @property
    def history_digest(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.physics.command_rollback_history.v1",
                "configuration_digest": self._configuration_digest,
                "snapshots": [
                    {
                        "tick": tick,
                        "snapshot_digest": self.history.at_tick(tick).snapshot_digest,
                    }
                    for tick in self.history.ticks()
                ],
                "command_tape_digest": self.commands.tape_digest,
            }
        )
