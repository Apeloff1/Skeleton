"""Bounded operator workflow for durable checkpoint-index repair.

Checkpoint lookup indexes are accelerators over the canonical append-only
checkpoint registry. Missing indexes are therefore repairable maintenance,
while malformed or conflicting indexes are integrity incidents and must never
be silently overwritten.

This module provides deterministic inspect/plan/apply semantics. A repair plan
binds the exact observed health and policy. Applying a stale plan fails closed
unless another worker has already completed the exact repair and the chain is
now healthy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable, Iterable

from skeleton.shells.ai.durable_checkpoint import (
    DurableChainCheckpointStore,
    DurableCheckpointError,
    DurableCheckpointIndexHealth,
    DurableCheckpointIndexState,
)


class CheckpointIndexRepairAction(str, Enum):
    NONE = "none"
    REPAIR_MISSING = "repair_missing"
    BLOCK_REGISTRY = "block_registry"
    BLOCK_CORRUPT = "block_corrupt"
    BLOCK_LIMIT = "block_limit"


class CheckpointIndexRepairState(str, Enum):
    HEALTHY = "healthy"
    PLANNED = "planned"
    REPAIRED = "repaired"
    ALREADY_REPAIRED = "already_repaired"
    BLOCKED = "blocked"
    STALE = "stale"


@dataclass(frozen=True)
class CheckpointIndexRepairPolicy:
    auto_repair_missing: bool = True
    max_repairs_per_chain: int = 4096
    max_chains_per_batch: int = 128
    require_registry_valid: bool = True

    def __post_init__(self) -> None:
        for name in (
            "auto_repair_missing",
            "require_registry_valid",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        for name, maximum in (
            ("max_repairs_per_chain", 100_000),
            ("max_chains_per_batch", 4096),
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
            "auto_repair_missing": self.auto_repair_missing,
            "max_repairs_per_chain": self.max_repairs_per_chain,
            "max_chains_per_batch": self.max_chains_per_batch,
            "require_registry_valid": self.require_registry_valid,
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
class CheckpointIndexRepairPlan:
    schema_version: int
    chain_id: str
    action: CheckpointIndexRepairAction
    health_digest: str
    policy_digest: str
    checkpoint_count: int
    missing_digest_indexes: tuple[str, ...]
    missing_root_indexes: tuple[str, ...]
    corrupt_indexes: tuple[str, ...]
    max_repairs: int
    created_at: float
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported checkpoint index repair plan schema"
            )
        if not self.chain_id or len(self.chain_id) > 128:
            raise ValueError(
                "invalid checkpoint index repair chain_id"
            )
        object.__setattr__(
            self,
            "action",
            CheckpointIndexRepairAction(
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
        if (
            isinstance(self.checkpoint_count, bool)
            or not isinstance(self.checkpoint_count, int)
            or self.checkpoint_count < 0
        ):
            raise ValueError(
                "checkpoint_count must be non-negative integer"
            )
        if (
            isinstance(self.max_repairs, bool)
            or not isinstance(self.max_repairs, int)
            or self.max_repairs <= 0
        ):
            raise ValueError(
                "max_repairs must be positive integer"
            )
        for name in (
            "missing_digest_indexes",
            "missing_root_indexes",
            "corrupt_indexes",
            "reasons",
        ):
            value = tuple(
                getattr(self, name)
            )
            if any(
                not isinstance(item, str)
                or not item
                or len(item) > 2048
                for item in value
            ):
                raise ValueError(
                    f"invalid {name}"
                )
            object.__setattr__(
                self,
                name,
                value,
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
            self.missing_count
            > self.max_repairs
            and self.action
            is CheckpointIndexRepairAction.REPAIR_MISSING
        ):
            raise ValueError(
                "repair plan exceeds max_repairs"
            )
        if (
            self.corrupt_indexes
            and self.action
            is CheckpointIndexRepairAction.REPAIR_MISSING
        ):
            raise ValueError(
                "repair plan may not auto-repair corrupt indexes"
            )

    @property
    def missing_count(self) -> int:
        return (
            len(self.missing_digest_indexes)
            + len(self.missing_root_indexes)
        )

    @property
    def executable(self) -> bool:
        return (
            self.action
            is CheckpointIndexRepairAction.REPAIR_MISSING
        )

    @property
    def blocked(self) -> bool:
        return self.action in {
            CheckpointIndexRepairAction.BLOCK_REGISTRY,
            CheckpointIndexRepairAction.BLOCK_CORRUPT,
            CheckpointIndexRepairAction.BLOCK_LIMIT,
        }

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            "chain_id": self.chain_id,
            "action": self.action.value,
            "health_digest": self.health_digest,
            "policy_digest": self.policy_digest,
            "checkpoint_count": self.checkpoint_count,
            "missing_digest_indexes": list(
                self.missing_digest_indexes
            ),
            "missing_root_indexes": list(
                self.missing_root_indexes
            ),
            "corrupt_indexes": list(
                self.corrupt_indexes
            ),
            "missing_count": self.missing_count,
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
class CheckpointIndexRepairResult:
    chain_id: str
    state: CheckpointIndexRepairState
    action: CheckpointIndexRepairAction
    plan_digest: str
    before_health_digest: str
    after_health_digest: str
    repaired: int
    requested_repairs: int
    post_health: DurableCheckpointIndexHealth
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.chain_id or len(self.chain_id) > 128:
            raise ValueError(
                "invalid checkpoint index repair result chain_id"
            )
        object.__setattr__(
            self,
            "state",
            CheckpointIndexRepairState(
                self.state
            ),
        )
        object.__setattr__(
            self,
            "action",
            CheckpointIndexRepairAction(
                self.action
            ),
        )
        for name in (
            "plan_digest",
            "before_health_digest",
            "after_health_digest",
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
            "repaired",
            "requested_repairs",
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
        if (
            self.repaired
            > self.requested_repairs
        ):
            raise ValueError(
                "repaired count exceeds requested repairs"
            )
        if not isinstance(
            self.post_health,
            DurableCheckpointIndexHealth,
        ):
            raise TypeError(
                "post_health must be DurableCheckpointIndexHealth"
            )
        if (
            self.post_health.chain_id
            != self.chain_id
        ):
            raise ValueError(
                "post_health chain differs from result"
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
                CheckpointIndexRepairState.HEALTHY,
                CheckpointIndexRepairState.REPAIRED,
                CheckpointIndexRepairState.ALREADY_REPAIRED,
            }
            and self.post_health.healthy
        )

    @property
    def mutated(self) -> bool:
        return self.repaired > 0

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
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
            "repaired": self.repaired,
            "requested_repairs": (
                self.requested_repairs
            ),
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
class CheckpointIndexRepairBatchReport:
    results: tuple[
        CheckpointIndexRepairResult,
        ...,
    ]
    policy_digest: str

    def __post_init__(self) -> None:
        values = tuple(
            self.results
        )
        ids = tuple(
            item.chain_id
            for item in values
        )
        if ids != tuple(sorted(ids)):
            raise ValueError(
                "repair batch results must be sorted by chain_id"
            )
        if len(ids) != len(set(ids)):
            raise ValueError(
                "duplicate repair batch chain_id"
            )
        object.__setattr__(
            self,
            "results",
            values,
        )
        if len(self.policy_digest) != 64:
            raise ValueError(
                "policy_digest must be 64-character digest"
            )

    @property
    def ok(self) -> bool:
        return all(
            item.ok
            for item in self.results
        )

    @property
    def repaired(self) -> int:
        return sum(
            item.repaired
            for item in self.results
        )

    @property
    def blocked(self) -> int:
        return sum(
            item.state
            is CheckpointIndexRepairState.BLOCKED
            for item in self.results
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "ok": self.ok,
            "repaired": self.repaired,
            "blocked": self.blocked,
            "policy_digest": self.policy_digest,
            "results": [
                item.to_dict()
                for item in self.results
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


class CheckpointIndexRepairError(RuntimeError):
    pass


class DurableCheckpointIndexRepairCoordinator:
    """Plan and apply missing-index repair without masking corruption."""

    def __init__(
        self,
        checkpoints: DurableChainCheckpointStore,
        policy: CheckpointIndexRepairPolicy | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(
            checkpoints,
            DurableChainCheckpointStore,
        ):
            raise TypeError(
                "checkpoints must be DurableChainCheckpointStore"
            )
        if not callable(clock):
            raise TypeError(
                "clock must be callable"
            )
        self.checkpoints = checkpoints
        self.policy = (
            policy
            or CheckpointIndexRepairPolicy()
        )
        if not isinstance(
            self.policy,
            CheckpointIndexRepairPolicy,
        ):
            raise TypeError(
                "policy must be CheckpointIndexRepairPolicy"
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
            raise CheckpointIndexRepairError(
                "repair clock returned invalid time"
            )
        return float(value)

    def inspect(
        self,
        chain_id: str,
    ) -> CheckpointIndexRepairPlan:
        health = (
            self.checkpoints
            .inspect_lookup_indexes(
                chain_id
            )
        )
        reasons: list[str] = []
        if not health.registry_valid:
            action = (
                CheckpointIndexRepairAction.BLOCK_REGISTRY
            )
            reasons.append(
                "canonical checkpoint registry failed integrity"
            )
        elif health.corrupt_indexes:
            action = (
                CheckpointIndexRepairAction.BLOCK_CORRUPT
            )
            reasons.append(
                "checkpoint index conflict requires manual review"
            )
        elif health.missing == 0:
            action = (
                CheckpointIndexRepairAction.NONE
            )
        elif (
            health.missing
            > self.policy.max_repairs_per_chain
        ):
            action = (
                CheckpointIndexRepairAction.BLOCK_LIMIT
            )
            reasons.append(
                "missing checkpoint indexes exceed repair policy bound"
            )
        elif not self.policy.auto_repair_missing:
            action = (
                CheckpointIndexRepairAction.NONE
            )
            reasons.append(
                "automatic missing-index repair is disabled"
            )
        else:
            action = (
                CheckpointIndexRepairAction.REPAIR_MISSING
            )
            reasons.append(
                "missing checkpoint indexes can be rebuilt from canonical registry"
            )

        return CheckpointIndexRepairPlan(
            1,
            chain_id,
            action,
            health.digest,
            self.policy.digest,
            health.checkpoint_count,
            health.missing_digest_indexes,
            health.missing_root_indexes,
            health.corrupt_indexes,
            self.policy.max_repairs_per_chain,
            self._now(),
            tuple(reasons),
        )

    def apply(
        self,
        plan: CheckpointIndexRepairPlan,
    ) -> CheckpointIndexRepairResult:
        if not isinstance(
            plan,
            CheckpointIndexRepairPlan,
        ):
            raise TypeError(
                "plan must be CheckpointIndexRepairPlan"
            )
        if (
            plan.policy_digest
            != self.policy.digest
        ):
            raise CheckpointIndexRepairError(
                "repair plan policy differs from active policy"
            )

        current = (
            self.checkpoints
            .inspect_lookup_indexes(
                plan.chain_id
            )
        )
        if current.healthy:
            state = (
                CheckpointIndexRepairState.HEALTHY
                if plan.action
                is CheckpointIndexRepairAction.NONE
                else CheckpointIndexRepairState.ALREADY_REPAIRED
            )
            return CheckpointIndexRepairResult(
                plan.chain_id,
                state,
                plan.action,
                plan.digest,
                plan.health_digest,
                current.digest,
                0,
                plan.missing_count,
                current,
                (
                    "checkpoint indexes are already healthy",
                ),
            )

        if current.digest != plan.health_digest:
            return CheckpointIndexRepairResult(
                plan.chain_id,
                CheckpointIndexRepairState.STALE,
                plan.action,
                plan.digest,
                plan.health_digest,
                current.digest,
                0,
                plan.missing_count,
                current,
                (
                    "repair plan is stale; live index health changed",
                ),
            )

        if plan.blocked:
            return CheckpointIndexRepairResult(
                plan.chain_id,
                CheckpointIndexRepairState.BLOCKED,
                plan.action,
                plan.digest,
                plan.health_digest,
                current.digest,
                0,
                plan.missing_count,
                current,
                plan.reasons,
            )

        if (
            plan.action
            is CheckpointIndexRepairAction.NONE
        ):
            return CheckpointIndexRepairResult(
                plan.chain_id,
                CheckpointIndexRepairState.BLOCKED,
                plan.action,
                plan.digest,
                plan.health_digest,
                current.digest,
                0,
                plan.missing_count,
                current,
                (
                    "repair plan does not authorize mutation",
                ),
            )

        try:
            repaired = (
                self.checkpoints
                .repair_missing_lookup_indexes(
                    plan.chain_id,
                    max_repairs=plan.max_repairs,
                )
            )
        except DurableCheckpointError as exc:
            raise CheckpointIndexRepairError(
                str(exc)
            ) from exc

        after = (
            self.checkpoints
            .inspect_lookup_indexes(
                plan.chain_id
            )
        )
        if not after.healthy:
            raise CheckpointIndexRepairError(
                "repair completed without restoring healthy index state"
            )
        return CheckpointIndexRepairResult(
            plan.chain_id,
            CheckpointIndexRepairState.REPAIRED,
            plan.action,
            plan.digest,
            plan.health_digest,
            after.digest,
            repaired,
            plan.missing_count,
            after,
            (
                f"repaired {repaired} missing checkpoint index(es)",
            ),
        )

    def repair(
        self,
        chain_id: str,
    ) -> CheckpointIndexRepairResult:
        return self.apply(
            self.inspect(
                chain_id
            )
        )

    def repair_batch(
        self,
        chain_ids: Iterable[str],
    ) -> CheckpointIndexRepairBatchReport:
        ids = tuple(chain_ids)
        if not ids:
            raise ValueError(
                "at least one chain_id is required"
            )
        if (
            len(ids)
            > self.policy.max_chains_per_batch
        ):
            raise CheckpointIndexRepairError(
                "repair batch exceeds chain policy bound"
            )
        if any(
            not isinstance(item, str)
            or not item
            or len(item) > 128
            for item in ids
        ):
            raise ValueError(
                "invalid repair batch chain_id"
            )
        if len(ids) != len(set(ids)):
            raise ValueError(
                "duplicate repair batch chain_id"
            )
        results = tuple(
            self.repair(chain_id)
            for chain_id in sorted(ids)
        )
        return CheckpointIndexRepairBatchReport(
            results,
            self.policy.digest,
        )
