"""Non-destructive retention planning for durable evidence chains.

Retention planning identifies a signed historical prefix suitable for archival
when live-chain capacity grows.  It deliberately does not delete nodes.
Historical root verification in the current implementation still reads local
committed nodes, so pruning without an archive-backed reader would break the
recovery contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math

from skeleton.shells.ai.durable_checkpoint import (
    CheckpointableEvidenceChain,
    DurableChainCheckpointStore,
    SignedDurableChainCheckpoint,
)
from skeleton.shells.ai.durable_verification_health import (
    DurableChainVerificationHealth,
)


class DurableRetentionState(str, Enum):
    HEALTHY = "healthy"
    ARCHIVE_RECOMMENDED = "archive_recommended"
    CHECKPOINT_REQUIRED = "checkpoint_required"
    CAPACITY_CRITICAL = "capacity_critical"


@dataclass(frozen=True)
class DurableRetentionPolicy:
    minimum_live_tail: int = 1_000
    minimum_archive_batch: int = 250
    target_utilization: float = 0.70
    warning_utilization: float = 0.80
    critical_utilization: float = 0.95
    max_protected_roots: int = 256

    def __post_init__(self) -> None:
        for name in (
            "minimum_live_tail",
            "minimum_archive_batch",
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
        if self.max_protected_roots <= 0:
            raise ValueError(
                "max_protected_roots must be positive"
            )
        for name in (
            "target_utilization",
            "warning_utilization",
            "critical_utilization",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0.0 < float(value) <= 1.0
            ):
                raise ValueError(
                    f"{name} must be in (0, 1]"
                )
            object.__setattr__(
                self,
                name,
                float(value),
            )
        if not (
            self.target_utilization
            <= self.warning_utilization
            <= self.critical_utilization
        ):
            raise ValueError(
                "retention utilization thresholds must be monotonic"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "minimum_live_tail": self.minimum_live_tail,
            "minimum_archive_batch": self.minimum_archive_batch,
            "target_utilization": self.target_utilization,
            "warning_utilization": self.warning_utilization,
            "critical_utilization": self.critical_utilization,
            "max_protected_roots": self.max_protected_roots,
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
class ProtectedHistoricalRoot:
    root_hash: str
    sequence: int

    def __post_init__(self) -> None:
        if len(self.root_hash) != 64:
            raise ValueError(
                "protected root must be SHA-256 hex"
            )
        # Opaque 64-character protected root digest.
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError(
                "protected root sequence must be non-negative"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "root_hash": self.root_hash,
            "sequence": self.sequence,
        }


@dataclass(frozen=True)
class DurableRetentionPlan:
    chain_id: str
    state: DurableRetentionState
    policy_digest: str
    current_sequence: int
    current_root: str
    capacity: int
    utilization: float
    checkpoint_digest: str
    checkpoint_sequence: int
    checkpoint_root: str
    archive_through_sequence: int
    archive_through_root: str
    archive_node_count: int
    estimated_live_after_archive: int
    protected_roots: tuple[ProtectedHistoricalRoot, ...]
    local_deletion_safe: bool
    reasons: tuple[str, ...]
    hot_floor_sequence: int = 0
    hot_node_count: int = -1

    def __post_init__(self) -> None:
        if not self.chain_id or len(self.chain_id) > 128:
            raise ValueError("invalid retention chain_id")
        object.__setattr__(
            self,
            "state",
            DurableRetentionState(
                self.state
            ),
        )
        for name in (
            "policy_digest",
            "current_root",
        ):
            value = getattr(self, name)
            if len(value) != 64:
                raise ValueError(
                    f"{name} must be SHA-256 hex"
                )
        for name in (
            "checkpoint_digest",
            "checkpoint_root",
            "archive_through_root",
        ):
            value = getattr(self, name)
            if value and len(value) != 64:
                raise ValueError(
                    f"{name} must be SHA-256 hex"
                )
        for name in (
            "current_sequence",
            "checkpoint_sequence",
            "archive_through_sequence",
            "archive_node_count",
            "estimated_live_after_archive",
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
            isinstance(self.capacity, bool)
            or not isinstance(self.capacity, int)
            or self.capacity <= 0
        ):
            raise ValueError(
                "capacity must be positive integer"
            )
        if (
            isinstance(self.utilization, bool)
            or not isinstance(self.utilization, (int, float))
            or not math.isfinite(float(self.utilization))
            or float(self.utilization) < 0.0
        ):
            raise ValueError(
                "utilization must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "utilization",
            float(self.utilization),
        )
        object.__setattr__(
            self,
            "protected_roots",
            tuple(self.protected_roots),
        )
        if (
            isinstance(self.hot_floor_sequence, bool)
            or not isinstance(self.hot_floor_sequence, int)
            or self.hot_floor_sequence < 0
            or self.hot_floor_sequence > self.current_sequence
        ):
            raise ValueError(
                "hot_floor_sequence must be within current chain"
            )
        hot_node_count = self.hot_node_count
        if hot_node_count == -1:
            hot_node_count = (
                self.current_sequence
                - self.hot_floor_sequence
            )
            object.__setattr__(
                self,
                "hot_node_count",
                hot_node_count,
            )
        if (
            isinstance(hot_node_count, bool)
            or not isinstance(hot_node_count, int)
            or hot_node_count < 0
            or hot_node_count
            != self.current_sequence
            - self.hot_floor_sequence
        ):
            raise ValueError(
                "hot_node_count must equal current sequence minus hot floor"
            )
        if self.archive_node_count != self.archive_through_sequence:
            raise ValueError(
                "archive count must match prefix sequence"
            )
        if self.estimated_live_after_archive != (
            self.current_sequence
            - self.archive_through_sequence
        ):
            raise ValueError(
                "estimated live count is inconsistent"
            )
        if self.archive_through_sequence > self.current_sequence:
            raise ValueError(
                "archive prefix exceeds current chain"
            )
        if not isinstance(
            self.local_deletion_safe,
            bool,
        ):
            raise ValueError(
                "local_deletion_safe must be bool"
            )
        if self.local_deletion_safe:
            raise ValueError(
                "local deletion is not supported by current retention contract"
            )
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )

    @property
    def archive_recommended(self) -> bool:
        return self.archive_through_sequence > 0

    @property
    def capacity_remaining(self) -> int:
        return max(
            0,
            self.capacity - self.hot_node_count,
        )

    @property
    def estimated_capacity_remaining_after_archive(self) -> int:
        return max(
            0,
            self.capacity
            - self.estimated_live_after_archive,
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
            "policy_digest": self.policy_digest,
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "hot_floor_sequence": self.hot_floor_sequence,
            "hot_node_count": self.hot_node_count,
            "capacity": self.capacity,
            "utilization": self.utilization,
            "capacity_remaining": self.capacity_remaining,
            "checkpoint_digest": self.checkpoint_digest,
            "checkpoint_sequence": self.checkpoint_sequence,
            "checkpoint_root": self.checkpoint_root,
            "archive_through_sequence": self.archive_through_sequence,
            "archive_through_root": self.archive_through_root,
            "archive_node_count": self.archive_node_count,
            "archive_recommended": self.archive_recommended,
            "estimated_live_after_archive": (
                self.estimated_live_after_archive
            ),
            "estimated_capacity_remaining_after_archive": (
                self.estimated_capacity_remaining_after_archive
            ),
            "protected_roots": [
                item.to_dict()
                for item in self.protected_roots
            ],
            "local_deletion_safe": self.local_deletion_safe,
            "reasons": list(self.reasons),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableRetentionError(RuntimeError):
    pass


class DurableRetentionPlanner:
    """Select a signed committed prefix for archival without deleting it."""

    def __init__(
        self,
        checkpoints: DurableChainCheckpointStore,
        policy: DurableRetentionPolicy | None = None,
    ) -> None:
        if not isinstance(
            checkpoints,
            DurableChainCheckpointStore,
        ):
            raise TypeError(
                "checkpoints must be DurableChainCheckpointStore"
            )
        self.checkpoints = checkpoints
        self.policy = (
            policy or DurableRetentionPolicy()
        )

    @staticmethod
    def _capacity(
        chain,
        explicit: int | None,
    ) -> int:
        if explicit is not None:
            if (
                isinstance(explicit, bool)
                or not isinstance(explicit, int)
                or explicit <= 0
            ):
                raise ValueError(
                    "capacity must be positive integer"
                )
            return explicit
        value = getattr(
            chain,
            "max_events",
            getattr(
                chain,
                "max_receipts",
                None,
            ),
        )
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
        ):
            raise ValueError(
                "chain capacity is unavailable; provide capacity"
            )
        return value

    @staticmethod
    def _hot_occupancy(
        chain,
        current_sequence: int,
    ) -> tuple[int, int]:
        floor_sequence = 0
        floor_method = getattr(
            chain,
            "hot_floor",
            None,
        )
        active_method = getattr(
            chain,
            "_hot_floor_active",
            None,
        )
        if callable(floor_method):
            floor = floor_method()
            candidate = int(
                getattr(floor, "sequence", 0)
            )
            if candidate > 0:
                if callable(active_method):
                    if bool(active_method(floor)):
                        floor_sequence = candidate
                else:
                    floor_sequence = candidate
        hot_length = getattr(
            chain,
            "hot_length",
            None,
        )
        if callable(hot_length):
            hot_nodes = int(hot_length())
        else:
            hot_nodes = (
                current_sequence - floor_sequence
            )
        if (
            floor_sequence < 0
            or floor_sequence > current_sequence
            or hot_nodes < 0
            or hot_nodes
            != current_sequence - floor_sequence
        ):
            raise DurableRetentionError(
                "live hot-tier occupancy is inconsistent with chain head"
            )
        return floor_sequence, hot_nodes

    def _protected(
        self,
        chain: CheckpointableEvidenceChain,
        roots: tuple[str, ...],
    ) -> tuple[ProtectedHistoricalRoot, ...]:
        if len(roots) > self.policy.max_protected_roots:
            raise ValueError(
                "protected root bound exceeded"
            )
        if len(roots) != len(set(roots)):
            raise ValueError(
                "duplicate protected historical root"
            )
        result = []
        for root in sorted(roots):
            if len(root) != 64:
                raise ValueError(
                    "protected root must be SHA-256 hex"
                )
            if not chain.root_is_ancestor(root):
                raise DurableRetentionError(
                    "protected root is not a committed ancestor"
                )
            historical = chain.snapshot_at(root)
            sequence = (
                0
                if not historical
                else int(
                    historical[-1].sequence
                )
            )
            result.append(
                ProtectedHistoricalRoot(
                    root,
                    sequence,
                )
            )
        return tuple(result)

    def plan(
        self,
        chain_id: str,
        chain: CheckpointableEvidenceChain,
        *,
        protected_roots: tuple[str, ...] = (),
        capacity: int | None = None,
        verified_head: DurableChainVerificationHealth | None = None,
    ) -> DurableRetentionPlan:
        if not chain_id or len(chain_id) > 128:
            raise ValueError("invalid chain_id")
        if not isinstance(
            chain,
            CheckpointableEvidenceChain,
        ):
            raise TypeError(
                "chain does not support retention verification"
            )
        head = chain.head()
        current_sequence = int(
            head.sequence
        )
        current_root = str(
            head.root_hash
        )
        if verified_head is None:
            if not chain.verify():
                raise DurableRetentionError(
                    "cannot plan retention for invalid chain"
                )
        else:
            if not isinstance(
                verified_head,
                DurableChainVerificationHealth,
            ):
                raise TypeError(
                    "verified_head must be DurableChainVerificationHealth"
                )
            if not verified_head.ok:
                raise DurableRetentionError(
                    "verified durable chain head is not healthy"
                )
            if verified_head.chain_id != chain_id:
                raise DurableRetentionError(
                    "verified durable chain head chain_id mismatch"
                )
            if (
                verified_head.current_sequence
                != current_sequence
                or verified_head.current_root
                != current_root
            ):
                raise DurableRetentionError(
                    "verified durable chain head differs from live head"
                )
        chain_capacity = self._capacity(
            chain,
            capacity,
        )
        (
            hot_floor_sequence,
            hot_node_count,
        ) = self._hot_occupancy(
            chain,
            current_sequence,
        )
        utilization = (
            hot_node_count / chain_capacity
        )
        protected = self._protected(
            chain,
            tuple(protected_roots),
        )

        maximum_archive_sequence = max(
            0,
            current_sequence
            - self.policy.minimum_live_tail,
        )
        checkpoints = []
        for item in self.checkpoints.for_chain(
            chain_id
        ):
            checkpoint = item.checkpoint
            if (
                hot_floor_sequence
                < checkpoint.sequence
                <= maximum_archive_sequence
            ):
                verification = (
                    self.checkpoints.inspect(
                        item,
                        chain,
                    )
                )
                if verification.valid:
                    checkpoints.append(item)

        selected: (
            SignedDurableChainCheckpoint | None
        ) = (
            checkpoints[-1]
            if checkpoints
            else None
        )

        archive_sequence = 0
        archive_root = ""
        checkpoint_digest = ""
        checkpoint_sequence = 0
        checkpoint_root = ""
        reasons: list[str] = []

        if selected is not None:
            checkpoint_digest = (
                selected.checkpoint.digest
            )
            checkpoint_sequence = (
                selected.checkpoint.sequence
            )
            checkpoint_root = (
                selected.checkpoint.root_hash
            )

        pressure = (
            utilization
            >= self.policy.target_utilization
        )
        if pressure and selected is None:
            reasons.append(
                "capacity pressure requires a signed archival checkpoint"
            )
        elif pressure and selected is not None:
            if (
                selected.checkpoint.sequence
                - hot_floor_sequence
                >= self.policy.minimum_archive_batch
            ):
                archive_sequence = (
                    selected.checkpoint.sequence
                )
                archive_root = (
                    selected.checkpoint.root_hash
                )
                reasons.append(
                    "signed committed prefix is eligible for archival"
                )
            else:
                reasons.append(
                    "eligible checkpoint interval is below minimum archive batch"
                )

        if utilization >= self.policy.critical_utilization:
            state = DurableRetentionState.CAPACITY_CRITICAL
            reasons.append(
                "live evidence chain utilization is critical"
            )
        elif (
            pressure
            and selected is None
        ):
            state = DurableRetentionState.CHECKPOINT_REQUIRED
        elif archive_sequence > 0:
            state = DurableRetentionState.ARCHIVE_RECOMMENDED
        else:
            state = DurableRetentionState.HEALTHY
            if (
                utilization
                >= self.policy.warning_utilization
            ):
                reasons.append(
                    "evidence capacity is above warning threshold"
                )

        reasons.append(
            "local deletion remains unsafe; retention planning never authorizes "
            "deletion and destructive pruning requires separate signed authority"
        )

        return DurableRetentionPlan(
            chain_id,
            state,
            self.policy.digest,
            current_sequence,
            current_root,
            chain_capacity,
            utilization,
            checkpoint_digest,
            checkpoint_sequence,
            checkpoint_root,
            archive_sequence,
            archive_root,
            archive_sequence,
            current_sequence - archive_sequence,
            protected,
            False,
            tuple(reasons),
            hot_floor_sequence,
            hot_node_count,
        )
