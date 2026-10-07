"""P1 installer/update/repair/uninstall lifecycle qualification.

This module is evidence-only. It does not install, update, repair, uninstall,
publish, or mutate production state. It joins independently produced lifecycle
scenario receipts to the exact accepted REL-01 release qualification.

REL-02 is fail closed unless one exact release candidate proves all mandatory
lifecycle scenarios:
- clean install;
- normal update;
- interrupted update with rollback to the exact pre-update snapshot;
- repair;
- repeated repair with idempotent state;
- uninstall with no application-owned residue or unowned critical state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef
from skeleton.release.qualification import ReleaseQualificationDecision


INSTALLER_LIFECYCLE_SCHEMA_VERSION = 1
INSTALLER_LIFECYCLE_TASK_ID = "P1-REL-02"
INSTALLER_LIFECYCLE_ACCOUNTABILITY_ID = "ACC-P1-REL-02"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")


class InstallerLifecycleError(ValueError):
    """Installer lifecycle evidence is malformed or incomplete."""


class InstallerLifecycleScenario(str, Enum):
    CLEAN_INSTALL = "clean_install"
    UPDATE = "update"
    INTERRUPTED_UPDATE = "interrupted_update"
    REPAIR = "repair"
    REPAIR_REPEAT = "repair_repeat"
    UNINSTALL = "uninstall"


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InstallerLifecycleError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise InstallerLifecycleError(f"{field} must be normalized")
    return normalized


def _token(value: object, field: str, *, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or not _TOKEN_RE.fullmatch(value)
    ):
        raise InstallerLifecycleError(f"{field} must be a canonical token")
    return value


def _sha40(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA40_RE.fullmatch(value):
        raise InstallerLifecycleError(
            f"{field} must be lowercase 40-character git SHA"
        )
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise InstallerLifecycleError(f"{field} must be lowercase sha256")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InstallerLifecycleError(
            f"{field} must be a non-negative integer"
        )
    return value


def _canonical_digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InstallerLifecycleError(
            "installer lifecycle payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise InstallerLifecycleError(
            "evidence_refs must contain EvidenceRef values"
        )
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise InstallerLifecycleError(
                "evidence_refs must contain EvidenceRef values"
            )
        _text(item.source, "evidence.source")
        _sha256(item.digest, "evidence.digest")
        _token(item.category, "evidence.category", maximum=128)
        by_key[(item.source, item.digest, item.category)] = item
    if not by_key:
        raise InstallerLifecycleError("evidence_refs must be non-empty")
    return tuple(by_key[key] for key in sorted(by_key))


@dataclass(frozen=True, slots=True)
class InstallerLifecycleReceipt:
    scenario: InstallerLifecycleScenario
    source_commit: str
    release_qualification_digest: str
    installer_metadata_digest: str
    target_version: str
    before_snapshot_digest: str
    after_snapshot_digest: str
    expected_target_snapshot_digest: str
    ownership_policy_digest: str
    retention_policy_digest: str
    verifier_id: str
    verifier_digest: str
    test_manifest_digest: str
    evidence_refs: tuple[EvidenceRef, ...]
    rollback_snapshot_digest: str | None = None
    retained_user_data_digest: str | None = None
    passed: bool = True
    independent: bool = True
    interrupted: bool = False
    recovered: bool = False
    production_mutation_count: int = 0
    application_owned_residual_count: int = 0
    unowned_critical_count: int = 0

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self,
                "scenario",
                InstallerLifecycleScenario(self.scenario),
            )
        except ValueError as exc:
            raise InstallerLifecycleError(
                "invalid installer lifecycle scenario"
            ) from exc
        object.__setattr__(
            self,
            "source_commit",
            _sha40(self.source_commit, "source_commit"),
        )
        for field in (
            "release_qualification_digest",
            "installer_metadata_digest",
            "before_snapshot_digest",
            "after_snapshot_digest",
            "expected_target_snapshot_digest",
            "ownership_policy_digest",
            "retention_policy_digest",
            "verifier_digest",
            "test_manifest_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        for field in (
            "rollback_snapshot_digest",
            "retained_user_data_digest",
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
            "target_version",
            _token(self.target_version, "target_version"),
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
            "passed",
            "independent",
            "interrupted",
            "recovered",
        ):
            if not isinstance(getattr(self, field), bool):
                raise InstallerLifecycleError(f"{field} must be boolean")
        for field in (
            "production_mutation_count",
            "application_owned_residual_count",
            "unowned_critical_count",
        ):
            object.__setattr__(
                self,
                field,
                _nonnegative_int(getattr(self, field), field),
            )
        if self.scenario.value not in {
            item.category for item in self.evidence_refs
        }:
            raise InstallerLifecycleError(
                "scenario receipt requires exact scenario evidence category"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario.value,
            "source_commit": self.source_commit,
            "release_qualification_digest": self.release_qualification_digest,
            "installer_metadata_digest": self.installer_metadata_digest,
            "target_version": self.target_version,
            "before_snapshot_digest": self.before_snapshot_digest,
            "after_snapshot_digest": self.after_snapshot_digest,
            "expected_target_snapshot_digest": (
                self.expected_target_snapshot_digest
            ),
            "rollback_snapshot_digest": self.rollback_snapshot_digest,
            "retained_user_data_digest": self.retained_user_data_digest,
            "ownership_policy_digest": self.ownership_policy_digest,
            "retention_policy_digest": self.retention_policy_digest,
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
            "passed": self.passed,
            "independent": self.independent,
            "interrupted": self.interrupted,
            "recovered": self.recovered,
            "production_mutation_count": self.production_mutation_count,
            "application_owned_residual_count": (
                self.application_owned_residual_count
            ),
            "unowned_critical_count": self.unowned_critical_count,
        }

    @property
    def receipt_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class InstallerLifecycleQualificationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    source_commit: str
    release_qualification_digest: str
    installer_metadata_digest: str
    target_version: str
    ownership_policy_digest: str
    retention_policy_digest: str
    scenario_receipt_digests: tuple[str, ...]
    task_id: str = INSTALLER_LIFECYCLE_TASK_ID
    accountability_id: str = INSTALLER_LIFECYCLE_ACCOUNTABILITY_ID
    schema_version: int = INSTALLER_LIFECYCLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise InstallerLifecycleError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise InstallerLifecycleError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "source_commit",
            _sha40(self.source_commit, "source_commit"),
        )
        for field in (
            "release_qualification_digest",
            "installer_metadata_digest",
            "ownership_policy_digest",
            "retention_policy_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "target_version",
            _token(self.target_version, "target_version"),
        )
        if not isinstance(self.scenario_receipt_digests, tuple):
            raise InstallerLifecycleError(
                "scenario_receipt_digests must be tuple"
            )
        object.__setattr__(
            self,
            "scenario_receipt_digests",
            tuple(
                sorted(
                    {
                        _sha256(item, "scenario_receipt_digests")
                        for item in self.scenario_receipt_digests
                    }
                )
            ),
        )
        if self.task_id != INSTALLER_LIFECYCLE_TASK_ID:
            raise InstallerLifecycleError("task_id drift")
        if self.accountability_id != INSTALLER_LIFECYCLE_ACCOUNTABILITY_ID:
            raise InstallerLifecycleError("accountability_id drift")
        if self.schema_version != INSTALLER_LIFECYCLE_SCHEMA_VERSION:
            raise InstallerLifecycleError(
                "unsupported lifecycle qualification schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "source_commit": self.source_commit,
            "release_qualification_digest": (
                self.release_qualification_digest
            ),
            "installer_metadata_digest": self.installer_metadata_digest,
            "target_version": self.target_version,
            "ownership_policy_digest": self.ownership_policy_digest,
            "retention_policy_digest": self.retention_policy_digest,
            "scenario_receipt_digests": list(
                self.scenario_receipt_digests
            ),
            "production_authority": False,
            "publishing_authority": False,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise InstallerLifecycleError(
                "rejected installer lifecycle cannot become promotion evidence"
            )
        return EvidenceRef(
            source=f"p1:rel-02:installer-lifecycle:{self.source_commit}",
            digest=self.decision_digest,
            category="installer_lifecycle_qualification",
        )


def qualify_installer_lifecycle(
    *,
    release_qualification: ReleaseQualificationDecision,
    receipts: Iterable[InstallerLifecycleReceipt],
    installer_metadata_digest: str,
    target_version: str,
) -> InstallerLifecycleQualificationDecision:
    if not isinstance(release_qualification, ReleaseQualificationDecision):
        raise TypeError(
            "release_qualification must be ReleaseQualificationDecision"
        )
    rows = tuple(receipts)
    if any(not isinstance(item, InstallerLifecycleReceipt) for item in rows):
        raise TypeError(
            "receipts must contain InstallerLifecycleReceipt values"
        )
    installer_digest = _sha256(
        installer_metadata_digest,
        "installer_metadata_digest",
    )
    version = _token(target_version, "target_version")
    reasons: list[str] = []

    if not release_qualification.accepted:
        reasons.append("release-qualification-rejected")
    if (
        installer_digest
        != release_qualification.installer_metadata_digest
    ):
        reasons.append("release-installer-metadata-mismatch")

    expected_release_digest = release_qualification.decision_digest
    source_commit = release_qualification.source_commit

    by_scenario: dict[
        InstallerLifecycleScenario,
        list[InstallerLifecycleReceipt],
    ] = {scenario: [] for scenario in InstallerLifecycleScenario}
    for receipt in rows:
        by_scenario[receipt.scenario].append(receipt)
        prefix = receipt.scenario.value
        if receipt.source_commit != source_commit:
            reasons.append(f"{prefix}:source-commit-mismatch")
        if receipt.release_qualification_digest != expected_release_digest:
            reasons.append(f"{prefix}:release-qualification-mismatch")
        if receipt.installer_metadata_digest != installer_digest:
            reasons.append(f"{prefix}:installer-metadata-mismatch")
        if receipt.target_version != version:
            reasons.append(f"{prefix}:target-version-mismatch")
        if receipt.passed is not True:
            reasons.append(f"{prefix}:scenario-failed")
        if receipt.independent is not True:
            reasons.append(f"{prefix}:not-independent")
        if receipt.production_mutation_count != 0:
            reasons.append(f"{prefix}:production-mutated")
        if receipt.unowned_critical_count != 0:
            reasons.append(f"{prefix}:unowned-critical-state")

    for scenario, scenario_rows in by_scenario.items():
        if len(scenario_rows) != 1:
            reasons.append(
                f"scenario-cardinality:{scenario.value}"
            )

    ownership_digests = {
        item.ownership_policy_digest for item in rows
    }
    retention_digests = {
        item.retention_policy_digest for item in rows
    }
    if len(ownership_digests) != 1:
        reasons.append("ownership-policy-drift")
    if len(retention_digests) != 1:
        reasons.append("retention-policy-drift")

    def one(
        scenario: InstallerLifecycleScenario,
    ) -> InstallerLifecycleReceipt | None:
        scenario_rows = by_scenario[scenario]
        return scenario_rows[0] if len(scenario_rows) == 1 else None

    clean = one(InstallerLifecycleScenario.CLEAN_INSTALL)
    if clean is not None:
        if clean.interrupted:
            reasons.append("clean_install:unexpected-interruption")
        if clean.recovered:
            reasons.append("clean_install:unexpected-recovery")
        if (
            clean.after_snapshot_digest
            != clean.expected_target_snapshot_digest
        ):
            reasons.append("clean_install:target-snapshot-mismatch")

    update = one(InstallerLifecycleScenario.UPDATE)
    if update is not None:
        if update.interrupted:
            reasons.append("update:unexpected-interruption")
        if update.recovered:
            reasons.append("update:unexpected-recovery")
        if (
            update.after_snapshot_digest
            != update.expected_target_snapshot_digest
        ):
            reasons.append("update:target-snapshot-mismatch")

    interrupted = one(
        InstallerLifecycleScenario.INTERRUPTED_UPDATE
    )
    if interrupted is not None:
        if not interrupted.interrupted:
            reasons.append(
                "interrupted_update:interruption-not-observed"
            )
        if not interrupted.recovered:
            reasons.append(
                "interrupted_update:not-recovered"
            )
        if interrupted.rollback_snapshot_digest is None:
            reasons.append(
                "interrupted_update:rollback-snapshot-missing"
            )
        else:
            if (
                interrupted.after_snapshot_digest
                != interrupted.rollback_snapshot_digest
            ):
                reasons.append(
                    "interrupted_update:rollback-result-mismatch"
                )
            if (
                interrupted.before_snapshot_digest
                != interrupted.rollback_snapshot_digest
            ):
                reasons.append(
                    "interrupted_update:preupdate-state-not-restored"
                )

    repair = one(InstallerLifecycleScenario.REPAIR)
    if repair is not None:
        if repair.interrupted:
            reasons.append("repair:unexpected-interruption")
        if (
            repair.after_snapshot_digest
            != repair.expected_target_snapshot_digest
        ):
            reasons.append("repair:target-snapshot-mismatch")

    repeat_repair = one(
        InstallerLifecycleScenario.REPAIR_REPEAT
    )
    if repeat_repair is not None:
        if repeat_repair.interrupted:
            reasons.append("repair_repeat:unexpected-interruption")
        if (
            repeat_repair.before_snapshot_digest
            != repeat_repair.after_snapshot_digest
        ):
            reasons.append("repair_repeat:not-idempotent")
        if (
            repeat_repair.after_snapshot_digest
            != repeat_repair.expected_target_snapshot_digest
        ):
            reasons.append(
                "repair_repeat:target-snapshot-mismatch"
            )

    uninstall = one(InstallerLifecycleScenario.UNINSTALL)
    if uninstall is not None:
        if uninstall.interrupted:
            reasons.append("uninstall:unexpected-interruption")
        if uninstall.application_owned_residual_count != 0:
            reasons.append("uninstall:application-residue")
        if uninstall.retained_user_data_digest is None:
            reasons.append("uninstall:retention-evidence-missing")
        if (
            uninstall.after_snapshot_digest
            == uninstall.expected_target_snapshot_digest
        ):
            reasons.append("uninstall:application-state-still-installed")

    ownership_digest = (
        next(iter(ownership_digests))
        if len(ownership_digests) == 1
        else _canonical_digest({"invalid": "ownership-policy-drift"})
    )
    retention_digest = (
        next(iter(retention_digests))
        if len(retention_digests) == 1
        else _canonical_digest({"invalid": "retention-policy-drift"})
    )

    normalized = tuple(sorted(set(reasons)))
    return InstallerLifecycleQualificationDecision(
        accepted=not normalized,
        reasons=normalized,
        source_commit=source_commit,
        release_qualification_digest=expected_release_digest,
        installer_metadata_digest=installer_digest,
        target_version=version,
        ownership_policy_digest=ownership_digest,
        retention_policy_digest=retention_digest,
        scenario_receipt_digests=tuple(
            item.receipt_digest for item in rows
        ),
    )


__all__ = [
    "INSTALLER_LIFECYCLE_ACCOUNTABILITY_ID",
    "INSTALLER_LIFECYCLE_SCHEMA_VERSION",
    "INSTALLER_LIFECYCLE_TASK_ID",
    "InstallerLifecycleError",
    "InstallerLifecycleQualificationDecision",
    "InstallerLifecycleReceipt",
    "InstallerLifecycleScenario",
    "qualify_installer_lifecycle",
]
