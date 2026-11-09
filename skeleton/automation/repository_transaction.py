"""Fail-closed autonomous repository mutation lifecycle for VOL-022.

The lifecycle carries proposal and verification evidence only. It never grants
repository write/merge authority. Mutation authority remains external to this
state machine.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Iterable

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.automation.transactional_workspace import (
    EditLease,
    WorkspaceError,
    WorkspaceReceipt,
)
from skeleton.automation.independent_review import ReviewReceipt, verify_review


MAX_PLANNED_PATHS = 256
MAX_ID_BYTES = 256


class MutationPhase(str, Enum):
    INSPECT = "inspect"
    PLAN = "plan"
    LEASE = "lease"
    EDIT = "edit"
    BUILD = "build"
    TEST = "test"
    REVIEW = "review"
    VERIFY = "verify"
    COMPLETE = "complete"
    FAILED = "failed"


def _digest(value: object) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def _hex(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise WorkspaceError(f"invalid {field}")
    return value


def _identity(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > MAX_ID_BYTES
    ):
        raise WorkspaceError(f"invalid {field}")
    return value


def _path(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise WorkspaceError("invalid planned path")
    if value.startswith(("/", "\\")) or "\\" in value:
        raise WorkspaceError("planned path must be repository-relative POSIX")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise WorkspaceError("planned path traversal or ambiguity")
    return value


@dataclass(frozen=True, slots=True)
class ChangePlan:
    transaction_id: str
    proposer_id: str
    base_digest: str
    planned_paths: tuple[str, ...]
    authority_scope: str = "change-plan-proposal-only"

    def __post_init__(self) -> None:
        object.__setattr__(self, "transaction_id", _identity(self.transaction_id, "transaction_id"))
        object.__setattr__(self, "proposer_id", _identity(self.proposer_id, "proposer_id"))
        object.__setattr__(self, "base_digest", _hex(self.base_digest, "base_digest"))
        if (
            not isinstance(self.planned_paths, tuple)
            or not self.planned_paths
            or len(self.planned_paths) > MAX_PLANNED_PATHS
        ):
            raise WorkspaceError("invalid planned path set")
        paths = tuple(sorted(_path(path) for path in self.planned_paths))
        if len(paths) != len(set(paths)):
            raise WorkspaceError("duplicate planned path")
        object.__setattr__(self, "planned_paths", paths)
        if self.authority_scope != "change-plan-proposal-only":
            raise WorkspaceError("change plan cannot grant repository authority")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "transaction_id": self.transaction_id,
                "proposer_id": self.proposer_id,
                "base_digest": self.base_digest,
                "planned_paths": self.planned_paths,
                "authority_scope": self.authority_scope,
            }
        )


@dataclass(frozen=True, slots=True)
class PatchReceipt:
    plan_digest: str
    workspace_result_digest: str
    workspace_operation_digest: str
    lease_digest: str
    changed_paths: tuple[str, ...]
    rollback_base_digest: str
    authority_scope: str = "patch-evidence-only"

    def __post_init__(self) -> None:
        for field in (
            "plan_digest",
            "workspace_result_digest",
            "workspace_operation_digest",
            "lease_digest",
            "rollback_base_digest",
        ):
            object.__setattr__(self, field, _hex(getattr(self, field), field))
        if not isinstance(self.changed_paths, tuple):
            raise WorkspaceError("changed_paths must be tuple")
        paths = tuple(sorted(_path(path) for path in self.changed_paths))
        if len(paths) != len(set(paths)):
            raise WorkspaceError("duplicate changed path")
        object.__setattr__(self, "changed_paths", paths)
        if self.authority_scope != "patch-evidence-only":
            raise WorkspaceError("patch receipt cannot grant repository authority")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "plan_digest": self.plan_digest,
                "workspace_result_digest": self.workspace_result_digest,
                "workspace_operation_digest": self.workspace_operation_digest,
                "lease_digest": self.lease_digest,
                "changed_paths": self.changed_paths,
                "rollback_base_digest": self.rollback_base_digest,
                "authority_scope": self.authority_scope,
            }
        )


@dataclass(frozen=True, slots=True)
class PhaseEvidence:
    phase: MutationPhase
    evidence_digest: str
    success: bool
    authority_scope: str = "repository-engineering-evidence-only"

    def __post_init__(self) -> None:
        if not isinstance(self.phase, MutationPhase):
            raise WorkspaceError("typed mutation phase required")
        object.__setattr__(self, "evidence_digest", _hex(self.evidence_digest, "evidence_digest"))
        if not isinstance(self.success, bool):
            raise WorkspaceError("phase success must be bool")
        if self.authority_scope != "repository-engineering-evidence-only":
            raise WorkspaceError("phase evidence cannot grant repository authority")


class RepositoryMutationTransaction:
    """Enforce inspect→plan→lease→edit→build→test→review→verify."""

    def __init__(self, *, transaction_id: str, proposer_id: str) -> None:
        self.transaction_id = _identity(transaction_id, "transaction_id")
        self.proposer_id = _identity(proposer_id, "proposer_id")
        self.phase = MutationPhase.INSPECT
        self._base_digest: str | None = None
        self.plan: ChangePlan | None = None
        self.lease: EditLease | None = None
        self.workspace_receipt: WorkspaceReceipt | None = None
        self.patch_receipt: PatchReceipt | None = None
        self.review_receipt: ReviewReceipt | None = None
        self._evidence: list[PhaseEvidence] = []

    @property
    def evidence(self) -> tuple[PhaseEvidence, ...]:
        return tuple(self._evidence)

    def _require(self, expected: MutationPhase) -> None:
        if self.phase != expected:
            raise WorkspaceError(
                f"mutation phase mismatch: expected {expected.value}, got {self.phase.value}"
            )

    def _record(self, phase: MutationPhase, digest: str, success: bool = True) -> None:
        self._evidence.append(PhaseEvidence(phase, digest, success))

    def record_inspection(self, *, base_digest: str, evidence_digest: str) -> None:
        self._require(MutationPhase.INSPECT)
        self._base_digest = _hex(base_digest, "base_digest")
        self._record(MutationPhase.INSPECT, evidence_digest)
        self.phase = MutationPhase.PLAN

    def record_plan(self, *, planned_paths: tuple[str, ...]) -> ChangePlan:
        self._require(MutationPhase.PLAN)
        if self._base_digest is None:
            raise WorkspaceError("inspection base digest missing")
        plan = ChangePlan(
            self.transaction_id,
            self.proposer_id,
            self._base_digest,
            planned_paths,
        )
        self.plan = plan
        self._record(MutationPhase.PLAN, plan.digest)
        self.phase = MutationPhase.LEASE
        return plan

    def bind_lease(self, lease: EditLease) -> None:
        self._require(MutationPhase.LEASE)
        if not isinstance(lease, EditLease):
            raise WorkspaceError("typed edit lease required")
        if self.plan is None:
            raise WorkspaceError("change plan missing")
        if lease.base_digest != self.plan.base_digest:
            raise WorkspaceError("edit lease base does not match change plan")
        if lease.owner_id != self.plan.proposer_id:
            raise WorkspaceError("edit lease owner does not match proposer")
        if lease.paths != self.plan.planned_paths:
            raise WorkspaceError("edit lease paths must exactly match change plan")
        self.lease = lease
        self._record(MutationPhase.LEASE, lease.digest)
        self.phase = MutationPhase.EDIT

    def record_edit(self, workspace: WorkspaceReceipt) -> PatchReceipt:
        self._require(MutationPhase.EDIT)
        if not isinstance(workspace, WorkspaceReceipt):
            raise WorkspaceError("typed workspace receipt required")
        if self.plan is None or self.lease is None:
            raise WorkspaceError("plan/lease binding missing")
        if workspace.base_digest != self.plan.base_digest:
            raise WorkspaceError("workspace base does not match change plan")
        changed = tuple(sorted(workspace.changed_paths))
        if not set(changed).issubset(set(self.plan.planned_paths)):
            raise WorkspaceError("workspace changed path outside change plan")
        patch = PatchReceipt(
            plan_digest=self.plan.digest,
            workspace_result_digest=workspace.result_digest,
            workspace_operation_digest=workspace.operation_digest,
            lease_digest=self.lease.digest,
            changed_paths=changed,
            rollback_base_digest=workspace.base_digest,
        )
        self.workspace_receipt = workspace
        self.patch_receipt = patch
        self._record(MutationPhase.EDIT, patch.digest)
        self.phase = MutationPhase.BUILD
        return patch

    def record_build(self, *, evidence_digest: str, success: bool) -> None:
        self._require(MutationPhase.BUILD)
        self._record(MutationPhase.BUILD, evidence_digest, success)
        self.phase = MutationPhase.TEST if success else MutationPhase.FAILED

    def record_test(self, *, evidence_digest: str, success: bool) -> None:
        self._require(MutationPhase.TEST)
        self._record(MutationPhase.TEST, evidence_digest, success)
        self.phase = MutationPhase.REVIEW if success else MutationPhase.FAILED

    def record_review(self, review: ReviewReceipt) -> None:
        self._require(MutationPhase.REVIEW)
        if not isinstance(review, ReviewReceipt):
            raise WorkspaceError("typed review receipt required")
        if self.workspace_receipt is None:
            raise WorkspaceError("workspace receipt missing")
        valid = verify_review(self.workspace_receipt, review)
        self._record(MutationPhase.REVIEW, review.review_digest, valid)
        if not valid:
            self.phase = MutationPhase.FAILED
            raise WorkspaceError("independent review did not approve exact patch")
        self.review_receipt = review
        self.phase = MutationPhase.VERIFY

    def record_verification(self, *, evidence_digest: str, success: bool) -> None:
        self._require(MutationPhase.VERIFY)
        self._record(MutationPhase.VERIFY, evidence_digest, success)
        self.phase = MutationPhase.COMPLETE if success else MutationPhase.FAILED

    @property
    def completion_digest(self) -> str:
        if self.phase != MutationPhase.COMPLETE:
            raise WorkspaceError("mutation transaction is not complete")
        if self.plan is None or self.patch_receipt is None or self.review_receipt is None:
            raise WorkspaceError("completion evidence is incomplete")
        return _digest(
            {
                "transaction_id": self.transaction_id,
                "proposer_id": self.proposer_id,
                "plan_digest": self.plan.digest,
                "patch_digest": self.patch_receipt.digest,
                "review_digest": self.review_receipt.review_digest,
                "phases": [
                    {
                        "phase": item.phase.value,
                        "evidence_digest": item.evidence_digest,
                        "success": item.success,
                    }
                    for item in self._evidence
                ],
                "authority_scope": "repository-engineering-evidence-only",
            }
        )


__all__ = [
    "ChangePlan",
    "MutationPhase",
    "PatchReceipt",
    "PhaseEvidence",
    "RepositoryMutationTransaction",
]
