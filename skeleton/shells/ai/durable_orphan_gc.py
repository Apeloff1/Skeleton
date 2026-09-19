"""Maintenance-gated deletion of proven unreachable durable chain nodes.

Discovery and deletion are intentionally separate.  A scan can identify safe
candidates, but destructive mutation additionally requires:

* a bounded immutable plan derived from an exact scan digest;
* an active signed ORPHAN_GC durable-maintenance epoch;
* a live chain resource commitment covering head and hot-floor state;
* per-record revision/hash revalidation immediately before deletion;
* proof that the target is still unindexed and not a committed ancestor.

The operator is idempotent.  A target already absent on retry is recorded as
such and never treated as evidence that some other record can be deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable, Iterable

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.durable_maintenance import (
    DurableMaintenanceGuard,
    DurableMaintenanceOperation,
    DurableMaintenanceResource,
)
from skeleton.shells.ai.durable_orphan_scan import (
    DurableOrphanNodeKind,
    DurableOrphanNodeRecord,
    DurableOrphanRecordState,
    DurableOrphanScanReport,
    DurableOrphanScanner,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
)


def _identity(
    name: str,
    value: str,
    *,
    maximum: int,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
    ):
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
        raise ValueError(f"{name} must be 64-character digest")
    return value.lower()


def _timestamp(
    name: str,
    value: float,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(
            f"{name} must be finite and non-negative"
        )
    return float(value)


@dataclass(frozen=True)
class DurableOrphanGCPolicy:
    max_delete_targets: int = 256
    max_scan_age_seconds: float = 300.0
    require_chain_verification_after_each_delete: bool = True
    require_empty_manual_review: bool = True

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_delete_targets, bool)
            or not isinstance(self.max_delete_targets, int)
            or self.max_delete_targets <= 0
        ):
            raise ValueError(
                "max_delete_targets must be positive integer"
            )
        object.__setattr__(
            self,
            "max_scan_age_seconds",
            _timestamp(
                "max_scan_age_seconds",
                self.max_scan_age_seconds,
            ),
        )
        if self.max_scan_age_seconds <= 0.0:
            raise ValueError(
                "max_scan_age_seconds must be positive"
            )
        for name in (
            "require_chain_verification_after_each_delete",
            "require_empty_manual_review",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "max_delete_targets": self.max_delete_targets,
            "max_scan_age_seconds": self.max_scan_age_seconds,
            "require_chain_verification_after_each_delete": (
                self.require_chain_verification_after_each_delete
            ),
            "require_empty_manual_review": (
                self.require_empty_manual_review
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
class DurableOrphanDeleteTarget:
    chain_id: str
    node_kind: DurableOrphanNodeKind
    backend_namespace: str
    backend_key: str
    expected_revision: int
    sequence: int
    node_hash: str
    previous_hash: str
    scan_record_digest: str

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        object.__setattr__(
            self,
            "node_kind",
            DurableOrphanNodeKind(
                self.node_kind
            ),
        )
        _identity(
            "backend_namespace",
            self.backend_namespace,
            maximum=128,
        )
        _identity(
            "backend_key",
            self.backend_key,
            maximum=512,
        )
        if (
            isinstance(self.expected_revision, bool)
            or not isinstance(self.expected_revision, int)
            or self.expected_revision <= 0
        ):
            raise ValueError(
                "expected_revision must be positive integer"
            )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError(
                "delete target sequence must be positive integer"
            )
        for name in (
            "node_hash",
            "previous_hash",
            "scan_record_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )

    @classmethod
    def from_scan_record(
        cls,
        item: DurableOrphanNodeRecord,
    ) -> "DurableOrphanDeleteTarget":
        if not isinstance(
            item,
            DurableOrphanNodeRecord,
        ):
            raise TypeError(
                "item must be DurableOrphanNodeRecord"
            )
        if (
            item.state
            is not DurableOrphanRecordState.ORPHAN_CANDIDATE
            or not item.safe_to_delete
        ):
            raise ValueError(
                "scan record is not delete-safe orphan candidate"
            )
        return cls(
            item.chain_id,
            item.node_kind,
            item.backend_namespace,
            item.backend_key,
            item.backend_revision,
            item.sequence,
            item.node_hash,
            item.previous_hash,
            item.identity_digest,
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
            "chain_id": self.chain_id,
            "node_kind": self.node_kind.value,
            "backend_namespace": self.backend_namespace,
            "backend_key": self.backend_key,
            "expected_revision": self.expected_revision,
            "sequence": self.sequence,
            "node_hash": self.node_hash,
            "previous_hash": self.previous_hash,
            "scan_record_digest": self.scan_record_digest,
        }


@dataclass(frozen=True)
class DurableOrphanGCPlan:
    schema_version: int
    plan_id: str
    chain_id: str
    node_kind: DurableOrphanNodeKind
    policy_digest: str
    scanner_policy_digest: str
    scan_digest: str
    head_sequence: int
    head_root: str
    floor_sequence: int
    floor_root: str
    floor_active: bool
    targets: tuple[DurableOrphanDeleteTarget, ...]
    created_at: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported orphan GC plan schema"
            )
        object.__setattr__(
            self,
            "plan_id",
            _digest(
                "plan_id",
                self.plan_id,
            ),
        )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        object.__setattr__(
            self,
            "node_kind",
            DurableOrphanNodeKind(
                self.node_kind
            ),
        )
        for name in (
            "policy_digest",
            "scanner_policy_digest",
            "scan_digest",
            "head_root",
            "floor_root",
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
            "head_sequence",
            "floor_sequence",
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
            self.floor_active,
            bool,
        ):
            raise ValueError(
                "floor_active must be bool"
            )
        object.__setattr__(
            self,
            "targets",
            tuple(self.targets),
        )
        if any(
            item.chain_id != self.chain_id
            or item.node_kind is not self.node_kind
            for item in self.targets
        ):
            raise ValueError(
                "orphan GC target binding mismatch"
            )
        target_digests = tuple(
            item.digest
            for item in self.targets
        )
        if len(target_digests) != len(
            set(target_digests)
        ):
            raise ValueError(
                "duplicate orphan GC target"
            )
        object.__setattr__(
            self,
            "created_at",
            _timestamp(
                "created_at",
                self.created_at,
            ),
        )
        expected_plan_id = self.derive_id(
            chain_id=self.chain_id,
            node_kind=self.node_kind,
            policy_digest=self.policy_digest,
            scanner_policy_digest=self.scanner_policy_digest,
            scan_digest=self.scan_digest,
            head_sequence=self.head_sequence,
            head_root=self.head_root,
            floor_sequence=self.floor_sequence,
            floor_root=self.floor_root,
            floor_active=self.floor_active,
            targets=self.targets,
            created_at=self.created_at,
        )
        if self.plan_id != expected_plan_id:
            raise ValueError(
                "orphan GC plan_id differs from deterministic binding"
            )

    @staticmethod
    def derive_id(
        *,
        chain_id: str,
        node_kind: DurableOrphanNodeKind,
        policy_digest: str,
        scanner_policy_digest: str,
        scan_digest: str,
        head_sequence: int,
        head_root: str,
        floor_sequence: int,
        floor_root: str,
        floor_active: bool,
        targets: tuple[
            DurableOrphanDeleteTarget,
            ...,
        ],
        created_at: float,
    ) -> str:
        raw = json.dumps(
            {
                "chain_id": chain_id,
                "node_kind": DurableOrphanNodeKind(
                    node_kind
                ).value,
                "policy_digest": policy_digest,
                "scanner_policy_digest": (
                    scanner_policy_digest
                ),
                "scan_digest": scan_digest,
                "head_sequence": head_sequence,
                "head_root": head_root,
                "floor_sequence": floor_sequence,
                "floor_root": floor_root,
                "floor_active": floor_active,
                "targets": [
                    item.to_dict()
                    for item in targets
                ],
                "created_at": float(
                    created_at
                ),
                "authority": (
                    "durable-orphan-gc-plan"
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def empty(self) -> bool:
        return not self.targets

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(
                include_digest=False,
            ),
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
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "chain_id": self.chain_id,
            "node_kind": self.node_kind.value,
            "policy_digest": self.policy_digest,
            "scanner_policy_digest": (
                self.scanner_policy_digest
            ),
            "scan_digest": self.scan_digest,
            "head_sequence": self.head_sequence,
            "head_root": self.head_root,
            "floor_sequence": self.floor_sequence,
            "floor_root": self.floor_root,
            "floor_active": self.floor_active,
            "targets": [
                item.to_dict()
                for item in self.targets
            ],
            "created_at": self.created_at,
            "empty": self.empty,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableOrphanDeleteState(str, Enum):
    DELETED = "deleted"
    ALREADY_ABSENT = "already_absent"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class DurableOrphanDeleteResult:
    target_digest: str
    state: DurableOrphanDeleteState
    backend_key: str
    node_hash: str
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_digest",
            _digest(
                "target_digest",
                self.target_digest,
            ),
        )
        object.__setattr__(
            self,
            "state",
            DurableOrphanDeleteState(
                self.state
            ),
        )
        _identity(
            "backend_key",
            self.backend_key,
            maximum=512,
        )
        object.__setattr__(
            self,
            "node_hash",
            _digest(
                "node_hash",
                self.node_hash,
            ),
        )
        if (
            not isinstance(self.reason, str)
            or len(self.reason) > 2048
        ):
            raise ValueError(
                "invalid orphan delete result reason"
            )
        if (
            self.state
            is DurableOrphanDeleteState.BLOCKED
            and not self.reason
        ):
            raise ValueError(
                "blocked orphan delete requires reason"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "target_digest": self.target_digest,
            "state": self.state.value,
            "backend_key": self.backend_key,
            "node_hash": self.node_hash,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DurableOrphanGCResult:
    plan_id: str
    plan_digest: str
    maintenance_epoch_id: str
    chain_id: str
    node_kind: DurableOrphanNodeKind
    results: tuple[DurableOrphanDeleteResult, ...]
    chain_verified: bool
    completed_at: float

    def __post_init__(self) -> None:
        for name in (
            "plan_id",
            "plan_digest",
            "maintenance_epoch_id",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        object.__setattr__(
            self,
            "node_kind",
            DurableOrphanNodeKind(
                self.node_kind
            ),
        )
        object.__setattr__(
            self,
            "results",
            tuple(self.results),
        )
        if not isinstance(
            self.chain_verified,
            bool,
        ):
            raise ValueError(
                "chain_verified must be bool"
            )
        object.__setattr__(
            self,
            "completed_at",
            _timestamp(
                "completed_at",
                self.completed_at,
            ),
        )

    @property
    def deleted(self) -> int:
        return sum(
            item.state
            is DurableOrphanDeleteState.DELETED
            for item in self.results
        )

    @property
    def already_absent(self) -> int:
        return sum(
            item.state
            is DurableOrphanDeleteState.ALREADY_ABSENT
            for item in self.results
        )

    @property
    def blocked(self) -> int:
        return sum(
            item.state
            is DurableOrphanDeleteState.BLOCKED
            for item in self.results
        )

    @property
    def ok(self) -> bool:
        return (
            self.chain_verified
            and self.blocked == 0
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(
                include_digest=False,
            ),
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
            "plan_id": self.plan_id,
            "plan_digest": self.plan_digest,
            "maintenance_epoch_id": (
                self.maintenance_epoch_id
            ),
            "chain_id": self.chain_id,
            "node_kind": self.node_kind.value,
            "results": [
                item.to_dict()
                for item in self.results
            ],
            "chain_verified": self.chain_verified,
            "completed_at": self.completed_at,
            "deleted": self.deleted,
            "already_absent": (
                self.already_absent
            ),
            "blocked": self.blocked,
            "ok": self.ok,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableOrphanGCError(RuntimeError):
    pass


class DurableOrphanGCStale(
    DurableOrphanGCError
):
    pass


class DurableOrphanGCManualReview(
    DurableOrphanGCError
):
    pass


class DurableOrphanGCOperator:
    """Plan and execute bounded orphan deletion under maintenance authority."""

    def __init__(
        self,
        scanner: DurableOrphanScanner,
        *,
        policy: DurableOrphanGCPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(
            scanner,
            DurableOrphanScanner,
        ):
            raise TypeError(
                "scanner must be DurableOrphanScanner"
            )
        self.scanner = scanner
        self.policy = (
            policy or DurableOrphanGCPolicy()
        )
        if not isinstance(
            self.policy,
            DurableOrphanGCPolicy,
        ):
            raise TypeError(
                "policy must be DurableOrphanGCPolicy"
            )
        if not callable(clock):
            raise TypeError(
                "clock must be callable"
            )
        self._clock = clock

    @staticmethod
    def _head_floor(
        chain: object,
    ) -> tuple[int, str, int, str, bool]:
        head = chain.head()
        head_sequence = int(
            getattr(head, "sequence")
        )
        head_root = _digest(
            "head_root",
            str(
                getattr(head, "root_hash")
            ),
        )
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
        if not callable(floor_method):
            return (
                head_sequence,
                head_root,
                0,
                "0" * 64,
                False,
            )
        floor = floor_method()
        floor_sequence = int(
            getattr(floor, "sequence", 0)
        )
        floor_root = _digest(
            "floor_root",
            str(
                getattr(
                    floor,
                    "root_hash",
                    "0" * 64,
                )
            ),
        )
        floor_active = bool(
            callable(active_method)
            and active_method(floor)
        )
        return (
            head_sequence,
            head_root,
            floor_sequence,
            floor_root,
            floor_active,
        )

    def maintenance_resource(
        self,
        chain_id: str,
        chain: object,
    ) -> DurableMaintenanceResource:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        (
            head_sequence,
            head_root,
            floor_sequence,
            floor_root,
            floor_active,
        ) = self._head_floor(chain)
        state_raw = json.dumps(
            {
                "chain_id": chain_id,
                "namespace": str(
                    getattr(
                        chain,
                        "namespace",
                        "",
                    )
                ),
                "head_sequence": head_sequence,
                "head_root": head_root,
                "floor_sequence": floor_sequence,
                "floor_root": floor_root,
                "floor_active": floor_active,
                "purpose": "orphan-gc",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return DurableMaintenanceResource(
            chain_id,
            "orphan-gc-chain",
            head_sequence,
            head_root,
            hashlib.sha256(
                state_raw
            ).hexdigest(),
        )

    def plan(
        self,
        chain_id: str,
        chain: object,
        *,
        max_targets: int | None = None,
    ) -> DurableOrphanGCPlan:
        report = self.scanner.scan(
            chain_id,
            chain,
        )
        if (
            self.policy.require_empty_manual_review
            and report.requires_manual_review
        ):
            raise DurableOrphanGCManualReview(
                "orphan scan contains corruption or authority conflicts"
            )
        limit = (
            self.policy.max_delete_targets
            if max_targets is None
            else max_targets
        )
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit <= 0
            or limit > self.policy.max_delete_targets
        ):
            raise ValueError(
                "max_targets outside GC policy"
            )
        targets = tuple(
            DurableOrphanDeleteTarget
            .from_scan_record(item)
            for item in report.safe_delete_candidates[
                :limit
            ]
        )
        now = _timestamp(
            "GC plan clock",
            self._clock(),
        )
        plan_id = DurableOrphanGCPlan.derive_id(
            chain_id=report.chain_id,
            node_kind=report.node_kind,
            policy_digest=self.policy.digest,
            scanner_policy_digest=(
                report.policy_digest
            ),
            scan_digest=report.digest,
            head_sequence=report.head_sequence,
            head_root=report.head_root,
            floor_sequence=(
                report.floor_sequence
            ),
            floor_root=report.floor_root,
            floor_active=report.floor_active,
            targets=targets,
            created_at=now,
        )
        return DurableOrphanGCPlan(
            1,
            plan_id,
            report.chain_id,
            report.node_kind,
            self.policy.digest,
            report.policy_digest,
            report.digest,
            report.head_sequence,
            report.head_root,
            report.floor_sequence,
            report.floor_root,
            report.floor_active,
            targets,
            now,
        )

    def _require_fresh(
        self,
        plan: DurableOrphanGCPlan,
    ) -> None:
        now = _timestamp(
            "GC execution clock",
            self._clock(),
        )
        age = now - plan.created_at
        if age < 0.0:
            raise DurableOrphanGCStale(
                "orphan GC plan is from the future"
            )
        if age > self.policy.max_scan_age_seconds:
            raise DurableOrphanGCStale(
                "orphan GC plan exceeded maximum age"
            )
        if (
            plan.policy_digest
            != self.policy.digest
        ):
            raise DurableOrphanGCStale(
                "orphan GC policy changed after plan"
            )
        if (
            plan.scanner_policy_digest
            != self.scanner.policy.digest
        ):
            raise DurableOrphanGCStale(
                "orphan scanner policy changed after plan"
            )

    @staticmethod
    def _record_node_hash(
        chain: object,
        value: object,
    ) -> str:
        if isinstance(
            chain,
            DistributedAIDecisionJournal,
        ):
            return str(
                getattr(
                    value,
                    "event_hash",
                    "",
                )
            )
        if isinstance(
            chain,
            DistributedReceiptChain,
        ):
            return str(
                getattr(
                    value,
                    "receipt_hash",
                    "",
                )
            )
        raise TypeError(
            "unsupported orphan GC chain"
        )

    @staticmethod
    def _sequence_index_hash(
        chain: object,
        sequence: int,
    ) -> str:
        key = chain._sequence_key(
            sequence
        )
        record = chain.backend.get(
            chain.namespace,
            key,
        )
        if record is None:
            return ""
        value = record.value
        return str(
            getattr(
                value,
                "event_hash",
                getattr(
                    value,
                    "receipt_hash",
                    "",
                ),
            )
        )

    def _revalidate_target(
        self,
        chain: object,
        target: DurableOrphanDeleteTarget,
    ):
        record = chain.backend.get(
            target.backend_namespace,
            target.backend_key,
        )
        if record is None:
            return None
        if (
            record.revision
            != target.expected_revision
        ):
            raise DurableOrphanGCStale(
                "orphan candidate backend revision changed"
            )
        node_hash = _digest(
            "candidate node hash",
            self._record_node_hash(
                chain,
                record.value,
            ),
        )
        if node_hash != target.node_hash:
            raise DurableOrphanGCManualReview(
                "orphan candidate backend content changed"
            )
        sequence = int(
            getattr(
                record.value,
                "sequence",
                0,
            )
        )
        previous_hash = _digest(
            "candidate previous hash",
            str(
                getattr(
                    record.value,
                    "previous_hash",
                    "",
                )
            ),
        )
        if (
            sequence != target.sequence
            or previous_hash
            != target.previous_hash
        ):
            raise DurableOrphanGCManualReview(
                "orphan candidate identity changed"
            )

        index_hash = (
            self._sequence_index_hash(
                chain,
                target.sequence,
            )
        )
        if index_hash == target.node_hash:
            raise DurableOrphanGCManualReview(
                "orphan candidate became sequence-index authority"
            )

        head = chain.head()
        if target.sequence > int(
            getattr(head, "sequence")
        ):
            raise DurableOrphanGCManualReview(
                "orphan candidate sequence exceeds current head"
            )
        if target.node_hash == str(
            getattr(head, "root_hash")
        ):
            raise DurableOrphanGCManualReview(
                "orphan candidate became current head"
            )

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
            if (
                callable(active_method)
                and active_method(floor)
                and target.sequence
                <= int(
                    getattr(
                        floor,
                        "sequence",
                        0,
                    )
                )
            ):
                raise DurableOrphanGCManualReview(
                    "orphan candidate is now at or below active hot floor"
                )

        try:
            if chain.root_is_ancestor(
                target.node_hash
            ):
                raise DurableOrphanGCManualReview(
                    "orphan candidate became committed ancestor"
                )
        except DurableOrphanGCManualReview:
            raise
        except Exception as exc:
            raise DurableOrphanGCManualReview(
                "unable to prove orphan candidate remains unreachable"
            ) from exc

        return record

    def execute(
        self,
        plan: DurableOrphanGCPlan,
        chain: object,
        *,
        maintenance: DurableMaintenanceGuard,
    ) -> DurableOrphanGCResult:
        if not isinstance(
            plan,
            DurableOrphanGCPlan,
        ):
            raise TypeError(
                "plan must be DurableOrphanGCPlan"
            )
        if not isinstance(
            maintenance,
            DurableMaintenanceGuard,
        ):
            raise TypeError(
                "maintenance must be DurableMaintenanceGuard"
            )
        if plan.empty:
            # No destructive action is required.  Preserve the exact plan in
            # the result while avoiding needless maintenance lease churn.
            return DurableOrphanGCResult(
                plan.plan_id,
                plan.digest,
                maintenance.signed.epoch_id,
                plan.chain_id,
                plan.node_kind,
                (),
                bool(chain.verify()),
                _timestamp(
                    "GC completion clock",
                    self._clock(),
                ),
            )

        self._require_fresh(
            plan
        )
        resource = self.maintenance_resource(
            plan.chain_id,
            chain,
        )
        maintenance.require(
            operation=(
                DurableMaintenanceOperation.ORPHAN_GC
            ),
            resources=(
                plan.chain_id,
            ),
            live_resources=(
                resource,
            ),
        )

        if (
            str(
                getattr(
                    chain,
                    "namespace",
                    "",
                )
            )
            != plan.targets[0]
            .backend_namespace
        ):
            raise DurableOrphanGCManualReview(
                "orphan GC plan namespace differs from live chain"
            )

        results: list[
            DurableOrphanDeleteResult
        ] = []
        for target in plan.targets:
            if (
                target.chain_id
                != plan.chain_id
                or target.node_kind
                is not plan.node_kind
            ):
                raise DurableOrphanGCManualReview(
                    "orphan GC target binding differs from plan"
                )
            record = self._revalidate_target(
                chain,
                target,
            )
            if record is None:
                results.append(
                    DurableOrphanDeleteResult(
                        target.digest,
                        DurableOrphanDeleteState.ALREADY_ABSENT,
                        target.backend_key,
                        target.node_hash,
                    )
                )
                continue

            try:
                deleted = chain.backend.delete(
                    target.backend_namespace,
                    target.backend_key,
                    expected_revision=(
                        target.expected_revision
                    ),
                )
            except Exception as exc:
                raise DurableOrphanGCStale(
                    "orphan candidate delete conflicted"
                ) from exc
            if not deleted:
                results.append(
                    DurableOrphanDeleteResult(
                        target.digest,
                        DurableOrphanDeleteState.ALREADY_ABSENT,
                        target.backend_key,
                        target.node_hash,
                    )
                )
                continue

            if chain.backend.get(
                target.backend_namespace,
                target.backend_key,
            ) is not None:
                raise DurableOrphanGCManualReview(
                    "orphan candidate remains after delete"
                )
            if (
                self.policy
                .require_chain_verification_after_each_delete
                and not chain.verify()
            ):
                raise DurableOrphanGCManualReview(
                    "committed chain failed verification after orphan delete"
                )
            results.append(
                DurableOrphanDeleteResult(
                    target.digest,
                    DurableOrphanDeleteState.DELETED,
                    target.backend_key,
                    target.node_hash,
                )
            )

        chain_verified = bool(
            chain.verify()
        )
        if not chain_verified:
            raise DurableOrphanGCManualReview(
                "committed chain failed final verification after orphan GC"
            )
        return DurableOrphanGCResult(
            plan.plan_id,
            plan.digest,
            maintenance.signed.epoch_id,
            plan.chain_id,
            plan.node_kind,
            tuple(results),
            chain_verified,
            _timestamp(
                "GC completion clock",
                self._clock(),
            ),
        )

    def verify_result(
        self,
        plan: DurableOrphanGCPlan,
        result: DurableOrphanGCResult,
        chain: object,
    ) -> bool:
        if (
            not isinstance(
                plan,
                DurableOrphanGCPlan,
            )
            or not isinstance(
                result,
                DurableOrphanGCResult,
            )
        ):
            return False
        if (
            result.plan_id != plan.plan_id
            or result.plan_digest
            != plan.digest
            or result.chain_id
            != plan.chain_id
            or result.node_kind
            is not plan.node_kind
            or len(result.results)
            != len(plan.targets)
        ):
            return False
        if not result.ok:
            return False
        for target, outcome in zip(
            plan.targets,
            result.results,
        ):
            if (
                outcome.target_digest
                != target.digest
                or outcome.node_hash
                != target.node_hash
                or outcome.backend_key
                != target.backend_key
            ):
                return False
            if chain.backend.get(
                target.backend_namespace,
                target.backend_key,
            ) is not None:
                return False
        return bool(
            chain.verify()
        )
