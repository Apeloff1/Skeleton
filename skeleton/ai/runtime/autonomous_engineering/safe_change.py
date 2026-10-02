"""Workspace-aware P3 safe-change planning and transactional mutation boundary."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

from skeleton.repo_machine.impact import ImpactReport, analyze_impact
from skeleton.repo_machine.model import RepositoryModel
from skeleton.repo_machine.review import ReviewRoute, route_independent_review
from skeleton.repo_machine.transaction import (
    EditLease,
    LeaseRegistry,
    WorkspaceTransaction,
)

from .workflow import CompiledWorkflow


class SafeChangeError(RuntimeError):
    """A proposed repository change cannot cross the P3 mutation boundary."""


def _json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\x00" in value or "\\" in value:
        raise SafeChangeError("change path must be canonical POSIX text")
    pure = PurePosixPath(value)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
        or pure.as_posix() != value
    ):
        raise SafeChangeError(f"unsafe change path: {value!r}")
    if len(value) > 1024:
        raise SafeChangeError("change path exceeds size limit")
    return value


def _paths(values: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(sorted({_path(value) for value in values}))
    if not normalized:
        raise SafeChangeError("safe-change plan requires at least one path")
    if len(normalized) > 256:
        raise SafeChangeError("safe-change plan exceeds path limit")
    return normalized


@dataclass(frozen=True, slots=True)
class SafeChangePlan:
    workflow_id: str
    workflow_ir_digest: str
    task_id: str
    author_id: str
    repository_fingerprint: str
    changed_paths: tuple[str, ...]
    touched_zones: tuple[str, ...]
    affected_zones: tuple[str, ...]
    test_zones: tuple[str, ...]
    critical_zones: tuple[str, ...]
    risk_score: int
    required_gates: tuple[str, ...]
    lease_scopes: tuple[str, ...]
    reviewer_id: str
    verifier_id: str
    plan_digest: str

    def __post_init__(self) -> None:
        if not 0 <= self.risk_score <= 100:
            raise SafeChangeError("risk_score must be in [0,100]")
        for field in ("workflow_ir_digest", "repository_fingerprint", "plan_digest"):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise SafeChangeError(f"{field} must be lowercase sha256")
        if self.changed_paths != tuple(sorted(set(self.changed_paths))):
            raise SafeChangeError("changed_paths must be sorted unique")
        if self.lease_scopes != self.changed_paths:
            raise SafeChangeError("lease scopes must exactly match planned paths")
        if len({self.author_id, self.reviewer_id, self.verifier_id}) != 3:
            raise SafeChangeError("author, reviewer and verifier must be independent")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.safe_change_plan.v1",
            "workflow_id": self.workflow_id,
            "workflow_ir_digest": self.workflow_ir_digest,
            "task_id": self.task_id,
            "author_id": self.author_id,
            "repository_fingerprint": self.repository_fingerprint,
            "changed_paths": list(self.changed_paths),
            "touched_zones": list(self.touched_zones),
            "affected_zones": list(self.affected_zones),
            "test_zones": list(self.test_zones),
            "critical_zones": list(self.critical_zones),
            "risk_score": self.risk_score,
            "required_gates": list(self.required_gates),
            "lease_scopes": list(self.lease_scopes),
            "reviewer_id": self.reviewer_id,
            "verifier_id": self.verifier_id,
            "plan_digest": self.plan_digest,
        }


def _plan_material(
    workflow: CompiledWorkflow,
    task_id: str,
    author_id: str,
    model: RepositoryModel,
    paths: tuple[str, ...],
    impact: ImpactReport,
    route: ReviewRoute,
    gates: tuple[str, ...],
) -> dict[str, object]:
    return {
        "workflow_id": workflow.workflow_id,
        "workflow_ir_digest": workflow.ir_digest,
        "task_id": task_id,
        "author_id": author_id,
        "repository_fingerprint": model.fingerprint,
        "changed_paths": list(paths),
        "touched_zones": list(impact.touched_zones),
        "affected_zones": list(impact.transitively_affected_zones),
        "test_zones": list(impact.test_zones),
        "critical_zones": list(impact.critical_zones),
        "risk_score": impact.risk_score,
        "required_gates": list(gates),
        "lease_scopes": list(paths),
        "reviewer_id": route.reviewer_id,
        "verifier_id": route.verifier_id,
    }


def plan_safe_change(
    workflow: CompiledWorkflow,
    model: RepositoryModel,
    *,
    task_id: str,
    changed_paths: Iterable[str],
    author_id: str,
    reviewer_candidates: Sequence[str],
    verifier_candidates: Sequence[str],
    transitive_depth: int = 3,
) -> SafeChangePlan:
    """Create a deterministic, independently-routed repository mutation plan."""

    if task_id not in workflow.task_map:
        raise SafeChangeError(f"unknown workflow task: {task_id}")
    task = workflow.task_map[task_id]
    if task.effect_class not in {"write", "external"}:
        raise SafeChangeError(
            f"task {task_id} is not declared effectful and cannot mutate repository state"
        )
    if task.approval_required is not True:
        raise SafeChangeError(f"task {task_id} lacks explicit effect approval requirement")
    paths = _paths(changed_paths)
    route = route_independent_review(
        author_id,
        reviewer_candidates,
        verifier_candidates,
    )
    impact = analyze_impact(model, paths, transitive_depth=transitive_depth)

    gates = {
        "exact-path-lease",
        "optimistic-write-fence",
        "rollback-on-partial-failure",
        "independent-review",
        "independent-verification",
        "operator-approval",
        "focused-regression",
    }
    if impact.critical_zones or impact.risk_score >= 50:
        gates.add("critical-surface-review")
    if any(path.startswith(".github/workflows/") for path in paths):
        gates.add("workflow-control-plane-security")
    if "unclassified" in impact.touched_zones:
        gates.add("repository-classification")

    ordered_gates = tuple(sorted(gates))
    material = _plan_material(
        workflow,
        task_id,
        author_id.strip(),
        model,
        paths,
        impact,
        route,
        ordered_gates,
    )
    return SafeChangePlan(
        workflow_id=workflow.workflow_id,
        workflow_ir_digest=workflow.ir_digest,
        task_id=task_id,
        author_id=author_id.strip(),
        repository_fingerprint=model.fingerprint,
        changed_paths=paths,
        touched_zones=impact.touched_zones,
        affected_zones=impact.transitively_affected_zones,
        test_zones=impact.test_zones,
        critical_zones=impact.critical_zones,
        risk_score=impact.risk_score,
        required_gates=ordered_gates,
        lease_scopes=paths,
        reviewer_id=route.reviewer_id,
        verifier_id=route.verifier_id,
        plan_digest=_digest(material),
    )


def acquire_change_lease(
    plan: SafeChangePlan,
    registry: LeaseRegistry,
    *,
    ttl_s: float = 300.0,
) -> EditLease:
    """Acquire the exact path lease declared by a safe-change plan."""

    if not isinstance(plan, SafeChangePlan):
        raise TypeError("plan must be SafeChangePlan")
    if not isinstance(registry, LeaseRegistry):
        raise TypeError("registry must be LeaseRegistry")
    lease = registry.acquire(plan.author_id, plan.lease_scopes, ttl_s=ttl_s)
    if lease.paths != plan.lease_scopes:
        registry.release(lease.lease_id, plan.author_id)
        raise SafeChangeError("lease registry returned scope drift")
    return lease


def open_change_transaction(
    root: str | Path,
    plan: SafeChangePlan,
    registry: LeaseRegistry,
    lease: EditLease,
) -> WorkspaceTransaction:
    """Open the existing rollback-capable repository transaction for a plan."""

    if lease.owner_id != plan.author_id:
        raise SafeChangeError("lease owner does not match plan author")
    if lease.paths != plan.lease_scopes:
        raise SafeChangeError("lease scope does not match plan")
    return WorkspaceTransaction(root, registry, lease)


__all__ = [
    "SafeChangeError",
    "SafeChangePlan",
    "acquire_change_lease",
    "open_change_transaction",
    "plan_safe_change",
]
