"""Forensic consistency proof for durable compaction authority lineages.

The compaction operator answers whether a workflow is *currently* executable.
That is intentionally time-sensitive: live heads move and short-lived
certificates/authorizations expire.  For incident response and long-term
forensics we need a different question:

    Did this historical destructive workflow bind one internally consistent,
    signed chain of authority and evidence?

This module is read-only.  It never issues authority, repairs indexes, advances
hot floors, resumes pruning, or deletes evidence.  It verifies the immutable
lineage:

workflow -> readiness certificate -> pruning authorization -> archive ->
frozen pruning manifest -> pruning operation -> signed hot floor.

Historical certificates and authorizations are not rejected merely because
their TTL has elapsed; their stores still verify signatures on retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from skeleton.shells.ai.durable_compaction_operator import (
    DurableCompactionOperator,
    DurableCompactionWorkflow,
    DurableCompactionWorkflowPhase,
)
from skeleton.shells.ai.durable_hot_floor import (
    SignedDurableHotFloor,
)
from skeleton.shells.ai.durable_pruning import (
    DurablePruningManifest,
    DurablePruningOperation,
    DurablePruningPhase,
)


class CompactionLineageStatus(str, Enum):
    VERIFIED = "verified"
    INCOMPLETE = "incomplete"
    MANUAL_REVIEW = "manual_review"


class CompactionLineageSeverity(str, Enum):
    INFO = "info"
    MISSING = "missing"
    CONFLICT = "conflict"
    CORRUPTION = "corruption"


@dataclass(frozen=True)
class CompactionLineageFinding:
    code: str
    severity: CompactionLineageSeverity
    message: str

    def __post_init__(self) -> None:
        if not self.code or len(self.code) > 160:
            raise ValueError(
                "invalid compaction lineage finding code"
            )
        object.__setattr__(
            self,
            "severity",
            CompactionLineageSeverity(
                self.severity
            ),
        )
        if (
            not self.message
            or len(self.message) > 2048
        ):
            raise ValueError(
                "invalid compaction lineage finding message"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
        }


@dataclass(frozen=True)
class CompactionLineageArtifactState:
    expected: bool
    present: bool
    verified: bool
    artifact_id: str = ""
    artifact_digest: str = ""

    def __post_init__(self) -> None:
        for name in (
            "expected",
            "present",
            "verified",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        if self.verified and not self.present:
            raise ValueError(
                "verified artifact must be present"
            )
        if len(self.artifact_id) > 256:
            raise ValueError(
                "artifact_id too long"
            )
        if (
            self.artifact_digest
            and len(self.artifact_digest) != 64
        ):
            raise ValueError(
                "artifact_digest must be 64-character digest"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "expected": self.expected,
            "present": self.present,
            "verified": self.verified,
            "artifact_id": self.artifact_id,
            "artifact_digest": self.artifact_digest,
        }


@dataclass(frozen=True)
class DurableCompactionLineageReport:
    workflow_id: str
    chain_id: str
    workflow_phase: str
    workflow_revision: int | None
    status: CompactionLineageStatus
    workflow_digest: str
    certificate: CompactionLineageArtifactState
    authorization: CompactionLineageArtifactState
    archive: CompactionLineageArtifactState
    pruning_manifest: CompactionLineageArtifactState
    pruning_operation: CompactionLineageArtifactState
    hot_floor: CompactionLineageArtifactState
    findings: tuple[CompactionLineageFinding, ...]

    def __post_init__(self) -> None:
        if (
            not self.workflow_id
            or len(self.workflow_id) > 256
        ):
            raise ValueError(
                "invalid compaction lineage workflow_id"
            )
        if len(self.chain_id) > 128:
            raise ValueError(
                "compaction lineage chain_id too long"
            )
        if self.workflow_revision is not None and (
            isinstance(self.workflow_revision, bool)
            or not isinstance(
                self.workflow_revision,
                int,
            )
            or self.workflow_revision <= 0
        ):
            raise ValueError(
                "workflow_revision must be positive"
            )
        object.__setattr__(
            self,
            "status",
            CompactionLineageStatus(
                self.status
            ),
        )
        if (
            self.workflow_digest
            and len(self.workflow_digest) != 64
        ):
            raise ValueError(
                "workflow_digest must be 64-character digest"
            )
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )

    @property
    def ok(self) -> bool:
        return (
            self.status
            is CompactionLineageStatus.VERIFIED
        )

    @property
    def safe_to_resume(self) -> bool:
        return (
            self.status
            is CompactionLineageStatus.INCOMPLETE
        )

    @property
    def requires_manual_review(self) -> bool:
        return (
            self.status
            is CompactionLineageStatus.MANUAL_REVIEW
        )

    @property
    def errors(self) -> int:
        return sum(
            finding.severity
            in {
                CompactionLineageSeverity.CONFLICT,
                CompactionLineageSeverity.CORRUPTION,
            }
            for finding in self.findings
        )

    @property
    def missing(self) -> int:
        return sum(
            finding.severity
            is CompactionLineageSeverity.MISSING
            for finding in self.findings
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
            "workflow_id": self.workflow_id,
            "chain_id": self.chain_id,
            "workflow_phase": self.workflow_phase,
            "workflow_revision": (
                self.workflow_revision
            ),
            "status": self.status.value,
            "ok": self.ok,
            "safe_to_resume": self.safe_to_resume,
            "requires_manual_review": (
                self.requires_manual_review
            ),
            "errors": self.errors,
            "missing": self.missing,
            "workflow_digest": self.workflow_digest,
            "certificate": self.certificate.to_dict(),
            "authorization": (
                self.authorization.to_dict()
            ),
            "archive": self.archive.to_dict(),
            "pruning_manifest": (
                self.pruning_manifest.to_dict()
            ),
            "pruning_operation": (
                self.pruning_operation.to_dict()
            ),
            "hot_floor": self.hot_floor.to_dict(),
            "findings": [
                item.to_dict()
                for item in self.findings
            ],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableCompactionLineageError(
    RuntimeError
):
    pass


class DurableCompactionLineageAuditor:
    """Read-only historical proof over a DurableCompactionOperator."""

    def __init__(
        self,
        operator: DurableCompactionOperator,
    ) -> None:
        if not isinstance(
            operator,
            DurableCompactionOperator,
        ):
            raise TypeError(
                "operator must be DurableCompactionOperator"
            )
        self.operator = operator
        self.certificates = (
            operator.certificates
        )
        self.authorizations = (
            operator.authorizations
        )
        self.pruning = operator.pruning
        self.hot_floors = (
            operator.pruning.hot_floors
        )
        self.archives = (
            operator.planner.archives
        )

    @staticmethod
    def _workflow_digest(
        workflow: DurableCompactionWorkflow,
    ) -> str:
        raw = json.dumps(
            workflow.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _add(
        findings: list[
            CompactionLineageFinding
        ],
        code: str,
        severity: CompactionLineageSeverity,
        message: str,
    ) -> None:
        findings.append(
            CompactionLineageFinding(
                code,
                severity,
                message,
            )
        )

    @staticmethod
    def _expected(
        workflow: DurableCompactionWorkflow,
        phase: DurableCompactionWorkflowPhase,
    ) -> bool:
        order = {
            DurableCompactionWorkflowPhase.PLANNED: 10,
            DurableCompactionWorkflowPhase.CERTIFIED: 20,
            DurableCompactionWorkflowPhase.AUTHORIZED: 30,
            DurableCompactionWorkflowPhase.PREPARED: 40,
            DurableCompactionWorkflowPhase.EXECUTING: 50,
            DurableCompactionWorkflowPhase.COMPLETE: 60,
            DurableCompactionWorkflowPhase.MANUAL_REVIEW: 90,
        }
        return (
            order[workflow.phase]
            >= order[phase]
            and workflow.phase
            is not DurableCompactionWorkflowPhase.MANUAL_REVIEW
        )

    @staticmethod
    def _state(
        *,
        expected: bool,
        present: bool,
        verified: bool,
        artifact_id: str = "",
        artifact_digest: str = "",
    ) -> CompactionLineageArtifactState:
        return CompactionLineageArtifactState(
            expected,
            present,
            verified,
            artifact_id,
            artifact_digest,
        )

    @staticmethod
    def _check_equal(
        findings: list[
            CompactionLineageFinding
        ],
        *,
        code: str,
        left,
        right,
        message: str,
    ) -> bool:
        if left == right:
            return True
        DurableCompactionLineageAuditor._add(
            findings,
            code,
            CompactionLineageSeverity.CONFLICT,
            message,
        )
        return False

    def _certificate(
        self,
        workflow: DurableCompactionWorkflow,
        findings: list[
            CompactionLineageFinding
        ],
    ):
        expected = self._expected(
            workflow,
            DurableCompactionWorkflowPhase.CERTIFIED,
        )
        if not workflow.certificate_id:
            if expected:
                self._add(
                    findings,
                    "certificate.binding_missing",
                    CompactionLineageSeverity.CONFLICT,
                    "workflow phase requires certificate binding",
                )
            return (
                None,
                self._state(
                    expected=expected,
                    present=False,
                    # Missing artifacts that are not required yet are benign,
                    # but they are not "verified": verification is meaningful
                    # only for a present artifact.  Keep absence and validity
                    # as separate dimensions so the state invariant remains
                    # fail-closed.
                    verified=False,
                ),
            )
        try:
            item = self.certificates.get(
                workflow.certificate_id
            )
        except Exception as exc:
            self._add(
                findings,
                "certificate.lookup_corruption",
                CompactionLineageSeverity.CORRUPTION,
                "certificate lookup/verification raised "
                f"{type(exc).__name__}",
            )
            return (
                None,
                self._state(
                    expected=True,
                    present=False,
                    verified=False,
                    artifact_id=workflow.certificate_id,
                    artifact_digest=(
                        workflow.certificate_digest
                    ),
                ),
            )
        if item is None:
            self._add(
                findings,
                "certificate.missing",
                CompactionLineageSeverity.MISSING,
                "workflow-bound compaction certificate is missing",
            )
            return (
                None,
                self._state(
                    expected=True,
                    present=False,
                    verified=False,
                    artifact_id=workflow.certificate_id,
                    artifact_digest=(
                        workflow.certificate_digest
                    ),
                ),
            )

        cert = item.certificate
        ok = True
        for code, left, right, message in (
            (
                "certificate.digest",
                workflow.certificate_digest,
                cert.digest,
                "certificate digest differs from workflow",
            ),
            (
                "certificate.chain",
                workflow.chain_id,
                cert.chain_id,
                "certificate chain differs from workflow",
            ),
            (
                "certificate.readiness",
                workflow.readiness_digest,
                cert.readiness_digest,
                "certificate readiness differs from workflow",
            ),
            (
                "certificate.retention",
                workflow.retention_plan_digest,
                cert.retention_plan_digest,
                "certificate retention plan differs from workflow",
            ),
            (
                "certificate.policy",
                workflow.compaction_policy_digest,
                cert.compaction_policy_digest,
                "certificate compaction policy differs from workflow",
            ),
            (
                "certificate.current_sequence",
                workflow.current_sequence,
                cert.current_sequence,
                "certificate current sequence differs from workflow",
            ),
            (
                "certificate.current_root",
                workflow.current_root,
                cert.current_root,
                "certificate current root differs from workflow",
            ),
            (
                "certificate.cutoff_sequence",
                workflow.cutoff_sequence,
                cert.cutoff_sequence,
                "certificate cutoff sequence differs from workflow",
            ),
            (
                "certificate.cutoff_root",
                workflow.cutoff_root,
                cert.cutoff_root,
                "certificate cutoff root differs from workflow",
            ),
            (
                "certificate.archive",
                workflow.archive_id,
                cert.archive_id,
                "certificate archive differs from workflow",
            ),
            (
                "certificate.archive_manifest",
                workflow.archive_manifest_digest,
                cert.archive_manifest_digest,
                "certificate archive manifest differs from workflow",
            ),
        ):
            ok = (
                self._check_equal(
                    findings,
                    code=code,
                    left=left,
                    right=right,
                    message=message,
                )
                and ok
            )
        return (
            item,
            self._state(
                expected=True,
                present=True,
                verified=ok,
                artifact_id=cert.certificate_id,
                artifact_digest=cert.digest,
            ),
        )

    def _authorization(
        self,
        workflow: DurableCompactionWorkflow,
        certificate,
        findings: list[
            CompactionLineageFinding
        ],
    ):
        expected = self._expected(
            workflow,
            DurableCompactionWorkflowPhase.AUTHORIZED,
        )
        if not workflow.authorization_id:
            if expected:
                self._add(
                    findings,
                    "authorization.binding_missing",
                    CompactionLineageSeverity.CONFLICT,
                    "workflow phase requires authorization binding",
                )
            return (
                None,
                self._state(
                    expected=expected,
                    present=False,
                    # Missing artifacts that are not required yet are benign,
                    # but they are not "verified": verification is meaningful
                    # only for a present artifact.  Keep absence and validity
                    # as separate dimensions so the state invariant remains
                    # fail-closed.
                    verified=False,
                ),
            )
        try:
            item = self.authorizations.get(
                workflow.authorization_id
            )
        except Exception as exc:
            self._add(
                findings,
                "authorization.lookup_corruption",
                CompactionLineageSeverity.CORRUPTION,
                "authorization lookup/verification raised "
                f"{type(exc).__name__}",
            )
            return (
                None,
                self._state(
                    expected=True,
                    present=False,
                    verified=False,
                    artifact_id=workflow.authorization_id,
                    artifact_digest=(
                        workflow.authorization_digest
                    ),
                ),
            )
        if item is None:
            self._add(
                findings,
                "authorization.missing",
                CompactionLineageSeverity.MISSING,
                "workflow-bound pruning authorization is missing",
            )
            return (
                None,
                self._state(
                    expected=True,
                    present=False,
                    verified=False,
                    artifact_id=workflow.authorization_id,
                    artifact_digest=(
                        workflow.authorization_digest
                    ),
                ),
            )

        auth = item.authorization
        ok = True
        checks = (
            (
                "authorization.digest",
                workflow.authorization_digest,
                auth.digest,
                "authorization digest differs from workflow",
            ),
            (
                "authorization.chain",
                workflow.chain_id,
                auth.chain_id,
                "authorization chain differs from workflow",
            ),
            (
                "authorization.retention",
                workflow.retention_plan_digest,
                auth.retention_plan_digest,
                "authorization retention differs from workflow",
            ),
            (
                "authorization.policy",
                workflow.compaction_policy_digest,
                auth.compaction_policy_digest,
                "authorization policy differs from workflow",
            ),
            (
                "authorization.current_sequence",
                workflow.current_sequence,
                auth.current_sequence,
                "authorization current sequence differs from workflow",
            ),
            (
                "authorization.current_root",
                workflow.current_root,
                auth.current_root,
                "authorization current root differs from workflow",
            ),
            (
                "authorization.cutoff_sequence",
                workflow.cutoff_sequence,
                auth.cutoff_sequence,
                "authorization cutoff sequence differs from workflow",
            ),
            (
                "authorization.cutoff_root",
                workflow.cutoff_root,
                auth.cutoff_root,
                "authorization cutoff root differs from workflow",
            ),
            (
                "authorization.previous_sequence",
                workflow.previous_floor_sequence,
                auth.previous_floor_sequence,
                "authorization previous floor sequence differs from workflow",
            ),
            (
                "authorization.previous_root",
                workflow.previous_floor_root,
                auth.previous_floor_root,
                "authorization previous floor root differs from workflow",
            ),
            (
                "authorization.delete_count",
                workflow.delete_count,
                auth.delete_count,
                "authorization delete count differs from workflow",
            ),
            (
                "authorization.archive",
                workflow.archive_id,
                auth.archive_id,
                "authorization archive differs from workflow",
            ),
            (
                "authorization.archive_manifest",
                workflow.archive_manifest_digest,
                auth.archive_manifest_digest,
                "authorization archive manifest differs from workflow",
            ),
            (
                "authorization.operator",
                workflow.operator_id,
                auth.operator_id,
                "authorization operator differs from workflow",
            ),
        )
        for code, left, right, message in checks:
            ok = (
                self._check_equal(
                    findings,
                    code=code,
                    left=left,
                    right=right,
                    message=message,
                )
                and ok
            )

        if certificate is not None:
            cert = certificate.certificate
            for code, left, right, message in (
                (
                    "authorization.certificate_id",
                    cert.certificate_id,
                    auth.certificate_id,
                    "authorization references different certificate",
                ),
                (
                    "authorization.certificate_digest",
                    cert.digest,
                    auth.certificate_digest,
                    "authorization certificate digest differs",
                ),
                (
                    "authorization.protected_roots",
                    cert.protected_roots_digest,
                    auth.protected_roots_digest,
                    "authorization protected roots differ from certificate",
                ),
            ):
                ok = (
                    self._check_equal(
                        findings,
                        code=code,
                        left=left,
                        right=right,
                        message=message,
                    )
                    and ok
                )

        return (
            item,
            self._state(
                expected=True,
                present=True,
                verified=ok,
                artifact_id=auth.authorization_id,
                artifact_digest=auth.digest,
            ),
        )

    def _archive(
        self,
        workflow: DurableCompactionWorkflow,
        findings: list[
            CompactionLineageFinding
        ],
    ):
        # Archive coverage is part of the workflow binding from PLANNED onward.
        try:
            stored = self.archives.get(
                workflow.archive_id
            )
        except Exception as exc:
            self._add(
                findings,
                "archive.lookup_corruption",
                CompactionLineageSeverity.CORRUPTION,
                "archive lookup raised "
                f"{type(exc).__name__}",
            )
            return (
                None,
                self._state(
                    expected=True,
                    present=False,
                    verified=False,
                    artifact_id=workflow.archive_id,
                    artifact_digest=(
                        workflow.archive_manifest_digest
                    ),
                ),
            )
        if stored is None:
            self._add(
                findings,
                "archive.missing",
                CompactionLineageSeverity.MISSING,
                "workflow-bound durable archive is missing",
            )
            return (
                None,
                self._state(
                    expected=True,
                    present=False,
                    verified=False,
                    artifact_id=workflow.archive_id,
                    artifact_digest=(
                        workflow.archive_manifest_digest
                    ),
                ),
            )

        manifest = stored.manifest.manifest
        ok = True
        try:
            archive_verified = bool(
                self.archives.verify_archive(
                    stored
                )
            )
        except Exception as exc:
            archive_verified = False
            self._add(
                findings,
                "archive.verify_corruption",
                CompactionLineageSeverity.CORRUPTION,
                "archive verification raised "
                f"{type(exc).__name__}",
            )
        if not archive_verified:
            self._add(
                findings,
                "archive.invalid",
                CompactionLineageSeverity.CORRUPTION,
                "workflow-bound archive failed canonical verification",
            )
            ok = False

        for code, left, right, message in (
            (
                "archive.id",
                workflow.archive_id,
                manifest.archive_id,
                "archive id differs from workflow",
            ),
            (
                "archive.chain",
                workflow.chain_id,
                manifest.chain_id,
                "archive chain differs from workflow",
            ),
            (
                "archive.manifest_digest",
                workflow.archive_manifest_digest,
                manifest.digest,
                "archive manifest digest differs from workflow",
            ),
        ):
            ok = (
                self._check_equal(
                    findings,
                    code=code,
                    left=left,
                    right=right,
                    message=message,
                )
                and ok
            )

        if manifest.checkpoint_sequence < workflow.cutoff_sequence:
            self._add(
                findings,
                "archive.cutoff_not_covered",
                CompactionLineageSeverity.CONFLICT,
                "archive checkpoint does not cover workflow cutoff",
            )
            ok = False
        elif workflow.cutoff_sequence > 0:
            try:
                entry = manifest.entries[
                    workflow.cutoff_sequence - 1
                ]
                if entry.node_hash != workflow.cutoff_root:
                    self._add(
                        findings,
                        "archive.cutoff_root",
                        CompactionLineageSeverity.CONFLICT,
                        "archive entry at cutoff sequence differs from workflow cutoff root",
                    )
                    ok = False
            except Exception as exc:
                self._add(
                    findings,
                    "archive.cutoff_lookup_corruption",
                    CompactionLineageSeverity.CORRUPTION,
                    "archive cutoff lookup raised "
                    f"{type(exc).__name__}",
                )
                ok = False

        try:
            if not self.archives.verify_root(
                workflow.chain_id,
                workflow.cutoff_root,
            ):
                self._add(
                    findings,
                    "archive.cutoff_unverifiable",
                    CompactionLineageSeverity.CORRUPTION,
                    "workflow cutoff root is not verifiable from archive",
                )
                ok = False
        except Exception as exc:
            self._add(
                findings,
                "archive.cutoff_verify_error",
                CompactionLineageSeverity.CORRUPTION,
                "cutoff root verification raised "
                f"{type(exc).__name__}",
            )
            ok = False

        return (
            stored,
            self._state(
                expected=True,
                present=True,
                verified=ok,
                artifact_id=manifest.archive_id,
                artifact_digest=manifest.digest,
            ),
        )

    def _manifest(
        self,
        workflow: DurableCompactionWorkflow,
        authorization,
        findings: list[
            CompactionLineageFinding
        ],
    ):
        expected = self._expected(
            workflow,
            DurableCompactionWorkflowPhase.PREPARED,
        )
        if not workflow.pruning_operation_id:
            if expected:
                self._add(
                    findings,
                    "manifest.operation_binding_missing",
                    CompactionLineageSeverity.CONFLICT,
                    "workflow phase requires pruning operation binding",
                )
            return (
                None,
                self._state(
                    expected=expected,
                    present=False,
                    # Missing artifacts that are not required yet are benign,
                    # but they are not "verified": verification is meaningful
                    # only for a present artifact.  Keep absence and validity
                    # as separate dimensions so the state invariant remains
                    # fail-closed.
                    verified=False,
                ),
            )
        try:
            item = self.pruning.manifest(
                workflow.pruning_operation_id
            )
        except Exception as exc:
            self._add(
                findings,
                "manifest.lookup_corruption",
                CompactionLineageSeverity.CORRUPTION,
                "pruning manifest lookup raised "
                f"{type(exc).__name__}",
            )
            return (
                None,
                self._state(
                    expected=True,
                    present=False,
                    verified=False,
                    artifact_id=workflow.pruning_operation_id,
                    artifact_digest=(
                        workflow.pruning_manifest_digest
                    ),
                ),
            )
        if item is None:
            self._add(
                findings,
                "manifest.missing",
                CompactionLineageSeverity.MISSING,
                "workflow-bound pruning manifest is missing",
            )
            return (
                None,
                self._state(
                    expected=True,
                    present=False,
                    verified=False,
                    artifact_id=workflow.pruning_operation_id,
                    artifact_digest=(
                        workflow.pruning_manifest_digest
                    ),
                ),
            )

        manifest: DurablePruningManifest = item
        ok = True
        checks = (
            (
                "manifest.digest",
                workflow.pruning_manifest_digest,
                manifest.digest,
                "pruning manifest digest differs from workflow",
            ),
            (
                "manifest.operation",
                workflow.pruning_operation_id,
                manifest.operation_id,
                "pruning manifest operation differs from workflow",
            ),
            (
                "manifest.chain",
                workflow.chain_id,
                manifest.chain_id,
                "pruning manifest chain differs from workflow",
            ),
            (
                "manifest.current_sequence",
                workflow.current_sequence,
                manifest.current_sequence,
                "pruning manifest current sequence differs from workflow",
            ),
            (
                "manifest.current_root",
                workflow.current_root,
                manifest.current_root,
                "pruning manifest current root differs from workflow",
            ),
            (
                "manifest.previous_sequence",
                workflow.previous_floor_sequence,
                manifest.previous_floor_sequence,
                "pruning manifest previous floor sequence differs from workflow",
            ),
            (
                "manifest.previous_root",
                workflow.previous_floor_root,
                manifest.previous_floor_root,
                "pruning manifest previous floor root differs from workflow",
            ),
            (
                "manifest.cutoff_sequence",
                workflow.cutoff_sequence,
                manifest.cutoff_sequence,
                "pruning manifest cutoff sequence differs from workflow",
            ),
            (
                "manifest.cutoff_root",
                workflow.cutoff_root,
                manifest.cutoff_root,
                "pruning manifest cutoff root differs from workflow",
            ),
            (
                "manifest.archive",
                workflow.archive_id,
                manifest.archive_id,
                "pruning manifest archive differs from workflow",
            ),
            (
                "manifest.archive_digest",
                workflow.archive_manifest_digest,
                manifest.archive_manifest_digest,
                "pruning manifest archive digest differs from workflow",
            ),
            (
                "manifest.delete_count",
                workflow.delete_count,
                manifest.delete_count,
                "pruning manifest delete count differs from workflow",
            ),
        )
        for code, left, right, message in checks:
            ok = (
                self._check_equal(
                    findings,
                    code=code,
                    left=left,
                    right=right,
                    message=message,
                )
                and ok
            )
        if authorization is not None:
            ok = (
                self._check_equal(
                    findings,
                    code="manifest.authorization",
                    left=authorization.authorization.authorization_id,
                    right=manifest.authorization_id,
                    message="pruning manifest references different authorization",
                )
                and ok
            )
        return (
            manifest,
            self._state(
                expected=True,
                present=True,
                verified=ok,
                artifact_id=manifest.operation_id,
                artifact_digest=manifest.digest,
            ),
        )

    def _operation(
        self,
        workflow: DurableCompactionWorkflow,
        manifest: DurablePruningManifest | None,
        findings: list[
            CompactionLineageFinding
        ],
    ):
        expected = self._expected(
            workflow,
            DurableCompactionWorkflowPhase.PREPARED,
        )
        if not workflow.pruning_operation_id:
            return (
                None,
                self._state(
                    expected=expected,
                    present=False,
                    # Missing artifacts that are not required yet are benign,
                    # but they are not "verified": verification is meaningful
                    # only for a present artifact.  Keep absence and validity
                    # as separate dimensions so the state invariant remains
                    # fail-closed.
                    verified=False,
                ),
            )
        try:
            item = self.pruning.operation(
                workflow.pruning_operation_id
            )
        except Exception as exc:
            self._add(
                findings,
                "operation.lookup_corruption",
                CompactionLineageSeverity.CORRUPTION,
                "pruning operation lookup raised "
                f"{type(exc).__name__}",
            )
            return (
                None,
                self._state(
                    expected=True,
                    present=False,
                    verified=False,
                    artifact_id=workflow.pruning_operation_id,
                ),
            )
        if item is None:
            self._add(
                findings,
                "operation.missing",
                CompactionLineageSeverity.MISSING,
                "workflow-bound pruning operation is missing",
            )
            return (
                None,
                self._state(
                    expected=True,
                    present=False,
                    verified=False,
                    artifact_id=workflow.pruning_operation_id,
                ),
            )

        operation: DurablePruningOperation = item
        ok = True
        for code, left, right, message in (
            (
                "operation.id",
                workflow.pruning_operation_id,
                operation.operation_id,
                "pruning operation id differs from workflow",
            ),
            (
                "operation.chain",
                workflow.chain_id,
                operation.chain_id,
                "pruning operation chain differs from workflow",
            ),
            (
                "operation.manifest_digest",
                workflow.pruning_manifest_digest,
                operation.manifest_digest,
                "pruning operation manifest digest differs from workflow",
            ),
            (
                "operation.phase",
                workflow.pruning_phase,
                operation.phase.value,
                "pruning operation phase differs from workflow",
            ),
            (
                "operation.deleted_items",
                workflow.deleted_items,
                operation.deleted_items,
                "pruning operation deleted count differs from workflow",
            ),
        ):
            ok = (
                self._check_equal(
                    findings,
                    code=code,
                    left=left,
                    right=right,
                    message=message,
                )
                and ok
            )
        if manifest is not None:
            ok = (
                self._check_equal(
                    findings,
                    code="operation.manifest",
                    left=manifest.digest,
                    right=operation.manifest_digest,
                    message="pruning operation does not bind frozen manifest",
                )
                and ok
            )
            ok = (
                self._check_equal(
                    findings,
                    code="operation.authorization",
                    left=manifest.authorization_id,
                    right=operation.authorization_id,
                    message="pruning operation authorization differs from manifest",
                )
                and ok
            )
        if workflow.floor_id:
            ok = (
                self._check_equal(
                    findings,
                    code="operation.floor",
                    left=workflow.floor_id,
                    right=operation.floor_id,
                    message="pruning operation floor differs from workflow",
                )
                and ok
            )
        return (
            operation,
            self._state(
                expected=True,
                present=True,
                verified=ok,
                artifact_id=operation.operation_id,
            ),
        )

    def _floor(
        self,
        workflow: DurableCompactionWorkflow,
        certificate,
        authorization,
        operation: DurablePruningOperation | None,
        findings: list[
            CompactionLineageFinding
        ],
    ):
        expected = (
            workflow.phase
            is DurableCompactionWorkflowPhase.COMPLETE
            or bool(workflow.floor_id)
        )
        if not expected:
            return (
                None,
                self._state(
                    expected=False,
                    present=False,
                    verified=True,
                ),
            )
        if not workflow.floor_id:
            self._add(
                findings,
                "floor.binding_missing",
                CompactionLineageSeverity.CONFLICT,
                "complete workflow lacks floor binding",
            )
            return (
                None,
                self._state(
                    expected=True,
                    present=False,
                    verified=False,
                ),
            )

        try:
            item = self.hot_floors.floor_at(
                workflow.chain_id,
                workflow.cutoff_sequence,
            )
        except Exception as exc:
            self._add(
                findings,
                "floor.lookup_corruption",
                CompactionLineageSeverity.CORRUPTION,
                "historical hot floor lookup raised "
                f"{type(exc).__name__}",
            )
            return (
                None,
                self._state(
                    expected=True,
                    present=False,
                    verified=False,
                    artifact_id=workflow.floor_id,
                ),
            )
        if item is None:
            self._add(
                findings,
                "floor.missing",
                CompactionLineageSeverity.MISSING,
                "workflow-bound historical hot floor is missing",
            )
            return (
                None,
                self._state(
                    expected=True,
                    present=False,
                    verified=False,
                    artifact_id=workflow.floor_id,
                ),
            )

        floor_item: SignedDurableHotFloor = item
        floor = floor_item.floor
        ok = True
        try:
            history = self.hot_floors.inspect_history(
                workflow.chain_id
            )
        except Exception as exc:
            history = None
            self._add(
                findings,
                "floor.history_corruption",
                CompactionLineageSeverity.CORRUPTION,
                "hot floor history inspection raised "
                f"{type(exc).__name__}",
            )
            ok = False
        if history is not None:
            if not history.ok:
                self._add(
                    findings,
                    "floor.history_incomplete",
                    CompactionLineageSeverity.CORRUPTION,
                    (
                        history.issues[0]
                        if history.issues
                        else "hot floor history is incomplete"
                    ),
                )
                ok = False
            elif not any(
                historical.floor.floor_id
                == floor.floor_id
                for historical in history.floors
            ):
                self._add(
                    findings,
                    "floor.not_committed_ancestor",
                    CompactionLineageSeverity.CONFLICT,
                    "historical floor is not on committed floor lineage",
                )
                ok = False
        checks = (
            (
                "floor.id",
                workflow.floor_id,
                floor.floor_id,
                "hot floor id differs from workflow",
            ),
            (
                "floor.chain",
                workflow.chain_id,
                floor.chain_id,
                "hot floor chain differs from workflow",
            ),
            (
                "floor.sequence",
                workflow.cutoff_sequence,
                floor.sequence,
                "hot floor sequence differs from workflow cutoff",
            ),
            (
                "floor.root",
                workflow.cutoff_root,
                floor.root_hash,
                "hot floor root differs from workflow cutoff",
            ),
            (
                "floor.previous_sequence",
                workflow.previous_floor_sequence,
                floor.previous_sequence,
                "hot floor previous sequence differs from workflow",
            ),
            (
                "floor.previous_root",
                workflow.previous_floor_root,
                floor.previous_root_hash,
                "hot floor previous root differs from workflow",
            ),
            (
                "floor.archive",
                workflow.archive_id,
                floor.archive_id,
                "hot floor archive differs from workflow",
            ),
            (
                "floor.archive_manifest",
                workflow.archive_manifest_digest,
                floor.archive_manifest_digest,
                "hot floor archive manifest differs from workflow",
            ),
            (
                "floor.operation",
                workflow.pruning_operation_id,
                floor.operation_id,
                "hot floor operation differs from workflow",
            ),
        )
        for code, left, right, message in checks:
            ok = (
                self._check_equal(
                    findings,
                    code=code,
                    left=left,
                    right=right,
                    message=message,
                )
                and ok
            )
        if certificate is not None:
            ok = (
                self._check_equal(
                    findings,
                    code="floor.certificate",
                    left=certificate.certificate.certificate_id,
                    right=floor.compaction_certificate_id,
                    message="hot floor certificate differs from workflow certificate",
                )
                and ok
            )
        if authorization is not None:
            ok = (
                self._check_equal(
                    findings,
                    code="floor.authorization",
                    left=authorization.authorization.authorization_id,
                    right=floor.pruning_authorization_id,
                    message="hot floor authorization differs from workflow authorization",
                )
                and ok
            )
        if operation is not None:
            ok = (
                self._check_equal(
                    findings,
                    code="floor.operation_floor",
                    left=operation.floor_id,
                    right=floor.floor_id,
                    message="pruning operation and hot floor disagree",
                )
                and ok
            )
            if operation.fencing_token != floor.fencing_token:
                self._add(
                    findings,
                    "floor.fencing_token",
                    CompactionLineageSeverity.CONFLICT,
                    "hot floor fencing token differs from pruning operation",
                )
                ok = False

        return (
            floor_item,
            self._state(
                expected=True,
                present=True,
                verified=ok,
                artifact_id=floor.floor_id,
                artifact_digest=floor.digest,
            ),
        )

    @staticmethod
    def _status(
        workflow: DurableCompactionWorkflow,
        findings: tuple[
            CompactionLineageFinding,
            ...,
        ],
    ) -> CompactionLineageStatus:
        if any(
            item.severity
            in {
                CompactionLineageSeverity.CONFLICT,
                CompactionLineageSeverity.CORRUPTION,
            }
            for item in findings
        ):
            return (
                CompactionLineageStatus.MANUAL_REVIEW
            )
        if any(
            item.severity
            is CompactionLineageSeverity.MISSING
            for item in findings
        ):
            # Once an immutable id is bound, losing the referenced artifact is
            # historical evidence loss, not a safe resumable state.
            return (
                CompactionLineageStatus.MANUAL_REVIEW
            )
        if (
            workflow.phase
            is DurableCompactionWorkflowPhase.COMPLETE
        ):
            return CompactionLineageStatus.VERIFIED
        if (
            workflow.phase
            is DurableCompactionWorkflowPhase.MANUAL_REVIEW
        ):
            return (
                CompactionLineageStatus.MANUAL_REVIEW
            )
        return CompactionLineageStatus.INCOMPLETE

    def inspect(
        self,
        workflow_id: str,
    ) -> DurableCompactionLineageReport:
        if (
            not isinstance(workflow_id, str)
            or not workflow_id
            or len(workflow_id) != 64
        ):
            raise ValueError(
                "workflow_id must be 64-character digest"
            )
        try:
            stored = self.operator.current(
                workflow_id
            )
        except Exception as exc:
            finding = CompactionLineageFinding(
                "workflow.lookup_corruption",
                CompactionLineageSeverity.CORRUPTION,
                "workflow lookup raised "
                f"{type(exc).__name__}",
            )
            return DurableCompactionLineageReport(
                workflow_id,
                "",
                "",
                None,
                CompactionLineageStatus.MANUAL_REVIEW,
                "",
                self._state(
                    expected=False,
                    present=False,
                    verified=False,
                ),
                self._state(
                    expected=False,
                    present=False,
                    verified=False,
                ),
                self._state(
                    expected=False,
                    present=False,
                    verified=False,
                ),
                self._state(
                    expected=False,
                    present=False,
                    verified=False,
                ),
                self._state(
                    expected=False,
                    present=False,
                    verified=False,
                ),
                self._state(
                    expected=False,
                    present=False,
                    verified=False,
                ),
                (finding,),
            )

        if stored is None:
            finding = CompactionLineageFinding(
                "workflow.missing",
                CompactionLineageSeverity.MISSING,
                "compaction workflow is missing",
            )
            return DurableCompactionLineageReport(
                workflow_id,
                "",
                "",
                None,
                CompactionLineageStatus.INCOMPLETE,
                "",
                self._state(
                    expected=False,
                    present=False,
                    verified=False,
                ),
                self._state(
                    expected=False,
                    present=False,
                    verified=False,
                ),
                self._state(
                    expected=False,
                    present=False,
                    verified=False,
                ),
                self._state(
                    expected=False,
                    present=False,
                    verified=False,
                ),
                self._state(
                    expected=False,
                    present=False,
                    verified=False,
                ),
                self._state(
                    expected=False,
                    present=False,
                    verified=False,
                ),
                (finding,),
            )

        workflow = stored.workflow
        findings: list[
            CompactionLineageFinding
        ] = []

        certificate, certificate_state = (
            self._certificate(
                workflow,
                findings,
            )
        )
        authorization, authorization_state = (
            self._authorization(
                workflow,
                certificate,
                findings,
            )
        )
        _, archive_state = self._archive(
            workflow,
            findings,
        )
        manifest, manifest_state = self._manifest(
            workflow,
            authorization,
            findings,
        )
        operation, operation_state = self._operation(
            workflow,
            manifest,
            findings,
        )
        _, floor_state = self._floor(
            workflow,
            certificate,
            authorization,
            operation,
            findings,
        )

        findings_tuple = tuple(findings)
        return DurableCompactionLineageReport(
            workflow.workflow_id,
            workflow.chain_id,
            workflow.phase.value,
            stored.revision,
            self._status(
                workflow,
                findings_tuple,
            ),
            self._workflow_digest(
                workflow
            ),
            certificate_state,
            authorization_state,
            archive_state,
            manifest_state,
            operation_state,
            floor_state,
            findings_tuple,
        )

    def require_verified(
        self,
        workflow_id: str,
    ) -> DurableCompactionLineageReport:
        report = self.inspect(
            workflow_id
        )
        if not report.ok:
            detail = (
                report.findings[0].message
                if report.findings
                else (
                    "durable compaction lineage "
                    f"is {report.status.value}"
                )
            )
            raise DurableCompactionLineageError(
                detail
            )
        return report
