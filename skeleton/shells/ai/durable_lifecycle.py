"""Non-destructive durable evidence lifecycle coordination.

This module composes retention planning, signed checkpoint publication,
portable archive persistence, and compaction readiness into one operator-facing
workflow. It may create signed checkpoints and archive records. It never
deletes hot evidence and never grants destructive authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from skeleton.shells.ai.durable_archive import (
    DurableArchiveManifestBuilder,
    SignedDurableArchiveManifest,
)
from skeleton.shells.ai.durable_archive_store import (
    DurableArchiveRepository,
    DurableArchiveStoreReport,
)
from skeleton.shells.ai.durable_checkpoint import (
    CheckpointableEvidenceChain,
    DurableChainCheckpointStore,
    SignedDurableChainCheckpoint,
)
from skeleton.shells.ai.durable_compaction import (
    DurableCompactionPlanner,
    DurableCompactionReadiness,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionPlan,
    DurableRetentionPlanner,
    DurableRetentionState,
)
from skeleton.shells.ai.durable_verification_health import (
    DurableChainVerificationHealth,
)


class DurableLifecycleState(str, Enum):
    HEALTHY = "healthy"
    CHECKPOINT_REQUIRED = "checkpoint_required"
    CHECKPOINT_PRIMED = "checkpoint_primed"
    ARCHIVE_REQUIRED = "archive_required"
    ARCHIVE_STORED = "archive_stored"
    COMPACTION_READY = "compaction_ready"
    BLOCKED = "blocked"


class DurableLifecycleAction(str, Enum):
    NONE = "none"
    CHECKPOINT_PUBLISHED = "checkpoint_published"
    ARCHIVE_PERSISTED = "archive_persisted"
    ARCHIVE_REUSED = "archive_reused"


@dataclass(frozen=True)
class DurableLifecyclePolicy:
    prime_checkpoint_on_pressure: bool = True
    persist_archive_when_recommended: bool = True
    require_compaction_ready_after_archive: bool = True
    max_protected_roots: int = 256

    def __post_init__(self) -> None:
        for name in (
            "prime_checkpoint_on_pressure",
            "persist_archive_when_recommended",
            "require_compaction_ready_after_archive",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        if (
            isinstance(self.max_protected_roots, bool)
            or not isinstance(
                self.max_protected_roots,
                int,
            )
            or self.max_protected_roots <= 0
        ):
            raise ValueError(
                "max_protected_roots must be positive integer"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "prime_checkpoint_on_pressure": (
                self.prime_checkpoint_on_pressure
            ),
            "persist_archive_when_recommended": (
                self.persist_archive_when_recommended
            ),
            "require_compaction_ready_after_archive": (
                self.require_compaction_ready_after_archive
            ),
            "max_protected_roots": (
                self.max_protected_roots
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
class DurableLifecycleReport:
    chain_id: str
    state: DurableLifecycleState
    action: DurableLifecycleAction
    policy_digest: str
    retention: DurableRetentionPlan
    checkpoint: SignedDurableChainCheckpoint | None
    archive: SignedDurableArchiveManifest | None
    archive_store: DurableArchiveStoreReport | None
    compaction: DurableCompactionReadiness | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.chain_id, str)
            or not self.chain_id
            or len(self.chain_id) > 128
        ):
            raise ValueError(
                "invalid lifecycle chain_id"
            )
        object.__setattr__(
            self,
            "state",
            DurableLifecycleState(
                self.state
            ),
        )
        object.__setattr__(
            self,
            "action",
            DurableLifecycleAction(
                self.action
            ),
        )
        if (
            not isinstance(self.policy_digest, str)
            or len(self.policy_digest) != 64
        ):
            raise ValueError(
                "policy_digest must be 64-character digest"
            )
        if not isinstance(
            self.retention,
            DurableRetentionPlan,
        ):
            raise TypeError(
                "retention must be DurableRetentionPlan"
            )
        if self.retention.chain_id != self.chain_id:
            raise ValueError(
                "retention chain_id differs from lifecycle report"
            )
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )

    @property
    def ok(self) -> bool:
        return self.state in {
            DurableLifecycleState.HEALTHY,
            DurableLifecycleState.CHECKPOINT_PRIMED,
            DurableLifecycleState.ARCHIVE_STORED,
            DurableLifecycleState.COMPACTION_READY,
        }

    @property
    def destructive_action_authorized(self) -> bool:
        return False

    @property
    def archive_persisted(self) -> bool:
        return (
            self.archive is not None
            and self.archive_store is not None
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
            "action": self.action.value,
            "ok": self.ok,
            "destructive_action_authorized": (
                self.destructive_action_authorized
            ),
            "policy_digest": self.policy_digest,
            "retention": self.retention.to_dict(),
            "checkpoint": (
                None
                if self.checkpoint is None
                else self.checkpoint.to_dict()
            ),
            "archive": (
                None
                if self.archive is None
                else self.archive.to_dict()
            ),
            "archive_store": (
                None
                if self.archive_store is None
                else self.archive_store.to_dict()
            ),
            "compaction": (
                None
                if self.compaction is None
                else self.compaction.to_dict()
            ),
            "reasons": list(self.reasons),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableLifecycleError(RuntimeError):
    pass


class DurableEvidenceLifecycleCoordinator:
    """Coordinate checkpoint/archive readiness without deleting evidence."""

    def __init__(
        self,
        checkpoints: DurableChainCheckpointStore,
        retention: DurableRetentionPlanner,
        archive_builder: DurableArchiveManifestBuilder,
        archives: DurableArchiveRepository,
        compaction: DurableCompactionPlanner,
        policy: DurableLifecyclePolicy | None = None,
    ) -> None:
        if not isinstance(
            checkpoints,
            DurableChainCheckpointStore,
        ):
            raise TypeError(
                "checkpoints must be DurableChainCheckpointStore"
            )
        if not isinstance(
            retention,
            DurableRetentionPlanner,
        ):
            raise TypeError(
                "retention must be DurableRetentionPlanner"
            )
        if not isinstance(
            archive_builder,
            DurableArchiveManifestBuilder,
        ):
            raise TypeError(
                "archive_builder must be DurableArchiveManifestBuilder"
            )
        if not isinstance(
            archives,
            DurableArchiveRepository,
        ):
            raise TypeError(
                "archives must be DurableArchiveRepository"
            )
        if not isinstance(
            compaction,
            DurableCompactionPlanner,
        ):
            raise TypeError(
                "compaction must be DurableCompactionPlanner"
            )
        self.checkpoints = checkpoints
        self.retention = retention
        self.archive_builder = archive_builder
        self.archives = archives
        self.compaction = compaction
        self.policy = (
            policy or DurableLifecyclePolicy()
        )

    def _retention(
        self,
        chain_id: str,
        chain: CheckpointableEvidenceChain,
        *,
        protected_roots: tuple[str, ...],
        capacity: int | None,
        verified_head: DurableChainVerificationHealth | None = None,
    ) -> DurableRetentionPlan:
        if (
            not isinstance(protected_roots, tuple)
            or len(protected_roots)
            > self.policy.max_protected_roots
        ):
            raise ValueError(
                "protected root bound exceeds lifecycle policy"
            )
        return self.retention.plan(
            chain_id,
            chain,
            protected_roots=protected_roots,
            capacity=capacity,
            verified_head=verified_head,
        )

    def _checkpoint_for_retention(
        self,
        plan: DurableRetentionPlan,
    ) -> SignedDurableChainCheckpoint | None:
        if not plan.checkpoint_digest:
            return None
        matches = tuple(
            item
            for item in self.checkpoints.for_chain(
                plan.chain_id
            )
            if item.checkpoint.digest
            == plan.checkpoint_digest
        )
        if len(matches) != 1:
            raise DurableLifecycleError(
                "retention checkpoint is not uniquely present in registry"
            )
        checkpoint = matches[0]
        if (
            checkpoint.checkpoint.sequence
            != plan.checkpoint_sequence
            or checkpoint.checkpoint.root_hash
            != plan.checkpoint_root
        ):
            raise DurableLifecycleError(
                "retention checkpoint identity differs from registry"
            )
        return checkpoint

    def inspect(
        self,
        chain_id: str,
        chain: CheckpointableEvidenceChain,
        *,
        protected_roots: tuple[str, ...] = (),
        capacity: int | None = None,
        verified_head: DurableChainVerificationHealth | None = None,
    ) -> DurableLifecycleReport:
        plan = self._retention(
            chain_id,
            chain,
            protected_roots=tuple(
                protected_roots
            ),
            capacity=capacity,
            verified_head=verified_head,
        )
        checkpoint = self._checkpoint_for_retention(
            plan
        )
        reasons = list(plan.reasons)

        if (
            plan.state
            is DurableRetentionState.HEALTHY
        ):
            return DurableLifecycleReport(
                chain_id,
                DurableLifecycleState.HEALTHY,
                DurableLifecycleAction.NONE,
                self.policy.digest,
                plan,
                checkpoint,
                None,
                None,
                None,
                tuple(reasons),
            )

        if (
            plan.state
            is DurableRetentionState.CHECKPOINT_REQUIRED
            or (
                not plan.archive_recommended
                and plan.state
                is DurableRetentionState.CAPACITY_CRITICAL
            )
        ):
            reasons.append(
                "lifecycle requires a signed checkpoint before future archival"
            )
            return DurableLifecycleReport(
                chain_id,
                DurableLifecycleState.CHECKPOINT_REQUIRED,
                DurableLifecycleAction.NONE,
                self.policy.digest,
                plan,
                checkpoint,
                None,
                None,
                None,
                tuple(reasons),
            )

        if not plan.archive_recommended:
            reasons.append(
                "retention pressure exists but no archive prefix is currently eligible"
            )
            return DurableLifecycleReport(
                chain_id,
                DurableLifecycleState.BLOCKED,
                DurableLifecycleAction.NONE,
                self.policy.digest,
                plan,
                checkpoint,
                None,
                None,
                None,
                tuple(reasons),
            )

        if checkpoint is None:
            reasons.append(
                "archive prefix is present but its checkpoint is unavailable"
            )
            return DurableLifecycleReport(
                chain_id,
                DurableLifecycleState.BLOCKED,
                DurableLifecycleAction.NONE,
                self.policy.digest,
                plan,
                None,
                None,
                None,
                None,
                tuple(reasons),
            )

        index = self.archives.root_index(
            chain_id,
            plan.archive_through_root,
        )
        if index is None:
            reasons.append(
                "eligible retention prefix has not been persisted to archive repository"
            )
            return DurableLifecycleReport(
                chain_id,
                DurableLifecycleState.ARCHIVE_REQUIRED,
                DurableLifecycleAction.NONE,
                self.policy.digest,
                plan,
                checkpoint,
                None,
                None,
                None,
                tuple(reasons),
            )

        stored = self.archives.get(
            index.archive_id
        )
        if (
            stored is None
            or not self.archives.verify_archive(
                stored
            )
        ):
            reasons.append(
                "archive repository contains invalid evidence for retention prefix"
            )
            return DurableLifecycleReport(
                chain_id,
                DurableLifecycleState.BLOCKED,
                DurableLifecycleAction.NONE,
                self.policy.digest,
                plan,
                checkpoint,
                (
                    None
                    if stored is None
                    else stored.manifest
                ),
                None,
                None,
                tuple(reasons),
            )

        readiness = self.compaction.inspect(
            plan,
            chain,
        )
        if readiness.ready:
            reasons.append(
                "archive is persisted and compaction readiness is verified"
            )
            return DurableLifecycleReport(
                chain_id,
                DurableLifecycleState.COMPACTION_READY,
                DurableLifecycleAction.NONE,
                self.policy.digest,
                plan,
                checkpoint,
                stored.manifest,
                None,
                readiness,
                tuple(reasons),
            )

        reasons.extend(readiness.reasons)
        return DurableLifecycleReport(
            chain_id,
            (
                DurableLifecycleState.BLOCKED
                if self.policy.require_compaction_ready_after_archive
                else DurableLifecycleState.ARCHIVE_STORED
            ),
            DurableLifecycleAction.ARCHIVE_REUSED,
            self.policy.digest,
            plan,
            checkpoint,
            stored.manifest,
            None,
            readiness,
            tuple(reasons),
        )

    def prepare(
        self,
        chain_id: str,
        chain: CheckpointableEvidenceChain,
        *,
        protected_roots: tuple[str, ...] = (),
        capacity: int | None = None,
        verified_head: DurableChainVerificationHealth | None = None,
    ) -> DurableLifecycleReport:
        report = self.inspect(
            chain_id,
            chain,
            protected_roots=protected_roots,
            capacity=capacity,
            verified_head=verified_head,
        )

        if (
            report.state
            is DurableLifecycleState.CHECKPOINT_REQUIRED
            and self.policy.prime_checkpoint_on_pressure
        ):
            checkpoint = self.checkpoints.publish(
                chain_id,
                chain,
            )
            reasons = list(report.reasons)
            reasons.append(
                "current committed head was checkpointed for future archival eligibility"
            )
            refreshed = self._retention(
                chain_id,
                chain,
                protected_roots=tuple(
                    protected_roots
                ),
                capacity=capacity,
                verified_head=verified_head,
            )
            return DurableLifecycleReport(
                chain_id,
                DurableLifecycleState.CHECKPOINT_PRIMED,
                DurableLifecycleAction.CHECKPOINT_PUBLISHED,
                self.policy.digest,
                refreshed,
                checkpoint,
                None,
                None,
                None,
                tuple(reasons),
            )

        if (
            report.state
            is DurableLifecycleState.ARCHIVE_REQUIRED
            and self.policy.persist_archive_when_recommended
        ):
            checkpoint = report.checkpoint
            if checkpoint is None:
                raise DurableLifecycleError(
                    "archive-required lifecycle state lacks checkpoint"
                )
            archive = self.archive_builder.build(
                checkpoint,
                chain,
            )
            store_report = self.archives.put(
                archive,
                checkpoint,
                chain,
            )
            refreshed = self.inspect(
                chain_id,
                chain,
                protected_roots=protected_roots,
                capacity=capacity,
            )
            reasons = list(refreshed.reasons)
            reasons.append(
                "eligible signed prefix was persisted to durable archive repository"
            )
            prepared_state = (
                DurableLifecycleState.COMPACTION_READY
                if (
                    refreshed.compaction is not None
                    and refreshed.compaction.ready
                )
                else (
                    DurableLifecycleState.BLOCKED
                    if self.policy.require_compaction_ready_after_archive
                    else DurableLifecycleState.ARCHIVE_STORED
                )
            )
            return DurableLifecycleReport(
                chain_id,
                prepared_state,
                DurableLifecycleAction.ARCHIVE_PERSISTED,
                self.policy.digest,
                refreshed.retention,
                checkpoint,
                archive,
                store_report,
                refreshed.compaction,
                tuple(reasons),
            )

        return report

    def require_operational(
        self,
        chain_id: str,
        chain: CheckpointableEvidenceChain,
        *,
        protected_roots: tuple[str, ...] = (),
        capacity: int | None = None,
        verified_head: DurableChainVerificationHealth | None = None,
    ) -> DurableLifecycleReport:
        report = self.inspect(
            chain_id,
            chain,
            protected_roots=protected_roots,
            capacity=capacity,
            verified_head=verified_head,
        )
        if not report.ok:
            detail = (
                report.reasons[0]
                if report.reasons
                else "durable lifecycle is not operational"
            )
            raise DurableLifecycleError(
                detail
            )
        return report
