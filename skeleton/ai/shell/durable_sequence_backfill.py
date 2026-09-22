"""Bounded, resumable orchestration for durable sequence-index backfill.

Sequence indexes are acceleration metadata only.  This controller never
changes journal/receipt authority and never grants execution authority.  It
pins an immutable historical anchor, advances backward in bounded batches,
supports restart from a digestible cursor, and schedules multiple chains in
round-robin order so one large history cannot monopolize a maintenance pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Mapping

from skeleton.shells.sequence_index import (
    SequenceIndexBackfillBatch,
    SequenceIndexBackfillableChain,
)


GENESIS_HASH = "0" * 64


def _chain_id(value: str) -> str:
    value = str(value).strip()
    if not value or len(value) > 128:
        raise ValueError("invalid sequence backfill chain_id")
    return value


def _digest(name: str, value: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be 64-character digest")
    return value.lower()


@dataclass(frozen=True)
class DurableSequenceBackfillPolicy:
    max_items_per_batch: int = 1024
    max_batches_per_chain: int = 128
    max_total_items: int = 100_000
    max_chains: int = 32
    continue_on_error: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_items_per_batch",
            "max_batches_per_chain",
            "max_total_items",
            "max_chains",
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
        if not isinstance(
            self.continue_on_error,
            bool,
        ):
            raise ValueError(
                "continue_on_error must be bool"
            )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "max_items_per_batch": self.max_items_per_batch,
            "max_batches_per_chain": self.max_batches_per_chain,
            "max_total_items": self.max_total_items,
            "max_chains": self.max_chains,
            "continue_on_error": self.continue_on_error,
        }


@dataclass(frozen=True)
class DurableSequenceBackfillCursor:
    chain_id: str
    anchor_sequence: int
    anchor_root: str
    next_sequence: int
    next_root: str
    batches_completed: int = 0
    items_processed: int = 0
    indexed: int = 0
    already_indexed: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "chain_id",
            _chain_id(self.chain_id),
        )
        for name in (
            "anchor_sequence",
            "next_sequence",
            "batches_completed",
            "items_processed",
            "indexed",
            "already_indexed",
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
        object.__setattr__(
            self,
            "anchor_root",
            _digest(
                "anchor_root",
                self.anchor_root,
            ),
        )
        object.__setattr__(
            self,
            "next_root",
            _digest(
                "next_root",
                self.next_root,
            ),
        )
        if self.next_sequence > self.anchor_sequence:
            raise ValueError(
                "backfill cursor next_sequence exceeds anchor"
            )
        if (
            self.anchor_sequence == 0
            and self.anchor_root != GENESIS_HASH
        ):
            raise ValueError(
                "zero anchor sequence must use genesis root"
            )
        if (
            self.anchor_sequence > 0
            and self.anchor_root == GENESIS_HASH
        ):
            raise ValueError(
                "nonzero anchor sequence may not use genesis root"
            )
        if (
            self.next_sequence == 0
            and self.next_root != GENESIS_HASH
        ):
            raise ValueError(
                "complete backfill cursor must use genesis next root"
            )
        if (
            self.next_sequence > 0
            and self.next_root == GENESIS_HASH
        ):
            raise ValueError(
                "incomplete backfill cursor may not use genesis next root"
            )
        if self.items_processed != (
            self.indexed + self.already_indexed
        ):
            raise ValueError(
                "backfill cursor item counters are inconsistent"
            )

    @property
    def complete(self) -> bool:
        return self.next_sequence == 0

    @property
    def progress_fraction(self) -> float:
        if self.anchor_sequence == 0:
            return 1.0
        return (
            self.anchor_sequence - self.next_sequence
        ) / self.anchor_sequence

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
        data: dict[str, object] = {
            "chain_id": self.chain_id,
            "anchor_sequence": self.anchor_sequence,
            "anchor_root": self.anchor_root,
            "next_sequence": self.next_sequence,
            "next_root": self.next_root,
            "batches_completed": self.batches_completed,
            "items_processed": self.items_processed,
            "indexed": self.indexed,
            "already_indexed": self.already_indexed,
            "complete": self.complete,
            "progress_fraction": self.progress_fraction,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableSequenceBackfillState(str, Enum):
    COMPLETE = "complete"
    PAUSED = "paused"
    ERROR = "error"


@dataclass(frozen=True)
class DurableSequenceBackfillStep:
    before: DurableSequenceBackfillCursor
    batch: SequenceIndexBackfillBatch
    after: DurableSequenceBackfillCursor

    def __post_init__(self) -> None:
        if self.before.chain_id != self.after.chain_id:
            raise ValueError(
                "sequence backfill step chain changed"
            )
        if (
            self.batch.requested_end_sequence
            != self.before.next_sequence
            or self.batch.requested_end_root
            != self.before.next_root
        ):
            raise ValueError(
                "sequence backfill batch does not match input cursor"
            )
        if (
            self.batch.next_sequence
            != self.after.next_sequence
            or self.batch.next_root
            != self.after.next_root
        ):
            raise ValueError(
                "sequence backfill batch does not match output cursor"
            )
        if self.after.batches_completed != (
            self.before.batches_completed + 1
        ):
            raise ValueError(
                "sequence backfill step batch counter mismatch"
            )
        if self.after.items_processed != (
            self.before.items_processed
            + self.batch.covered_items
        ):
            raise ValueError(
                "sequence backfill step item counter mismatch"
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
            "before": self.before.to_dict(),
            "batch": self.batch.to_dict(),
            "after": self.after.to_dict(),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableSequenceBackfillChainReport:
    chain_id: str
    state: DurableSequenceBackfillState
    cursor: DurableSequenceBackfillCursor
    batches_run: int
    items_processed_this_run: int
    indexed_this_run: int
    already_indexed_this_run: int
    error: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "chain_id",
            _chain_id(self.chain_id),
        )
        object.__setattr__(
            self,
            "state",
            DurableSequenceBackfillState(
                self.state
            ),
        )
        if self.cursor.chain_id != self.chain_id:
            raise ValueError(
                "sequence backfill report cursor chain mismatch"
            )
        for name in (
            "batches_run",
            "items_processed_this_run",
            "indexed_this_run",
            "already_indexed_this_run",
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
        if self.items_processed_this_run != (
            self.indexed_this_run
            + self.already_indexed_this_run
        ):
            raise ValueError(
                "sequence backfill report counters are inconsistent"
            )
        if len(self.error) > 2048:
            raise ValueError(
                "sequence backfill error too long"
            )
        if (
            self.state
            is DurableSequenceBackfillState.ERROR
        ) != bool(self.error):
            raise ValueError(
                "sequence backfill error/state mismatch"
            )
        if (
            self.state
            is DurableSequenceBackfillState.COMPLETE
            and not self.cursor.complete
        ):
            raise ValueError(
                "complete sequence backfill report has incomplete cursor"
            )

    @property
    def complete(self) -> bool:
        return (
            self.state
            is DurableSequenceBackfillState.COMPLETE
        )

    @property
    def ok(self) -> bool:
        return (
            self.state
            is not DurableSequenceBackfillState.ERROR
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
        data: dict[str, object] = {
            "chain_id": self.chain_id,
            "state": self.state.value,
            "complete": self.complete,
            "ok": self.ok,
            "cursor": self.cursor.to_dict(),
            "batches_run": self.batches_run,
            "items_processed_this_run": (
                self.items_processed_this_run
            ),
            "indexed_this_run": self.indexed_this_run,
            "already_indexed_this_run": (
                self.already_indexed_this_run
            ),
            "error": self.error,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableSequenceBackfillFleetReport:
    chains: tuple[
        DurableSequenceBackfillChainReport,
        ...
    ]
    policy_digest: str
    rounds: int
    total_items_processed: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "chains",
            tuple(self.chains),
        )
        if len(self.policy_digest) != 64:
            raise ValueError(
                "policy_digest must be SHA-256 shaped"
            )
        if (
            isinstance(self.rounds, bool)
            or not isinstance(self.rounds, int)
            or self.rounds < 0
        ):
            raise ValueError(
                "rounds must be non-negative integer"
            )
        if (
            isinstance(self.total_items_processed, bool)
            or not isinstance(
                self.total_items_processed,
                int,
            )
            or self.total_items_processed < 0
        ):
            raise ValueError(
                "total_items_processed must be non-negative integer"
            )
        ids = tuple(
            item.chain_id
            for item in self.chains
        )
        if len(ids) != len(set(ids)):
            raise ValueError(
                "duplicate sequence backfill chain report"
            )
        if self.total_items_processed != sum(
            item.items_processed_this_run
            for item in self.chains
        ):
            raise ValueError(
                "fleet backfill total differs from chain reports"
            )

    @property
    def complete(self) -> int:
        return sum(
            item.complete
            for item in self.chains
        )

    @property
    def paused(self) -> int:
        return sum(
            item.state
            is DurableSequenceBackfillState.PAUSED
            for item in self.chains
        )

    @property
    def errors(self) -> int:
        return sum(
            item.state
            is DurableSequenceBackfillState.ERROR
            for item in self.chains
        )

    @property
    def ok(self) -> bool:
        return (
            bool(self.chains)
            and self.errors == 0
        )

    @property
    def all_complete(self) -> bool:
        return (
            bool(self.chains)
            and self.complete == len(self.chains)
        )

    @property
    def cursors(
        self,
    ) -> dict[
        str,
        DurableSequenceBackfillCursor,
    ]:
        return {
            item.chain_id: item.cursor
            for item in self.chains
        }

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
        data: dict[str, object] = {
            "chains": [
                item.to_dict()
                for item in self.chains
            ],
            "policy_digest": self.policy_digest,
            "rounds": self.rounds,
            "total_items_processed": (
                self.total_items_processed
            ),
            "complete": self.complete,
            "paused": self.paused,
            "errors": self.errors,
            "ok": self.ok,
            "all_complete": self.all_complete,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableSequenceBackfillError(RuntimeError):
    pass


class DurableSequenceBackfillOperator:
    """Run fair, bounded backfill over one or more durable chains."""

    def __init__(
        self,
        policy: (
            DurableSequenceBackfillPolicy
            | None
        ) = None,
    ) -> None:
        self.policy = (
            policy
            or DurableSequenceBackfillPolicy()
        )
        if not isinstance(
            self.policy,
            DurableSequenceBackfillPolicy,
        ):
            raise TypeError(
                "policy must be DurableSequenceBackfillPolicy"
            )

    @staticmethod
    def _require_chain(chain: object) -> None:
        if not isinstance(
            chain,
            SequenceIndexBackfillableChain,
        ):
            raise TypeError(
                "chain must satisfy SequenceIndexBackfillableChain"
            )

    def begin(
        self,
        chain_id: str,
        chain: object,
    ) -> DurableSequenceBackfillCursor:
        chain_id = _chain_id(chain_id)
        self._require_chain(chain)
        head = chain.head()
        sequence = int(head.sequence)
        root = str(head.root_hash)
        if sequence < 0:
            raise DurableSequenceBackfillError(
                "chain head sequence is negative"
            )
        root = _digest("head_root", root)
        if sequence == 0:
            root = GENESIS_HASH
        return DurableSequenceBackfillCursor(
            chain_id,
            sequence,
            root,
            sequence,
            root,
        )

    def _require_cursor(
        self,
        chain_id: str,
        chain: object,
        cursor: DurableSequenceBackfillCursor,
    ) -> None:
        if not isinstance(
            cursor,
            DurableSequenceBackfillCursor,
        ):
            raise TypeError(
                "cursor must be DurableSequenceBackfillCursor"
            )
        if cursor.chain_id != chain_id:
            raise DurableSequenceBackfillError(
                "sequence backfill cursor chain mismatch"
            )
        if cursor.anchor_sequence == 0:
            return
        try:
            ancestor = bool(
                chain.root_is_ancestor(
                    cursor.anchor_root
                )
            )
        except Exception as exc:
            raise DurableSequenceBackfillError(
                "unable to verify backfill anchor ancestry"
            ) from exc
        if not ancestor:
            raise DurableSequenceBackfillError(
                "backfill anchor is no longer committed ancestor"
            )

    def step(
        self,
        chain_id: str,
        chain: object,
        cursor: DurableSequenceBackfillCursor,
        *,
        max_items: int | None = None,
    ) -> DurableSequenceBackfillStep | None:
        chain_id = _chain_id(chain_id)
        self._require_chain(chain)
        self._require_cursor(
            chain_id,
            chain,
            cursor,
        )
        if cursor.complete:
            return None
        budget = (
            self.policy.max_items_per_batch
            if max_items is None
            else max_items
        )
        if (
            isinstance(budget, bool)
            or not isinstance(budget, int)
            or budget <= 0
        ):
            raise ValueError(
                "max_items must be positive integer"
            )
        budget = min(
            budget,
            self.policy.max_items_per_batch,
        )
        batch = (
            chain.backfill_sequence_indexes_batch(
                end_sequence=cursor.next_sequence,
                end_root=cursor.next_root,
                max_items=budget,
            )
        )
        if not isinstance(
            batch,
            SequenceIndexBackfillBatch,
        ):
            raise DurableSequenceBackfillError(
                "chain returned invalid backfill batch type"
            )
        if (
            batch.requested_end_sequence
            != cursor.next_sequence
            or batch.requested_end_root
            != cursor.next_root
        ):
            raise DurableSequenceBackfillError(
                "chain backfill batch changed requested cursor"
            )
        if batch.covered_items <= 0:
            raise DurableSequenceBackfillError(
                "sequence backfill made no progress"
            )
        if batch.covered_items > budget:
            raise DurableSequenceBackfillError(
                "sequence backfill exceeded batch budget"
            )
        if batch.next_sequence >= cursor.next_sequence:
            raise DurableSequenceBackfillError(
                "sequence backfill cursor did not move backward"
            )

        after = DurableSequenceBackfillCursor(
            chain_id,
            cursor.anchor_sequence,
            cursor.anchor_root,
            batch.next_sequence,
            batch.next_root,
            cursor.batches_completed + 1,
            (
                cursor.items_processed
                + batch.covered_items
            ),
            cursor.indexed + batch.indexed,
            (
                cursor.already_indexed
                + batch.already_indexed
            ),
        )
        return DurableSequenceBackfillStep(
            cursor,
            batch,
            after,
        )

    def run(
        self,
        chains: Mapping[str, object],
        *,
        cursors: Mapping[
            str,
            DurableSequenceBackfillCursor,
        ] | None = None,
    ) -> DurableSequenceBackfillFleetReport:
        if not isinstance(chains, Mapping):
            raise TypeError(
                "chains must be a mapping"
            )
        if not chains:
            raise ValueError(
                "at least one chain is required"
            )
        if len(chains) > self.policy.max_chains:
            raise DurableSequenceBackfillError(
                "sequence backfill chain count exceeds policy"
            )
        cursor_input = dict(
            cursors or {}
        )
        unknown = set(cursor_input) - {
            _chain_id(item)
            for item in chains
        }
        if unknown:
            raise DurableSequenceBackfillError(
                "cursor supplied for unknown chain"
            )

        normalized: dict[str, object] = {}
        state: dict[
            str,
            DurableSequenceBackfillCursor,
        ] = {}
        run_batches: dict[str, int] = {}
        run_items: dict[str, int] = {}
        run_indexed: dict[str, int] = {}
        run_existing: dict[str, int] = {}
        errors: dict[str, str] = {}

        for raw_id, chain in chains.items():
            chain_id = _chain_id(raw_id)
            if chain_id in normalized:
                raise ValueError(
                    "duplicate normalized chain_id"
                )
            self._require_chain(chain)
            normalized[chain_id] = chain
            cursor = cursor_input.get(
                chain_id
            )
            if cursor is None:
                cursor = self.begin(
                    chain_id,
                    chain,
                )
            else:
                self._require_cursor(
                    chain_id,
                    chain,
                    cursor,
                )
            state[chain_id] = cursor
            run_batches[chain_id] = 0
            run_items[chain_id] = 0
            run_indexed[chain_id] = 0
            run_existing[chain_id] = 0

        active = [
            chain_id
            for chain_id in sorted(normalized)
            if not state[chain_id].complete
        ]
        rounds = 0
        total_items = 0

        while active and (
            total_items
            < self.policy.max_total_items
        ):
            rounds += 1
            progressed = False
            next_active: list[str] = []
            for chain_id in active:
                if chain_id in errors:
                    continue
                cursor = state[chain_id]
                if cursor.complete:
                    continue
                if (
                    run_batches[chain_id]
                    >= self.policy.max_batches_per_chain
                ):
                    next_active.append(
                        chain_id
                    )
                    continue
                remaining = (
                    self.policy.max_total_items
                    - total_items
                )
                if remaining <= 0:
                    next_active.append(
                        chain_id
                    )
                    continue
                budget = min(
                    self.policy.max_items_per_batch,
                    remaining,
                )
                try:
                    step = self.step(
                        chain_id,
                        normalized[chain_id],
                        cursor,
                        max_items=budget,
                    )
                except Exception as exc:
                    errors[chain_id] = (
                        f"{type(exc).__name__}: "
                        f"{str(exc)}"
                    )[:2048]
                    if (
                        not self.policy
                        .continue_on_error
                    ):
                        raise DurableSequenceBackfillError(
                            errors[chain_id]
                        ) from exc
                    continue
                if step is None:
                    state[chain_id] = cursor
                    continue
                state[chain_id] = step.after
                run_batches[chain_id] += 1
                run_items[chain_id] += (
                    step.batch.covered_items
                )
                run_indexed[chain_id] += (
                    step.batch.indexed
                )
                run_existing[chain_id] += (
                    step.batch.already_indexed
                )
                total_items += (
                    step.batch.covered_items
                )
                progressed = True
                if not step.after.complete:
                    next_active.append(
                        chain_id
                    )
            active = next_active
            if not progressed:
                break

        reports: list[
            DurableSequenceBackfillChainReport
        ] = []
        for chain_id in sorted(normalized):
            cursor = state[chain_id]
            if chain_id in errors:
                chain_state = (
                    DurableSequenceBackfillState.ERROR
                )
                error = errors[chain_id]
            elif cursor.complete:
                chain_state = (
                    DurableSequenceBackfillState.COMPLETE
                )
                error = ""
            else:
                chain_state = (
                    DurableSequenceBackfillState.PAUSED
                )
                error = ""
            reports.append(
                DurableSequenceBackfillChainReport(
                    chain_id,
                    chain_state,
                    cursor,
                    run_batches[chain_id],
                    run_items[chain_id],
                    run_indexed[chain_id],
                    run_existing[chain_id],
                    error,
                )
            )
        return DurableSequenceBackfillFleetReport(
            tuple(reports),
            self.policy.digest,
            rounds,
            total_items,
        )

    def require_complete(
        self,
        chains: Mapping[str, object],
        *,
        cursors: Mapping[
            str,
            DurableSequenceBackfillCursor,
        ] | None = None,
    ) -> DurableSequenceBackfillFleetReport:
        report = self.run(
            chains,
            cursors=cursors,
        )
        if not report.all_complete:
            if report.errors:
                details = ", ".join(
                    f"{item.chain_id}={item.error}"
                    for item in report.chains
                    if item.state
                    is DurableSequenceBackfillState.ERROR
                )
                raise DurableSequenceBackfillError(
                    "sequence backfill encountered errors"
                    + (
                        f": {details}"
                        if details
                        else ""
                    )
                )
            raise DurableSequenceBackfillError(
                "sequence backfill paused before completion"
            )
        return report
