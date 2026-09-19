"""Monotonic history for durable replica consensus.

A fleet can unanimously agree and still be wrong if every member was rolled
back to an older snapshot.  This module persists the accepted consensus lineage
per logical source and verifies every new head against the actual source-chain
ancestry before advancing the durable history head.

The store is CAS-backed and immutable-by-digest.  Losing writers may leave
unreachable candidate epochs, but only the head-linked lineage is authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.durable_replica_consensus import (
    DurableReplicaConsensusError,
    DurableReplicaConsensusReport,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


def _identity(
    name: str,
    value: str,
    *,
    max_length: int = 128,
) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be str")
    if not value or len(value) > max_length:
        raise ValueError(f"invalid {name}")
    return value


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be SHA-256 hex"
        ) from exc
    return value.lower()


def _stable_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class DurableReplicaConsensusEpoch:
    schema_version: int
    source_id: str
    generation: int
    previous_digest: str
    consensus_state_digest: str
    consensus_policy_digest: str
    fleet_state_digest: str
    fleet_policy_digest: str
    journal_sequence: int
    journal_root: str
    receipt_sequence: int
    receipt_root: str
    agreeing_targets: tuple[str, ...]
    agreeing_failure_domains: tuple[str, ...]
    recorded_at: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported replica consensus epoch schema"
            )
        object.__setattr__(
            self,
            "source_id",
            _identity(
                "source_id",
                self.source_id,
            ),
        )
        if (
            isinstance(self.generation, bool)
            or not isinstance(
                self.generation,
                int,
            )
            or self.generation <= 0
        ):
            raise ValueError(
                "consensus generation must be positive integer"
            )
        object.__setattr__(
            self,
            "previous_digest",
            _digest(
                "previous_digest",
                self.previous_digest,
                optional=True,
            ),
        )
        if (
            self.generation == 1
            and self.previous_digest
        ):
            raise ValueError(
                "first consensus epoch may not bind previous digest"
            )
        if (
            self.generation > 1
            and not self.previous_digest
        ):
            raise ValueError(
                "later consensus epoch requires previous digest"
            )
        for name in (
            "consensus_state_digest",
            "consensus_policy_digest",
            "fleet_state_digest",
            "fleet_policy_digest",
            "journal_root",
            "receipt_root",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        for name in (
            "journal_sequence",
            "receipt_sequence",
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
        for name in (
            "agreeing_targets",
            "agreeing_failure_domains",
        ):
            values = tuple(
                getattr(self, name)
            )
            if not values:
                raise ValueError(
                    f"{name} must not be empty"
                )
            if values != tuple(
                sorted(values)
            ):
                raise ValueError(
                    f"{name} must be sorted"
                )
            if len(values) != len(
                set(values)
            ):
                raise ValueError(
                    f"{name} must be unique"
                )
            object.__setattr__(
                self,
                name,
                values,
            )
        if (
            isinstance(self.recorded_at, bool)
            or not isinstance(
                self.recorded_at,
                (int, float),
            )
            or not math.isfinite(
                float(self.recorded_at)
            )
            or float(self.recorded_at) < 0.0
        ):
            raise ValueError(
                "recorded_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "recorded_at",
            float(self.recorded_at),
        )

    @property
    def head_digest(self) -> str:
        return _stable_digest(
            {
                "journal_sequence": (
                    self.journal_sequence
                ),
                "journal_root": self.journal_root,
                "receipt_sequence": (
                    self.receipt_sequence
                ),
                "receipt_root": self.receipt_root,
            }
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
            "source_id": self.source_id,
            "generation": self.generation,
            "previous_digest": (
                self.previous_digest
            ),
            "consensus_state_digest": (
                self.consensus_state_digest
            ),
            "consensus_policy_digest": (
                self.consensus_policy_digest
            ),
            "fleet_state_digest": (
                self.fleet_state_digest
            ),
            "fleet_policy_digest": (
                self.fleet_policy_digest
            ),
            "journal_sequence": (
                self.journal_sequence
            ),
            "journal_root": self.journal_root,
            "receipt_sequence": (
                self.receipt_sequence
            ),
            "receipt_root": self.receipt_root,
            "agreeing_targets": list(
                self.agreeing_targets
            ),
            "agreeing_failure_domains": list(
                self.agreeing_failure_domains
            ),
            "recorded_at": self.recorded_at,
            "head_digest": self.head_digest,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableReplicaConsensusHistoryHead:
    source_id: str
    generation: int
    epoch_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            _identity(
                "source_id",
                self.source_id,
            ),
        )
        if (
            isinstance(self.generation, bool)
            or not isinstance(
                self.generation,
                int,
            )
            or self.generation <= 0
        ):
            raise ValueError(
                "history head generation must be positive"
            )
        object.__setattr__(
            self,
            "epoch_digest",
            _digest(
                "epoch_digest",
                self.epoch_digest,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "generation": self.generation,
            "epoch_digest": self.epoch_digest,
        }


@dataclass(frozen=True)
class StoredDurableReplicaConsensusEpoch:
    revision: int
    epoch: DurableReplicaConsensusEpoch
    head_revision: int
    head: DurableReplicaConsensusHistoryHead

    def __post_init__(self) -> None:
        for name in (
            "revision",
            "head_revision",
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
        if self.head.source_id != self.epoch.source_id:
            raise ValueError(
                "stored consensus epoch/head source mismatch"
            )
        if self.head.generation < self.epoch.generation:
            raise ValueError(
                "stored consensus head precedes epoch"
            )

    @property
    def current(self) -> bool:
        return (
            self.head.generation
            == self.epoch.generation
            and self.head.epoch_digest
            == self.epoch.digest
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "epoch": self.epoch.to_dict(),
            "head_revision": self.head_revision,
            "head": self.head.to_dict(),
            "current": self.current,
        }


class DurableReplicaConsensusHistoryError(
    RuntimeError,
):
    pass


class DurableReplicaConsensusRollback(
    DurableReplicaConsensusHistoryError,
):
    pass


class DurableReplicaConsensusEquivocation(
    DurableReplicaConsensusHistoryError,
):
    pass


class DurableReplicaConsensusHistoryStore:
    """Persist and ancestry-check accepted replica consensus epochs."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = (
            "shell-ai-durable-replica-consensus-history"
        ),
        max_cas_retries: int = 32,
        max_lineage_epochs: int = 100_000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid consensus history namespace"
            )
        if (
            isinstance(max_cas_retries, bool)
            or not isinstance(
                max_cas_retries,
                int,
            )
            or not 1 <= max_cas_retries <= 128
        ):
            raise ValueError(
                "max_cas_retries outside supported range"
            )
        if (
            isinstance(max_lineage_epochs, bool)
            or not isinstance(
                max_lineage_epochs,
                int,
            )
            or not 1 <= max_lineage_epochs <= 1_000_000
        ):
            raise ValueError(
                "max_lineage_epochs outside supported range"
            )
        if not callable(clock):
            raise TypeError(
                "clock must be callable"
            )
        self.backend = backend
        self.namespace = namespace
        self.max_cas_retries = (
            max_cas_retries
        )
        self.max_lineage_epochs = (
            max_lineage_epochs
        )
        self._clock = clock

    @staticmethod
    def _source_key(
        source_id: str,
    ) -> str:
        source_id = _identity(
            "source_id",
            source_id,
        )
        return "head:" + hashlib.sha256(
            source_id.encode()
        ).hexdigest()

    @staticmethod
    def _epoch_key(
        epoch_digest: str,
    ) -> str:
        epoch_digest = _digest(
            "epoch_digest",
            epoch_digest,
        )
        return "epoch:" + epoch_digest

    @staticmethod
    def _require_chain_surface(
        chain,
        *,
        label: str,
    ) -> None:
        for method in (
            "head",
            "root_for_sequence",
        ):
            if not callable(
                getattr(
                    chain,
                    method,
                    None,
                )
            ):
                raise TypeError(
                    f"{label} chain is missing {method}"
                )

    @staticmethod
    def _chain_head(
        chain,
        *,
        label: str,
    ) -> tuple[int, str]:
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
            raise DurableReplicaConsensusHistoryError(
                f"{label} chain returned invalid head"
            )
        return sequence, root_hash

    @staticmethod
    def _root_at(
        chain,
        sequence: int,
        *,
        label: str,
    ) -> str:
        try:
            root_hash = chain.root_for_sequence(
                sequence
            )
        except Exception as exc:
            raise DurableReplicaConsensusHistoryError(
                f"{label} chain cannot resolve sequence {sequence}"
            ) from exc
        return _digest(
            f"{label}_root",
            root_hash,
        )

    def _verify_live_head(
        self,
        report: DurableReplicaConsensusReport,
        journal_chain,
        receipt_chain,
    ) -> None:
        selected = report.selected
        if (
            selected is None
            or not report.certifiable
        ):
            raise DurableReplicaConsensusError(
                "consensus report is not certifiable"
            )
        for chain, sequence, root_hash, label in (
            (
                journal_chain,
                selected.head.journal_sequence,
                selected.head.journal_root,
                "journal",
            ),
            (
                receipt_chain,
                selected.head.receipt_sequence,
                selected.head.receipt_root,
                "receipt",
            ),
        ):
            self._require_chain_surface(
                chain,
                label=label,
            )
            live_sequence, live_root = (
                self._chain_head(
                    chain,
                    label=label,
                )
            )
            if (
                live_sequence != sequence
                or live_root != root_hash
            ):
                raise DurableReplicaConsensusHistoryError(
                    f"{label} live head differs from consensus report"
                )
            resolved = self._root_at(
                chain,
                sequence,
                label=label,
            )
            if resolved != root_hash:
                raise DurableReplicaConsensusHistoryError(
                    f"{label} consensus root is not canonical at sequence"
                )

    def _current_head(
        self,
        source_id: str,
    ) -> tuple[
        int,
        DurableReplicaConsensusHistoryHead,
    ] | None:
        record = self.backend.get(
            self.namespace,
            self._source_key(
                source_id
            ),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableReplicaConsensusHistoryHead,
        ):
            raise DurableReplicaConsensusHistoryError(
                "consensus history head has invalid value type"
            )
        return (
            record.revision,
            record.value,
        )

    def get_epoch(
        self,
        epoch_digest: str,
    ) -> tuple[
        int,
        DurableReplicaConsensusEpoch,
    ] | None:
        record = self.backend.get(
            self.namespace,
            self._epoch_key(
                epoch_digest
            ),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableReplicaConsensusEpoch,
        ):
            raise DurableReplicaConsensusHistoryError(
                "consensus epoch has invalid value type"
            )
        if (
            record.value.digest
            != epoch_digest
        ):
            raise DurableReplicaConsensusHistoryError(
                "consensus epoch digest/key mismatch"
            )
        return (
            record.revision,
            record.value,
        )

    def current(
        self,
        source_id: str,
    ) -> StoredDurableReplicaConsensusEpoch | None:
        current = self._current_head(
            source_id
        )
        if current is None:
            return None
        head_revision, head = current
        stored = self.get_epoch(
            head.epoch_digest
        )
        if stored is None:
            raise DurableReplicaConsensusHistoryError(
                "consensus history head references missing epoch"
            )
        revision, epoch = stored
        if (
            epoch.source_id
            != head.source_id
            or epoch.generation
            != head.generation
        ):
            raise DurableReplicaConsensusHistoryError(
                "consensus history head/epoch mismatch"
            )
        return StoredDurableReplicaConsensusEpoch(
            revision,
            epoch,
            head_revision,
            head,
        )

    @staticmethod
    def _same_state(
        epoch: DurableReplicaConsensusEpoch,
        report: DurableReplicaConsensusReport,
    ) -> bool:
        selected = report.selected
        if selected is None:
            return False
        return (
            epoch.consensus_state_digest
            == report.state_digest
            and epoch.consensus_policy_digest
            == report.consensus_policy_digest
            and epoch.fleet_state_digest
            == report.fleet_state_digest
            and epoch.fleet_policy_digest
            == report.fleet_policy_digest
            and epoch.journal_sequence
            == selected.head.journal_sequence
            and epoch.journal_root
            == selected.head.journal_root
            and epoch.receipt_sequence
            == selected.head.receipt_sequence
            and epoch.receipt_root
            == selected.head.receipt_root
            and epoch.agreeing_targets
            == selected.target_ids
            and epoch.agreeing_failure_domains
            == selected.failure_domains
        )

    def _verify_transition(
        self,
        previous: DurableReplicaConsensusEpoch,
        report: DurableReplicaConsensusReport,
        journal_chain,
        receipt_chain,
    ) -> None:
        selected = report.selected
        if selected is None:
            raise DurableReplicaConsensusError(
                "consensus report has no selected head"
            )
        for (
            prior_sequence,
            prior_root,
            current_sequence,
            current_root,
            chain,
            label,
        ) in (
            (
                previous.journal_sequence,
                previous.journal_root,
                selected.head.journal_sequence,
                selected.head.journal_root,
                journal_chain,
                "journal",
            ),
            (
                previous.receipt_sequence,
                previous.receipt_root,
                selected.head.receipt_sequence,
                selected.head.receipt_root,
                receipt_chain,
                "receipt",
            ),
        ):
            if current_sequence < prior_sequence:
                raise DurableReplicaConsensusRollback(
                    f"{label} consensus sequence rolled back"
                )
            if (
                current_sequence == prior_sequence
                and current_root != prior_root
            ):
                raise DurableReplicaConsensusEquivocation(
                    f"{label} consensus root changed at same sequence"
                )
            resolved_prior = self._root_at(
                chain,
                prior_sequence,
                label=label,
            )
            if resolved_prior != prior_root:
                raise DurableReplicaConsensusEquivocation(
                    f"{label} source history no longer contains prior consensus root"
                )
            resolved_current = self._root_at(
                chain,
                current_sequence,
                label=label,
            )
            if resolved_current != current_root:
                raise DurableReplicaConsensusEquivocation(
                    f"{label} current consensus root is not canonical"
                )

    def _put_epoch(
        self,
        epoch: DurableReplicaConsensusEpoch,
    ) -> int:
        key = self._epoch_key(
            epoch.digest
        )
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is not None:
            if not isinstance(
                existing.value,
                DurableReplicaConsensusEpoch,
            ):
                raise DurableReplicaConsensusHistoryError(
                    "consensus epoch key has invalid value type"
                )
            if existing.value != epoch:
                raise DurableReplicaConsensusHistoryError(
                    "content-addressed consensus epoch collision"
                )
            return existing.revision
        try:
            stored = self.backend.put_if_absent(
                self.namespace,
                key,
                epoch,
            )
            return stored.revision
        except DistributedStateConflict:
            winner = self.backend.get(
                self.namespace,
                key,
            )
            if (
                winner is None
                or not isinstance(
                    winner.value,
                    DurableReplicaConsensusEpoch,
                )
                or winner.value != epoch
            ):
                raise
            return winner.revision

    def record(
        self,
        report: DurableReplicaConsensusReport,
        *,
        journal_chain,
        receipt_chain,
    ) -> StoredDurableReplicaConsensusEpoch:
        if not isinstance(
            report,
            DurableReplicaConsensusReport,
        ):
            raise TypeError(
                "report must be DurableReplicaConsensusReport"
            )
        if not report.certifiable:
            raise DurableReplicaConsensusError(
                "cannot record uncertifiable replica consensus"
            )
        selected = report.selected
        if selected is None:
            raise DurableReplicaConsensusError(
                "consensus report has no selected head"
            )
        self._verify_live_head(
            report,
            journal_chain,
            receipt_chain,
        )

        for _ in range(
            self.max_cas_retries
        ):
            current = self.current(
                report.source_id
            )
            if (
                current is not None
                and self._same_state(
                    current.epoch,
                    report,
                )
            ):
                return current

            if current is not None:
                self._verify_transition(
                    current.epoch,
                    report,
                    journal_chain,
                    receipt_chain,
                )
                generation = (
                    current.epoch.generation
                    + 1
                )
                previous_digest = (
                    current.epoch.digest
                )
                expected_head_revision = (
                    current.head_revision
                )
            else:
                generation = 1
                previous_digest = ""
                head_record = (
                    self._current_head(
                        report.source_id
                    )
                )
                if head_record is not None:
                    continue
                expected_head_revision = 0

            now = float(
                self._clock()
            )
            if (
                not math.isfinite(now)
                or now < 0.0
            ):
                raise DurableReplicaConsensusHistoryError(
                    "consensus history clock returned invalid time"
                )
            epoch = (
                DurableReplicaConsensusEpoch(
                    1,
                    report.source_id,
                    generation,
                    previous_digest,
                    report.state_digest,
                    report.consensus_policy_digest,
                    report.fleet_state_digest,
                    report.fleet_policy_digest,
                    selected.head.journal_sequence,
                    selected.head.journal_root,
                    selected.head.receipt_sequence,
                    selected.head.receipt_root,
                    selected.target_ids,
                    selected.failure_domains,
                    now,
                )
            )
            epoch_revision = (
                self._put_epoch(epoch)
            )
            head = (
                DurableReplicaConsensusHistoryHead(
                    report.source_id,
                    generation,
                    epoch.digest,
                )
            )
            try:
                stored_head = (
                    self.backend.compare_and_swap(
                        self.namespace,
                        self._source_key(
                            report.source_id
                        ),
                        expected_revision=(
                            expected_head_revision
                        ),
                        value=head,
                    )
                )
                return (
                    StoredDurableReplicaConsensusEpoch(
                        epoch_revision,
                        epoch,
                        stored_head.revision,
                        head,
                    )
                )
            except DistributedStateConflict:
                latest = self.current(
                    report.source_id
                )
                if (
                    latest is not None
                    and self._same_state(
                        latest.epoch,
                        report,
                    )
                ):
                    return latest
                continue

        raise DurableReplicaConsensusHistoryError(
            "consensus history CAS retry budget exhausted"
        )

    def lineage(
        self,
        source_id: str,
        *,
        max_epochs: int | None = None,
    ) -> tuple[
        DurableReplicaConsensusEpoch,
        ...,
    ]:
        limit = (
            self.max_lineage_epochs
            if max_epochs is None
            else max_epochs
        )
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit
            <= self.max_lineage_epochs
        ):
            raise ValueError(
                "max_epochs outside supported range"
            )
        current = self.current(
            source_id
        )
        if current is None:
            return ()
        reverse: list[
            DurableReplicaConsensusEpoch
        ] = []
        seen: set[str] = set()
        epoch = current.epoch
        while True:
            if epoch.digest in seen:
                raise DurableReplicaConsensusHistoryError(
                    "consensus history lineage contains cycle"
                )
            seen.add(
                epoch.digest
            )
            reverse.append(
                epoch
            )
            if len(reverse) > limit:
                raise DurableReplicaConsensusHistoryError(
                    "consensus history lineage exceeds bound"
                )
            if epoch.generation == 1:
                if epoch.previous_digest:
                    raise DurableReplicaConsensusHistoryError(
                        "first consensus epoch unexpectedly has parent"
                    )
                break
            if not epoch.previous_digest:
                raise DurableReplicaConsensusHistoryError(
                    "consensus history lineage is truncated"
                )
            previous = self.get_epoch(
                epoch.previous_digest
            )
            if previous is None:
                raise DurableReplicaConsensusHistoryError(
                    "consensus history parent epoch is missing"
                )
            _, parent = previous
            if (
                parent.source_id
                != epoch.source_id
                or parent.generation
                != epoch.generation - 1
            ):
                raise DurableReplicaConsensusHistoryError(
                    "consensus history generation linkage is invalid"
                )
            epoch = parent
        return tuple(
            reversed(reverse)
        )

    def verify(
        self,
        source_id: str,
        *,
        journal_chain,
        receipt_chain,
    ) -> bool:
        try:
            lineage = self.lineage(
                source_id
            )
            if not lineage:
                return True
            self._require_chain_surface(
                journal_chain,
                label="journal",
            )
            self._require_chain_surface(
                receipt_chain,
                label="receipt",
            )
            previous = None
            for expected_generation, epoch in enumerate(
                lineage,
                start=1,
            ):
                if (
                    epoch.generation
                    != expected_generation
                ):
                    return False
                if previous is not None:
                    if (
                        epoch.previous_digest
                        != previous.digest
                    ):
                        return False
                    if (
                        epoch.journal_sequence
                        < previous.journal_sequence
                        or epoch.receipt_sequence
                        < previous.receipt_sequence
                    ):
                        return False
                    if (
                        epoch.journal_sequence
                        == previous.journal_sequence
                        and epoch.journal_root
                        != previous.journal_root
                    ):
                        return False
                    if (
                        epoch.receipt_sequence
                        == previous.receipt_sequence
                        and epoch.receipt_root
                        != previous.receipt_root
                    ):
                        return False
                if (
                    self._root_at(
                        journal_chain,
                        epoch.journal_sequence,
                        label="journal",
                    )
                    != epoch.journal_root
                ):
                    return False
                if (
                    self._root_at(
                        receipt_chain,
                        epoch.receipt_sequence,
                        label="receipt",
                    )
                    != epoch.receipt_root
                ):
                    return False
                previous = epoch
            current = self.current(
                source_id
            )
            return (
                current is not None
                and current.epoch.digest
                == lineage[-1].digest
            )
        except Exception:
            return False

    def require_current(
        self,
        report: DurableReplicaConsensusReport,
        *,
        journal_chain,
        receipt_chain,
    ) -> StoredDurableReplicaConsensusEpoch:
        current = self.current(
            report.source_id
        )
        if current is None:
            raise DurableReplicaConsensusHistoryError(
                "replica consensus history is empty"
            )
        if not self._same_state(
            current.epoch,
            report,
        ):
            raise DurableReplicaConsensusHistoryError(
                "live replica consensus differs from durable history head"
            )
        if not self.verify(
            report.source_id,
            journal_chain=journal_chain,
            receipt_chain=receipt_chain,
        ):
            raise DurableReplicaConsensusHistoryError(
                "replica consensus history failed verification"
            )
        return current
