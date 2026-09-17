"""Bounded rollback session over deterministic physics snapshots."""
from __future__ import annotations

from dataclasses import dataclass

from ..ecs.canonical import digest
from .errors import PhysicsSnapshotError
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
