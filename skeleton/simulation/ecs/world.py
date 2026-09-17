"""Deterministic world-session control plane over the authoritative ECS store.

The low-level :mod:`store` module intentionally stays small.  This module adds
operator-facing workflows that are useful to game builders without creating a
second source of truth: named checkpoints, isolated forks, planned change sets,
state comparisons, bounded history and evidence records.

All mutations still flow through ``EntityStore`` and ``BatchPlanner``.  World
sessions only retain immutable snapshots and digest-chained evidence.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .batch import BatchOperation, BatchPlanner
from .canonical import digest
from .errors import BoundsError, SnapshotError, ValidationError
from .execution import StoreSnapshot, capture_snapshot, restore_snapshot
from .inspection import StateDiff, diff_state, inspect_store
from .journal import JournalKind, MutationJournal
from .store import EntityStore

MAX_WORLD_CHECKPOINTS = 512
MAX_CHANGESET_OPERATIONS = 50_000
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _name(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not _NAME_RE.fullmatch(value):
        raise ValidationError(f"invalid {label}", context={label: value})
    return value


@dataclass(frozen=True)
class WorldPolicy:
    """Session-local safety and retention policy.

    Store-level hard limits remain authoritative.  These values are narrower
    workflow limits that callers may use to keep editor or simulation sessions
    intentionally small.
    """

    checkpoint_capacity: int = 64
    journal_capacity: int = 10_000
    max_changeset_operations: int = 10_000
    require_clean_restore: bool = True

    def __post_init__(self) -> None:
        for name, value, minimum, maximum in (
            ("checkpoint_capacity", self.checkpoint_capacity, 1, MAX_WORLD_CHECKPOINTS),
            ("journal_capacity", self.journal_capacity, 1, 100_000),
            (
                "max_changeset_operations",
                self.max_changeset_operations,
                1,
                MAX_CHANGESET_OPERATIONS,
            ),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValidationError(f"{name} must be integer")
            if not minimum <= value <= maximum:
                raise ValidationError(
                    f"{name} outside supported range",
                    context={"value": value, "minimum": minimum, "maximum": maximum},
                )
        if not isinstance(self.require_clean_restore, bool):
            raise ValidationError("require_clean_restore must be boolean")

    @property
    def fingerprint(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.ecs.world_policy.v1",
                "checkpoint_capacity": self.checkpoint_capacity,
                "journal_capacity": self.journal_capacity,
                "max_changeset_operations": self.max_changeset_operations,
                "require_clean_restore": self.require_clean_restore,
            }
        )


@dataclass(frozen=True)
class WorldCheckpoint:
    name: str
    snapshot: StoreSnapshot
    sequence: int
    reason: str
    checkpoint_digest: str

    def __post_init__(self) -> None:
        _name(self.name, label="checkpoint name")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise ValidationError("checkpoint sequence must be non-negative integer")
        if not isinstance(self.reason, str):
            raise ValidationError("checkpoint reason must be text")

    @property
    def revision(self) -> int:
        return self.snapshot.revision

    @property
    def tick(self) -> int:
        return self.snapshot.tick

    @property
    def state_digest(self) -> str:
        return self.snapshot.state_digest


@dataclass(frozen=True)
class ChangeSet:
    """Immutable ordered request to mutate a world.

    Dependency semantics and conflict detection are delegated to ``BatchPlanner``.
    The changeset digest binds the human metadata and operation fingerprints.
    """

    change_id: str
    operations: tuple[BatchOperation, ...]
    description: str = ""
    expected_base_digest: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _name(self.change_id, label="change id")
        operations = tuple(self.operations)
        if len(operations) > MAX_CHANGESET_OPERATIONS:
            raise BoundsError(
                "changeset operation bound exceeded",
                context={"maximum": MAX_CHANGESET_OPERATIONS},
            )
        if len({row.operation_id for row in operations}) != len(operations):
            raise ValidationError("changeset operation ids must be unique")
        if not isinstance(self.description, str):
            raise ValidationError("changeset description must be text")
        if self.expected_base_digest is not None:
            if not isinstance(self.expected_base_digest, str) or len(self.expected_base_digest) != 64:
                raise ValidationError("expected base digest must be sha256 text")
        if not isinstance(self.metadata, Mapping):
            raise ValidationError("changeset metadata must be mapping")
        digest(dict(self.metadata))
        object.__setattr__(self, "operations", operations)
        object.__setattr__(self, "metadata", copy.deepcopy(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.ecs.changeset.v1",
                "change_id": self.change_id,
                "operations": [row.fingerprint for row in self.operations],
                "description": self.description,
                "expected_base_digest": self.expected_base_digest,
                "metadata": dict(self.metadata),
            }
        )


@dataclass(frozen=True)
class ChangeSetPreview:
    change_id: str
    change_fingerprint: str
    base_digest: str
    result_digest: str
    base_revision: int
    result_revision: int
    state_diff: StateDiff
    operation_count: int

    @property
    def changed(self) -> bool:
        return self.base_digest != self.result_digest


@dataclass(frozen=True)
class ChangeSetReceipt:
    change_id: str
    change_fingerprint: str
    before_digest: str
    after_digest: str
    before_revision: int
    after_revision: int
    operation_count: int
    journal_sequence: int


@dataclass(frozen=True)
class WorldFork:
    name: str
    parent_digest: str
    parent_revision: int
    session: "WorldSession"
    fork_digest: str


@dataclass(frozen=True)
class WorldStatus:
    name: str
    revision: int
    tick: int
    state_digest: str
    entities: int
    components: int
    resources: int
    tombstones: int
    checkpoints: tuple[str, ...]
    journal_entries: int
    policy_fingerprint: str
    status_digest: str


class WorldSession:
    """Bounded deterministic editing/simulation session.

    ``WorldSession`` never mutates a store outside explicit methods. Preview is
    clone-only, checkpoints are immutable snapshots, and restore validates the
    checkpoint digest before replacing authoritative state.
    """

    def __init__(
        self,
        name: str,
        store: EntityStore | None = None,
        *,
        policy: WorldPolicy | None = None,
    ) -> None:
        self.name = _name(name, label="world name")
        self.store = store or EntityStore()
        if not isinstance(self.store, EntityStore):
            raise ValidationError("WorldSession requires EntityStore")
        self.policy = policy or WorldPolicy()
        self.journal = MutationJournal(capacity=self.policy.journal_capacity)
        self._checkpoints: dict[str, WorldCheckpoint] = {}
        self._checkpoint_order: list[str] = []
        self._checkpoint_sequence = 0

    def checkpoint_names(self) -> tuple[str, ...]:
        return tuple(self._checkpoint_order)

    def checkpoint(self, name: str, *, reason: str = "") -> WorldCheckpoint:
        name = _name(name, label="checkpoint name")
        snapshot = capture_snapshot(self.store)
        material = {
            "domain": "skeleton.simulation.ecs.world_checkpoint.v1",
            "world": self.name,
            "name": name,
            "sequence": self._checkpoint_sequence,
            "reason": reason,
            "state_digest": snapshot.state_digest,
            "revision": snapshot.revision,
            "tick": snapshot.tick,
            "policy": self.policy.fingerprint,
        }
        row = WorldCheckpoint(
            name=name,
            snapshot=snapshot,
            sequence=self._checkpoint_sequence,
            reason=reason,
            checkpoint_digest=digest(material),
        )
        self._checkpoint_sequence += 1
        if name not in self._checkpoints:
            if len(self._checkpoint_order) >= self.policy.checkpoint_capacity:
                oldest = self._checkpoint_order.pop(0)
                self._checkpoints.pop(oldest, None)
            self._checkpoint_order.append(name)
        self._checkpoints[name] = row
        self.journal.append(
            JournalKind.CHECKPOINT,
            "world_checkpoint",
            name,
            {
                "checkpoint_digest": row.checkpoint_digest,
                "state_digest": row.state_digest,
                "revision": row.revision,
            },
            tick=self.store.tick,
            source=self.name,
        )
        return row

    def get_checkpoint(self, name: str) -> WorldCheckpoint:
        name = _name(name, label="checkpoint name")
        try:
            return self._checkpoints[name]
        except KeyError as exc:
            raise SnapshotError(
                "world checkpoint not found",
                context={"world": self.name, "checkpoint": name},
            ) from exc

    @staticmethod
    def _verify_checkpoint(checkpoint: WorldCheckpoint) -> None:
        if checkpoint.snapshot.store.state_digest != checkpoint.state_digest:
            raise SnapshotError("world checkpoint snapshot is corrupt")
        if checkpoint.snapshot.revision != checkpoint.snapshot.store.revision:
            raise SnapshotError("world checkpoint revision mismatch")
        if checkpoint.snapshot.tick != checkpoint.snapshot.store.tick:
            raise SnapshotError("world checkpoint tick mismatch")

    def _expected_checkpoint_digest(self, checkpoint: WorldCheckpoint) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.ecs.world_checkpoint.v1",
                "world": self.name,
                "name": checkpoint.name,
                "sequence": checkpoint.sequence,
                "reason": checkpoint.reason,
                "state_digest": checkpoint.state_digest,
                "revision": checkpoint.revision,
                "tick": checkpoint.tick,
                "policy": self.policy.fingerprint,
            }
        )

    def restore(self, name: str, *, require_current_digest: str | None = None) -> WorldCheckpoint:
        checkpoint = self.get_checkpoint(name)
        self._verify_checkpoint(checkpoint)
        if checkpoint.checkpoint_digest != self._expected_checkpoint_digest(checkpoint):
            raise SnapshotError("world checkpoint metadata digest mismatch")
        if require_current_digest is not None and self.store.state_digest != require_current_digest:
            raise SnapshotError(
                "world restore current digest precondition failed",
                context={"expected": require_current_digest, "actual": self.store.state_digest},
            )
        before = self.store.state_digest
        restore_snapshot(self.store, checkpoint.snapshot)
        self.store.assert_invariants()
        self.journal.mutation(
            "restore_checkpoint",
            checkpoint.name,
            {"before_digest": before, "after_digest": self.store.state_digest},
            tick=self.store.tick,
            source=self.name,
        )
        return checkpoint

    def preview(self, change: ChangeSet) -> ChangeSetPreview:
        if not isinstance(change, ChangeSet):
            raise ValidationError("preview requires ChangeSet")
        if len(change.operations) > self.policy.max_changeset_operations:
            raise BoundsError(
                "changeset exceeds world session operation policy",
                context={
                    "count": len(change.operations),
                    "maximum": self.policy.max_changeset_operations,
                },
            )
        if change.expected_base_digest is not None and change.expected_base_digest != self.store.state_digest:
            raise ValidationError(
                "changeset base digest mismatch",
                context={"expected": change.expected_base_digest, "actual": self.store.state_digest},
            )
        clone = self.store.clone()
        before = capture_snapshot(clone)
        planner = BatchPlanner(change.operations)
        planner.commit(clone)
        clone.assert_invariants()
        after = capture_snapshot(clone)
        return ChangeSetPreview(
            change_id=change.change_id,
            change_fingerprint=change.fingerprint,
            base_digest=before.state_digest,
            result_digest=after.state_digest,
            base_revision=before.revision,
            result_revision=after.revision,
            state_diff=diff_state(before, after),
            operation_count=len(change.operations),
        )

    def apply(self, change: ChangeSet) -> ChangeSetReceipt:
        preview = self.preview(change)
        before_digest = self.store.state_digest
        before_revision = self.store.revision
        planner = BatchPlanner(change.operations)
        result = planner.commit(self.store)
        self.store.assert_invariants()
        if self.store.state_digest != preview.result_digest:
            raise ValidationError(
                "changeset commit diverged from deterministic preview",
                context={
                    "preview": preview.result_digest,
                    "actual": self.store.state_digest,
                },
            )
        entry = self.journal.mutation(
            "apply_changeset",
            change.change_id,
            {
                "change_fingerprint": change.fingerprint,
                "plan_digest": result.plan_digest,
                "before_digest": before_digest,
                "after_digest": self.store.state_digest,
                "before_revision": before_revision,
                "after_revision": self.store.revision,
                "operations": len(change.operations),
            },
            tick=self.store.tick,
            source=self.name,
        )
        return ChangeSetReceipt(
            change_id=change.change_id,
            change_fingerprint=change.fingerprint,
            before_digest=before_digest,
            after_digest=self.store.state_digest,
            before_revision=before_revision,
            after_revision=self.store.revision,
            operation_count=len(change.operations),
            journal_sequence=entry.sequence,
        )

    def fork(self, name: str) -> WorldFork:
        name = _name(name, label="fork name")
        fork_store = self.store.clone()
        child = WorldSession(name, fork_store, policy=copy.deepcopy(self.policy))
        material = {
            "domain": "skeleton.simulation.ecs.world_fork.v1",
            "parent": self.name,
            "child": name,
            "parent_digest": self.store.state_digest,
            "parent_revision": self.store.revision,
            "policy": self.policy.fingerprint,
        }
        fork = WorldFork(
            name=name,
            parent_digest=self.store.state_digest,
            parent_revision=self.store.revision,
            session=child,
            fork_digest=digest(material),
        )
        self.journal.append(
            JournalKind.NOTE,
            "fork_world",
            name,
            {
                "fork_digest": fork.fork_digest,
                "state_digest": fork.parent_digest,
                "revision": fork.parent_revision,
            },
            tick=self.store.tick,
            source=self.name,
        )
        return fork

    def diff_checkpoint(self, name: str, *, include_unchanged: bool = False) -> StateDiff:
        checkpoint = self.get_checkpoint(name)
        return diff_state(
            checkpoint.snapshot,
            self.store,
            include_unchanged=include_unchanged,
        )

    def status(self) -> WorldStatus:
        inspection = inspect_store(self.store)
        material = {
            "domain": "skeleton.simulation.ecs.world_status.v1",
            "name": self.name,
            "revision": self.store.revision,
            "tick": self.store.tick,
            "state_digest": self.store.state_digest,
            "entities": self.store.entity_count,
            "components": self.store.component_count,
            "resources": self.store.resource_count,
            "tombstones": self.store.tombstone_count,
            "checkpoints": self.checkpoint_names(),
            "journal_entries": len(self.journal),
            "policy": self.policy.fingerprint,
            "inspection": inspection.inspection_digest,
        }
        return WorldStatus(
            name=self.name,
            revision=self.store.revision,
            tick=self.store.tick,
            state_digest=self.store.state_digest,
            entities=self.store.entity_count,
            components=self.store.component_count,
            resources=self.store.resource_count,
            tombstones=self.store.tombstone_count,
            checkpoints=self.checkpoint_names(),
            journal_entries=len(self.journal),
            policy_fingerprint=self.policy.fingerprint,
            status_digest=digest(material),
        )


def make_changeset(
    change_id: str,
    operations: Iterable[BatchOperation],
    *,
    description: str = "",
    expected_base_digest: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> ChangeSet:
    return ChangeSet(
        change_id=change_id,
        operations=tuple(operations),
        description=description,
        expected_base_digest=expected_base_digest,
        metadata=dict(metadata or {}),
    )
