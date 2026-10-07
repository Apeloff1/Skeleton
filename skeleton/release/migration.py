"""P1 migration and rollback compatibility qualification.

This module is evidence-only. It does not mutate schema, configuration, or
runtime state. It proves that migrations bound to the exact accepted REL-02
installer lifecycle can move forward, roll back to the exact prior snapshot,
and remain backward-readable during a declared compatibility window.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef
from skeleton.release.lifecycle import (
    InstallerLifecycleQualificationDecision,
)


MIGRATION_COMPATIBILITY_SCHEMA_VERSION = 1
MIGRATION_COMPATIBILITY_TASK_ID = "P1-REL-03"
MIGRATION_COMPATIBILITY_ACCOUNTABILITY_ID = "ACC-P1-REL-03"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")


class MigrationCompatibilityError(ValueError):
    """Migration compatibility evidence is malformed or incomplete."""


class MigrationKind(str, Enum):
    SCHEMA = "schema"
    CONFIG = "config"
    STATE = "state"


def _token(value: object, field: str, *, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or not _TOKEN_RE.fullmatch(value)
    ):
        raise MigrationCompatibilityError(
            f"{field} must be a canonical token"
        )
    return value


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MigrationCompatibilityError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise MigrationCompatibilityError(f"{field} must be normalized")
    return normalized


def _sha40(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA40_RE.fullmatch(value):
        raise MigrationCompatibilityError(
            f"{field} must be lowercase 40-character git SHA"
        )
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise MigrationCompatibilityError(
            f"{field} must be lowercase sha256"
        )
    return value


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MigrationCompatibilityError(
            "migration compatibility payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _tokens(
    values: Iterable[str],
    field: str,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise MigrationCompatibilityError(f"{field} must be an iterable")
    normalized = tuple(sorted({_token(item, field) for item in values}))
    if not normalized:
        raise MigrationCompatibilityError(f"{field} must be non-empty")
    return normalized


def _evidence(
    values: Iterable[EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise MigrationCompatibilityError(
            "evidence_refs must contain EvidenceRef values"
        )
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise MigrationCompatibilityError(
                "evidence_refs must contain EvidenceRef values"
            )
        _text(item.source, "evidence.source")
        _sha256(item.digest, "evidence.digest")
        _token(item.category, "evidence.category", maximum=128)
        by_key[(item.source, item.digest, item.category)] = item
    if not by_key:
        raise MigrationCompatibilityError(
            "evidence_refs must be non-empty"
        )
    return tuple(by_key[key] for key in sorted(by_key))


@dataclass(frozen=True, slots=True)
class MigrationSpec:
    migration_id: str
    kind: MigrationKind
    from_version: str
    to_version: str
    forward_migration_digest: str
    rollback_migration_digest: str
    backward_reader_digest: str
    declared_reader_versions: tuple[str, ...]
    irreversible: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "migration_id",
            _token(self.migration_id, "migration_id"),
        )
        try:
            object.__setattr__(
                self,
                "kind",
                MigrationKind(self.kind),
            )
        except ValueError as exc:
            raise MigrationCompatibilityError(
                "invalid migration kind"
            ) from exc
        for field in ("from_version", "to_version"):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        if self.from_version == self.to_version:
            raise MigrationCompatibilityError(
                "migration versions must differ"
            )
        for field in (
            "forward_migration_digest",
            "rollback_migration_digest",
            "backward_reader_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "declared_reader_versions",
            _tokens(
                self.declared_reader_versions,
                "declared_reader_versions",
            ),
        )
        if self.from_version not in self.declared_reader_versions:
            raise MigrationCompatibilityError(
                "rollback source version must be a declared compatible reader"
            )
        if not isinstance(self.irreversible, bool):
            raise MigrationCompatibilityError(
                "irreversible must be boolean"
            )
        if self.irreversible:
            raise MigrationCompatibilityError(
                "REL-03 cannot qualify irreversible migration"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "migration_id": self.migration_id,
            "kind": self.kind.value,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "forward_migration_digest": self.forward_migration_digest,
            "rollback_migration_digest": self.rollback_migration_digest,
            "backward_reader_digest": self.backward_reader_digest,
            "declared_reader_versions": list(
                self.declared_reader_versions
            ),
            "irreversible": self.irreversible,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    plan_id: str
    source_commit: str
    lifecycle_qualification_digest: str
    from_version: str
    to_version: str
    rollback_window_digest: str
    migrations: tuple[MigrationSpec, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "plan_id",
            _token(self.plan_id, "plan_id"),
        )
        object.__setattr__(
            self,
            "source_commit",
            _sha40(self.source_commit, "source_commit"),
        )
        object.__setattr__(
            self,
            "lifecycle_qualification_digest",
            _sha256(
                self.lifecycle_qualification_digest,
                "lifecycle_qualification_digest",
            ),
        )
        for field in ("from_version", "to_version"):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        if self.from_version == self.to_version:
            raise MigrationCompatibilityError(
                "plan versions must differ"
            )
        object.__setattr__(
            self,
            "rollback_window_digest",
            _sha256(
                self.rollback_window_digest,
                "rollback_window_digest",
            ),
        )
        if not isinstance(self.migrations, tuple) or not self.migrations:
            raise MigrationCompatibilityError(
                "migrations must be a non-empty tuple"
            )
        if any(
            not isinstance(item, MigrationSpec)
            for item in self.migrations
        ):
            raise MigrationCompatibilityError(
                "migrations must contain MigrationSpec"
            )
        ids = [item.migration_id for item in self.migrations]
        if len(ids) != len(set(ids)):
            raise MigrationCompatibilityError(
                "migration IDs must be unique"
            )
        for item in self.migrations:
            if item.from_version != self.from_version:
                raise MigrationCompatibilityError(
                    f"{item.migration_id}: from_version drift"
                )
            if item.to_version != self.to_version:
                raise MigrationCompatibilityError(
                    f"{item.migration_id}: to_version drift"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "source_commit": self.source_commit,
            "lifecycle_qualification_digest": (
                self.lifecycle_qualification_digest
            ),
            "from_version": self.from_version,
            "to_version": self.to_version,
            "rollback_window_digest": self.rollback_window_digest,
            "migrations": [
                item.payload()
                for item in sorted(
                    self.migrations,
                    key=lambda row: row.migration_id,
                )
            ],
        }

    @property
    def plan_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class MigrationCompatibilityReceipt:
    migration_id: str
    migration_digest: str
    source_commit: str
    lifecycle_qualification_digest: str
    rollback_window_digest: str
    from_version: str
    to_version: str
    pre_migration_snapshot_digest: str
    upgraded_snapshot_digest: str
    rollback_snapshot_digest: str
    backward_read_source_digest: str
    forward_migration_digest: str
    rollback_migration_digest: str
    backward_reader_digest: str
    reader_version: str
    verifier_id: str
    verifier_digest: str
    test_manifest_digest: str
    evidence_refs: tuple[EvidenceRef, ...]
    forward_applied: bool = True
    rollback_succeeded: bool = True
    backward_read_succeeded: bool = True
    independent: bool = True
    production_mutation_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "migration_id",
            _token(self.migration_id, "migration_id"),
        )
        object.__setattr__(
            self,
            "source_commit",
            _sha40(self.source_commit, "source_commit"),
        )
        for field in (
            "migration_digest",
            "lifecycle_qualification_digest",
            "rollback_window_digest",
            "pre_migration_snapshot_digest",
            "upgraded_snapshot_digest",
            "rollback_snapshot_digest",
            "backward_read_source_digest",
            "forward_migration_digest",
            "rollback_migration_digest",
            "backward_reader_digest",
            "verifier_digest",
            "test_manifest_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        for field in ("from_version", "to_version", "reader_version"):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "verifier_id",
            _token(self.verifier_id, "verifier_id"),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence(self.evidence_refs),
        )
        for field in (
            "forward_applied",
            "rollback_succeeded",
            "backward_read_succeeded",
            "independent",
        ):
            if not isinstance(getattr(self, field), bool):
                raise MigrationCompatibilityError(
                    f"{field} must be boolean"
                )
        if (
            isinstance(self.production_mutation_count, bool)
            or not isinstance(self.production_mutation_count, int)
            or self.production_mutation_count < 0
        ):
            raise MigrationCompatibilityError(
                "production_mutation_count must be non-negative integer"
            )
        if "migration_compatibility" not in {
            item.category for item in self.evidence_refs
        }:
            raise MigrationCompatibilityError(
                "receipt requires migration_compatibility evidence"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "migration_id": self.migration_id,
            "migration_digest": self.migration_digest,
            "source_commit": self.source_commit,
            "lifecycle_qualification_digest": (
                self.lifecycle_qualification_digest
            ),
            "rollback_window_digest": self.rollback_window_digest,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "pre_migration_snapshot_digest": (
                self.pre_migration_snapshot_digest
            ),
            "upgraded_snapshot_digest": self.upgraded_snapshot_digest,
            "rollback_snapshot_digest": self.rollback_snapshot_digest,
            "backward_read_source_digest": (
                self.backward_read_source_digest
            ),
            "forward_migration_digest": self.forward_migration_digest,
            "rollback_migration_digest": self.rollback_migration_digest,
            "backward_reader_digest": self.backward_reader_digest,
            "reader_version": self.reader_version,
            "verifier_id": self.verifier_id,
            "verifier_digest": self.verifier_digest,
            "test_manifest_digest": self.test_manifest_digest,
            "evidence_refs": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence_refs
            ],
            "forward_applied": self.forward_applied,
            "rollback_succeeded": self.rollback_succeeded,
            "backward_read_succeeded": self.backward_read_succeeded,
            "independent": self.independent,
            "production_mutation_count": self.production_mutation_count,
        }

    @property
    def receipt_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class MigrationCompatibilityDecision:
    accepted: bool
    reasons: tuple[str, ...]
    source_commit: str
    lifecycle_qualification_digest: str
    plan_digest: str
    rollback_window_digest: str
    from_version: str
    to_version: str
    receipt_digests: tuple[str, ...]
    task_id: str = MIGRATION_COMPATIBILITY_TASK_ID
    accountability_id: str = MIGRATION_COMPATIBILITY_ACCOUNTABILITY_ID
    schema_version: int = MIGRATION_COMPATIBILITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise MigrationCompatibilityError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise MigrationCompatibilityError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "source_commit",
            _sha40(self.source_commit, "source_commit"),
        )
        for field in (
            "lifecycle_qualification_digest",
            "plan_digest",
            "rollback_window_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        for field in ("from_version", "to_version"):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        if not isinstance(self.receipt_digests, tuple):
            raise MigrationCompatibilityError(
                "receipt_digests must be tuple"
            )
        object.__setattr__(
            self,
            "receipt_digests",
            tuple(
                sorted(
                    {
                        _sha256(item, "receipt_digests")
                        for item in self.receipt_digests
                    }
                )
            ),
        )
        if self.task_id != MIGRATION_COMPATIBILITY_TASK_ID:
            raise MigrationCompatibilityError("task_id drift")
        if self.accountability_id != MIGRATION_COMPATIBILITY_ACCOUNTABILITY_ID:
            raise MigrationCompatibilityError("accountability_id drift")
        if self.schema_version != MIGRATION_COMPATIBILITY_SCHEMA_VERSION:
            raise MigrationCompatibilityError(
                "unsupported migration compatibility schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "source_commit": self.source_commit,
            "lifecycle_qualification_digest": (
                self.lifecycle_qualification_digest
            ),
            "plan_digest": self.plan_digest,
            "rollback_window_digest": self.rollback_window_digest,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "receipt_digests": list(self.receipt_digests),
            "production_authority": False,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise MigrationCompatibilityError(
                "rejected migration compatibility cannot become promotion evidence"
            )
        return EvidenceRef(
            source=f"p1:rel-03:migration:{self.source_commit}",
            digest=self.decision_digest,
            category="migration_rollback_compatibility",
        )


def qualify_migration_compatibility(
    *,
    lifecycle_qualification: InstallerLifecycleQualificationDecision,
    plan: MigrationPlan,
    receipts: Iterable[MigrationCompatibilityReceipt],
) -> MigrationCompatibilityDecision:
    if not isinstance(
        lifecycle_qualification,
        InstallerLifecycleQualificationDecision,
    ):
        raise TypeError(
            "lifecycle_qualification must be "
            "InstallerLifecycleQualificationDecision"
        )
    if not isinstance(plan, MigrationPlan):
        raise TypeError("plan must be MigrationPlan")
    rows = tuple(receipts)
    if any(
        not isinstance(item, MigrationCompatibilityReceipt)
        for item in rows
    ):
        raise TypeError(
            "receipts must contain MigrationCompatibilityReceipt"
        )

    reasons: list[str] = []
    if not lifecycle_qualification.accepted:
        reasons.append("lifecycle-qualification-rejected")
    if plan.source_commit != lifecycle_qualification.source_commit:
        reasons.append("plan-source-commit-mismatch")
    if (
        plan.lifecycle_qualification_digest
        != lifecycle_qualification.decision_digest
    ):
        reasons.append("plan-lifecycle-digest-mismatch")
    if plan.to_version != lifecycle_qualification.target_version:
        reasons.append("plan-target-version-mismatch")

    by_id: dict[str, list[MigrationCompatibilityReceipt]] = {
        item.migration_id: [] for item in plan.migrations
    }
    for receipt in rows:
        if receipt.migration_id not in by_id:
            reasons.append(
                f"unexpected-migration-receipt:{receipt.migration_id}"
            )
            continue
        by_id[receipt.migration_id].append(receipt)

    for spec in plan.migrations:
        matches = by_id[spec.migration_id]
        if len(matches) != 1:
            reasons.append(
                f"receipt-cardinality:{spec.migration_id}"
            )
            continue
        receipt = matches[0]
        prefix = spec.migration_id
        if receipt.migration_digest != spec.digest:
            reasons.append(f"{prefix}:migration-digest-mismatch")
        if receipt.source_commit != plan.source_commit:
            reasons.append(f"{prefix}:source-commit-mismatch")
        if (
            receipt.lifecycle_qualification_digest
            != plan.lifecycle_qualification_digest
        ):
            reasons.append(f"{prefix}:lifecycle-digest-mismatch")
        if receipt.rollback_window_digest != plan.rollback_window_digest:
            reasons.append(f"{prefix}:rollback-window-mismatch")
        if receipt.from_version != spec.from_version:
            reasons.append(f"{prefix}:from-version-mismatch")
        if receipt.to_version != spec.to_version:
            reasons.append(f"{prefix}:to-version-mismatch")
        if receipt.forward_migration_digest != spec.forward_migration_digest:
            reasons.append(f"{prefix}:forward-migration-mismatch")
        if receipt.rollback_migration_digest != spec.rollback_migration_digest:
            reasons.append(f"{prefix}:rollback-migration-mismatch")
        if receipt.backward_reader_digest != spec.backward_reader_digest:
            reasons.append(f"{prefix}:backward-reader-mismatch")
        if receipt.reader_version not in spec.declared_reader_versions:
            reasons.append(f"{prefix}:reader-version-outside-window")
        if receipt.reader_version != spec.from_version:
            reasons.append(f"{prefix}:rollback-reader-version-mismatch")
        if not receipt.forward_applied:
            reasons.append(f"{prefix}:forward-not-applied")
        if not receipt.rollback_succeeded:
            reasons.append(f"{prefix}:rollback-failed")
        if not receipt.backward_read_succeeded:
            reasons.append(f"{prefix}:backward-read-failed")
        if not receipt.independent:
            reasons.append(f"{prefix}:not-independent")
        if receipt.production_mutation_count != 0:
            reasons.append(f"{prefix}:production-mutated")
        if (
            receipt.rollback_snapshot_digest
            != receipt.pre_migration_snapshot_digest
        ):
            reasons.append(f"{prefix}:rollback-snapshot-mismatch")
        if (
            receipt.backward_read_source_digest
            != receipt.upgraded_snapshot_digest
        ):
            reasons.append(f"{prefix}:backward-read-source-mismatch")

    normalized = tuple(sorted(set(reasons)))
    return MigrationCompatibilityDecision(
        accepted=not normalized,
        reasons=normalized,
        source_commit=lifecycle_qualification.source_commit,
        lifecycle_qualification_digest=(
            lifecycle_qualification.decision_digest
        ),
        plan_digest=plan.plan_digest,
        rollback_window_digest=plan.rollback_window_digest,
        from_version=plan.from_version,
        to_version=plan.to_version,
        receipt_digests=tuple(
            item.receipt_digest for item in rows
        ),
    )


__all__ = [
    "MIGRATION_COMPATIBILITY_ACCOUNTABILITY_ID",
    "MIGRATION_COMPATIBILITY_SCHEMA_VERSION",
    "MIGRATION_COMPATIBILITY_TASK_ID",
    "MigrationCompatibilityDecision",
    "MigrationCompatibilityError",
    "MigrationCompatibilityReceipt",
    "MigrationKind",
    "MigrationPlan",
    "MigrationSpec",
    "qualify_migration_compatibility",
]
