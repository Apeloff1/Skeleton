"""Non-destructive compaction readiness for durable evidence chains.

Retention planning selects a signed committed prefix that should be archived.
Archive storage proves that the historical payloads remain reconstructable.
This module combines those facts into a bounded readiness certificate.

Readiness is deliberately not deletion authority. The report always exposes
destructive_action_authorized=False. A future destructive executor must have an
independent fenced protocol, rollback/recovery story, and hot-chain base-anchor
semantics before any nodes may be removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from skeleton.shells.ai.durable_archive_store import (
    DurableArchiveRepository,
    DurableArchiveStoreError,
)
from skeleton.shells.ai.durable_checkpoint import (
    CheckpointableEvidenceChain,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionPlan,
    ProtectedHistoricalRoot,
)


class DurableCompactionState(str, Enum):
    READY = "ready"
    NO_ARCHIVE_CANDIDATE = "no_archive_candidate"
    ARCHIVE_MISSING = "archive_missing"
    ARCHIVE_INVALID = "archive_invalid"
    STALE_RETENTION_PLAN = "stale_retention_plan"
    LIVE_TAIL_TOO_SMALL = "live_tail_too_small"
    PROTECTED_ROOT_GAP = "protected_root_gap"
    CHAIN_INVALID = "chain_invalid"


@dataclass(frozen=True)
class DurableCompactionPolicy:
    minimum_live_tail: int = 1_000
    maximum_candidate_nodes: int = 50_000
    max_protected_roots: int = 256
    require_current_head_match: bool = True
    require_archive_for_evicted_protected_roots: bool = True

    def __post_init__(self) -> None:
        for name in (
            "minimum_live_tail",
            "maximum_candidate_nodes",
            "max_protected_roots",
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
        if self.maximum_candidate_nodes <= 0:
            raise ValueError(
                "maximum_candidate_nodes must be positive"
            )
        if self.max_protected_roots <= 0:
            raise ValueError(
                "max_protected_roots must be positive"
            )
        for name in (
            "require_current_head_match",
            "require_archive_for_evicted_protected_roots",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")

    def to_dict(self) -> dict[str, object]:
        return {
            "minimum_live_tail": self.minimum_live_tail,
            "maximum_candidate_nodes": self.maximum_candidate_nodes,
            "max_protected_roots": self.max_protected_roots,
            "require_current_head_match": (
                self.require_current_head_match
            ),
            "require_archive_for_evicted_protected_roots": (
                self.require_archive_for_evicted_protected_roots
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
class DurableCompactionRootCoverage:
    root_hash: str
    sequence: int
    would_be_evicted: bool
    archived: bool
    live: bool
    covered: bool
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.root_hash, str) or len(self.root_hash) != 64:
            raise ValueError(
                "compaction root_hash must be 64-character digest"
            )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError(
                "compaction root sequence must be non-negative"
            )
        for name in (
            "would_be_evicted",
            "archived",
            "live",
            "covered",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")
        if self.covered and not (
            self.archived or self.live
        ):
            raise ValueError(
                "covered compaction root must be archived or live"
            )
        if len(self.reason) > 2048:
            raise ValueError(
                "compaction coverage reason too long"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "root_hash": self.root_hash,
            "sequence": self.sequence,
            "would_be_evicted": self.would_be_evicted,
            "archived": self.archived,
            "live": self.live,
            "covered": self.covered,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DurableCompactionReadiness:
    chain_id: str
    state: DurableCompactionState
    policy_digest: str
    retention_plan_digest: str
    current_sequence: int
    current_root: str
    cutoff_sequence: int
    cutoff_root: str
    live_tail: int
    candidate_nodes: int
    archive_id: str
    archive_manifest_digest: str
    archive_verified: bool
    cutoff_archived: bool
    protected_roots: tuple[
        DurableCompactionRootCoverage,
        ...,
    ]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.chain_id, str)
            or not self.chain_id
            or len(self.chain_id) > 128
        ):
            raise ValueError(
                "invalid compaction chain_id"
            )
        object.__setattr__(
            self,
            "state",
            DurableCompactionState(
                self.state
            ),
        )
        for name in (
            "policy_digest",
            "retention_plan_digest",
            "current_root",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64:
                raise ValueError(
                    f"{name} must be 64-character digest"
                )
        if self.cutoff_root and len(self.cutoff_root) != 64:
            raise ValueError(
                "cutoff_root must be empty or 64-character digest"
            )
        if self.archive_manifest_digest and len(
            self.archive_manifest_digest
        ) != 64:
            raise ValueError(
                "archive_manifest_digest must be empty or digest"
            )
        for name in (
            "current_sequence",
            "cutoff_sequence",
            "live_tail",
            "candidate_nodes",
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
        if self.cutoff_sequence > self.current_sequence:
            raise ValueError(
                "compaction cutoff exceeds current sequence"
            )
        if self.live_tail != (
            self.current_sequence
            - self.cutoff_sequence
        ):
            raise ValueError(
                "compaction live_tail is inconsistent"
            )
        if self.candidate_nodes != self.cutoff_sequence:
            raise ValueError(
                "compaction candidate count must equal cutoff sequence"
            )
        for name in (
            "archive_verified",
            "cutoff_archived",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")
        object.__setattr__(
            self,
            "protected_roots",
            tuple(self.protected_roots),
        )
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )

    @property
    def ready(self) -> bool:
        return (
            self.state
            is DurableCompactionState.READY
        )

    @property
    def destructive_action_authorized(self) -> bool:
        return False

    @property
    def all_protected_roots_covered(self) -> bool:
        return all(
            item.covered
            for item in self.protected_roots
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
            "ready": self.ready,
            "destructive_action_authorized": (
                self.destructive_action_authorized
            ),
            "policy_digest": self.policy_digest,
            "retention_plan_digest": (
                self.retention_plan_digest
            ),
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "cutoff_sequence": self.cutoff_sequence,
            "cutoff_root": self.cutoff_root,
            "live_tail": self.live_tail,
            "candidate_nodes": self.candidate_nodes,
            "archive_id": self.archive_id,
            "archive_manifest_digest": (
                self.archive_manifest_digest
            ),
            "archive_verified": self.archive_verified,
            "cutoff_archived": self.cutoff_archived,
            "all_protected_roots_covered": (
                self.all_protected_roots_covered
            ),
            "protected_roots": [
                item.to_dict()
                for item in self.protected_roots
            ],
            "reasons": list(self.reasons),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableCompactionError(RuntimeError):
    pass


class DurableCompactionPlanner:
    """Prove archive coverage for a retention-selected hot prefix."""

    def __init__(
        self,
        archives: DurableArchiveRepository,
        policy: DurableCompactionPolicy | None = None,
    ) -> None:
        if not isinstance(
            archives,
            DurableArchiveRepository,
        ):
            raise TypeError(
                "archives must be DurableArchiveRepository"
            )
        self.archives = archives
        self.policy = (
            policy or DurableCompactionPolicy()
        )

    @staticmethod
    def _head(
        chain: CheckpointableEvidenceChain,
    ) -> tuple[int, str]:
        head = chain.head()
        return int(head.sequence), str(
            head.root_hash
        )

    def _coverage(
        self,
        chain_id: str,
        chain: CheckpointableEvidenceChain,
        root: ProtectedHistoricalRoot,
        *,
        cutoff_sequence: int,
    ) -> DurableCompactionRootCoverage:
        would_be_evicted = (
            root.sequence <= cutoff_sequence
        )
        archived = False
        live = False
        archive_error = ""
        try:
            archived = self.archives.verify_root(
                chain_id,
                root.root_hash,
            )
        except Exception as exc:
            archive_error = (
                "archive verification raised "
                f"{type(exc).__name__}"
            )
        try:
            live = bool(
                chain.root_is_ancestor(
                    root.root_hash
                )
            )
        except Exception:
            live = False

        if (
            would_be_evicted
            and self.policy.require_archive_for_evicted_protected_roots
        ):
            covered = archived
            reason = (
                ""
                if covered
                else (
                    archive_error
                    or "protected root would be evicted without verified archive coverage"
                )
            )
        else:
            covered = archived or live
            reason = (
                ""
                if covered
                else (
                    archive_error
                    or "protected root is unavailable from live chain and archive"
                )
            )
        return DurableCompactionRootCoverage(
            root.root_hash,
            root.sequence,
            would_be_evicted,
            archived,
            live,
            covered,
            reason,
        )

    def inspect(
        self,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
    ) -> DurableCompactionReadiness:
        if not isinstance(
            retention,
            DurableRetentionPlan,
        ):
            raise TypeError(
                "retention must be DurableRetentionPlan"
            )
        if not isinstance(
            chain,
            CheckpointableEvidenceChain,
        ):
            raise TypeError(
                "chain must satisfy CheckpointableEvidenceChain"
            )
        if len(retention.protected_roots) > self.policy.max_protected_roots:
            raise ValueError(
                "protected root bound exceeds compaction policy"
            )

        reasons: list[str] = []
        try:
            chain_valid = bool(chain.verify())
        except Exception as exc:
            chain_valid = False
            reasons.append(
                "live chain verification raised "
                f"{type(exc).__name__}"
            )

        try:
            current_sequence, current_root = self._head(
                chain
            )
        except Exception as exc:
            current_sequence = 0
            current_root = "0" * 64
            chain_valid = False
            reasons.append(
                "live chain head inspection raised "
                f"{type(exc).__name__}"
            )

        cutoff_sequence = (
            retention.archive_through_sequence
        )
        cutoff_root = (
            retention.archive_through_root
        )
        live_tail = max(
            0,
            current_sequence - cutoff_sequence,
        )
        candidate_nodes = cutoff_sequence

        state = DurableCompactionState.READY
        archive_id = ""
        archive_manifest_digest = ""
        archive_verified = False
        cutoff_archived = False

        if not chain_valid:
            state = DurableCompactionState.CHAIN_INVALID
            reasons.append(
                "live chain failed integrity verification"
            )
        elif (
            self.policy.require_current_head_match
            and (
                retention.current_sequence
                != current_sequence
                or retention.current_root
                != current_root
            )
        ):
            state = DurableCompactionState.STALE_RETENTION_PLAN
            reasons.append(
                "live chain head differs from retention plan"
            )
        elif cutoff_sequence <= 0 or not cutoff_root:
            state = DurableCompactionState.NO_ARCHIVE_CANDIDATE
            reasons.append(
                "retention plan contains no archival prefix"
            )
        elif candidate_nodes > self.policy.maximum_candidate_nodes:
            state = DurableCompactionState.STALE_RETENTION_PLAN
            reasons.append(
                "retention candidate prefix exceeds compaction policy bound"
            )
        elif live_tail < self.policy.minimum_live_tail:
            state = DurableCompactionState.LIVE_TAIL_TOO_SMALL
            reasons.append(
                "retention prefix would leave less than minimum live tail"
            )
        else:
            index = None
            try:
                index = self.archives.root_index(
                    retention.chain_id,
                    cutoff_root,
                )
            except Exception as exc:
                reasons.append(
                    "archive root index lookup raised "
                    f"{type(exc).__name__}"
                )
            if index is None:
                state = DurableCompactionState.ARCHIVE_MISSING
                reasons.append(
                    "retention cutoff root is not present in archive repository"
                )
            else:
                archive_id = index.archive_id
                archive_manifest_digest = (
                    index.archive_manifest_digest
                )
                if index.sequence != cutoff_sequence:
                    state = DurableCompactionState.ARCHIVE_INVALID
                    reasons.append(
                        "archive cutoff sequence differs from retention plan"
                    )
                else:
                    try:
                        stored = self.archives.require(
                            archive_id
                        )
                        archive_verified = (
                            self.archives.verify_archive(
                                stored
                            )
                        )
                        cutoff_archived = (
                            self.archives.verify_root(
                                retention.chain_id,
                                cutoff_root,
                            )
                        )
                    except (
                        DurableArchiveStoreError,
                        ValueError,
                        TypeError,
                        KeyError,
                    ) as exc:
                        archive_verified = False
                        cutoff_archived = False
                        reasons.append(
                            "archive verification raised "
                            f"{type(exc).__name__}"
                        )
                    if not archive_verified or not cutoff_archived:
                        state = DurableCompactionState.ARCHIVE_INVALID
                        reasons.append(
                            "archive repository cannot verify retention cutoff"
                        )

        coverages = tuple(
            self._coverage(
                retention.chain_id,
                chain,
                root,
                cutoff_sequence=cutoff_sequence,
            )
            for root in retention.protected_roots
        )
        if any(
            not item.covered
            for item in coverages
        ):
            if (
                state
                is DurableCompactionState.READY
            ):
                state = (
                    DurableCompactionState.PROTECTED_ROOT_GAP
                )
            reasons.extend(
                item.reason
                for item in coverages
                if item.reason
            )

        if state is DurableCompactionState.READY:
            reasons.append(
                "archive coverage is sufficient for non-destructive compaction readiness"
            )
            reasons.append(
                "readiness does not authorize destructive deletion"
            )

        return DurableCompactionReadiness(
            retention.chain_id,
            state,
            self.policy.digest,
            retention.digest,
            current_sequence,
            current_root,
            cutoff_sequence,
            cutoff_root,
            live_tail,
            candidate_nodes,
            archive_id,
            archive_manifest_digest,
            archive_verified,
            cutoff_archived,
            coverages,
            tuple(reasons),
        )

    def require_ready(
        self,
        retention: DurableRetentionPlan,
        chain: CheckpointableEvidenceChain,
    ) -> DurableCompactionReadiness:
        report = self.inspect(
            retention,
            chain,
        )
        if not report.ready:
            detail = (
                report.reasons[0]
                if report.reasons
                else "durable compaction is not ready"
            )
            raise DurableCompactionError(detail)
        return report
