"""Bounded repair workflow for durable archive lookup metadata.

Durable archive records, signed manifests, archived node payloads, and signed
checkpoint authority are canonical evidence. Root indexes and per-chain archive
heads are derived lookup metadata. Missing derived metadata can be rebuilt from
a verified archive, but conflicting mappings must never be overwritten
automatically.

Repair plans bind the exact archive-index health and policy observed during
inspection. Apply rechecks health before mutation, treats concurrently completed
repair as idempotent success, and marks changed-but-still-degraded state stale.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable, Iterable

from skeleton.shells.ai.durable_archive_store import (
    DurableArchiveIndexHealth,
    DurableArchiveIndexState,
    DurableArchiveRepository,
    DurableArchiveStoreError,
)


class ArchiveIndexRepairAction(str, Enum):
    NONE = "none"
    REPAIR_MISSING = "repair_missing"
    BLOCK_ARCHIVE = "block_archive"
    BLOCK_CORRUPT = "block_corrupt"
    BLOCK_LIMIT = "block_limit"


class ArchiveIndexRepairState(str, Enum):
    HEALTHY = "healthy"
    REPAIRED = "repaired"
    ALREADY_REPAIRED = "already_repaired"
    BLOCKED = "blocked"
    STALE = "stale"


@dataclass(frozen=True)
class ArchiveIndexRepairPolicy:
    auto_repair_missing: bool = True
    max_repairs_per_archive: int = 100_000
    max_archives_per_batch: int = 128

    def __post_init__(self) -> None:
        if not isinstance(
            self.auto_repair_missing,
            bool,
        ):
            raise ValueError(
                "auto_repair_missing must be bool"
            )
        for name, maximum in (
            ("max_repairs_per_archive", 1_000_000),
            ("max_archives_per_batch", 4096),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
                or value > maximum
            ):
                raise ValueError(
                    f"{name} outside supported range"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "auto_repair_missing": (
                self.auto_repair_missing
            ),
            "max_repairs_per_archive": (
                self.max_repairs_per_archive
            ),
            "max_archives_per_batch": (
                self.max_archives_per_batch
            ),
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
class ArchiveIndexRepairPlan:
    schema_version: int
    archive_id: str
    chain_id: str
    action: ArchiveIndexRepairAction
    health_digest: str
    policy_digest: str
    missing_root_indexes: tuple[str, ...]
    missing_replica_roots: tuple[str, ...]
    corrupt_root_indexes: tuple[str, ...]
    head_repair_required: bool
    max_repairs: int
    created_at: float
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported archive index repair plan schema"
            )
        for name, maximum in (
            ("archive_id", 160),
            ("chain_id", 128),
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or not value
                or len(value) > maximum
            ):
                raise ValueError(
                    f"invalid {name}"
                )
        object.__setattr__(
            self,
            "action",
            ArchiveIndexRepairAction(
                self.action
            ),
        )
        for name in (
            "health_digest",
            "policy_digest",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or len(value) != 64
            ):
                raise ValueError(
                    f"{name} must be 64-character digest"
                )
        for name in (
            "missing_root_indexes",
            "missing_replica_roots",
            "corrupt_root_indexes",
            "reasons",
        ):
            values = tuple(
                getattr(self, name)
            )
            if any(
                not isinstance(item, str)
                or not item
                or len(item) > 2048
                for item in values
            ):
                raise ValueError(
                    f"invalid {name}"
                )
            object.__setattr__(
                self,
                name,
                values,
            )
        if not isinstance(
            self.head_repair_required,
            bool,
        ):
            raise ValueError(
                "head_repair_required must be bool"
            )
        if (
            isinstance(self.max_repairs, bool)
            or not isinstance(self.max_repairs, int)
            or self.max_repairs <= 0
        ):
            raise ValueError(
                "max_repairs must be positive integer"
            )
        if (
            isinstance(self.created_at, bool)
            or not isinstance(self.created_at, (int, float))
            or not math.isfinite(
                float(self.created_at)
            )
            or float(self.created_at) < 0.0
        ):
            raise ValueError(
                "created_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "created_at",
            float(self.created_at),
        )
        if (
            self.repair_units
            > self.max_repairs
            and self.action
            is ArchiveIndexRepairAction.REPAIR_MISSING
        ):
            raise ValueError(
                "archive repair plan exceeds max_repairs"
            )
        if (
            self.corrupt_root_indexes
            and self.action
            is ArchiveIndexRepairAction.REPAIR_MISSING
        ):
            raise ValueError(
                "archive repair plan may not repair corruption"
            )

    @property
    def repair_units(self) -> int:
        return (
            len(self.missing_root_indexes)
            + len(self.missing_replica_roots)
            + int(self.head_repair_required)
        )

    @property
    def executable(self) -> bool:
        return (
            self.action
            is ArchiveIndexRepairAction.REPAIR_MISSING
        )

    @property
    def blocked(self) -> bool:
        return self.action in {
            ArchiveIndexRepairAction.BLOCK_ARCHIVE,
            ArchiveIndexRepairAction.BLOCK_CORRUPT,
            ArchiveIndexRepairAction.BLOCK_LIMIT,
        }

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            "archive_id": self.archive_id,
            "chain_id": self.chain_id,
            "action": self.action.value,
            "health_digest": self.health_digest,
            "policy_digest": self.policy_digest,
            "missing_root_indexes": list(
                self.missing_root_indexes
            ),
            "missing_replica_roots": list(
                self.missing_replica_roots
            ),
            "corrupt_root_indexes": list(
                self.corrupt_root_indexes
            ),
            "head_repair_required": (
                self.head_repair_required
            ),
            "repair_units": self.repair_units,
            "max_repairs": self.max_repairs,
            "created_at": self.created_at,
            "reasons": list(self.reasons),
            "executable": self.executable,
            "blocked": self.blocked,
        }
        if include_digest:
            data["digest"] = self.digest
        return data

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(
                include_digest=False
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ArchiveIndexRepairResult:
    archive_id: str
    chain_id: str
    state: ArchiveIndexRepairState
    action: ArchiveIndexRepairAction
    plan_digest: str
    before_health_digest: str
    after_health_digest: str
    repaired_root_or_replica_indexes: int
    repaired_units: int
    head_repaired: bool
    post_health: DurableArchiveIndexHealth
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        for name, maximum in (
            ("archive_id", 160),
            ("chain_id", 128),
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or not value
                or len(value) > maximum
            ):
                raise ValueError(
                    f"invalid {name}"
                )
        object.__setattr__(
            self,
            "state",
            ArchiveIndexRepairState(
                self.state
            ),
        )
        object.__setattr__(
            self,
            "action",
            ArchiveIndexRepairAction(
                self.action
            ),
        )
        for name in (
            "plan_digest",
            "before_health_digest",
            "after_health_digest",
        ):
            if len(getattr(self, name)) != 64:
                raise ValueError(
                    f"{name} must be 64-character digest"
                )
        for name in (
            "repaired_root_or_replica_indexes",
            "repaired_units",
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
        if not isinstance(
            self.head_repaired,
            bool,
        ):
            raise ValueError(
                "head_repaired must be bool"
            )
        if not isinstance(
            self.post_health,
            DurableArchiveIndexHealth,
        ):
            raise TypeError(
                "post_health must be DurableArchiveIndexHealth"
            )
        if (
            self.post_health.archive_id
            != self.archive_id
            or self.post_health.chain_id
            != self.chain_id
        ):
            raise ValueError(
                "post health identity differs from repair result"
            )
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )

    @property
    def ok(self) -> bool:
        return (
            self.state
            in {
                ArchiveIndexRepairState.HEALTHY,
                ArchiveIndexRepairState.REPAIRED,
                ArchiveIndexRepairState.ALREADY_REPAIRED,
            }
            and self.post_health.healthy
        )

    @property
    def mutated(self) -> bool:
        return (
            self.repaired_units > 0
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "archive_id": self.archive_id,
            "chain_id": self.chain_id,
            "state": self.state.value,
            "action": self.action.value,
            "plan_digest": self.plan_digest,
            "before_health_digest": (
                self.before_health_digest
            ),
            "after_health_digest": (
                self.after_health_digest
            ),
            "repaired_root_or_replica_indexes": (
                self.repaired_root_or_replica_indexes
            ),
            "repaired_units": self.repaired_units,
            "head_repaired": self.head_repaired,
            "ok": self.ok,
            "mutated": self.mutated,
            "post_health": (
                self.post_health.to_dict()
            ),
            "reasons": list(self.reasons),
        }
        if include_digest:
            data["digest"] = self.digest
        return data

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(
                include_digest=False
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ArchiveIndexRepairBatchReport:
    results: tuple[
        ArchiveIndexRepairResult,
        ...,
    ]
    policy_digest: str

    def __post_init__(self) -> None:
        results = tuple(
            self.results
        )
        ids = tuple(
            item.archive_id
            for item in results
        )
        if ids != tuple(sorted(ids)):
            raise ValueError(
                "archive repair results must be sorted by archive_id"
            )
        if len(ids) != len(set(ids)):
            raise ValueError(
                "duplicate archive repair archive_id"
            )
        object.__setattr__(
            self,
            "results",
            results,
        )
        if len(self.policy_digest) != 64:
            raise ValueError(
                "policy_digest must be 64-character digest"
            )

    @property
    def ok(self) -> bool:
        return all(
            result.ok
            for result in self.results
        )

    @property
    def repaired_units(self) -> int:
        return sum(
            result.repaired_units
            for result in self.results
        )

    @property
    def blocked(self) -> int:
        return sum(
            result.state
            is ArchiveIndexRepairState.BLOCKED
            for result in self.results
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "ok": self.ok,
            "repaired_units": (
                self.repaired_units
            ),
            "blocked": self.blocked,
            "policy_digest": (
                self.policy_digest
            ),
            "results": [
                result.to_dict()
                for result in self.results
            ],
        }
        if include_digest:
            data["digest"] = self.digest
        return data

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(
                include_digest=False
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


class ArchiveIndexRepairError(RuntimeError):
    pass


class DurableArchiveIndexRepairCoordinator:
    """Plan and apply bounded archive lookup-metadata repair."""

    def __init__(
        self,
        archives: DurableArchiveRepository,
        policy: ArchiveIndexRepairPolicy | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(
            archives,
            DurableArchiveRepository,
        ):
            raise TypeError(
                "archives must be DurableArchiveRepository"
            )
        if not callable(clock):
            raise TypeError(
                "clock must be callable"
            )
        self.archives = archives
        self.policy = (
            policy
            or ArchiveIndexRepairPolicy()
        )
        if not isinstance(
            self.policy,
            ArchiveIndexRepairPolicy,
        ):
            raise TypeError(
                "policy must be ArchiveIndexRepairPolicy"
            )
        self._clock = clock

    def _now(self) -> float:
        value = self._clock()
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(
                float(value)
            )
            or float(value) < 0.0
        ):
            raise ArchiveIndexRepairError(
                "archive repair clock returned invalid time"
            )
        return float(value)

    def inspect(
        self,
        archive_id: str,
    ) -> ArchiveIndexRepairPlan:
        # Validate temporal authority before any archive lookup so an invalid
        # coordinator clock cannot be masked by a missing/corrupt archive.
        created_at = self._now()
        try:
            health = (
                self.archives
                .inspect_indexes(
                    archive_id
                )
            )
        except DurableArchiveStoreError as exc:
            raise ArchiveIndexRepairError(
                str(exc)
            ) from exc

        reasons: list[str] = []
        if not health.archive_valid:
            action = (
                ArchiveIndexRepairAction.BLOCK_ARCHIVE
            )
            reasons.append(
                "archive failed canonical verification"
            )
        elif (
            health.corrupt_root_indexes
            or not health.head_valid
        ):
            action = (
                ArchiveIndexRepairAction.BLOCK_CORRUPT
            )
            reasons.append(
                "archive lookup metadata conflicts with canonical archive"
            )
        elif health.missing == 0:
            action = (
                ArchiveIndexRepairAction.NONE
            )
        elif (
            health.missing
            > self.policy.max_repairs_per_archive
        ):
            action = (
                ArchiveIndexRepairAction.BLOCK_LIMIT
            )
            reasons.append(
                "archive lookup repair exceeds policy bound"
            )
        elif not self.policy.auto_repair_missing:
            action = (
                ArchiveIndexRepairAction.NONE
            )
            reasons.append(
                "automatic archive index repair is disabled"
            )
        else:
            action = (
                ArchiveIndexRepairAction.REPAIR_MISSING
            )
            reasons.append(
                "missing archive lookup metadata can be rebuilt from verified archive"
            )

        return ArchiveIndexRepairPlan(
            1,
            archive_id,
            health.chain_id,
            action,
            health.digest,
            self.policy.digest,
            health.missing_root_indexes,
            health.missing_replica_roots,
            health.corrupt_root_indexes,
            health.head_repair_required,
            self.policy.max_repairs_per_archive,
            created_at,
            tuple(reasons),
        )

    def apply(
        self,
        plan: ArchiveIndexRepairPlan,
    ) -> ArchiveIndexRepairResult:
        if not isinstance(
            plan,
            ArchiveIndexRepairPlan,
        ):
            raise TypeError(
                "plan must be ArchiveIndexRepairPlan"
            )
        if (
            plan.policy_digest
            != self.policy.digest
        ):
            raise ArchiveIndexRepairError(
                "archive repair plan policy differs from active policy"
            )
        try:
            current = (
                self.archives
                .inspect_indexes(
                    plan.archive_id
                )
            )
        except DurableArchiveStoreError as exc:
            raise ArchiveIndexRepairError(
                str(exc)
            ) from exc
        if current.chain_id != plan.chain_id:
            raise ArchiveIndexRepairError(
                "archive repair chain identity changed"
            )
        if current.healthy:
            state = (
                ArchiveIndexRepairState.HEALTHY
                if plan.action
                is ArchiveIndexRepairAction.NONE
                else ArchiveIndexRepairState.ALREADY_REPAIRED
            )
            return ArchiveIndexRepairResult(
                plan.archive_id,
                plan.chain_id,
                state,
                plan.action,
                plan.digest,
                plan.health_digest,
                current.digest,
                0,
                0,
                False,
                current,
                (
                    "archive indexes are already healthy",
                ),
            )
        if current.digest != plan.health_digest:
            return ArchiveIndexRepairResult(
                plan.archive_id,
                plan.chain_id,
                ArchiveIndexRepairState.STALE,
                plan.action,
                plan.digest,
                plan.health_digest,
                current.digest,
                0,
                0,
                False,
                current,
                (
                    "archive repair plan is stale; live health changed",
                ),
            )
        if plan.blocked:
            return ArchiveIndexRepairResult(
                plan.archive_id,
                plan.chain_id,
                ArchiveIndexRepairState.BLOCKED,
                plan.action,
                plan.digest,
                plan.health_digest,
                current.digest,
                0,
                0,
                False,
                current,
                plan.reasons,
            )
        if (
            plan.action
            is ArchiveIndexRepairAction.NONE
        ):
            return ArchiveIndexRepairResult(
                plan.archive_id,
                plan.chain_id,
                ArchiveIndexRepairState.BLOCKED,
                plan.action,
                plan.digest,
                plan.health_digest,
                current.digest,
                0,
                0,
                False,
                current,
                (
                    "archive repair plan does not authorize mutation",
                ),
            )

        before_missing = current.missing
        before_head = (
            current.head_repair_required
        )
        try:
            index_mutations = (
                self.archives
                .repair_indexes(
                    plan.archive_id
                )
            )
        except DurableArchiveStoreError as exc:
            raise ArchiveIndexRepairError(
                str(exc)
            ) from exc
        after = (
            self.archives
            .inspect_indexes(
                plan.archive_id
            )
        )
        if not after.healthy:
            raise ArchiveIndexRepairError(
                "archive repair did not restore healthy lookup metadata"
            )
        repaired_units = (
            before_missing
            - after.missing
        )
        if repaired_units < 0:
            raise ArchiveIndexRepairError(
                "archive repair increased missing metadata"
            )
        return ArchiveIndexRepairResult(
            plan.archive_id,
            plan.chain_id,
            ArchiveIndexRepairState.REPAIRED,
            plan.action,
            plan.digest,
            plan.health_digest,
            after.digest,
            index_mutations,
            repaired_units,
            before_head
            and not after.head_repair_required,
            after,
            (
                f"repaired {repaired_units} archive lookup metadata unit(s)",
            ),
        )

    def repair(
        self,
        archive_id: str,
    ) -> ArchiveIndexRepairResult:
        return self.apply(
            self.inspect(
                archive_id
            )
        )

    def repair_batch(
        self,
        archive_ids: Iterable[str],
    ) -> ArchiveIndexRepairBatchReport:
        ids = tuple(
            archive_ids
        )
        if not ids:
            raise ValueError(
                "at least one archive_id is required"
            )
        if (
            len(ids)
            > self.policy.max_archives_per_batch
        ):
            raise ArchiveIndexRepairError(
                "archive repair batch exceeds policy bound"
            )
        if any(
            not isinstance(item, str)
            or not item
            or len(item) > 160
            for item in ids
        ):
            raise ValueError(
                "invalid archive_id"
            )
        if len(ids) != len(set(ids)):
            raise ValueError(
                "duplicate archive_id"
            )
        results = tuple(
            self.repair(
                archive_id
            )
            for archive_id in sorted(ids)
        )
        return ArchiveIndexRepairBatchReport(
            results,
            self.policy.digest,
        )
