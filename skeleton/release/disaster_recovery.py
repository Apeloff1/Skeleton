"""P1 disaster recovery and incident feedback qualification.

Evidence-only authority for REL-05. It binds executable disaster-recovery drill
receipts to the exact REL-04 backup/restore qualification and requires every
incident corrective action to be linked into the accepted LEARN-06 failure
knowledge ledger. It does not execute recovery or mutate production.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef
from skeleton.eval.failure_knowledge import (
    FailureKnowledgeLedger,
    FailureKnowledgeQualificationDecision,
    FailureSourceKind,
)
from skeleton.release.restore import BackupRestoreQualificationDecision


DISASTER_RECOVERY_SCHEMA_VERSION = 1
DISASTER_RECOVERY_TASK_ID = "P1-REL-05"
DISASTER_RECOVERY_ACCOUNTABILITY_ID = "ACC-P1-REL-05"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,319}$")


class DisasterRecoveryError(ValueError):
    """Disaster recovery evidence is malformed or incomplete."""


class DisasterScenario(str, Enum):
    AUTHORITATIVE_STORE_LOSS = "authoritative_store_loss"
    CORRUPT_BACKUP = "corrupt_backup"
    CONTROL_PLANE_LOSS = "control_plane_loss"


def _token(value: object, field: str, *, maximum: int = 320) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or not _TOKEN_RE.fullmatch(value)
    ):
        raise DisasterRecoveryError(f"{field} must be a canonical token")
    return value


def _text(value: object, field: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DisasterRecoveryError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise DisasterRecoveryError(f"{field} must be normalized")
    return normalized


def _sha40(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA40_RE.fullmatch(value):
        raise DisasterRecoveryError(
            f"{field} must be lowercase 40-character git SHA"
        )
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise DisasterRecoveryError(f"{field} must be lowercase sha256")
    return value


def _finite_nonnegative(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DisasterRecoveryError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise DisasterRecoveryError(f"{field} must be non-negative")
    return result


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
        raise DisasterRecoveryError(
            "disaster recovery payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _tokens(
    values: Iterable[str],
    field: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise DisasterRecoveryError(f"{field} must be an iterable")
    result = tuple(sorted({_token(item, field) for item in values}))
    if not result and not allow_empty:
        raise DisasterRecoveryError(f"{field} must be non-empty")
    return result


def _evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise DisasterRecoveryError(
            "evidence_refs must contain EvidenceRef values"
        )
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise DisasterRecoveryError(
                "evidence_refs must contain EvidenceRef values"
            )
        _text(item.source, "evidence.source", maximum=2048)
        _sha256(item.digest, "evidence.digest")
        _token(item.category, "evidence.category", maximum=128)
        by_key[(item.source, item.digest, item.category)] = item
    if not by_key:
        raise DisasterRecoveryError("evidence_refs must be non-empty")
    return tuple(by_key[key] for key in sorted(by_key))


@dataclass(frozen=True, slots=True)
class IncidentCorrectiveAction:
    action_id: str
    incident_id: str
    incident_digest: str
    owner_id: str
    risk_obligation_id: str
    risk_obligation_digest: str
    failure_knowledge_ledger_digest: str
    failure_record_digest: str
    corrective_test_digest: str
    evidence_refs: tuple[EvidenceRef, ...]
    completed: bool = True
    independently_verified: bool = True

    def __post_init__(self) -> None:
        for field in (
            "action_id",
            "incident_id",
            "owner_id",
            "risk_obligation_id",
        ):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        for field in (
            "incident_digest",
            "risk_obligation_digest",
            "failure_knowledge_ledger_digest",
            "failure_record_digest",
            "corrective_test_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence(self.evidence_refs),
        )
        if self.completed is not True:
            raise DisasterRecoveryError(
                "corrective action must be completed before qualification"
            )
        if self.independently_verified is not True:
            raise DisasterRecoveryError(
                "corrective action must be independently verified"
            )
        if "incident_followup" not in {
            item.category for item in self.evidence_refs
        }:
            raise DisasterRecoveryError(
                "corrective action requires incident_followup evidence"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "incident_id": self.incident_id,
            "incident_digest": self.incident_digest,
            "owner_id": self.owner_id,
            "risk_obligation_id": self.risk_obligation_id,
            "risk_obligation_digest": self.risk_obligation_digest,
            "failure_knowledge_ledger_digest": (
                self.failure_knowledge_ledger_digest
            ),
            "failure_record_digest": self.failure_record_digest,
            "corrective_test_digest": self.corrective_test_digest,
            "evidence_refs": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence_refs
            ],
            "completed": self.completed,
            "independently_verified": self.independently_verified,
        }

    @property
    def action_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class DisasterRecoveryDrillReceipt:
    scenario: DisasterScenario
    source_commit: str
    backup_restore_qualification_digest: str
    authoritative_state_digest: str
    pre_failure_state_digest: str
    recovered_state_digest: str
    rto_target_seconds: float
    rto_observed_seconds: float
    rpo_target_seconds: float
    rpo_observed_seconds: float
    incident_id: str
    incident_digest: str
    corrective_action_ids: tuple[str, ...]
    verifier_id: str
    verifier_digest: str
    test_manifest_digest: str
    evidence_refs: tuple[EvidenceRef, ...]
    passed: bool = True
    independent: bool = True
    production_mutation_count: int = 0

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self,
                "scenario",
                DisasterScenario(self.scenario),
            )
        except ValueError as exc:
            raise DisasterRecoveryError("invalid disaster scenario") from exc
        object.__setattr__(
            self,
            "source_commit",
            _sha40(self.source_commit, "source_commit"),
        )
        for field in (
            "backup_restore_qualification_digest",
            "authoritative_state_digest",
            "pre_failure_state_digest",
            "recovered_state_digest",
            "incident_digest",
            "verifier_digest",
            "test_manifest_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        for field in (
            "rto_target_seconds",
            "rto_observed_seconds",
            "rpo_target_seconds",
            "rpo_observed_seconds",
        ):
            object.__setattr__(
                self,
                field,
                _finite_nonnegative(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "incident_id",
            _token(self.incident_id, "incident_id"),
        )
        object.__setattr__(
            self,
            "corrective_action_ids",
            _tokens(self.corrective_action_ids, "corrective_action_ids"),
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
        if self.passed is not True:
            raise DisasterRecoveryError(
                "DR drill must pass before qualification"
            )
        if self.independent is not True:
            raise DisasterRecoveryError(
                "DR drill must be independently verified"
            )
        if (
            isinstance(self.production_mutation_count, bool)
            or not isinstance(self.production_mutation_count, int)
            or self.production_mutation_count != 0
        ):
            raise DisasterRecoveryError(
                "DR qualification cannot mutate production"
            )
        if "disaster_recovery" not in {
            item.category for item in self.evidence_refs
        }:
            raise DisasterRecoveryError(
                "DR receipt requires disaster_recovery evidence"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario.value,
            "source_commit": self.source_commit,
            "backup_restore_qualification_digest": (
                self.backup_restore_qualification_digest
            ),
            "authoritative_state_digest": self.authoritative_state_digest,
            "pre_failure_state_digest": self.pre_failure_state_digest,
            "recovered_state_digest": self.recovered_state_digest,
            "rto_target_seconds": self.rto_target_seconds,
            "rto_observed_seconds": self.rto_observed_seconds,
            "rpo_target_seconds": self.rpo_target_seconds,
            "rpo_observed_seconds": self.rpo_observed_seconds,
            "incident_id": self.incident_id,
            "incident_digest": self.incident_digest,
            "corrective_action_ids": list(self.corrective_action_ids),
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
            "production_mutation_count": self.production_mutation_count,
        }

    @property
    def receipt_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class DisasterRecoveryQualificationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    source_commit: str
    backup_restore_qualification_digest: str
    failure_knowledge_qualification_digest: str
    authoritative_state_digest: str
    drill_receipt_digests: tuple[str, ...]
    corrective_action_digests: tuple[str, ...]
    task_id: str = DISASTER_RECOVERY_TASK_ID
    accountability_id: str = DISASTER_RECOVERY_ACCOUNTABILITY_ID
    schema_version: int = DISASTER_RECOVERY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise DisasterRecoveryError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise DisasterRecoveryError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "source_commit",
            _sha40(self.source_commit, "source_commit"),
        )
        for field in (
            "backup_restore_qualification_digest",
            "failure_knowledge_qualification_digest",
            "authoritative_state_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        for field in (
            "drill_receipt_digests",
            "corrective_action_digests",
        ):
            values = getattr(self, field)
            if not isinstance(values, tuple):
                raise DisasterRecoveryError(f"{field} must be tuple")
            object.__setattr__(
                self,
                field,
                tuple(
                    sorted({_sha256(item, field) for item in values})
                ),
            )
        if self.task_id != DISASTER_RECOVERY_TASK_ID:
            raise DisasterRecoveryError("task_id drift")
        if self.accountability_id != DISASTER_RECOVERY_ACCOUNTABILITY_ID:
            raise DisasterRecoveryError("accountability_id drift")
        if self.schema_version != DISASTER_RECOVERY_SCHEMA_VERSION:
            raise DisasterRecoveryError(
                "unsupported disaster recovery schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "source_commit": self.source_commit,
            "backup_restore_qualification_digest": (
                self.backup_restore_qualification_digest
            ),
            "failure_knowledge_qualification_digest": (
                self.failure_knowledge_qualification_digest
            ),
            "authoritative_state_digest": self.authoritative_state_digest,
            "drill_receipt_digests": list(self.drill_receipt_digests),
            "corrective_action_digests": list(
                self.corrective_action_digests
            ),
            "production_authority": False,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise DisasterRecoveryError(
                "rejected disaster recovery cannot become promotion evidence"
            )
        return EvidenceRef(
            source=f"p1:rel-05:disaster-recovery:{self.source_commit}",
            digest=self.decision_digest,
            category="disaster_recovery_qualification",
        )


def qualify_disaster_recovery(
    *,
    backup_restore: BackupRestoreQualificationDecision,
    failure_knowledge: FailureKnowledgeQualificationDecision,
    failure_knowledge_ledger: FailureKnowledgeLedger,
    drills: Iterable[DisasterRecoveryDrillReceipt],
    corrective_actions: Iterable[IncidentCorrectiveAction],
) -> DisasterRecoveryQualificationDecision:
    if not isinstance(backup_restore, BackupRestoreQualificationDecision):
        raise TypeError(
            "backup_restore must be BackupRestoreQualificationDecision"
        )
    if not isinstance(
        failure_knowledge,
        FailureKnowledgeQualificationDecision,
    ):
        raise TypeError(
            "failure_knowledge must be FailureKnowledgeQualificationDecision"
        )
    if not isinstance(failure_knowledge_ledger, FailureKnowledgeLedger):
        raise TypeError(
            "failure_knowledge_ledger must be FailureKnowledgeLedger"
        )
    drill_rows = tuple(drills)
    action_rows = tuple(corrective_actions)
    if any(
        not isinstance(item, DisasterRecoveryDrillReceipt)
        for item in drill_rows
    ):
        raise TypeError(
            "drills must contain DisasterRecoveryDrillReceipt"
        )
    if any(
        not isinstance(item, IncidentCorrectiveAction)
        for item in action_rows
    ):
        raise TypeError(
            "corrective_actions must contain IncidentCorrectiveAction"
        )

    reasons: list[str] = []
    if not backup_restore.accepted:
        reasons.append("backup-restore-rejected")
    if not failure_knowledge.accepted:
        reasons.append("failure-knowledge-rejected")
    if failure_knowledge.ledger_digest != failure_knowledge_ledger.ledger_digest:
        reasons.append("failure-knowledge-ledger-digest-mismatch")

    record_by_digest = {
        item.record_digest: item
        for item in failure_knowledge_ledger.records
    }
    action_by_id = {item.action_id: item for item in action_rows}
    if len(action_by_id) != len(action_rows):
        reasons.append("corrective-action-id-duplicate")

    by_scenario: dict[
        DisasterScenario,
        list[DisasterRecoveryDrillReceipt],
    ] = {scenario: [] for scenario in DisasterScenario}
    incident_digests: dict[str, set[str]] = {}

    for action in action_rows:
        if (
            action.failure_knowledge_ledger_digest
            != failure_knowledge.ledger_digest
        ):
            reasons.append(
                f"corrective-action-failure-ledger-mismatch:{action.action_id}"
            )
        record = record_by_digest.get(action.failure_record_digest)
        if record is None:
            reasons.append(
                f"corrective-action-failure-record-missing:{action.action_id}"
            )
        else:
            if record.source_kind is not FailureSourceKind.INCIDENT:
                reasons.append(
                    f"corrective-action-failure-record-not-incident:{action.action_id}"
                )
            if record.source_ref != f"incident:{action.incident_id}":
                reasons.append(
                    f"corrective-action-incident-source-mismatch:{action.action_id}"
                )
            if (
                record.risk_obligation_id != action.risk_obligation_id
                or record.risk_obligation_digest
                != action.risk_obligation_digest
            ):
                reasons.append(
                    f"corrective-action-risk-identity-mismatch:{action.action_id}"
                )
        incident_digests.setdefault(
            action.incident_id,
            set(),
        ).add(action.incident_digest)

    for drill in drill_rows:
        by_scenario[drill.scenario].append(drill)
        prefix = drill.scenario.value
        if drill.source_commit != backup_restore.source_commit:
            reasons.append(f"{prefix}:source-commit-mismatch")
        if (
            drill.backup_restore_qualification_digest
            != backup_restore.decision_digest
        ):
            reasons.append(f"{prefix}:backup-restore-digest-mismatch")
        if (
            drill.authoritative_state_digest
            != backup_restore.authoritative_state_digest
        ):
            reasons.append(f"{prefix}:authoritative-state-digest-mismatch")
        if drill.pre_failure_state_digest != drill.recovered_state_digest:
            reasons.append(f"{prefix}:semantic-recovery-mismatch")
        if drill.rto_observed_seconds > drill.rto_target_seconds:
            reasons.append(f"{prefix}:rto-exceeded")
        if drill.rpo_observed_seconds > drill.rpo_target_seconds:
            reasons.append(f"{prefix}:rpo-exceeded")
        for action_id in drill.corrective_action_ids:
            action = action_by_id.get(action_id)
            if action is None:
                reasons.append(
                    f"{prefix}:corrective-action-missing:{action_id}"
                )
                continue
            if action.incident_id != drill.incident_id:
                reasons.append(
                    f"{prefix}:corrective-action-incident-mismatch:{action_id}"
                )
            if action.incident_digest != drill.incident_digest:
                reasons.append(
                    f"{prefix}:corrective-action-digest-mismatch:{action_id}"
                )
        observed = incident_digests.get(drill.incident_id, set())
        if observed and observed != {drill.incident_digest}:
            reasons.append(f"{prefix}:incident-digest-conflict")

    for scenario, rows in by_scenario.items():
        if len(rows) != 1:
            reasons.append(
                f"drill-cardinality:{scenario.value}"
            )

    referenced_actions = {
        action_id
        for drill in drill_rows
        for action_id in drill.corrective_action_ids
    }
    for action in action_rows:
        if action.action_id not in referenced_actions:
            reasons.append(
                f"orphan-corrective-action:{action.action_id}"
            )

    normalized = tuple(sorted(set(reasons)))
    return DisasterRecoveryQualificationDecision(
        accepted=not normalized,
        reasons=normalized,
        source_commit=backup_restore.source_commit,
        backup_restore_qualification_digest=backup_restore.decision_digest,
        failure_knowledge_qualification_digest=(
            failure_knowledge.decision_digest
        ),
        authoritative_state_digest=backup_restore.authoritative_state_digest,
        drill_receipt_digests=tuple(
            item.receipt_digest for item in drill_rows
        ),
        corrective_action_digests=tuple(
            item.action_digest for item in action_rows
        ),
    )


__all__ = [
    "DISASTER_RECOVERY_ACCOUNTABILITY_ID",
    "DISASTER_RECOVERY_SCHEMA_VERSION",
    "DISASTER_RECOVERY_TASK_ID",
    "DisasterRecoveryDrillReceipt",
    "DisasterRecoveryError",
    "DisasterRecoveryQualificationDecision",
    "DisasterScenario",
    "IncidentCorrectiveAction",
    "qualify_disaster_recovery",
]
