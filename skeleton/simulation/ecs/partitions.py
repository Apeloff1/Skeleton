"""Deterministic world partition assignments and derived partition views.

Partitions are explicit metadata over live entity ids.  They do not own entity
state and can always be rebuilt or discarded.  This makes them suitable for
streaming, editor selection, simulation regions and work scheduling without
creating a competing persistence plane.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .canonical import digest
from .errors import BoundsError, EntityNotFoundError, ValidationError
from .store import EntityStore

MAX_PARTITIONS = 16_384
MAX_ENTITIES_PER_PARTITION = 1_000_000
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


def _token(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ValidationError(f"invalid {label}", context={label: value})
    return value


@dataclass(frozen=True)
class PartitionPolicy:
    max_partitions: int = 1024
    max_entities_per_partition: int = 100_000
    allow_unassigned: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.max_partitions, bool) or not isinstance(self.max_partitions, int):
            raise ValidationError("max_partitions must be integer")
        if not 1 <= self.max_partitions <= MAX_PARTITIONS:
            raise ValidationError("max_partitions outside supported range")
        if isinstance(self.max_entities_per_partition, bool) or not isinstance(
            self.max_entities_per_partition, int
        ):
            raise ValidationError("max_entities_per_partition must be integer")
        if not 1 <= self.max_entities_per_partition <= MAX_ENTITIES_PER_PARTITION:
            raise ValidationError("max_entities_per_partition outside supported range")
        if not isinstance(self.allow_unassigned, bool):
            raise ValidationError("allow_unassigned must be boolean")

    @property
    def fingerprint(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.ecs.partition_policy.v1",
                "max_partitions": self.max_partitions,
                "max_entities_per_partition": self.max_entities_per_partition,
                "allow_unassigned": self.allow_unassigned,
            }
        )


@dataclass(frozen=True)
class PartitionRecord:
    partition_id: str
    entity_ids: tuple[str, ...]
    entity_count: int
    partition_digest: str


@dataclass(frozen=True)
class PartitionSnapshot:
    store_revision: int
    store_digest: str
    policy_fingerprint: str
    partitions: tuple[PartitionRecord, ...]
    unassigned: tuple[str, ...]
    assignment_count: int
    snapshot_digest: str


@dataclass(frozen=True)
class PartitionMove:
    entity_id: str
    from_partition: str | None
    to_partition: str | None


@dataclass(frozen=True)
class PartitionPlan:
    moves: tuple[PartitionMove, ...]
    source_digest: str
    target_digest: str
    plan_digest: str

    @property
    def changed(self) -> bool:
        return bool(self.moves)


class WorldPartitionIndex:
    """One-partition-per-entity derived index with stale-store detection."""

    def __init__(
        self,
        store: EntityStore,
        *,
        policy: PartitionPolicy | None = None,
    ) -> None:
        if not isinstance(store, EntityStore):
            raise ValidationError("WorldPartitionIndex requires EntityStore")
        self.store = store
        self.policy = policy or PartitionPolicy()
        self._entity_to_partition: dict[str, str] = {}
        self._partition_to_entities: dict[str, set[str]] = {}
        self._store_revision = store.revision
        self._store_digest = store.state_digest

    def _touch_store(self) -> None:
        self._store_revision = self.store.revision
        self._store_digest = self.store.state_digest

    def is_current(self) -> bool:
        return (
            self.store.revision == self._store_revision
            and self.store.state_digest == self._store_digest
        )

    def refresh_store_marker(self, *, purge_missing: bool = True) -> tuple[str, ...]:
        removed: list[str] = []
        if purge_missing:
            live = set(self.store.entity_ids())
            for entity_id in sorted(tuple(self._entity_to_partition)):
                if entity_id not in live:
                    removed.append(entity_id)
                    self.unassign(entity_id, require_live=False)
        self._touch_store()
        self.assert_invariants()
        return tuple(removed)

    def partition_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._partition_to_entities))

    def has_partition(self, partition_id: str) -> bool:
        partition_id = _token(partition_id, label="partition id")
        return partition_id in self._partition_to_entities

    def partition_of(self, entity_id: str) -> str | None:
        if not isinstance(entity_id, str) or not entity_id:
            raise ValidationError("entity id must be non-empty text")
        return self._entity_to_partition.get(entity_id)

    def entities(self, partition_id: str) -> tuple[str, ...]:
        partition_id = _token(partition_id, label="partition id")
        return tuple(sorted(self._partition_to_entities.get(partition_id, ())))

    def assign(self, entity_id: str, partition_id: str) -> PartitionMove:
        if not self.store.has_entity(entity_id):
            raise EntityNotFoundError(
                "partition assignment entity not found",
                context={"entity_id": entity_id},
            )
        partition_id = _token(partition_id, label="partition id")
        old = self._entity_to_partition.get(entity_id)
        if old == partition_id:
            return PartitionMove(entity_id, old, partition_id)
        if partition_id not in self._partition_to_entities:
            if len(self._partition_to_entities) >= self.policy.max_partitions:
                raise BoundsError(
                    "partition bound exceeded",
                    context={"maximum": self.policy.max_partitions},
                )
            self._partition_to_entities[partition_id] = set()
        target = self._partition_to_entities[partition_id]
        if len(target) >= self.policy.max_entities_per_partition:
            raise BoundsError(
                "partition entity bound exceeded",
                context={
                    "partition_id": partition_id,
                    "maximum": self.policy.max_entities_per_partition,
                },
            )
        if old is not None:
            old_members = self._partition_to_entities.get(old)
            if old_members is not None:
                old_members.discard(entity_id)
                if not old_members:
                    self._partition_to_entities.pop(old, None)
        target.add(entity_id)
        self._entity_to_partition[entity_id] = partition_id
        self._touch_store()
        return PartitionMove(entity_id, old, partition_id)

    def assign_many(
        self,
        partition_id: str,
        entity_ids: Iterable[str],
    ) -> tuple[PartitionMove, ...]:
        partition_id = _token(partition_id, label="partition id")
        unique = tuple(sorted(set(entity_ids)))
        if len(unique) > self.policy.max_entities_per_partition:
            raise BoundsError("assignment batch exceeds partition policy")
        clone_entity = dict(self._entity_to_partition)
        clone_partition = {key: set(values) for key, values in self._partition_to_entities.items()}
        moves: list[PartitionMove] = []
        try:
            for entity_id in unique:
                moves.append(self.assign(entity_id, partition_id))
        except Exception:
            self._entity_to_partition = clone_entity
            self._partition_to_entities = clone_partition
            raise
        self.assert_invariants()
        return tuple(moves)

    def unassign(self, entity_id: str, *, require_live: bool = True) -> PartitionMove:
        if require_live and not self.store.has_entity(entity_id):
            raise EntityNotFoundError(
                "partition unassignment entity not found",
                context={"entity_id": entity_id},
            )
        old = self._entity_to_partition.pop(entity_id, None)
        if old is not None:
            members = self._partition_to_entities.get(old)
            if members is not None:
                members.discard(entity_id)
                if not members:
                    self._partition_to_entities.pop(old, None)
        self._touch_store()
        return PartitionMove(entity_id, old, None)

    def unassigned(self) -> tuple[str, ...]:
        assigned = set(self._entity_to_partition)
        return tuple(entity_id for entity_id in self.store.entity_ids() if entity_id not in assigned)

    def require_complete(self) -> None:
        missing = self.unassigned()
        if missing and not self.policy.allow_unassigned:
            raise ValidationError(
                "partition index contains unassigned entities",
                context={"count": len(missing), "first": missing[:16]},
            )

    def snapshot(self) -> PartitionSnapshot:
        rows: list[PartitionRecord] = []
        for partition_id in self.partition_ids():
            entity_ids = self.entities(partition_id)
            rows.append(
                PartitionRecord(
                    partition_id=partition_id,
                    entity_ids=entity_ids,
                    entity_count=len(entity_ids),
                    partition_digest=digest(
                        {
                            "domain": "skeleton.simulation.ecs.partition.v1",
                            "partition_id": partition_id,
                            "entity_ids": entity_ids,
                        }
                    ),
                )
            )
        unassigned = self.unassigned()
        material = {
            "domain": "skeleton.simulation.ecs.partition_snapshot.v1",
            "store_revision": self.store.revision,
            "store_digest": self.store.state_digest,
            "policy": self.policy.fingerprint,
            "partitions": [
                {
                    "partition_id": row.partition_id,
                    "entity_ids": row.entity_ids,
                    "partition_digest": row.partition_digest,
                }
                for row in rows
            ],
            "unassigned": unassigned,
        }
        return PartitionSnapshot(
            store_revision=self.store.revision,
            store_digest=self.store.state_digest,
            policy_fingerprint=self.policy.fingerprint,
            partitions=tuple(rows),
            unassigned=unassigned,
            assignment_count=len(self._entity_to_partition),
            snapshot_digest=digest(material),
        )

    @property
    def fingerprint(self) -> str:
        return self.snapshot().snapshot_digest

    def plan_to(self, target: Mapping[str, str]) -> PartitionPlan:
        if not isinstance(target, Mapping):
            raise ValidationError("partition target must be mapping")
        normalized: dict[str, str] = {}
        for entity_id, partition_id in target.items():
            if not self.store.has_entity(entity_id):
                raise EntityNotFoundError(
                    "partition plan entity not found",
                    context={"entity_id": entity_id},
                )
            normalized[str(entity_id)] = _token(str(partition_id), label="partition id")
        source = self.snapshot()
        moves: list[PartitionMove] = []
        all_ids = sorted(set(self._entity_to_partition) | set(normalized))
        for entity_id in all_ids:
            left = self._entity_to_partition.get(entity_id)
            right = normalized.get(entity_id)
            if left != right:
                moves.append(PartitionMove(entity_id, left, right))
        target_digest = digest(
            {
                "domain": "skeleton.simulation.ecs.partition_target.v1",
                "assignments": sorted(normalized.items()),
            }
        )
        return PartitionPlan(
            moves=tuple(moves),
            source_digest=source.snapshot_digest,
            target_digest=target_digest,
            plan_digest=digest(
                {
                    "domain": "skeleton.simulation.ecs.partition_plan.v1",
                    "source": source.snapshot_digest,
                    "target": target_digest,
                    "moves": [row.__dict__ for row in moves],
                }
            ),
        )

    def apply_plan(self, plan: PartitionPlan) -> tuple[PartitionMove, ...]:
        if not isinstance(plan, PartitionPlan):
            raise ValidationError("apply_plan requires PartitionPlan")
        if self.snapshot().snapshot_digest != plan.source_digest:
            raise ValidationError("partition plan source digest is stale")
        backup_entity = dict(self._entity_to_partition)
        backup_partition = {key: set(values) for key, values in self._partition_to_entities.items()}
        applied: list[PartitionMove] = []
        try:
            for move in plan.moves:
                if move.to_partition is None:
                    applied.append(self.unassign(move.entity_id))
                else:
                    applied.append(self.assign(move.entity_id, move.to_partition))
            self.require_complete()
            self.assert_invariants()
        except Exception:
            self._entity_to_partition = backup_entity
            self._partition_to_entities = backup_partition
            raise
        return tuple(applied)

    def assert_invariants(self) -> None:
        seen: set[str] = set()
        for partition_id, members in self._partition_to_entities.items():
            _token(partition_id, label="partition id")
            if len(members) > self.policy.max_entities_per_partition:
                raise ValidationError("partition entity bound violated")
            for entity_id in members:
                if entity_id in seen:
                    raise ValidationError("entity appears in multiple partitions")
                seen.add(entity_id)
                if self._entity_to_partition.get(entity_id) != partition_id:
                    raise ValidationError("partition reverse index mismatch")
                if not self.store.has_entity(entity_id):
                    raise ValidationError("partition references missing entity")
        if seen != set(self._entity_to_partition):
            raise ValidationError("partition forward/reverse index mismatch")
        if len(self._partition_to_entities) > self.policy.max_partitions:
            raise ValidationError("partition count bound violated")
        self.require_complete()
