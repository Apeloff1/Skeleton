"""Resumable bounded migration for durable secondary sequence indexes.

Legacy durable chains may predate sequence locators.  A full index rebuild can
exceed startup or request budgets on large histories.  This coordinator pins a
committed chain head, walks backward in bounded authoritative batches, and
persists a CAS restart cursor.  New chain growth creates a later generation
whose floor is the previously completed pinned head.

The migration state is operational metadata only.  Hash-linked journal/receipt
nodes remain authoritative, and conflicting locator entries block migration
rather than being overwritten.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.store_protocol import VersionedStateBackend
from skeleton.shells.sequence_index import (
    SequenceIndexBackfillableChain,
    SequenceIndexBackfillBatch,
)


def _chain_id(value: str) -> str:
    value = str(value).strip()
    if not value or len(value) > 128:
        raise ValueError("invalid sequence-index migration chain_id")
    return value


def _digest(
    name: str,
    value: str,
) -> str:
    if len(value) != 64:
        raise ValueError(f"{name} must be digest-shaped")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be hexadecimal"
        ) from exc
    return value.lower()


def _stable_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


class SequenceIndexMigrationPhase(str, Enum):
    RUNNING = "running"
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class DurableSequenceIndexMigrationPolicy:
    batch_size: int = 512
    max_batches_per_run: int = 8
    max_generations: int = 1_000_000
    max_cas_retries: int = 32

    def __post_init__(self) -> None:
        for name in (
            "batch_size",
            "max_batches_per_run",
            "max_generations",
            "max_cas_retries",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be positive integer"
                )

    @property
    def max_items_per_run(self) -> int:
        return (
            self.batch_size
            * self.max_batches_per_run
        )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict()
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "batch_size": self.batch_size,
            "max_batches_per_run": (
                self.max_batches_per_run
            ),
            "max_generations": self.max_generations,
            "max_cas_retries": self.max_cas_retries,
            "max_items_per_run": self.max_items_per_run,
        }


@dataclass(frozen=True)
class DurableSequenceIndexMigrationState:
    schema_version: int
    chain_id: str
    generation: int
    phase: SequenceIndexMigrationPhase
    pinned_head_sequence: int
    pinned_head_root: str
    floor_sequence: int
    floor_root: str
    next_sequence: int
    next_root: str
    indexed_total: int
    already_indexed_total: int
    batches_completed: int
    started_at: float
    updated_at: float
    policy_digest: str
    last_batch_digest: str = ""
    last_error_type: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported sequence-index migration schema"
            )
        object.__setattr__(
            self,
            "chain_id",
            _chain_id(self.chain_id),
        )
        object.__setattr__(
            self,
            "phase",
            SequenceIndexMigrationPhase(
                self.phase
            ),
        )
        for name in (
            "generation",
            "pinned_head_sequence",
            "floor_sequence",
            "next_sequence",
            "indexed_total",
            "already_indexed_total",
            "batches_completed",
        ):
            value = getattr(self, name)
            minimum = 1 if name == "generation" else 0
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < minimum
            ):
                raise ValueError(
                    f"{name} is outside supported range"
                )
        for name in (
            "pinned_head_root",
            "floor_root",
            "next_root",
            "policy_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        if self.last_batch_digest:
            object.__setattr__(
                self,
                "last_batch_digest",
                _digest(
                    "last_batch_digest",
                    self.last_batch_digest,
                ),
            )
        if len(self.last_error_type) > 256:
            raise ValueError(
                "last_error_type too long"
            )
        for name in (
            "started_at",
            "updated_at",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(
                    f"{name} must be finite and non-negative"
                )
            object.__setattr__(
                self,
                name,
                float(value),
            )
        if self.updated_at < self.started_at:
            raise ValueError(
                "migration updated_at precedes started_at"
            )
        if (
            self.floor_sequence
            > self.pinned_head_sequence
        ):
            raise ValueError(
                "migration floor exceeds pinned head"
            )
        if not (
            self.floor_sequence
            <= self.next_sequence
            <= self.pinned_head_sequence
        ):
            raise ValueError(
                "migration next sequence outside pinned range"
            )
        if self.phase is SequenceIndexMigrationPhase.COMPLETE:
            if (
                self.next_sequence
                != self.floor_sequence
                or self.next_root
                != self.floor_root
            ):
                raise ValueError(
                    "completed migration must terminate at floor"
                )
            if self.last_error_type:
                raise ValueError(
                    "completed migration may not retain error type"
                )
        if (
            self.phase
            is SequenceIndexMigrationPhase.BLOCKED
            and not self.last_error_type
        ):
            raise ValueError(
                "blocked migration requires error type"
            )

    @property
    def span_items(self) -> int:
        return (
            self.pinned_head_sequence
            - self.floor_sequence
        )

    @property
    def remaining_items(self) -> int:
        return (
            self.next_sequence
            - self.floor_sequence
        )

    @property
    def processed_items(self) -> int:
        return (
            self.span_items
            - self.remaining_items
        )

    @property
    def progress_fraction(self) -> float:
        if self.span_items == 0:
            return 1.0
        return (
            self.processed_items
            / self.span_items
        )

    @property
    def complete(self) -> bool:
        return (
            self.phase
            is SequenceIndexMigrationPhase.COMPLETE
        )

    @property
    def blocked(self) -> bool:
        return (
            self.phase
            is SequenceIndexMigrationPhase.BLOCKED
        )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict(
                include_digest=False
            )
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            "chain_id": self.chain_id,
            "generation": self.generation,
            "phase": self.phase.value,
            "complete": self.complete,
            "blocked": self.blocked,
            "pinned_head_sequence": (
                self.pinned_head_sequence
            ),
            "pinned_head_root": (
                self.pinned_head_root
            ),
            "floor_sequence": self.floor_sequence,
            "floor_root": self.floor_root,
            "next_sequence": self.next_sequence,
            "next_root": self.next_root,
            "span_items": self.span_items,
            "remaining_items": self.remaining_items,
            "processed_items": self.processed_items,
            "progress_fraction": (
                self.progress_fraction
            ),
            "indexed_total": self.indexed_total,
            "already_indexed_total": (
                self.already_indexed_total
            ),
            "batches_completed": (
                self.batches_completed
            ),
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "policy_digest": self.policy_digest,
            "last_batch_digest": (
                self.last_batch_digest
            ),
            "last_error_type": (
                self.last_error_type
            ),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class StoredSequenceIndexMigration:
    revision: int
    state: DurableSequenceIndexMigrationState

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError(
                "migration revision must be positive"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "state": self.state.to_dict(),
        }


@dataclass(frozen=True)
class SequenceIndexMigrationRun:
    before: DurableSequenceIndexMigrationState
    after: DurableSequenceIndexMigrationState
    batches: tuple[
        SequenceIndexBackfillBatch,
        ...
    ]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "batches",
            tuple(self.batches),
        )
        if self.before.chain_id != self.after.chain_id:
            raise ValueError(
                "migration run chain changed"
            )
        if (
            self.before.generation
            != self.after.generation
        ):
            raise ValueError(
                "migration run generation changed"
            )

    @property
    def indexed(self) -> int:
        return sum(
            item.indexed
            for item in self.batches
        )

    @property
    def already_indexed(self) -> int:
        return sum(
            item.already_indexed
            for item in self.batches
        )

    @property
    def advanced_items(self) -> int:
        return sum(
            item.covered_items
            for item in self.batches
        )

    @property
    def complete(self) -> bool:
        return self.after.complete

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict(
                include_digest=False
            )
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "batches": [
                item.to_dict()
                for item in self.batches
            ],
            "indexed": self.indexed,
            "already_indexed": (
                self.already_indexed
            ),
            "advanced_items": self.advanced_items,
            "complete": self.complete,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableSequenceIndexMigrationError(RuntimeError):
    pass


class DurableSequenceIndexMigrator:
    """CAS-backed restartable sequence-locator backfill coordinator."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-ai-sequence-index-migration",
        policy: DurableSequenceIndexMigrationPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid sequence-index migration namespace"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.backend = backend
        self.namespace = namespace
        self.policy = (
            policy
            or DurableSequenceIndexMigrationPolicy()
        )
        if not isinstance(
            self.policy,
            DurableSequenceIndexMigrationPolicy,
        ):
            raise TypeError(
                "policy must be DurableSequenceIndexMigrationPolicy"
            )
        self._clock = clock

    @staticmethod
    def key(chain_id: str) -> str:
        chain_id = _chain_id(chain_id)
        return "migration:" + hashlib.sha256(
            chain_id.encode()
        ).hexdigest()

    def _now(self) -> float:
        value = self._clock()
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0.0
        ):
            raise ValueError(
                "migration clock must return finite non-negative time"
            )
        return float(value)

    @staticmethod
    def _require_chain(
        chain: object,
    ) -> SequenceIndexBackfillableChain:
        if not isinstance(
            chain,
            SequenceIndexBackfillableChain,
        ):
            raise TypeError(
                "chain does not implement sequence-index backfill contract"
            )
        return chain

    def current(
        self,
        chain_id: str,
    ) -> StoredSequenceIndexMigration | None:
        record = self.backend.get(
            self.namespace,
            self.key(chain_id),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableSequenceIndexMigrationState,
        ):
            raise DurableSequenceIndexMigrationError(
                "migration backend value has invalid type"
            )
        return StoredSequenceIndexMigration(
            record.revision,
            record.value,
        )

    @staticmethod
    def _head(chain) -> tuple[int, str]:
        head = chain.head()
        sequence = int(head.sequence)
        root = _digest(
            "head_root",
            str(head.root_hash),
        )
        if sequence < 0:
            raise DurableSequenceIndexMigrationError(
                "chain head sequence is negative"
            )
        return sequence, root

    @staticmethod
    def _genesis(chain) -> str:
        batch = (
            chain.backfill_sequence_indexes_batch(
                end_sequence=0,
                max_items=1,
            )
        )
        if not batch.complete_to_genesis:
            raise DurableSequenceIndexMigrationError(
                "chain did not return genesis for empty backfill"
            )
        return batch.next_root

    def _initial_state(
        self,
        chain_id: str,
        chain,
        *,
        generation: int,
        floor_sequence: int,
        floor_root: str,
    ) -> DurableSequenceIndexMigrationState:
        head_sequence, head_root = self._head(
            chain
        )
        if head_sequence < floor_sequence:
            raise DurableSequenceIndexMigrationError(
                "chain head regressed below migration floor"
            )
        if (
            head_sequence == floor_sequence
            and head_root != floor_root
        ):
            raise DurableSequenceIndexMigrationError(
                "chain head forked at migration floor"
            )
        if floor_sequence and not chain.root_is_ancestor(
            floor_root
        ):
            raise DurableSequenceIndexMigrationError(
                "migration floor is not committed ancestor"
            )
        now = self._now()
        complete = (
            head_sequence == floor_sequence
        )
        return DurableSequenceIndexMigrationState(
            1,
            chain_id,
            generation,
            (
                SequenceIndexMigrationPhase.COMPLETE
                if complete
                else SequenceIndexMigrationPhase.RUNNING
            ),
            head_sequence,
            head_root,
            floor_sequence,
            floor_root,
            (
                floor_sequence
                if complete
                else head_sequence
            ),
            (
                floor_root
                if complete
                else head_root
            ),
            0,
            0,
            0,
            now,
            now,
            self.policy.digest,
        )

    def _create(
        self,
        state: DurableSequenceIndexMigrationState,
    ) -> StoredSequenceIndexMigration:
        try:
            record = self.backend.put_if_absent(
                self.namespace,
                self.key(state.chain_id),
                state,
            )
            return StoredSequenceIndexMigration(
                record.revision,
                state,
            )
        except DistributedStateConflict:
            current = self.current(
                state.chain_id
            )
            if current is None:
                raise
            return current

    def _replace(
        self,
        stored: StoredSequenceIndexMigration,
        state: DurableSequenceIndexMigrationState,
    ) -> StoredSequenceIndexMigration:
        if (
            stored.state.chain_id
            != state.chain_id
        ):
            raise DurableSequenceIndexMigrationError(
                "migration replacement changed chain_id"
            )
        try:
            record = self.backend.compare_and_swap(
                self.namespace,
                self.key(state.chain_id),
                expected_revision=stored.revision,
                value=state,
            )
        except DistributedStateConflict:
            raise
        return StoredSequenceIndexMigration(
            record.revision,
            state,
        )

    def begin(
        self,
        chain_id: str,
        chain: object,
    ) -> StoredSequenceIndexMigration:
        chain_id = _chain_id(chain_id)
        chain = self._require_chain(chain)
        genesis = self._genesis(chain)

        for _ in range(
            self.policy.max_cas_retries
        ):
            current = self.current(chain_id)
            if current is None:
                state = self._initial_state(
                    chain_id,
                    chain,
                    generation=1,
                    floor_sequence=0,
                    floor_root=genesis,
                )
                created = self._create(state)
                if (
                    created.state.chain_id
                    == chain_id
                ):
                    return created
                continue

            state = current.state
            if state.policy_digest != self.policy.digest:
                raise DurableSequenceIndexMigrationError(
                    "migration policy changed while state exists"
                )
            if (
                state.phase
                is SequenceIndexMigrationPhase.BLOCKED
            ):
                return current
            if not chain.root_is_ancestor(
                state.pinned_head_root
            ):
                blocked = replace(
                    state,
                    phase=(
                        SequenceIndexMigrationPhase.BLOCKED
                    ),
                    updated_at=self._now(),
                    last_error_type=(
                        "PinnedHeadNotAncestor"
                    ),
                )
                try:
                    return self._replace(
                        current,
                        blocked,
                    )
                except DistributedStateConflict:
                    continue

            if not state.complete:
                return current

            head_sequence, head_root = (
                self._head(chain)
            )
            if (
                head_sequence
                == state.pinned_head_sequence
            ):
                if (
                    head_root
                    != state.pinned_head_root
                ):
                    raise DurableSequenceIndexMigrationError(
                        "chain forked at completed migration head"
                    )
                return current
            if (
                head_sequence
                < state.pinned_head_sequence
            ):
                raise DurableSequenceIndexMigrationError(
                    "chain regressed after completed migration"
                )
            if state.generation >= (
                self.policy.max_generations
            ):
                raise DurableSequenceIndexMigrationError(
                    "migration generation bound exhausted"
                )

            next_state = self._initial_state(
                chain_id,
                chain,
                generation=state.generation + 1,
                floor_sequence=(
                    state.pinned_head_sequence
                ),
                floor_root=(
                    state.pinned_head_root
                ),
            )
            try:
                return self._replace(
                    current,
                    next_state,
                )
            except DistributedStateConflict:
                continue

        raise DurableSequenceIndexMigrationError(
            "migration begin CAS retry budget exhausted"
        )

    def _block(
        self,
        stored: StoredSequenceIndexMigration,
        exc: BaseException,
    ) -> StoredSequenceIndexMigration:
        error_type = type(exc).__name__[:256]
        for _ in range(
            self.policy.max_cas_retries
        ):
            current = self.current(
                stored.state.chain_id
            )
            if current is None:
                raise DurableSequenceIndexMigrationError(
                    "migration state disappeared while blocking"
                )
            if (
                current.state.generation
                != stored.state.generation
            ):
                return current
            blocked = replace(
                current.state,
                phase=(
                    SequenceIndexMigrationPhase.BLOCKED
                ),
                updated_at=self._now(),
                last_error_type=error_type,
            )
            try:
                return self._replace(
                    current,
                    blocked,
                )
            except DistributedStateConflict:
                continue
        raise DurableSequenceIndexMigrationError(
            "migration block CAS retry budget exhausted"
        )

    def retry_blocked(
        self,
        chain_id: str,
        chain: object,
    ) -> StoredSequenceIndexMigration:
        chain_id = _chain_id(chain_id)
        chain = self._require_chain(chain)
        for _ in range(
            self.policy.max_cas_retries
        ):
            current = self.current(chain_id)
            if current is None:
                return self.begin(
                    chain_id,
                    chain,
                )
            if (
                current.state.phase
                is not SequenceIndexMigrationPhase.BLOCKED
            ):
                return current
            if not chain.root_is_ancestor(
                current.state.pinned_head_root
            ):
                raise DurableSequenceIndexMigrationError(
                    "blocked migration pinned head is not committed ancestor"
                )
            running = replace(
                current.state,
                phase=(
                    SequenceIndexMigrationPhase.RUNNING
                    if (
                        current.state.next_sequence
                        > current.state.floor_sequence
                    )
                    else SequenceIndexMigrationPhase.COMPLETE
                ),
                updated_at=self._now(),
                last_error_type="",
            )
            try:
                return self._replace(
                    current,
                    running,
                )
            except DistributedStateConflict:
                continue
        raise DurableSequenceIndexMigrationError(
            "migration retry CAS budget exhausted"
        )

    def run(
        self,
        chain_id: str,
        chain: object,
    ) -> SequenceIndexMigrationRun:
        chain_id = _chain_id(chain_id)
        chain = self._require_chain(chain)
        stored = self.begin(
            chain_id,
            chain,
        )
        before = stored.state
        if before.blocked or before.complete:
            return SequenceIndexMigrationRun(
                before,
                before,
                (),
            )

        batches: list[
            SequenceIndexBackfillBatch
        ] = []
        for _ in range(
            self.policy.max_batches_per_run
        ):
            stored = self.current(chain_id)
            if stored is None:
                raise DurableSequenceIndexMigrationError(
                    "migration state disappeared during run"
                )
            state = stored.state
            if state.blocked or state.complete:
                break
            remaining = (
                state.next_sequence
                - state.floor_sequence
            )
            if remaining <= 0:
                raise DurableSequenceIndexMigrationError(
                    "running migration has no remaining range"
                )
            max_items = min(
                self.policy.batch_size,
                remaining,
            )
            try:
                batch = (
                    chain.backfill_sequence_indexes_batch(
                        end_sequence=(
                            state.next_sequence
                        ),
                        end_root=state.next_root,
                        max_items=max_items,
                    )
                )
                if (
                    batch.requested_end_sequence
                    != state.next_sequence
                    or batch.requested_end_root
                    != state.next_root
                ):
                    raise DurableSequenceIndexMigrationError(
                        "backfill batch did not honor migration cursor"
                    )
                if (
                    batch.next_sequence
                    < state.floor_sequence
                ):
                    raise DurableSequenceIndexMigrationError(
                        "backfill crossed migration floor"
                    )
                if (
                    batch.next_sequence
                    == state.floor_sequence
                    and batch.next_root
                    != state.floor_root
                ):
                    raise DurableSequenceIndexMigrationError(
                        "backfill reached wrong floor root"
                    )
                complete = (
                    batch.next_sequence
                    == state.floor_sequence
                )
                updated = replace(
                    state,
                    phase=(
                        SequenceIndexMigrationPhase.COMPLETE
                        if complete
                        else SequenceIndexMigrationPhase.RUNNING
                    ),
                    next_sequence=(
                        batch.next_sequence
                    ),
                    next_root=batch.next_root,
                    indexed_total=(
                        state.indexed_total
                        + batch.indexed
                    ),
                    already_indexed_total=(
                        state.already_indexed_total
                        + batch.already_indexed
                    ),
                    batches_completed=(
                        state.batches_completed + 1
                    ),
                    updated_at=self._now(),
                    last_batch_digest=batch.digest,
                    last_error_type="",
                )
                try:
                    stored = self._replace(
                        stored,
                        updated,
                    )
                except DistributedStateConflict:
                    # Index writes are immutable/idempotent. Another worker won
                    # the progress CAS; reload its authoritative cursor.
                    continue
                batches.append(batch)
                if stored.state.complete:
                    break
            except DistributedStateConflict:
                continue
            except BaseException as exc:
                blocked = self._block(
                    stored,
                    exc,
                )
                return SequenceIndexMigrationRun(
                    before,
                    blocked.state,
                    tuple(batches),
                )

        after_stored = self.current(chain_id)
        if after_stored is None:
            raise DurableSequenceIndexMigrationError(
                "migration state disappeared after run"
            )
        return SequenceIndexMigrationRun(
            before,
            after_stored.state,
            tuple(batches),
        )

    def require_complete(
        self,
        chain_id: str,
        chain: object,
    ) -> DurableSequenceIndexMigrationState:
        chain_id = _chain_id(chain_id)
        chain = self._require_chain(chain)
        current = self.current(chain_id)
        if current is None:
            raise DurableSequenceIndexMigrationError(
                "sequence-index migration has not started"
            )
        state = current.state
        if not state.complete:
            raise DurableSequenceIndexMigrationError(
                "sequence-index migration is not complete"
            )
        if not chain.root_is_ancestor(
            state.pinned_head_root
        ):
            raise DurableSequenceIndexMigrationError(
                "completed migration head is no longer committed ancestor"
            )
        return state
