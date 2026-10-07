"""P1 backup and restore qualification.

This module is evidence-only. It does not create backups or mutate restored
state. It distinguishes authoritative state, which must be restored without
semantic loss, from derived state, which must be deterministically rebuilt from
the exact authoritative restore set and a declared rebuild recipe.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef
from skeleton.release.migration import MigrationCompatibilityDecision


BACKUP_RESTORE_SCHEMA_VERSION = 1
BACKUP_RESTORE_TASK_ID = "P1-REL-04"
BACKUP_RESTORE_ACCOUNTABILITY_ID = "ACC-P1-REL-04"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")


class BackupRestoreError(ValueError):
    """Backup/restore evidence is malformed or incomplete."""


class BackupComponentRole(str, Enum):
    AUTHORITATIVE = "authoritative"
    DERIVED = "derived"


def _token(value: object, field: str, *, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or not _TOKEN_RE.fullmatch(value)
    ):
        raise BackupRestoreError(f"{field} must be a canonical token")
    return value


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BackupRestoreError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise BackupRestoreError(f"{field} must be normalized")
    return normalized


def _sha40(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA40_RE.fullmatch(value):
        raise BackupRestoreError(
            f"{field} must be lowercase 40-character git SHA"
        )
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise BackupRestoreError(f"{field} must be lowercase sha256")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise BackupRestoreError(f"{field} must be a positive integer")
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
        raise BackupRestoreError(
            "backup/restore payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _tokens(
    values: Iterable[str],
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise BackupRestoreError(f"{field} must be an iterable")
    normalized = tuple(sorted({_token(item, field) for item in values}))
    if not normalized and not allow_empty:
        raise BackupRestoreError(f"{field} must be non-empty")
    return normalized


def _evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise BackupRestoreError(
            "evidence_refs must contain EvidenceRef values"
        )
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise BackupRestoreError(
                "evidence_refs must contain EvidenceRef values"
            )
        _text(item.source, "evidence.source")
        _sha256(item.digest, "evidence.digest")
        _token(item.category, "evidence.category", maximum=128)
        by_key[(item.source, item.digest, item.category)] = item
    if not by_key:
        raise BackupRestoreError("evidence_refs must be non-empty")
    return tuple(by_key[key] for key in sorted(by_key))


@dataclass(frozen=True, slots=True)
class BackupComponent:
    component_id: str
    role: BackupComponentRole
    source_state_digest: str
    restore_order: int
    dependencies: tuple[str, ...] = ()
    backup_artifact_digest: str | None = None
    rebuild_recipe_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "component_id",
            _token(self.component_id, "component_id"),
        )
        try:
            object.__setattr__(
                self,
                "role",
                BackupComponentRole(self.role),
            )
        except ValueError as exc:
            raise BackupRestoreError(
                "invalid backup component role"
            ) from exc
        object.__setattr__(
            self,
            "source_state_digest",
            _sha256(self.source_state_digest, "source_state_digest"),
        )
        object.__setattr__(
            self,
            "restore_order",
            _positive_int(self.restore_order, "restore_order"),
        )
        object.__setattr__(
            self,
            "dependencies",
            _tokens(self.dependencies, "dependencies"),
        )
        if self.component_id in self.dependencies:
            raise BackupRestoreError(
                "component cannot depend on itself"
            )
        if self.backup_artifact_digest is not None:
            object.__setattr__(
                self,
                "backup_artifact_digest",
                _sha256(
                    self.backup_artifact_digest,
                    "backup_artifact_digest",
                ),
            )
        if self.rebuild_recipe_digest is not None:
            object.__setattr__(
                self,
                "rebuild_recipe_digest",
                _sha256(
                    self.rebuild_recipe_digest,
                    "rebuild_recipe_digest",
                ),
            )
        if self.role is BackupComponentRole.AUTHORITATIVE:
            if self.backup_artifact_digest is None:
                raise BackupRestoreError(
                    "authoritative component requires backup artifact"
                )
            if self.rebuild_recipe_digest is not None:
                raise BackupRestoreError(
                    "authoritative component cannot rely on rebuild recipe"
                )
        else:
            if self.rebuild_recipe_digest is None:
                raise BackupRestoreError(
                    "derived component requires rebuild recipe"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "role": self.role.value,
            "source_state_digest": self.source_state_digest,
            "restore_order": self.restore_order,
            "dependencies": list(self.dependencies),
            "backup_artifact_digest": self.backup_artifact_digest,
            "rebuild_recipe_digest": self.rebuild_recipe_digest,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class BackupManifest:
    backup_id: str
    source_commit: str
    migration_compatibility_digest: str
    components: tuple[BackupComponent, ...]
    backup_environment_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "backup_id",
            _token(self.backup_id, "backup_id"),
        )
        object.__setattr__(
            self,
            "source_commit",
            _sha40(self.source_commit, "source_commit"),
        )
        object.__setattr__(
            self,
            "migration_compatibility_digest",
            _sha256(
                self.migration_compatibility_digest,
                "migration_compatibility_digest",
            ),
        )
        object.__setattr__(
            self,
            "backup_environment_digest",
            _sha256(
                self.backup_environment_digest,
                "backup_environment_digest",
            ),
        )
        if not isinstance(self.components, tuple) or not self.components:
            raise BackupRestoreError(
                "components must be a non-empty tuple"
            )
        if any(
            not isinstance(item, BackupComponent)
            for item in self.components
        ):
            raise BackupRestoreError(
                "components must contain BackupComponent"
            )
        ids = [item.component_id for item in self.components]
        orders = [item.restore_order for item in self.components]
        if len(ids) != len(set(ids)):
            raise BackupRestoreError(
                "component IDs must be unique"
            )
        if len(orders) != len(set(orders)):
            raise BackupRestoreError(
                "restore order values must be unique"
            )
        by_id = {
            item.component_id: item for item in self.components
        }
        authoritative = [
            item
            for item in self.components
            if item.role is BackupComponentRole.AUTHORITATIVE
        ]
        if not authoritative:
            raise BackupRestoreError(
                "manifest requires authoritative state"
            )
        for item in self.components:
            for dependency in item.dependencies:
                if dependency not in by_id:
                    raise BackupRestoreError(
                        f"{item.component_id}: unknown dependency"
                    )
                if by_id[dependency].restore_order >= item.restore_order:
                    raise BackupRestoreError(
                        f"{item.component_id}: dependency restore order invalid"
                    )
            if (
                item.role is BackupComponentRole.DERIVED
                and not item.dependencies
            ):
                raise BackupRestoreError(
                    f"{item.component_id}: derived component requires restore dependencies"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "source_commit": self.source_commit,
            "migration_compatibility_digest": (
                self.migration_compatibility_digest
            ),
            "backup_environment_digest": self.backup_environment_digest,
            "components": [
                item.payload()
                for item in sorted(
                    self.components,
                    key=lambda row: row.restore_order,
                )
            ],
        }

    @property
    def manifest_digest(self) -> str:
        return _canonical_digest(self.payload())

    @property
    def authoritative_state_digest(self) -> str:
        return _canonical_digest(
            [
                {
                    "component_id": item.component_id,
                    "source_state_digest": item.source_state_digest,
                }
                for item in sorted(
                    (
                        row
                        for row in self.components
                        if row.role
                        is BackupComponentRole.AUTHORITATIVE
                    ),
                    key=lambda row: row.component_id,
                )
            ]
        )


@dataclass(frozen=True, slots=True)
class RestoreComponentReceipt:
    component_id: str
    component_digest: str
    source_commit: str
    manifest_digest: str
    restore_order: int
    completed_dependencies: tuple[str, ...]
    verifier_id: str
    verifier_digest: str
    test_manifest_digest: str
    evidence_refs: tuple[EvidenceRef, ...]
    observed_backup_artifact_digest: str | None = None
    restored_state_digest: str | None = None
    rebuild_recipe_digest: str | None = None
    rebuild_input_digest: str | None = None
    rebuilt_state_digest: str | None = None
    restored: bool = False
    rebuilt: bool = False
    independent: bool = True
    production_mutation_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "component_id",
            _token(self.component_id, "component_id"),
        )
        object.__setattr__(
            self,
            "source_commit",
            _sha40(self.source_commit, "source_commit"),
        )
        for field in (
            "component_digest",
            "manifest_digest",
            "verifier_digest",
            "test_manifest_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        for field in (
            "observed_backup_artifact_digest",
            "restored_state_digest",
            "rebuild_recipe_digest",
            "rebuild_input_digest",
            "rebuilt_state_digest",
        ):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(
                    self,
                    field,
                    _sha256(value, field),
                )
        object.__setattr__(
            self,
            "restore_order",
            _positive_int(self.restore_order, "restore_order"),
        )
        object.__setattr__(
            self,
            "completed_dependencies",
            _tokens(
                self.completed_dependencies,
                "completed_dependencies",
            ),
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
        for field in ("restored", "rebuilt", "independent"):
            if not isinstance(getattr(self, field), bool):
                raise BackupRestoreError(f"{field} must be boolean")
        if (
            isinstance(self.production_mutation_count, bool)
            or not isinstance(self.production_mutation_count, int)
            or self.production_mutation_count < 0
        ):
            raise BackupRestoreError(
                "production_mutation_count must be non-negative integer"
            )
        if "restore_drill" not in {
            item.category for item in self.evidence_refs
        }:
            raise BackupRestoreError(
                "receipt requires restore_drill evidence"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "component_digest": self.component_digest,
            "source_commit": self.source_commit,
            "manifest_digest": self.manifest_digest,
            "restore_order": self.restore_order,
            "completed_dependencies": list(
                self.completed_dependencies
            ),
            "observed_backup_artifact_digest": (
                self.observed_backup_artifact_digest
            ),
            "restored_state_digest": self.restored_state_digest,
            "rebuild_recipe_digest": self.rebuild_recipe_digest,
            "rebuild_input_digest": self.rebuild_input_digest,
            "rebuilt_state_digest": self.rebuilt_state_digest,
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
            "restored": self.restored,
            "rebuilt": self.rebuilt,
            "independent": self.independent,
            "production_mutation_count": self.production_mutation_count,
        }

    @property
    def receipt_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class BackupRestoreQualificationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    source_commit: str
    migration_compatibility_digest: str
    manifest_digest: str
    authoritative_state_digest: str
    receipt_digests: tuple[str, ...]
    task_id: str = BACKUP_RESTORE_TASK_ID
    accountability_id: str = BACKUP_RESTORE_ACCOUNTABILITY_ID
    schema_version: int = BACKUP_RESTORE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise BackupRestoreError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise BackupRestoreError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "source_commit",
            _sha40(self.source_commit, "source_commit"),
        )
        for field in (
            "migration_compatibility_digest",
            "manifest_digest",
            "authoritative_state_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if not isinstance(self.receipt_digests, tuple):
            raise BackupRestoreError(
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
        if self.task_id != BACKUP_RESTORE_TASK_ID:
            raise BackupRestoreError("task_id drift")
        if self.accountability_id != BACKUP_RESTORE_ACCOUNTABILITY_ID:
            raise BackupRestoreError("accountability_id drift")
        if self.schema_version != BACKUP_RESTORE_SCHEMA_VERSION:
            raise BackupRestoreError(
                "unsupported backup/restore qualification schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "source_commit": self.source_commit,
            "migration_compatibility_digest": (
                self.migration_compatibility_digest
            ),
            "manifest_digest": self.manifest_digest,
            "authoritative_state_digest": (
                self.authoritative_state_digest
            ),
            "receipt_digests": list(self.receipt_digests),
            "production_authority": False,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise BackupRestoreError(
                "rejected backup/restore cannot become promotion evidence"
            )
        return EvidenceRef(
            source=f"p1:rel-04:restore:{self.source_commit}",
            digest=self.decision_digest,
            category="backup_restore_qualification",
        )


def qualify_backup_restore(
    *,
    migration_compatibility: MigrationCompatibilityDecision,
    manifest: BackupManifest,
    receipts: Iterable[RestoreComponentReceipt],
) -> BackupRestoreQualificationDecision:
    if not isinstance(
        migration_compatibility,
        MigrationCompatibilityDecision,
    ):
        raise TypeError(
            "migration_compatibility must be MigrationCompatibilityDecision"
        )
    if not isinstance(manifest, BackupManifest):
        raise TypeError("manifest must be BackupManifest")
    rows = tuple(receipts)
    if any(not isinstance(item, RestoreComponentReceipt) for item in rows):
        raise TypeError(
            "receipts must contain RestoreComponentReceipt values"
        )

    reasons: list[str] = []
    if not migration_compatibility.accepted:
        reasons.append("migration-compatibility-rejected")
    if manifest.source_commit != migration_compatibility.source_commit:
        reasons.append("manifest-source-commit-mismatch")
    if (
        manifest.migration_compatibility_digest
        != migration_compatibility.decision_digest
    ):
        reasons.append("manifest-migration-digest-mismatch")

    by_id: dict[str, list[RestoreComponentReceipt]] = {
        item.component_id: [] for item in manifest.components
    }
    for receipt in rows:
        if receipt.component_id not in by_id:
            reasons.append(
                f"unexpected-restore-receipt:{receipt.component_id}"
            )
            continue
        by_id[receipt.component_id].append(receipt)

    for component in manifest.components:
        matches = by_id[component.component_id]
        if len(matches) != 1:
            reasons.append(
                f"restore-receipt-cardinality:{component.component_id}"
            )
            continue
        receipt = matches[0]
        prefix = component.component_id
        if receipt.component_digest != component.digest:
            reasons.append(f"{prefix}:component-digest-mismatch")
        if receipt.source_commit != manifest.source_commit:
            reasons.append(f"{prefix}:source-commit-mismatch")
        if receipt.manifest_digest != manifest.manifest_digest:
            reasons.append(f"{prefix}:manifest-digest-mismatch")
        if receipt.restore_order != component.restore_order:
            reasons.append(f"{prefix}:restore-order-mismatch")
        if receipt.completed_dependencies != component.dependencies:
            reasons.append(f"{prefix}:dependency-evidence-mismatch")
        if not receipt.independent:
            reasons.append(f"{prefix}:not-independent")
        if receipt.production_mutation_count != 0:
            reasons.append(f"{prefix}:production-mutated")

        if component.role is BackupComponentRole.AUTHORITATIVE:
            if not receipt.restored:
                reasons.append(f"{prefix}:not-restored")
            if receipt.rebuilt:
                reasons.append(f"{prefix}:unexpected-rebuild")
            if (
                receipt.observed_backup_artifact_digest
                != component.backup_artifact_digest
            ):
                reasons.append(f"{prefix}:backup-artifact-mismatch")
            if (
                receipt.restored_state_digest
                != component.source_state_digest
            ):
                reasons.append(f"{prefix}:semantic-restore-mismatch")
            if receipt.rebuild_recipe_digest is not None:
                reasons.append(f"{prefix}:unexpected-rebuild-recipe")
        else:
            if receipt.restored:
                reasons.append(f"{prefix}:derived-state-restored-as-authority")
            if not receipt.rebuilt:
                reasons.append(f"{prefix}:derived-state-not-rebuilt")
            if (
                receipt.rebuild_recipe_digest
                != component.rebuild_recipe_digest
            ):
                reasons.append(f"{prefix}:rebuild-recipe-mismatch")
            if (
                receipt.rebuild_input_digest
                != manifest.authoritative_state_digest
            ):
                reasons.append(f"{prefix}:rebuild-input-mismatch")
            if (
                receipt.rebuilt_state_digest
                != component.source_state_digest
            ):
                reasons.append(f"{prefix}:derived-rebuild-mismatch")

    normalized = tuple(sorted(set(reasons)))
    return BackupRestoreQualificationDecision(
        accepted=not normalized,
        reasons=normalized,
        source_commit=migration_compatibility.source_commit,
        migration_compatibility_digest=(
            migration_compatibility.decision_digest
        ),
        manifest_digest=manifest.manifest_digest,
        authoritative_state_digest=manifest.authoritative_state_digest,
        receipt_digests=tuple(
            item.receipt_digest for item in rows
        ),
    )


__all__ = [
    "BACKUP_RESTORE_ACCOUNTABILITY_ID",
    "BACKUP_RESTORE_SCHEMA_VERSION",
    "BACKUP_RESTORE_TASK_ID",
    "BackupComponent",
    "BackupComponentRole",
    "BackupManifest",
    "BackupRestoreError",
    "BackupRestoreQualificationDecision",
    "RestoreComponentReceipt",
    "qualify_backup_restore",
]
