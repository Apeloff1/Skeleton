"""Fail-closed repository maintenance and deletion decisions.

The legacy path-level deletion assessor remains available for compatibility.
VOL-092 extends that surface with immutable ownership policy, fresh
resource-digest evidence, bounded maintenance tasks, deterministic receipts and
an execution-time authorization recomputation boundary.

Nothing in this module performs deletion itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from pathlib import PurePosixPath
import re
from typing import Iterable, Mapping

MAINTENANCE_SCHEMA = "skeleton.repo_machine.maintenance.v1"
_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_REFERENCES = 1024
_MAX_RESOURCES = 16384
_MAX_TASKS = 4096
_MAX_EVIDENCE = 16384
_MAX_MUTATIONS = 100
_MAX_AGE_SECONDS = 31_536_000

_NON_WAIVABLE_PROTECTED_PATHS = (
    ".github/workflows",
    "docs/adr",
    "machine",
)


class MaintenancePolicyError(RuntimeError):
    """Legacy path-level deletion policy failed."""


class MaintenanceError(ValueError):
    """VOL-092 maintenance policy/evidence is unsafe or non-canonical."""


class MaintenanceRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ResourceKind(str, Enum):
    BRANCH = "branch"
    FILE = "file"
    DEPENDENCY = "dependency"
    ARTIFACT = "artifact"


class OwnershipClass(str, Enum):
    ACTIVE = "active"
    MIGRATION = "migration"
    GENERATED = "generated"
    RELEASE = "release"
    EVIDENCE = "evidence"
    UNOWNED = "unowned"


class MaintenanceAction(str, Enum):
    INSPECT = "inspect"
    UPDATE = "update"
    DELETE = "delete"


class MaintenanceVerdict(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"


def _text(value: object, field: str, *, max_len: int = 2048) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be text")
    text = value.strip()
    if (
        not text
        or len(text) > max_len
        or any(ord(char) < 32 and char not in "\t\n\r" for char in text)
    ):
        raise ValueError(f"{field} must be non-empty bounded text")
    return text


def _path(value: str) -> str:
    text = _text(value, "path")
    if "\x00" in text or "\\" in text:
        raise ValueError("path must be canonical POSIX text")
    pure = PurePosixPath(text)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("path must be repository-relative and traversal-free")
    if pure.as_posix() != text:
        raise ValueError("path is not canonical POSIX text")
    return text


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def _id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise MaintenanceError(f"{field} must be a stable identifier")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise MaintenanceError(f"{field} must be lowercase sha256")
    return value


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise MaintenanceError(f"{field} must be timezone-aware")
    normalized = value.astimezone(timezone.utc)
    if normalized.microsecond:
        raise MaintenanceError(f"{field} must use whole-second precision")
    return normalized


def _optional_utc(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    return _utc(value, field)


def _positive_int(value: object, field: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MaintenanceError(f"{field} must be an integer")
    if not 1 <= value <= maximum:
        raise MaintenanceError(f"{field} must be within [1, {maximum}]")
    return value


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MaintenanceError(
            "maintenance identity must be deterministic JSON"
        ) from exc
    return sha256(raw).hexdigest()


def _ids(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise MaintenanceError(f"{field} must be a tuple")
    if len(values) > _MAX_REFERENCES:
        raise MaintenanceError(f"{field} exceeds policy bound")
    normalized = tuple(sorted(_id(item, field) for item in values))
    if len(normalized) != len(set(normalized)):
        raise MaintenanceError(f"{field} contains duplicate identities")
    return normalized


# ---------------------------------------------------------------------------
# Compatibility deletion assessor used by the existing repository machine.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeletionAssessment:
    path: str
    owner_resolved: bool
    trace_reachable: bool
    retention_hold: bool
    migration_safe: bool
    regeneration_authority: str
    rollback_ref: str
    owner_evidence_ref: str
    trace_evidence_ref: str
    retention_evidence_ref: str
    migration_evidence_ref: str
    protected_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _path(self.path))
        object.__setattr__(
            self,
            "regeneration_authority",
            _text(
                self.regeneration_authority,
                "regeneration_authority",
                max_len=512,
            ),
        )
        object.__setattr__(
            self,
            "rollback_ref",
            _text(self.rollback_ref, "rollback_ref"),
        )
        for field in (
            "owner_evidence_ref",
            "trace_evidence_ref",
            "retention_evidence_ref",
            "migration_evidence_ref",
        ):
            object.__setattr__(
                self,
                field,
                _text(getattr(self, field), field, max_len=2048),
            )
        protected = tuple(
            sorted(
                {
                    *(_path(item) for item in self.protected_paths),
                    *_NON_WAIVABLE_PROTECTED_PATHS,
                }
            )
        )
        object.__setattr__(self, "protected_paths", protected)
        for field in (
            "owner_resolved",
            "trace_reachable",
            "retention_hold",
            "migration_safe",
        ):
            if not isinstance(getattr(self, field), bool):
                raise TypeError(f"{field} must be boolean")


@dataclass(frozen=True, slots=True)
class MaintenanceDecision:
    path: str
    allowed: bool
    blockers: tuple[str, ...]
    checks: tuple[str, ...]
    evidence_refs: tuple[str, ...]


_REQUIRED_CHECKS = (
    "canonical owner resolved",
    "trace reachability checked",
    "retention/evidence hold clear",
    "migration/cutover safe",
    "regeneration authority known",
    "rollback/recovery recorded",
)


def evaluate_deletion(assessment: DeletionAssessment) -> MaintenanceDecision:
    blockers: list[str] = []
    if any(
        _under(assessment.path, prefix)
        for prefix in assessment.protected_paths
    ):
        blockers.append("protected path")
    if not assessment.owner_resolved:
        blockers.append("canonical owner unresolved")
    if assessment.trace_reachable:
        blockers.append("live trace reachability")
    if assessment.retention_hold:
        blockers.append("retention/evidence hold")
    if not assessment.migration_safe:
        blockers.append("migration/cutover unsafe")
    return MaintenanceDecision(
        path=assessment.path,
        allowed=not blockers,
        blockers=tuple(blockers),
        checks=_REQUIRED_CHECKS,
        evidence_refs=(
            assessment.owner_evidence_ref,
            assessment.trace_evidence_ref,
            assessment.retention_evidence_ref,
            assessment.migration_evidence_ref,
            assessment.rollback_ref,
        ),
    )


def evaluate_batch(
    assessments: Iterable[DeletionAssessment],
) -> tuple[MaintenanceDecision, ...]:
    decisions = tuple(evaluate_deletion(item) for item in assessments)
    if len({item.path for item in decisions}) != len(decisions):
        raise MaintenancePolicyError("duplicate deletion candidate")
    ordered = tuple(sorted(decisions, key=lambda item: item.path))
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if _under(left.path, right.path) or _under(right.path, left.path):
                raise MaintenancePolicyError(
                    "overlapping deletion candidates: "
                    f"{left.path} and {right.path}"
                )
    return ordered


# ---------------------------------------------------------------------------
# VOL-092 evidence-bound ownership registry and mutation authority.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RepositoryOwnership:
    """Explicit owner/retention/preservation policy for one resource."""

    resource_id: str
    kind: ResourceKind
    ownership: OwnershipClass
    owner: str
    retention_reason: str
    mutation_authority_refs: tuple[str, ...]
    repository_path: str | None = None
    retention_until: datetime | None = None
    active_refs: tuple[str, ...] = ()
    preservation_refs: tuple[str, ...] = ()
    generation_source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "resource_id",
            _id(self.resource_id, "resource_id"),
        )
        if not isinstance(self.kind, ResourceKind):
            raise MaintenanceError("kind must be ResourceKind")
        if not isinstance(self.ownership, OwnershipClass):
            raise MaintenanceError("ownership must be OwnershipClass")
        object.__setattr__(self, "owner", _id(self.owner, "owner"))
        object.__setattr__(
            self,
            "retention_reason",
            _text(self.retention_reason, "retention_reason"),
        )
        object.__setattr__(
            self,
            "mutation_authority_refs",
            _ids(self.mutation_authority_refs, "mutation_authority_ref"),
        )
        if not self.mutation_authority_refs:
            raise MaintenanceError(
                "ownership requires at least one mutation authority"
            )
        if self.repository_path is not None:
            object.__setattr__(
                self,
                "repository_path",
                _path(self.repository_path),
            )
        if self.kind is ResourceKind.FILE and self.repository_path is None:
            raise MaintenanceError(
                "file ownership requires repository_path"
            )
        object.__setattr__(
            self,
            "retention_until",
            _optional_utc(self.retention_until, "retention_until"),
        )
        object.__setattr__(
            self,
            "active_refs",
            _ids(self.active_refs, "active_ref"),
        )
        object.__setattr__(
            self,
            "preservation_refs",
            _ids(self.preservation_refs, "preservation_ref"),
        )
        object.__setattr__(
            self,
            "generation_source_refs",
            _ids(self.generation_source_refs, "generation_source_ref"),
        )

        if self.ownership is OwnershipClass.UNOWNED:
            if self.active_refs or self.preservation_refs:
                raise MaintenanceError(
                    "unowned resource cannot carry active/preservation references"
                )
            if self.generation_source_refs:
                raise MaintenanceError(
                    "unowned resource cannot carry generation source references"
                )

        if self.ownership is OwnershipClass.GENERATED:
            if not self.generation_source_refs:
                raise MaintenanceError(
                    "generated resource requires explicit generation source references"
                )
        elif self.generation_source_refs:
            raise MaintenanceError(
                "generation source references are reserved for generated resources"
            )

        if self.ownership in (
            OwnershipClass.MIGRATION,
            OwnershipClass.RELEASE,
            OwnershipClass.EVIDENCE,
        ) and not self.preservation_refs:
            raise MaintenanceError(
                "protected ownership requires explicit preservation references"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": MAINTENANCE_SCHEMA,
                "resource_id": self.resource_id,
                "kind": self.kind.value,
                "ownership": self.ownership.value,
                "owner": self.owner,
                "retention_reason": self.retention_reason,
                "mutation_authority_refs": self.mutation_authority_refs,
                "repository_path": self.repository_path,
                "retention_until": (
                    self.retention_until.isoformat()
                    if self.retention_until is not None
                    else None
                ),
                "active_refs": self.active_refs,
                "preservation_refs": self.preservation_refs,
                "generation_source_refs": self.generation_source_refs,
            }
        )


@dataclass(frozen=True, slots=True)
class ResourceEvidence:
    """Fresh evidence about reachability, age and preservation bindings."""

    evidence_id: str
    resource_id: str
    observed_digest: str
    observed_at: datetime
    last_activity_at: datetime
    reachable: bool
    active_migration: bool
    release_bound: bool
    evidence_bound: bool
    regeneration_receipt_digest: str | None = None
    regeneration_source_refs: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence_id",
            _id(self.evidence_id, "evidence_id"),
        )
        object.__setattr__(
            self,
            "resource_id",
            _id(self.resource_id, "resource_id"),
        )
        object.__setattr__(
            self,
            "observed_digest",
            _sha(self.observed_digest, "observed_digest"),
        )
        object.__setattr__(
            self,
            "observed_at",
            _utc(self.observed_at, "observed_at"),
        )
        object.__setattr__(
            self,
            "last_activity_at",
            _utc(self.last_activity_at, "last_activity_at"),
        )
        if self.last_activity_at > self.observed_at:
            raise MaintenanceError(
                "last_activity_at cannot be after observed_at"
            )
        for field in (
            "reachable",
            "active_migration",
            "release_bound",
            "evidence_bound",
        ):
            if not isinstance(getattr(self, field), bool):
                raise MaintenanceError(f"{field} must be bool")
        if self.regeneration_receipt_digest is not None:
            object.__setattr__(
                self,
                "regeneration_receipt_digest",
                _sha(
                    self.regeneration_receipt_digest,
                    "regeneration_receipt_digest",
                ),
            )
        object.__setattr__(
            self,
            "regeneration_source_refs",
            _ids(
                self.regeneration_source_refs,
                "regeneration_source_ref",
            ),
        )
        if (
            self.regeneration_receipt_digest is None
            and self.regeneration_source_refs
        ):
            raise MaintenanceError(
                "regeneration source refs require regeneration receipt"
            )
        object.__setattr__(
            self,
            "provenance_refs",
            _ids(self.provenance_refs, "provenance_ref"),
        )
        if not self.provenance_refs:
            raise MaintenanceError(
                "resource evidence requires explicit provenance"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": MAINTENANCE_SCHEMA,
                "evidence_id": self.evidence_id,
                "resource_id": self.resource_id,
                "observed_digest": self.observed_digest,
                "observed_at": self.observed_at.isoformat(),
                "last_activity_at": self.last_activity_at.isoformat(),
                "reachable": self.reachable,
                "active_migration": self.active_migration,
                "release_bound": self.release_bound,
                "evidence_bound": self.evidence_bound,
                "regeneration_receipt_digest": (
                    self.regeneration_receipt_digest
                ),
                "regeneration_source_refs": self.regeneration_source_refs,
                "provenance_refs": self.provenance_refs,
            }
        )


@dataclass(frozen=True, slots=True)
class MaintenanceTask:
    """Bounded maintenance intent; it never grants mutation authority alone."""

    task_id: str
    resource_id: str
    action: MaintenanceAction
    risk: MaintenanceRisk
    expected_digest: str
    authority_ref: str
    mutation_limit: int
    evidence_ttl_seconds: int
    stale_after_seconds: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _id(self.task_id, "task_id"))
        object.__setattr__(
            self,
            "resource_id",
            _id(self.resource_id, "resource_id"),
        )
        if not isinstance(self.action, MaintenanceAction):
            raise MaintenanceError("action must be MaintenanceAction")
        if not isinstance(self.risk, MaintenanceRisk):
            raise MaintenanceError("risk must be MaintenanceRisk")
        object.__setattr__(
            self,
            "expected_digest",
            _sha(self.expected_digest, "expected_digest"),
        )
        object.__setattr__(
            self,
            "authority_ref",
            _id(self.authority_ref, "authority_ref"),
        )
        object.__setattr__(
            self,
            "mutation_limit",
            _positive_int(
                self.mutation_limit,
                "mutation_limit",
                _MAX_MUTATIONS,
            ),
        )
        object.__setattr__(
            self,
            "evidence_ttl_seconds",
            _positive_int(
                self.evidence_ttl_seconds,
                "evidence_ttl_seconds",
                _MAX_AGE_SECONDS,
            ),
        )
        object.__setattr__(
            self,
            "stale_after_seconds",
            _positive_int(
                self.stale_after_seconds,
                "stale_after_seconds",
                _MAX_AGE_SECONDS,
            ),
        )
        if self.action is MaintenanceAction.DELETE and self.risk in (
            MaintenanceRisk.LOW,
            MaintenanceRisk.MEDIUM,
        ):
            raise MaintenanceError(
                "deletion cannot be classified below high risk"
            )
        if self.action is MaintenanceAction.INSPECT and self.risk in (
            MaintenanceRisk.HIGH,
            MaintenanceRisk.CRITICAL,
        ):
            raise MaintenanceError(
                "inspect-only task cannot be classified high/critical"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": MAINTENANCE_SCHEMA,
                "task_id": self.task_id,
                "resource_id": self.resource_id,
                "action": self.action.value,
                "risk": self.risk.value,
                "expected_digest": self.expected_digest,
                "authority_ref": self.authority_ref,
                "mutation_limit": self.mutation_limit,
                "evidence_ttl_seconds": self.evidence_ttl_seconds,
                "stale_after_seconds": self.stale_after_seconds,
            }
        )


@dataclass(frozen=True, slots=True)
class MaintenanceReceipt:
    """Authorization result bound to exact policy/evidence/time."""

    task_id: str
    task_digest: str
    resource_id: str
    ownership_digest: str
    evidence_digest: str | None
    authority_ref: str
    assessed_at: datetime
    decision: MaintenanceVerdict
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _id(self.task_id, "task_id"))
        object.__setattr__(
            self,
            "task_digest",
            _sha(self.task_digest, "task_digest"),
        )
        object.__setattr__(
            self,
            "resource_id",
            _id(self.resource_id, "resource_id"),
        )
        object.__setattr__(
            self,
            "ownership_digest",
            _sha(self.ownership_digest, "ownership_digest"),
        )
        if self.evidence_digest is not None:
            object.__setattr__(
                self,
                "evidence_digest",
                _sha(self.evidence_digest, "evidence_digest"),
            )
        object.__setattr__(
            self,
            "authority_ref",
            _id(self.authority_ref, "authority_ref"),
        )
        object.__setattr__(
            self,
            "assessed_at",
            _utc(self.assessed_at, "assessed_at"),
        )
        if not isinstance(self.decision, MaintenanceVerdict):
            raise MaintenanceError("decision must be MaintenanceVerdict")
        if not isinstance(self.reasons, tuple):
            raise MaintenanceError("reasons must be a tuple")
        reasons = tuple(
            sorted(_text(item, "reason", max_len=256) for item in self.reasons)
        )
        if len(reasons) != len(set(reasons)):
            raise MaintenanceError("receipt contains duplicate reasons")
        object.__setattr__(self, "reasons", reasons)
        if self.decision is MaintenanceVerdict.ALLOW and reasons:
            raise MaintenanceError("allowed receipt cannot contain blockers")
        if self.decision is MaintenanceVerdict.BLOCK and not reasons:
            raise MaintenanceError("blocked receipt requires reasons")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": MAINTENANCE_SCHEMA,
                "task_id": self.task_id,
                "task_digest": self.task_digest,
                "resource_id": self.resource_id,
                "ownership_digest": self.ownership_digest,
                "evidence_digest": self.evidence_digest,
                "authority_ref": self.authority_ref,
                "assessed_at": self.assessed_at.isoformat(),
                "decision": self.decision.value,
                "reasons": self.reasons,
            }
        )


@dataclass(frozen=True, slots=True)
class MaintenancePlan:
    registry_digest: str
    assessed_at: datetime
    receipts: tuple[MaintenanceReceipt, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "registry_digest",
            _sha(self.registry_digest, "registry_digest"),
        )
        object.__setattr__(
            self,
            "assessed_at",
            _utc(self.assessed_at, "assessed_at"),
        )
        if not isinstance(self.receipts, tuple):
            raise MaintenanceError("receipts must be a tuple")
        if any(
            not isinstance(item, MaintenanceReceipt)
            for item in self.receipts
        ):
            raise MaintenanceError("plan contains invalid receipt")
        ordered = tuple(
            sorted(
                self.receipts,
                key=lambda item: (item.resource_id, item.task_id),
            )
        )
        task_ids = [item.task_id for item in ordered]
        if len(task_ids) != len(set(task_ids)):
            raise MaintenanceError("plan contains duplicate task identity")
        object.__setattr__(self, "receipts", ordered)

    @property
    def allowed(self) -> tuple[MaintenanceReceipt, ...]:
        return tuple(
            item
            for item in self.receipts
            if item.decision is MaintenanceVerdict.ALLOW
        )

    @property
    def blocked(self) -> tuple[MaintenanceReceipt, ...]:
        return tuple(
            item
            for item in self.receipts
            if item.decision is MaintenanceVerdict.BLOCK
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": MAINTENANCE_SCHEMA,
                "registry_digest": self.registry_digest,
                "assessed_at": self.assessed_at.isoformat(),
                "receipts": [item.digest for item in self.receipts],
            }
        )


def authorize(
    task: MaintenanceTask,
    ownership: RepositoryOwnership,
    evidence: ResourceEvidence | None,
    *,
    at: datetime,
) -> MaintenanceReceipt:
    if not isinstance(task, MaintenanceTask):
        raise TypeError("task must be MaintenanceTask")
    if not isinstance(ownership, RepositoryOwnership):
        raise TypeError("ownership must be RepositoryOwnership")
    if evidence is not None and not isinstance(evidence, ResourceEvidence):
        raise TypeError("evidence must be ResourceEvidence or None")

    now = _utc(at, "assessment time")
    if task.resource_id != ownership.resource_id:
        raise MaintenanceError("task/ownership resource mismatch")
    if evidence is not None and evidence.resource_id != task.resource_id:
        raise MaintenanceError("resource evidence mismatch")

    reasons: list[str] = []
    if (
        task.action in (MaintenanceAction.UPDATE, MaintenanceAction.DELETE)
        and task.authority_ref not in ownership.mutation_authority_refs
    ):
        reasons.append("mutation_authority_not_owned")

    if task.action is MaintenanceAction.INSPECT:
        return MaintenanceReceipt(
            task_id=task.task_id,
            task_digest=task.digest,
            resource_id=task.resource_id,
            ownership_digest=ownership.digest,
            evidence_digest=evidence.digest if evidence else None,
            authority_ref=task.authority_ref,
            assessed_at=now,
            decision=MaintenanceVerdict.ALLOW,
            reasons=(),
        )

    if evidence is None:
        reasons.append("missing_resource_evidence")
    else:
        if evidence.observed_at > now:
            reasons.append("evidence_observed_in_future")
        elif (
            now - evidence.observed_at
        ).total_seconds() > task.evidence_ttl_seconds:
            reasons.append("resource_evidence_stale")
        if evidence.observed_digest != task.expected_digest:
            reasons.append("resource_changed_since_observation")

    if task.action is MaintenanceAction.DELETE:
        if (
            ownership.repository_path is not None
            and any(
                _under(ownership.repository_path, prefix)
                for prefix in _NON_WAIVABLE_PROTECTED_PATHS
            )
        ):
            reasons.append("non_waivable_protected_path")
        if ownership.ownership in (
            OwnershipClass.ACTIVE,
            OwnershipClass.MIGRATION,
            OwnershipClass.RELEASE,
            OwnershipClass.EVIDENCE,
        ):
            reasons.append(
                f"protected_ownership:{ownership.ownership.value}"
            )
        if ownership.active_refs:
            reasons.append("active_references")
        if ownership.preservation_refs:
            reasons.append("preservation_references")
        if (
            ownership.retention_until is not None
            and ownership.retention_until > now
        ):
            reasons.append("retention_not_satisfied")

        if evidence is not None:
            activity_age = (
                now - evidence.last_activity_at
            ).total_seconds()
            if activity_age < task.stale_after_seconds:
                reasons.append("resource_not_stale")
            if evidence.reachable:
                reasons.append("resource_reachable")
            if evidence.active_migration:
                reasons.append("active_migration")
            if evidence.release_bound:
                reasons.append("release_bound")
            if evidence.evidence_bound:
                reasons.append("evidence_bound")
            if ownership.ownership is OwnershipClass.GENERATED:
                if evidence.regeneration_receipt_digest is None:
                    reasons.append("generated_regeneration_unproven")
                elif (
                    evidence.regeneration_source_refs
                    != ownership.generation_source_refs
                ):
                    reasons.append(
                        "generated_regeneration_sources_mismatch"
                    )

    decision = (
        MaintenanceVerdict.BLOCK
        if reasons
        else MaintenanceVerdict.ALLOW
    )
    return MaintenanceReceipt(
        task_id=task.task_id,
        task_digest=task.digest,
        resource_id=task.resource_id,
        ownership_digest=ownership.digest,
        evidence_digest=evidence.digest if evidence else None,
        authority_ref=task.authority_ref,
        assessed_at=now,
        decision=decision,
        reasons=tuple(sorted(set(reasons))),
    )


class MaintenanceRegistry:
    """Immutable resource ownership registry and deterministic planner."""

    def __init__(self, ownership: Iterable[RepositoryOwnership]) -> None:
        items = tuple(sorted(ownership, key=lambda item: item.resource_id))
        if not items or len(items) > _MAX_RESOURCES:
            raise MaintenanceError(
                "ownership registry size is outside policy bounds"
            )
        if any(
            not isinstance(item, RepositoryOwnership)
            for item in items
        ):
            raise MaintenanceError(
                "ownership registry contains invalid resource"
            )
        ids = [item.resource_id for item in items]
        if len(ids) != len(set(ids)):
            raise MaintenanceError("duplicate resource ownership identity")
        paths = [
            item.repository_path
            for item in items
            if item.repository_path is not None
        ]
        if len(paths) != len(set(paths)):
            raise MaintenanceError("duplicate repository path ownership")
        self.ownership = items
        self._by_id = {item.resource_id: item for item in items}

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": MAINTENANCE_SCHEMA,
                "ownership": [item.digest for item in self.ownership],
            }
        )

    def get(self, resource_id: str) -> RepositoryOwnership:
        key = _id(resource_id, "resource_id")
        item = self._by_id.get(key)
        if item is None:
            raise MaintenanceError("resource lacks ownership policy")
        return item

    def plan(
        self,
        tasks: Iterable[MaintenanceTask],
        evidence: Iterable[ResourceEvidence],
        *,
        at: datetime,
    ) -> MaintenancePlan:
        now = _utc(at, "assessment time")
        task_items = tuple(tasks)
        evidence_items = tuple(evidence)
        if len(task_items) > _MAX_TASKS:
            raise MaintenanceError("maintenance task set exceeds policy bound")
        if len(evidence_items) > _MAX_EVIDENCE:
            raise MaintenanceError(
                "maintenance evidence set exceeds policy bound"
            )
        if any(
            not isinstance(item, MaintenanceTask)
            for item in task_items
        ):
            raise MaintenanceError(
                "maintenance task set contains invalid task"
            )
        if any(
            not isinstance(item, ResourceEvidence)
            for item in evidence_items
        ):
            raise MaintenanceError(
                "maintenance evidence set contains invalid evidence"
            )

        task_ids = [item.task_id for item in task_items]
        if len(task_ids) != len(set(task_ids)):
            raise MaintenanceError("duplicate maintenance task identity")
        task_resources = [item.resource_id for item in task_items]
        if len(task_resources) != len(set(task_resources)):
            raise MaintenanceError(
                "multiple maintenance tasks for one resource are ambiguous"
            )

        deletion_paths: list[str] = []
        for item in task_items:
            if item.action is not MaintenanceAction.DELETE:
                continue
            policy = self.get(item.resource_id)
            if policy.repository_path is not None:
                deletion_paths.append(policy.repository_path)
        deletion_paths.sort()
        for index, left in enumerate(deletion_paths):
            for right in deletion_paths[index + 1 :]:
                if _under(left, right) or _under(right, left):
                    raise MaintenanceError(
                        "overlapping repository deletion paths"
                    )

        evidence_ids = [item.evidence_id for item in evidence_items]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise MaintenanceError("duplicate resource evidence identity")

        evidence_by_resource: dict[str, ResourceEvidence] = {}
        for item in evidence_items:
            if item.resource_id in evidence_by_resource:
                raise MaintenanceError(
                    "multiple evidence snapshots for one resource are ambiguous"
                )
            evidence_by_resource[item.resource_id] = item

        receipts = tuple(
            authorize(
                task,
                self.get(task.resource_id),
                evidence_by_resource.get(task.resource_id),
                at=now,
            )
            for task in task_items
        )
        return MaintenancePlan(
            registry_digest=self.digest,
            assessed_at=now,
            receipts=receipts,
        )


def enforce_mutation_budget(
    task: MaintenanceTask,
    ownership: RepositoryOwnership,
    evidence: ResourceEvidence,
    receipt: MaintenanceReceipt,
    mutation_count: int,
    *,
    at: datetime,
) -> None:
    """Recompute exact authorization immediately before mutation."""

    if not isinstance(receipt, MaintenanceReceipt):
        raise TypeError("receipt must be MaintenanceReceipt")
    expected = authorize(task, ownership, evidence, at=at)
    if receipt != expected:
        raise MaintenanceError(
            "receipt does not match current authorization inputs"
        )
    if receipt.decision is not MaintenanceVerdict.ALLOW:
        raise MaintenanceError("blocked maintenance task cannot mutate")
    count = _positive_int(
        mutation_count,
        "mutation_count",
        _MAX_MUTATIONS,
    )
    if count > task.mutation_limit:
        raise MaintenanceError("mutation batch exceeds task limit")


def plan_summary(plan: MaintenancePlan) -> Mapping[str, object]:
    if not isinstance(plan, MaintenancePlan):
        raise TypeError("plan must be MaintenancePlan")
    return {
        "schema": MAINTENANCE_SCHEMA,
        "registry_digest": plan.registry_digest,
        "assessed_at": plan.assessed_at.isoformat(),
        "plan_digest": plan.digest,
        "allowed_count": len(plan.allowed),
        "blocked_count": len(plan.blocked),
        "receipts": [
            {
                "task_id": item.task_id,
                "resource_id": item.resource_id,
                "decision": item.decision.value,
                "reasons": list(item.reasons),
                "receipt_digest": item.digest,
            }
            for item in plan.receipts
        ],
    }


__all__ = [
    "MAINTENANCE_SCHEMA",
    "DeletionAssessment",
    "MaintenanceAction",
    "MaintenanceDecision",
    "MaintenanceError",
    "MaintenancePlan",
    "MaintenancePolicyError",
    "MaintenanceReceipt",
    "MaintenanceRegistry",
    "MaintenanceRisk",
    "MaintenanceTask",
    "MaintenanceVerdict",
    "OwnershipClass",
    "RepositoryOwnership",
    "ResourceEvidence",
    "ResourceKind",
    "authorize",
    "enforce_mutation_budget",
    "evaluate_batch",
    "evaluate_deletion",
    "plan_summary",
]
