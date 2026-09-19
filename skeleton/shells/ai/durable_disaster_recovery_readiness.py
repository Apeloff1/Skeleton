"""Operational readiness guard for durable disaster recovery evidence.

This guard composes the latest signed consistency barrier, backup manifest, and
recovery drill with current source-chain state.  It is deliberately
non-mutating and does not grant execution, restore, compaction, or pruning
authority.

Readiness answers a narrower operational question: is the latest recovery
evidence fresh, internally linked, still ancestral to current source state, and
backed by a recent successful drill?
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable, Iterable

from skeleton.shells.ai.durable_backup_manifest import (
    DurableBackupManifest,
    DurableBackupManifestStore,
)
from skeleton.shells.ai.durable_consistency_barrier import (
    DurableConsistencyBarrier,
    DurableConsistencyBarrierStore,
)
from skeleton.shells.ai.durable_recovery_drill import (
    DurableRecoveryDrill,
    DurableRecoveryDrillStore,
)


def _stable_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _timestamp(name: str, value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"{name} must be finite and non-negative")
    return float(value)


class DurableDisasterRecoveryReadinessState(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    ERROR = "error"


class DurableDisasterRecoveryReadinessSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class DurableDisasterRecoveryReadinessPolicy:
    require_current_barrier: bool = True
    require_current_backup: bool = True
    require_current_drill: bool = True
    require_backup_matches_barrier: bool = True
    require_drill_matches_backup: bool = True
    require_successful_drill: bool = True
    block_on_drill_regression: bool = True
    require_backup_root_ancestry: bool = True
    max_barrier_age_seconds: float = 86_400.0
    max_backup_age_seconds: float = 86_400.0
    max_drill_age_seconds: float = 604_800.0
    max_source_sequence_lag: int = 10_000
    max_chains: int = 32
    max_findings: int = 256

    def __post_init__(self) -> None:
        for name in (
            "require_current_barrier",
            "require_current_backup",
            "require_current_drill",
            "require_backup_matches_barrier",
            "require_drill_matches_backup",
            "require_successful_drill",
            "block_on_drill_regression",
            "require_backup_root_ancestry",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(f"{name} must be bool")
        for name in (
            "max_barrier_age_seconds",
            "max_backup_age_seconds",
            "max_drill_age_seconds",
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
        for name in (
            "max_source_sequence_lag",
            "max_chains",
            "max_findings",
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
        if self.max_chains <= 0:
            raise ValueError(
                "max_chains must be positive"
            )
        if self.max_findings <= 0:
            raise ValueError(
                "max_findings must be positive"
            )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict()
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "require_current_barrier": (
                self.require_current_barrier
            ),
            "require_current_backup": (
                self.require_current_backup
            ),
            "require_current_drill": (
                self.require_current_drill
            ),
            "require_backup_matches_barrier": (
                self.require_backup_matches_barrier
            ),
            "require_drill_matches_backup": (
                self.require_drill_matches_backup
            ),
            "require_successful_drill": (
                self.require_successful_drill
            ),
            "block_on_drill_regression": (
                self.block_on_drill_regression
            ),
            "require_backup_root_ancestry": (
                self.require_backup_root_ancestry
            ),
            "max_barrier_age_seconds": (
                self.max_barrier_age_seconds
            ),
            "max_backup_age_seconds": (
                self.max_backup_age_seconds
            ),
            "max_drill_age_seconds": (
                self.max_drill_age_seconds
            ),
            "max_source_sequence_lag": (
                self.max_source_sequence_lag
            ),
            "max_chains": self.max_chains,
            "max_findings": self.max_findings,
        }


@dataclass(frozen=True)
class DurableDisasterRecoveryReadinessFinding:
    severity: DurableDisasterRecoveryReadinessSeverity
    code: str
    message: str
    chain_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "severity",
            DurableDisasterRecoveryReadinessSeverity(
                self.severity
            ),
        )
        if not self.code or len(self.code) > 128:
            raise ValueError(
                "invalid DR readiness finding code"
            )
        if (
            not self.message
            or len(self.message) > 2048
        ):
            raise ValueError(
                "invalid DR readiness finding message"
            )
        if len(self.chain_id) > 128:
            raise ValueError(
                "DR readiness finding chain_id too long"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "chain_id": self.chain_id,
        }


@dataclass(frozen=True)
class DurableDisasterRecoveryChainReadiness:
    chain_id: str
    backup_sequence: int
    backup_root: str
    source_sequence: int | None
    source_root: str
    sequence_lag: int | None
    backup_root_is_source_ancestor: bool
    within_lag_objective: bool
    findings: tuple[
        DurableDisasterRecoveryReadinessFinding,
        ...,
    ]

    def __post_init__(self) -> None:
        if (
            not self.chain_id
            or len(self.chain_id) > 128
        ):
            raise ValueError(
                "invalid DR readiness chain_id"
            )
        if (
            isinstance(self.backup_sequence, bool)
            or not isinstance(
                self.backup_sequence,
                int,
            )
            or self.backup_sequence < 0
        ):
            raise ValueError(
                "backup_sequence must be non-negative"
            )
        if len(self.backup_root) != 64:
            raise ValueError(
                "backup_root must be digest-shaped"
            )
        if self.source_sequence is not None and (
            isinstance(self.source_sequence, bool)
            or not isinstance(
                self.source_sequence,
                int,
            )
            or self.source_sequence < 0
        ):
            raise ValueError(
                "source_sequence must be non-negative when present"
            )
        if (
            self.source_root
            and len(self.source_root) != 64
        ):
            raise ValueError(
                "source_root must be digest-shaped when present"
            )
        if self.sequence_lag is not None and (
            isinstance(self.sequence_lag, bool)
            or not isinstance(
                self.sequence_lag,
                int,
            )
            or self.sequence_lag < 0
        ):
            raise ValueError(
                "sequence_lag must be non-negative when present"
            )
        for name in (
            "backup_root_is_source_ancestor",
            "within_lag_objective",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )

    @property
    def ready(self) -> bool:
        return (
            self.source_sequence is not None
            and self.backup_root_is_source_ancestor
            and self.within_lag_objective
            and not any(
                item.severity
                is DurableDisasterRecoveryReadinessSeverity.ERROR
                for item in self.findings
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "backup_sequence": (
                self.backup_sequence
            ),
            "backup_root": self.backup_root,
            "source_sequence": (
                self.source_sequence
            ),
            "source_root": self.source_root,
            "sequence_lag": self.sequence_lag,
            "backup_root_is_source_ancestor": (
                self.backup_root_is_source_ancestor
            ),
            "within_lag_objective": (
                self.within_lag_objective
            ),
            "ready": self.ready,
            "findings": [
                item.to_dict()
                for item in self.findings
            ],
        }


@dataclass(frozen=True)
class DurableDisasterRecoveryReadinessReport:
    state: DurableDisasterRecoveryReadinessState
    policy_digest: str
    barrier_name: str
    backup_name: str
    drill_name: str
    inspected_at: float
    barrier_id: str
    barrier_generation: int | None
    barrier_age_seconds: float | None
    backup_manifest_id: str
    backup_generation: int | None
    backup_age_seconds: float | None
    drill_id: str
    drill_generation: int | None
    drill_age_seconds: float | None
    drill_success: bool | None
    drill_regression: bool | None
    chains: tuple[
        DurableDisasterRecoveryChainReadiness,
        ...,
    ]
    findings: tuple[
        DurableDisasterRecoveryReadinessFinding,
        ...,
    ]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "state",
            DurableDisasterRecoveryReadinessState(
                self.state
            ),
        )
        if len(self.policy_digest) != 64:
            raise ValueError(
                "policy_digest must be digest-shaped"
            )
        for name in (
            "barrier_name",
            "backup_name",
            "drill_name",
        ):
            value = getattr(self, name)
            if not value or len(value) > 256:
                raise ValueError(
                    f"invalid {name}"
                )
        object.__setattr__(
            self,
            "inspected_at",
            _timestamp(
                "inspected_at",
                self.inspected_at,
            ),
        )
        for name in (
            "barrier_id",
            "backup_manifest_id",
            "drill_id",
        ):
            value = getattr(self, name)
            if value and len(value) != 64:
                raise ValueError(
                    f"{name} must be digest-shaped when present"
                )
        for name in (
            "barrier_generation",
            "backup_generation",
            "drill_generation",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be positive when present"
                )
        for name in (
            "barrier_age_seconds",
            "backup_age_seconds",
            "drill_age_seconds",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(
                    value,
                    (int, float),
                )
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(
                    f"{name} must be finite and non-negative when present"
                )
        for name in (
            "drill_success",
            "drill_regression",
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(
                value,
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool when present"
                )
        chains = tuple(self.chains)
        chain_ids = tuple(
            item.chain_id for item in chains
        )
        if chain_ids != tuple(sorted(chain_ids)):
            raise ValueError(
                "DR readiness chains must be sorted"
            )
        if len(chain_ids) != len(set(chain_ids)):
            raise ValueError(
                "duplicate DR readiness chain"
            )
        object.__setattr__(
            self,
            "chains",
            chains,
        )
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )

    @property
    def ready(self) -> bool:
        return (
            self.state
            is DurableDisasterRecoveryReadinessState.READY
        )

    @property
    def blocked(self) -> bool:
        return self.state in {
            DurableDisasterRecoveryReadinessState.BLOCKED,
            DurableDisasterRecoveryReadinessState.ERROR,
        }

    @property
    def errors(self) -> int:
        return sum(
            item.severity
            is DurableDisasterRecoveryReadinessSeverity.ERROR
            for item in self.findings
        ) + sum(
            finding.severity
            is DurableDisasterRecoveryReadinessSeverity.ERROR
            for chain in self.chains
            for finding in chain.findings
        )

    @property
    def warnings(self) -> int:
        return sum(
            item.severity
            is DurableDisasterRecoveryReadinessSeverity.WARNING
            for item in self.findings
        ) + sum(
            finding.severity
            is DurableDisasterRecoveryReadinessSeverity.WARNING
            for chain in self.chains
            for finding in chain.findings
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
            "state": self.state.value,
            "ready": self.ready,
            "blocked": self.blocked,
            "errors": self.errors,
            "warnings": self.warnings,
            "policy_digest": self.policy_digest,
            "barrier_name": self.barrier_name,
            "backup_name": self.backup_name,
            "drill_name": self.drill_name,
            "inspected_at": self.inspected_at,
            "barrier_id": self.barrier_id,
            "barrier_generation": (
                self.barrier_generation
            ),
            "barrier_age_seconds": (
                self.barrier_age_seconds
            ),
            "backup_manifest_id": (
                self.backup_manifest_id
            ),
            "backup_generation": (
                self.backup_generation
            ),
            "backup_age_seconds": (
                self.backup_age_seconds
            ),
            "drill_id": self.drill_id,
            "drill_generation": (
                self.drill_generation
            ),
            "drill_age_seconds": (
                self.drill_age_seconds
            ),
            "drill_success": self.drill_success,
            "drill_regression": (
                self.drill_regression
            ),
            "chains": [
                item.to_dict()
                for item in self.chains
            ],
            "findings": [
                item.to_dict()
                for item in self.findings
            ],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableDisasterRecoveryReadinessError(RuntimeError):
    pass


class DurableDisasterRecoveryReadinessGuard:
    """Evaluate latest signed DR evidence against current source chains."""

    def __init__(
        self,
        barrier_store: DurableConsistencyBarrierStore,
        backup_store: DurableBackupManifestStore,
        drill_store: DurableRecoveryDrillStore,
        *,
        policy: DurableDisasterRecoveryReadinessPolicy
        | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(
            barrier_store,
            DurableConsistencyBarrierStore,
        ):
            raise TypeError(
                "barrier_store must be DurableConsistencyBarrierStore"
            )
        if not isinstance(
            backup_store,
            DurableBackupManifestStore,
        ):
            raise TypeError(
                "backup_store must be DurableBackupManifestStore"
            )
        if not isinstance(
            drill_store,
            DurableRecoveryDrillStore,
        ):
            raise TypeError(
                "drill_store must be DurableRecoveryDrillStore"
            )
        self.barrier_store = barrier_store
        self.backup_store = backup_store
        self.drill_store = drill_store
        self.policy = (
            policy
            or DurableDisasterRecoveryReadinessPolicy()
        )
        if not isinstance(
            self.policy,
            DurableDisasterRecoveryReadinessPolicy,
        ):
            raise TypeError(
                "policy must be DurableDisasterRecoveryReadinessPolicy"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._clock = clock

    @staticmethod
    def _finding(
        findings: list[
            DurableDisasterRecoveryReadinessFinding
        ],
        severity: DurableDisasterRecoveryReadinessSeverity,
        code: str,
        message: str,
        chain_id: str = "",
    ) -> None:
        findings.append(
            DurableDisasterRecoveryReadinessFinding(
                severity,
                code,
                message,
                chain_id,
            )
        )

    def _entries(
        self,
        chains: Iterable[
            tuple[str, object]
        ],
    ) -> dict[str, object]:
        values = tuple(chains)
        if len(values) > self.policy.max_chains:
            raise DurableDisasterRecoveryReadinessError(
                "DR readiness chain bound exceeded"
            )
        result: dict[str, object] = {}
        for value in values:
            if (
                not isinstance(value, tuple)
                or len(value) != 2
            ):
                raise ValueError(
                    "DR readiness chains must be (chain_id, chain) pairs"
                )
            chain_id, chain = value
            if (
                not isinstance(chain_id, str)
                or not chain_id
                or len(chain_id) > 128
            ):
                raise ValueError(
                    "invalid DR readiness chain_id"
                )
            if chain_id in result:
                raise ValueError(
                    "duplicate DR readiness chain_id"
                )
            if not callable(
                getattr(chain, "head", None)
            ):
                raise TypeError(
                    f"DR readiness chain {chain_id} does not implement head"
                )
            result[chain_id] = chain
        return result

    @staticmethod
    def _ancestor(
        chain: object,
        sequence: int,
        root_hash: str,
    ) -> bool:
        root_is_ancestor = getattr(
            chain,
            "root_is_ancestor",
            None,
        )
        if callable(root_is_ancestor):
            try:
                return bool(
                    root_is_ancestor(
                        root_hash
                    )
                )
            except Exception:
                return False
        root_for_sequence = getattr(
            chain,
            "root_for_sequence",
            None,
        )
        if callable(root_for_sequence):
            try:
                return (
                    str(
                        root_for_sequence(
                            sequence
                        )
                    )
                    == root_hash
                )
            except Exception:
                return False
        return False

    @staticmethod
    def _age(
        now: float,
        timestamp: float,
    ) -> float:
        if timestamp > now:
            return float("inf")
        return now - timestamp

    def inspect(
        self,
        *,
        barrier_name: str,
        backup_name: str,
        drill_name: str,
        source_chains: Iterable[
            tuple[str, object]
        ],
    ) -> DurableDisasterRecoveryReadinessReport:
        for name, value in (
            ("barrier_name", barrier_name),
            ("backup_name", backup_name),
            ("drill_name", drill_name),
        ):
            if (
                not isinstance(value, str)
                or not value
                or len(value) > 256
            ):
                raise ValueError(
                    f"invalid {name}"
                )
        now = _timestamp(
            "inspected_at",
            self._clock(),
        )
        findings: list[
            DurableDisasterRecoveryReadinessFinding
        ] = []
        entries = self._entries(
            source_chains
        )

        barrier_stored = None
        backup_stored = None
        drill_stored = None
        try:
            barrier_stored = (
                self.barrier_store.current(
                    barrier_name
                )
            )
        except Exception as exc:
            self._finding(
                findings,
                DurableDisasterRecoveryReadinessSeverity.ERROR,
                "barrier.corruption",
                "latest consistency barrier cannot be verified: "
                f"{type(exc).__name__}",
            )
        try:
            backup_stored = (
                self.backup_store.current(
                    backup_name
                )
            )
        except Exception as exc:
            self._finding(
                findings,
                DurableDisasterRecoveryReadinessSeverity.ERROR,
                "backup.corruption",
                "latest backup manifest cannot be verified: "
                f"{type(exc).__name__}",
            )
        try:
            drill_stored = (
                self.drill_store.current(
                    drill_name
                )
            )
        except Exception as exc:
            self._finding(
                findings,
                DurableDisasterRecoveryReadinessSeverity.ERROR,
                "drill.corruption",
                "latest recovery drill cannot be verified: "
                f"{type(exc).__name__}",
            )

        barrier: (
            DurableConsistencyBarrier | None
        ) = (
            None
            if barrier_stored is None
            else barrier_stored.signed.barrier
        )
        backup: (
            DurableBackupManifest | None
        ) = (
            None
            if backup_stored is None
            else backup_stored.signed.manifest
        )
        drill: DurableRecoveryDrill | None = (
            None
            if drill_stored is None
            else drill_stored.signed.drill
        )

        if (
            barrier is None
            and self.policy.require_current_barrier
        ):
            self._finding(
                findings,
                DurableDisasterRecoveryReadinessSeverity.ERROR,
                "barrier.missing",
                "required current consistency barrier is missing",
            )
        if (
            backup is None
            and self.policy.require_current_backup
        ):
            self._finding(
                findings,
                DurableDisasterRecoveryReadinessSeverity.ERROR,
                "backup.missing",
                "required current backup manifest is missing",
            )
        if (
            drill is None
            and self.policy.require_current_drill
        ):
            self._finding(
                findings,
                DurableDisasterRecoveryReadinessSeverity.ERROR,
                "drill.missing",
                "required current recovery drill is missing",
            )

        barrier_age = (
            None
            if barrier is None
            else self._age(
                now,
                barrier.captured_at,
            )
        )
        backup_age = (
            None
            if backup is None
            else self._age(
                now,
                backup.created_at,
            )
        )
        drill_age = (
            None
            if drill is None
            else self._age(
                now,
                drill.completed_at,
            )
        )
        for (
            label,
            age,
            maximum,
        ) in (
            (
                "barrier",
                barrier_age,
                self.policy.max_barrier_age_seconds,
            ),
            (
                "backup",
                backup_age,
                self.policy.max_backup_age_seconds,
            ),
            (
                "drill",
                drill_age,
                self.policy.max_drill_age_seconds,
            ),
        ):
            if age is not None and age > maximum:
                self._finding(
                    findings,
                    DurableDisasterRecoveryReadinessSeverity.ERROR,
                    f"{label}.stale",
                    f"latest {label} exceeds configured freshness objective",
                )

        if (
            barrier is not None
            and backup is not None
            and self.policy.require_backup_matches_barrier
            and (
                backup.barrier_id
                != barrier.barrier_id
                or backup.barrier_digest
                != barrier.digest
            )
        ):
            self._finding(
                findings,
                DurableDisasterRecoveryReadinessSeverity.ERROR,
                "backup.barrier_mismatch",
                "latest backup is not built from latest barrier",
            )

        if (
            backup is not None
            and drill is not None
            and self.policy.require_drill_matches_backup
            and (
                drill.backup_manifest_id
                != backup.manifest_id
                or drill.backup_manifest_digest
                != backup.digest
            )
        ):
            self._finding(
                findings,
                DurableDisasterRecoveryReadinessSeverity.ERROR,
                "drill.backup_mismatch",
                "latest drill does not validate latest backup",
            )
        if (
            drill is not None
            and self.policy.require_successful_drill
            and not drill.success
        ):
            self._finding(
                findings,
                DurableDisasterRecoveryReadinessSeverity.ERROR,
                "drill.failed",
                "latest recovery drill did not meet recovery objectives",
            )
        if (
            drill is not None
            and self.policy.block_on_drill_regression
            and drill.regression
        ):
            self._finding(
                findings,
                DurableDisasterRecoveryReadinessSeverity.ERROR,
                "drill.regression",
                "latest recovery drill regressed relative to previous drill",
            )

        chain_reports: list[
            DurableDisasterRecoveryChainReadiness
        ] = []
        if backup is not None:
            expected_ids = {
                item.chain_id
                for item in backup.chains
            }
            if set(entries) != expected_ids:
                missing = sorted(
                    expected_ids - set(entries)
                )
                extra = sorted(
                    set(entries) - expected_ids
                )
                if missing:
                    self._finding(
                        findings,
                        DurableDisasterRecoveryReadinessSeverity.ERROR,
                        "chains.missing",
                        "source chains missing from readiness inspection: "
                        + ",".join(missing),
                    )
                if extra:
                    self._finding(
                        findings,
                        DurableDisasterRecoveryReadinessSeverity.ERROR,
                        "chains.extra",
                        "unexpected source chains in readiness inspection: "
                        + ",".join(extra),
                    )

            for backup_chain in backup.chains:
                chain = entries.get(
                    backup_chain.chain_id
                )
                local: list[
                    DurableDisasterRecoveryReadinessFinding
                ] = []
                if chain is None:
                    local.append(
                        DurableDisasterRecoveryReadinessFinding(
                            DurableDisasterRecoveryReadinessSeverity.ERROR,
                            "chain.missing",
                            "source chain is missing",
                            backup_chain.chain_id,
                        )
                    )
                    chain_reports.append(
                        DurableDisasterRecoveryChainReadiness(
                            backup_chain.chain_id,
                            backup_chain.barrier_head_sequence,
                            backup_chain.barrier_head_root,
                            None,
                            "",
                            None,
                            False,
                            False,
                            tuple(local),
                        )
                    )
                    continue
                try:
                    head = chain.head()
                    source_sequence = int(
                        head.sequence
                    )
                    source_root = str(
                        head.root_hash
                    )
                except Exception:
                    local.append(
                        DurableDisasterRecoveryReadinessFinding(
                            DurableDisasterRecoveryReadinessSeverity.ERROR,
                            "chain.head_invalid",
                            "source chain head has invalid shape",
                            backup_chain.chain_id,
                        )
                    )
                    chain_reports.append(
                        DurableDisasterRecoveryChainReadiness(
                            backup_chain.chain_id,
                            backup_chain.barrier_head_sequence,
                            backup_chain.barrier_head_root,
                            None,
                            "",
                            None,
                            False,
                            False,
                            tuple(local),
                        )
                    )
                    continue

                if (
                    source_sequence
                    < backup_chain.barrier_head_sequence
                ):
                    lag = None
                    ancestor = False
                    within = False
                    local.append(
                        DurableDisasterRecoveryReadinessFinding(
                            DurableDisasterRecoveryReadinessSeverity.ERROR,
                            "chain.rollback",
                            "source chain is behind backup barrier",
                            backup_chain.chain_id,
                        )
                    )
                else:
                    lag = (
                        source_sequence
                        - backup_chain.barrier_head_sequence
                    )
                    ancestor = self._ancestor(
                        chain,
                        backup_chain.barrier_head_sequence,
                        backup_chain.barrier_head_root,
                    )
                    within = (
                        lag
                        <= self.policy.max_source_sequence_lag
                    )
                    if (
                        self.policy.require_backup_root_ancestry
                        and not ancestor
                    ):
                        local.append(
                            DurableDisasterRecoveryReadinessFinding(
                                DurableDisasterRecoveryReadinessSeverity.ERROR,
                                "chain.backup_root_not_ancestor",
                                "backup root is no longer a provable source ancestor",
                                backup_chain.chain_id,
                            )
                        )
                    if not within:
                        local.append(
                            DurableDisasterRecoveryReadinessFinding(
                                DurableDisasterRecoveryReadinessSeverity.ERROR,
                                "chain.sequence_lag_exceeded",
                                "source-to-backup sequence lag exceeds objective",
                                backup_chain.chain_id,
                            )
                        )
                chain_reports.append(
                    DurableDisasterRecoveryChainReadiness(
                        backup_chain.chain_id,
                        backup_chain.barrier_head_sequence,
                        backup_chain.barrier_head_root,
                        source_sequence,
                        source_root,
                        lag,
                        ancestor,
                        within,
                        tuple(local),
                    )
                )

        ordered = tuple(
            sorted(
                chain_reports,
                key=lambda item: item.chain_id,
            )
        )
        all_findings = (
            list(findings)
            + [
                finding
                for item in ordered
                for finding in item.findings
            ]
        )
        if len(all_findings) > self.policy.max_findings:
            raise DurableDisasterRecoveryReadinessError(
                "DR readiness finding bound exceeded"
            )
        errors = sum(
            item.severity
            is DurableDisasterRecoveryReadinessSeverity.ERROR
            for item in all_findings
        )
        warnings = sum(
            item.severity
            is DurableDisasterRecoveryReadinessSeverity.WARNING
            for item in all_findings
        )
        if errors:
            state = (
                DurableDisasterRecoveryReadinessState.BLOCKED
            )
        elif warnings:
            state = (
                DurableDisasterRecoveryReadinessState.DEGRADED
            )
        else:
            state = (
                DurableDisasterRecoveryReadinessState.READY
            )

        return DurableDisasterRecoveryReadinessReport(
            state,
            self.policy.digest,
            barrier_name,
            backup_name,
            drill_name,
            now,
            (
                ""
                if barrier is None
                else barrier.barrier_id
            ),
            (
                None
                if barrier is None
                else barrier.generation
            ),
            barrier_age,
            (
                ""
                if backup is None
                else backup.manifest_id
            ),
            (
                None
                if backup is None
                else backup.generation
            ),
            backup_age,
            (
                ""
                if drill is None
                else drill.drill_id
            ),
            (
                None
                if drill is None
                else drill.generation
            ),
            drill_age,
            (
                None
                if drill is None
                else drill.success
            ),
            (
                None
                if drill is None
                else drill.regression
            ),
            ordered,
            tuple(findings),
        )

    def require_ready(
        self,
        *,
        barrier_name: str,
        backup_name: str,
        drill_name: str,
        source_chains: Iterable[
            tuple[str, object]
        ],
    ) -> DurableDisasterRecoveryReadinessReport:
        report = self.inspect(
            barrier_name=barrier_name,
            backup_name=backup_name,
            drill_name=drill_name,
            source_chains=source_chains,
        )
        if not report.ready:
            finding = next(
                (
                    item
                    for item in report.findings
                    if item.severity
                    is DurableDisasterRecoveryReadinessSeverity.ERROR
                ),
                None,
            )
            if finding is None:
                finding = next(
                    (
                        item
                        for chain in report.chains
                        for item in chain.findings
                        if item.severity
                        is DurableDisasterRecoveryReadinessSeverity.ERROR
                    ),
                    None,
                )
            detail = (
                finding.message
                if finding is not None
                else (
                    "disaster recovery readiness "
                    f"is {report.state.value}"
                )
            )
            raise DurableDisasterRecoveryReadinessError(
                detail
            )
        return report
