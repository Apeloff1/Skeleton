"""Bounded cross-backend replication for durable evidence chains.

Replication never rewrites history. A target is syncable only when its current
head is an exact prefix of the source. Source segments are verified before they
are restored, targets are re-verified after every batch, and divergence or
compacted-away source history fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Callable


class DurableReplicaState(str, Enum):
    IN_SYNC = "in_sync"
    LAGGING = "lagging"
    TARGET_AHEAD = "target_ahead"
    DIVERGED = "diverged"
    SOURCE_INVALID = "source_invalid"
    TARGET_INVALID = "target_invalid"
    HISTORY_UNAVAILABLE = "history_unavailable"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class DurableReplicationPolicy:
    max_batch_items: int = 1024
    max_batches_per_run: int = 64
    require_source_integrity: bool = True
    require_target_integrity: bool = True
    promotion_max_lag_items: int = 0

    def __post_init__(self) -> None:
        for name, lower, upper in (
            ("max_batch_items", 1, 65536),
            ("max_batches_per_run", 1, 4096),
            ("promotion_max_lag_items", 0, 1_000_000),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not lower <= value <= upper
            ):
                raise ValueError(
                    f"{name} outside supported range"
                )
        for name in (
            "require_source_integrity",
            "require_target_integrity",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")

    def to_dict(self) -> dict[str, object]:
        return {
            "max_batch_items": self.max_batch_items,
            "max_batches_per_run": self.max_batches_per_run,
            "require_source_integrity": self.require_source_integrity,
            "require_target_integrity": self.require_target_integrity,
            "promotion_max_lag_items": self.promotion_max_lag_items,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class DurableChainReplicationReport:
    chain_id: str
    state: DurableReplicaState
    source_sequence: int
    source_root: str
    target_sequence: int
    target_root: str
    lag_items: int
    source_valid: bool
    target_valid: bool
    next_sequence: int | None
    next_root: str
    reason: str
    policy_digest: str

    def __post_init__(self) -> None:
        if not self.chain_id or len(self.chain_id) > 128:
            raise ValueError("invalid replication chain_id")
        object.__setattr__(
            self,
            "state",
            DurableReplicaState(self.state),
        )
        for name in (
            "source_sequence",
            "target_sequence",
            "lag_items",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative integer"
                )
        if self.next_sequence is not None and (
            isinstance(self.next_sequence, bool)
            or not isinstance(self.next_sequence, int)
            or self.next_sequence <= 0
        ):
            raise ValueError(
                "next_sequence must be positive integer"
            )
        for name in (
            "source_root",
            "target_root",
            "next_root",
            "policy_digest",
        ):
            value = getattr(self, name)
            if value and len(value) != 64:
                raise ValueError(
                    f"{name} must be SHA-256 hex"
                )
        if not isinstance(self.source_valid, bool):
            raise ValueError("source_valid must be bool")
        if not isinstance(self.target_valid, bool):
            raise ValueError("target_valid must be bool")
        if len(self.reason) > 2048:
            raise ValueError("replication reason too long")

    @property
    def in_sync(self) -> bool:
        return self.state is DurableReplicaState.IN_SYNC

    @property
    def syncable(self) -> bool:
        return self.state is DurableReplicaState.LAGGING

    @property
    def promotion_ready(self) -> bool:
        return (
            self.source_valid
            and self.target_valid
            and self.state
            in {
                DurableReplicaState.IN_SYNC,
                DurableReplicaState.LAGGING,
            }
            and self.lag_items == 0
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data = {
            "chain_id": self.chain_id,
            "state": self.state.value,
            "source_sequence": self.source_sequence,
            "source_root": self.source_root,
            "target_sequence": self.target_sequence,
            "target_root": self.target_root,
            "lag_items": self.lag_items,
            "source_valid": self.source_valid,
            "target_valid": self.target_valid,
            "next_sequence": self.next_sequence,
            "next_root": self.next_root,
            "reason": self.reason,
            "policy_digest": self.policy_digest,
            "in_sync": self.in_sync,
            "syncable": self.syncable,
            "promotion_ready": self.promotion_ready,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableReplicationBatch:
    chain_id: str
    before: DurableChainReplicationReport
    after: DurableChainReplicationReport
    transferred_items: int
    first_sequence: int | None
    last_sequence: int | None
    start_root: str
    end_root: str

    def __post_init__(self) -> None:
        if self.before.chain_id != self.chain_id:
            raise ValueError("batch before chain_id mismatch")
        if self.after.chain_id != self.chain_id:
            raise ValueError("batch after chain_id mismatch")
        if (
            isinstance(self.transferred_items, bool)
            or not isinstance(self.transferred_items, int)
            or self.transferred_items < 0
        ):
            raise ValueError(
                "transferred_items must be non-negative integer"
            )
        if self.transferred_items == 0:
            if (
                self.first_sequence is not None
                or self.last_sequence is not None
            ):
                raise ValueError(
                    "empty replication batch may not bind sequences"
                )
        else:
            if (
                self.first_sequence is None
                or self.last_sequence is None
                or self.last_sequence < self.first_sequence
                or (
                    self.last_sequence
                    - self.first_sequence
                    + 1
                    != self.transferred_items
                )
            ):
                raise ValueError(
                    "replication batch sequence range mismatch"
                )
        for name in ("start_root", "end_root"):
            value = getattr(self, name)
            if value and len(value) != 64:
                raise ValueError(
                    f"{name} must be SHA-256 hex"
                )

    @property
    def completed(self) -> bool:
        return self.after.in_sync

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data = {
            "chain_id": self.chain_id,
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "transferred_items": self.transferred_items,
            "first_sequence": self.first_sequence,
            "last_sequence": self.last_sequence,
            "start_root": self.start_root,
            "end_root": self.end_root,
            "completed": self.completed,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableReplicationRun:
    chain_id: str
    initial: DurableChainReplicationReport
    final: DurableChainReplicationReport
    batches: tuple[DurableReplicationBatch, ...]
    max_batches: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "batches", tuple(self.batches))
        if (
            self.initial.chain_id != self.chain_id
            or self.final.chain_id != self.chain_id
            or any(
                batch.chain_id != self.chain_id
                for batch in self.batches
            )
        ):
            raise ValueError(
                "replication run chain_id mismatch"
            )
        if (
            isinstance(self.max_batches, bool)
            or not isinstance(self.max_batches, int)
            or self.max_batches <= 0
        ):
            raise ValueError(
                "max_batches must be positive integer"
            )
        if len(self.batches) > self.max_batches:
            raise ValueError(
                "replication run exceeds max_batches"
            )

    @property
    def transferred_items(self) -> int:
        return sum(
            batch.transferred_items
            for batch in self.batches
        )

    @property
    def completed(self) -> bool:
        return self.final.in_sync

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data = {
            "chain_id": self.chain_id,
            "initial": self.initial.to_dict(),
            "final": self.final.to_dict(),
            "batches": [
                batch.to_dict()
                for batch in self.batches
            ],
            "max_batches": self.max_batches,
            "transferred_items": self.transferred_items,
            "completed": self.completed,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableReplicationError(RuntimeError):
    pass


class DurableChainReplicator:
    """Inspect and incrementally replicate one immutable evidence chain."""

    REQUIRED_SOURCE_METHODS = (
        "head",
        "verify",
        "root_for_sequence",
        "snapshot_segment",
    )
    REQUIRED_TARGET_METHODS = (
        "head",
        "verify",
        "root_for_sequence",
        "restore_segment",
    )

    def __init__(
        self,
        chain_id: str,
        source,
        target,
        *,
        policy: DurableReplicationPolicy | None = None,
    ) -> None:
        if not chain_id or len(chain_id) > 128:
            raise ValueError("invalid replication chain_id")
        self.chain_id = chain_id
        self.source = source
        self.target = target
        self.policy = (
            policy or DurableReplicationPolicy()
        )
        self._require_surface(
            source,
            self.REQUIRED_SOURCE_METHODS,
            "source",
        )
        self._require_surface(
            target,
            self.REQUIRED_TARGET_METHODS,
            "target",
        )

    @staticmethod
    def _require_surface(
        value,
        methods: tuple[str, ...],
        label: str,
    ) -> None:
        missing = tuple(
            method
            for method in methods
            if not callable(
                getattr(value, method, None)
            )
        )
        if missing:
            raise TypeError(
                f"{label} replication chain is missing "
                + ", ".join(missing)
            )

    @staticmethod
    def _head(chain) -> tuple[int, str]:
        head = chain.head()
        sequence = getattr(
            head,
            "sequence",
            None,
        )
        root_hash = getattr(
            head,
            "root_hash",
            None,
        )
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 0
            or not isinstance(root_hash, str)
            or len(root_hash) != 64
        ):
            raise DurableReplicationError(
                "replication chain returned invalid head"
            )
        return sequence, root_hash

    @staticmethod
    def _integrity(chain) -> bool:
        try:
            return bool(chain.verify())
        except Exception:
            return False

    def _report(
        self,
        *,
        state: DurableReplicaState,
        source_sequence: int,
        source_root: str,
        target_sequence: int,
        target_root: str,
        source_valid: bool,
        target_valid: bool,
        next_sequence: int | None = None,
        next_root: str = "",
        reason: str = "",
    ) -> DurableChainReplicationReport:
        return DurableChainReplicationReport(
            self.chain_id,
            state,
            source_sequence,
            source_root,
            target_sequence,
            target_root,
            abs(source_sequence - target_sequence),
            source_valid,
            target_valid,
            next_sequence,
            next_root,
            reason,
            self.policy.digest,
        )

    def inspect(self) -> DurableChainReplicationReport:
        try:
            source_sequence, source_root = self._head(
                self.source
            )
        except Exception as exc:
            return self._report(
                state=DurableReplicaState.SOURCE_INVALID,
                source_sequence=0,
                source_root="0" * 64,
                target_sequence=0,
                target_root="0" * 64,
                source_valid=False,
                target_valid=False,
                reason=(
                    "source head inspection failed: "
                    f"{type(exc).__name__}"
                ),
            )
        try:
            target_sequence, target_root = self._head(
                self.target
            )
        except Exception as exc:
            return self._report(
                state=DurableReplicaState.TARGET_INVALID,
                source_sequence=source_sequence,
                source_root=source_root,
                target_sequence=0,
                target_root="0" * 64,
                source_valid=self._integrity(self.source),
                target_valid=False,
                reason=(
                    "target head inspection failed: "
                    f"{type(exc).__name__}"
                ),
            )

        source_valid = self._integrity(self.source)
        target_valid = self._integrity(self.target)
        if (
            self.policy.require_source_integrity
            and not source_valid
        ):
            return self._report(
                state=DurableReplicaState.SOURCE_INVALID,
                source_sequence=source_sequence,
                source_root=source_root,
                target_sequence=target_sequence,
                target_root=target_root,
                source_valid=False,
                target_valid=target_valid,
                reason="source chain failed integrity verification",
            )
        if (
            self.policy.require_target_integrity
            and not target_valid
        ):
            return self._report(
                state=DurableReplicaState.TARGET_INVALID,
                source_sequence=source_sequence,
                source_root=source_root,
                target_sequence=target_sequence,
                target_root=target_root,
                source_valid=source_valid,
                target_valid=False,
                reason="target chain failed integrity verification",
            )

        if source_sequence == target_sequence:
            if source_root == target_root:
                return self._report(
                    state=DurableReplicaState.IN_SYNC,
                    source_sequence=source_sequence,
                    source_root=source_root,
                    target_sequence=target_sequence,
                    target_root=target_root,
                    source_valid=source_valid,
                    target_valid=target_valid,
                )
            return self._report(
                state=DurableReplicaState.DIVERGED,
                source_sequence=source_sequence,
                source_root=source_root,
                target_sequence=target_sequence,
                target_root=target_root,
                source_valid=source_valid,
                target_valid=target_valid,
                reason="equal sequence has different roots",
            )

        if target_sequence < source_sequence:
            try:
                expected_target_root = (
                    self.source.root_for_sequence(
                        target_sequence
                    )
                )
            except Exception as exc:
                return self._report(
                    state=DurableReplicaState.HISTORY_UNAVAILABLE,
                    source_sequence=source_sequence,
                    source_root=source_root,
                    target_sequence=target_sequence,
                    target_root=target_root,
                    source_valid=source_valid,
                    target_valid=target_valid,
                    reason=(
                        "source cannot resolve target sequence: "
                        f"{type(exc).__name__}"
                    ),
                )
            if expected_target_root != target_root:
                return self._report(
                    state=DurableReplicaState.DIVERGED,
                    source_sequence=source_sequence,
                    source_root=source_root,
                    target_sequence=target_sequence,
                    target_root=target_root,
                    source_valid=source_valid,
                    target_valid=target_valid,
                    reason=(
                        "target root differs from source root "
                        "at target sequence"
                    ),
                )
            next_sequence = target_sequence + 1
            try:
                next_root = self.source.root_for_sequence(
                    next_sequence
                )
                self.source.snapshot_segment(
                    target_root,
                    next_root,
                    max_items=1,
                )
            except Exception as exc:
                return self._report(
                    state=DurableReplicaState.HISTORY_UNAVAILABLE,
                    source_sequence=source_sequence,
                    source_root=source_root,
                    target_sequence=target_sequence,
                    target_root=target_root,
                    source_valid=source_valid,
                    target_valid=target_valid,
                    next_sequence=next_sequence,
                    reason=(
                        "source cannot serve next replication item: "
                        f"{type(exc).__name__}"
                    ),
                )
            return self._report(
                state=DurableReplicaState.LAGGING,
                source_sequence=source_sequence,
                source_root=source_root,
                target_sequence=target_sequence,
                target_root=target_root,
                source_valid=source_valid,
                target_valid=target_valid,
                next_sequence=next_sequence,
                next_root=next_root,
            )

        try:
            expected_source_root = (
                self.target.root_for_sequence(
                    source_sequence
                )
            )
        except Exception as exc:
            return self._report(
                state=DurableReplicaState.TARGET_AHEAD,
                source_sequence=source_sequence,
                source_root=source_root,
                target_sequence=target_sequence,
                target_root=target_root,
                source_valid=source_valid,
                target_valid=target_valid,
                reason=(
                    "target is ahead and source prefix "
                    "cannot be resolved on target: "
                    f"{type(exc).__name__}"
                ),
            )
        if expected_source_root == source_root:
            return self._report(
                state=DurableReplicaState.TARGET_AHEAD,
                source_sequence=source_sequence,
                source_root=source_root,
                target_sequence=target_sequence,
                target_root=target_root,
                source_valid=source_valid,
                target_valid=target_valid,
                reason="target contains source as an exact prefix",
            )
        return self._report(
            state=DurableReplicaState.DIVERGED,
            source_sequence=source_sequence,
            source_root=source_root,
            target_sequence=target_sequence,
            target_root=target_root,
            source_valid=source_valid,
            target_valid=target_valid,
            reason="source root is not the target prefix at source sequence",
        )

    def sync_once(self) -> DurableReplicationBatch:
        before = self.inspect()
        if before.in_sync:
            return DurableReplicationBatch(
                self.chain_id,
                before,
                before,
                0,
                None,
                None,
                before.target_root,
                before.target_root,
            )
        if not before.syncable:
            raise DurableReplicationError(
                "replication is not syncable: "
                f"{before.state.value}: {before.reason}"
            )

        end_sequence = min(
            before.source_sequence,
            before.target_sequence
            + self.policy.max_batch_items,
        )
        try:
            end_root = self.source.root_for_sequence(
                end_sequence
            )
            values = self.source.snapshot_segment(
                before.target_root,
                end_root,
                max_items=self.policy.max_batch_items,
            )
        except Exception as exc:
            raise DurableReplicationError(
                "source segment read failed: "
                f"{type(exc).__name__}"
            ) from exc

        expected_count = (
            end_sequence - before.target_sequence
        )
        if len(values) != expected_count:
            raise DurableReplicationError(
                "source segment length differs from requested range"
            )
        if not values:
            raise DurableReplicationError(
                "lagging replication produced empty source segment"
            )

        try:
            self.target.restore_segment(
                values,
                max_items=self.policy.max_batch_items,
            )
        except Exception as exc:
            raise DurableReplicationError(
                "target segment restore failed: "
                f"{type(exc).__name__}"
            ) from exc

        after = self.inspect()
        if after.target_sequence < end_sequence:
            raise DurableReplicationError(
                "target did not advance through restored batch"
            )
        try:
            target_end_root = (
                self.target.root_for_sequence(
                    end_sequence
                )
            )
        except Exception as exc:
            raise DurableReplicationError(
                "target cannot resolve restored batch root"
            ) from exc
        if target_end_root != end_root:
            raise DurableReplicationError(
                "target restored batch root differs from source"
            )

        return DurableReplicationBatch(
            self.chain_id,
            before,
            after,
            len(values),
            before.target_sequence + 1,
            end_sequence,
            before.target_root,
            end_root,
        )

    def sync(
        self,
        *,
        max_batches: int | None = None,
    ) -> DurableReplicationRun:
        limit = (
            self.policy.max_batches_per_run
            if max_batches is None
            else max_batches
        )
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit <= 0
            or limit > 4096
        ):
            raise ValueError(
                "max_batches outside supported range"
            )
        initial = self.inspect()
        current = initial
        batches: list[DurableReplicationBatch] = []
        for _ in range(limit):
            if current.in_sync:
                break
            if not current.syncable:
                break
            batch = self.sync_once()
            batches.append(batch)
            current = batch.after
        final = self.inspect()
        return DurableReplicationRun(
            self.chain_id,
            initial,
            final,
            tuple(batches),
            limit,
        )

    def require_in_sync(
        self,
    ) -> DurableChainReplicationReport:
        report = self.inspect()
        if not report.in_sync:
            raise DurableReplicationError(
                "replica is not in sync: "
                f"{report.state.value}: {report.reason}"
            )
        return report


@dataclass(frozen=True)
class DurableEvidenceReplicationReport:
    journal: DurableChainReplicationReport
    receipts: DurableChainReplicationReport
    policy_digest: str

    def __post_init__(self) -> None:
        if len(self.policy_digest) != 64:
            raise ValueError(
                "policy_digest must be SHA-256 hex"
            )

    @property
    def in_sync(self) -> bool:
        return (
            self.journal.in_sync
            and self.receipts.in_sync
        )

    @property
    def promotion_ready(self) -> bool:
        return (
            self.in_sync
            and self.journal.source_valid
            and self.journal.target_valid
            and self.receipts.source_valid
            and self.receipts.target_valid
        )

    @property
    def max_lag_items(self) -> int:
        return max(
            self.journal.lag_items,
            self.receipts.lag_items,
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data = {
            "journal": self.journal.to_dict(),
            "receipts": self.receipts.to_dict(),
            "policy_digest": self.policy_digest,
            "in_sync": self.in_sync,
            "promotion_ready": self.promotion_ready,
            "max_lag_items": self.max_lag_items,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableEvidenceReplicationRun:
    journal: DurableReplicationRun
    receipts: DurableReplicationRun
    final: DurableEvidenceReplicationReport

    @property
    def transferred_items(self) -> int:
        return (
            self.journal.transferred_items
            + self.receipts.transferred_items
        )

    @property
    def completed(self) -> bool:
        return self.final.in_sync

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data = {
            "journal": self.journal.to_dict(),
            "receipts": self.receipts.to_dict(),
            "final": self.final.to_dict(),
            "transferred_items": self.transferred_items,
            "completed": self.completed,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableEvidenceReplicaManager:
    """Coordinate journal and receipt replication as one promotion unit."""

    def __init__(
        self,
        journal: DurableChainReplicator,
        receipts: DurableChainReplicator,
        *,
        policy: DurableReplicationPolicy | None = None,
    ) -> None:
        if not isinstance(
            journal,
            DurableChainReplicator,
        ):
            raise TypeError(
                "journal must be DurableChainReplicator"
            )
        if not isinstance(
            receipts,
            DurableChainReplicator,
        ):
            raise TypeError(
                "receipts must be DurableChainReplicator"
            )
        self.journal = journal
        self.receipts = receipts
        self.policy = (
            policy or journal.policy
        )

    def inspect(
        self,
    ) -> DurableEvidenceReplicationReport:
        return DurableEvidenceReplicationReport(
            self.journal.inspect(),
            self.receipts.inspect(),
            self.policy.digest,
        )

    def sync(
        self,
        *,
        max_batches: int | None = None,
    ) -> DurableEvidenceReplicationRun:
        journal_run = self.journal.sync(
            max_batches=max_batches
        )
        receipt_run = self.receipts.sync(
            max_batches=max_batches
        )
        return DurableEvidenceReplicationRun(
            journal_run,
            receipt_run,
            self.inspect(),
        )

    def require_promotion_ready(
        self,
    ) -> DurableEvidenceReplicationReport:
        report = self.inspect()
        if not report.promotion_ready:
            raise DurableReplicationError(
                "durable replica is not promotion ready"
            )
        if (
            report.max_lag_items
            > self.policy.promotion_max_lag_items
        ):
            raise DurableReplicationError(
                "durable replica lag exceeds promotion policy"
            )
        return report
