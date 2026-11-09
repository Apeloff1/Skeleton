"""Dependency-aware orchestration for a governed reverse-engineering campaign."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class WorkflowStageReceipt:
    stage_id: str
    category: str
    report_digest: str
    passed: bool
    critical: bool = True
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.stage_id or not self.category:
            raise ReverseEngineeringError("workflow stage identity is required")
        if not is_sha256_digest(self.report_digest):
            raise ReverseEngineeringError("report_digest must be sha256 hex")
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ReverseEngineeringError("workflow dependencies must be unique")
        if self.stage_id in self.depends_on:
            raise ReverseEngineeringError("workflow stage cannot depend on itself")


@dataclass(frozen=True)
class WorkflowStageResult:
    stage_id: str
    category: str
    declared_passed: bool
    effective_passed: bool
    blocked_by: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowOrchestrationReport:
    stage_count: int
    effective_pass_count: int
    blocked_stage_count: int
    critical_failure_count: int
    results: tuple[WorkflowStageResult, ...]
    status: str
    closure_ready: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage_count": self.stage_count,
            "effective_pass_count": self.effective_pass_count,
            "blocked_stage_count": self.blocked_stage_count,
            "critical_failure_count": self.critical_failure_count,
            "results": [
                {
                    "stage_id": item.stage_id,
                    "category": item.category,
                    "declared_passed": item.declared_passed,
                    "effective_passed": item.effective_passed,
                    "blocked_by": list(item.blocked_by),
                }
                for item in self.results
            ],
            "status": self.status,
            "closure_ready": self.closure_ready,
            "digest": self.digest,
        }


def orchestrate_campaign(
    stages: Sequence[WorkflowStageReceipt],
    *,
    required_categories: Sequence[str] = (
        "authorization",
        "protocol",
        "design",
        "execution",
        "evidence",
        "falsification",
        "replication",
        "lineage",
        "closure",
    ),
) -> WorkflowOrchestrationReport:
    if not stages:
        raise ReverseEngineeringError("workflow orchestration requires stages")
    ids = [stage.stage_id for stage in stages]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("workflow stage ids must be unique")
    by_id = {stage.stage_id: stage for stage in stages}
    for stage in stages:
        missing = set(stage.depends_on) - set(by_id)
        if missing:
            raise ReverseEngineeringError(
                f"workflow stage {stage.stage_id!r} has unknown dependencies"
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def check_cycle(stage_id: str) -> None:
        if stage_id in visited:
            return
        if stage_id in visiting:
            raise ReverseEngineeringError("workflow dependency graph contains a cycle")
        visiting.add(stage_id)
        for dependency in by_id[stage_id].depends_on:
            check_cycle(dependency)
        visiting.remove(stage_id)
        visited.add(stage_id)

    for stage_id in sorted(by_id):
        check_cycle(stage_id)

    effective: dict[str, bool] = {}

    def resolve(stage_id: str) -> bool:
        if stage_id in effective:
            return effective[stage_id]
        stage = by_id[stage_id]
        value = stage.passed and all(resolve(dep) for dep in stage.depends_on)
        effective[stage_id] = value
        return value

    results: list[WorkflowStageResult] = []
    for stage_id in sorted(by_id):
        stage = by_id[stage_id]
        blockers = tuple(
            sorted(dep for dep in stage.depends_on if not resolve(dep))
        )
        results.append(
            WorkflowStageResult(
                stage_id=stage.stage_id,
                category=stage.category,
                declared_passed=stage.passed,
                effective_passed=resolve(stage_id),
                blocked_by=blockers,
            )
        )

    categories = {
        category: [item for item in results if item.category == category]
        for category in set(item.category for item in results)
    }
    missing_categories = set(required_categories) - set(categories)
    failed_critical = [
        by_id[item.stage_id]
        for item in results
        if not item.effective_passed and by_id[item.stage_id].critical
    ]
    noncritical_failed = [
        item for item in results
        if not item.effective_passed and not by_id[item.stage_id].critical
    ]
    category_failures = {
        category
        for category, items in categories.items()
        if any(not item.effective_passed for item in items)
    }

    status = "verified"
    if missing_categories or failed_critical:
        status = "blocked"
    elif noncritical_failed or category_failures:
        status = "hold"

    closure_ready = (
        status == "verified"
        and not missing_categories
        and all(
            all(item.effective_passed for item in categories[category])
            for category in required_categories
        )
    )
    payload = {
        "required_categories": list(required_categories),
        "stages": [
            {
                "stage_id": stage.stage_id,
                "category": stage.category,
                "report_digest": stage.report_digest,
                "passed": stage.passed,
                "critical": stage.critical,
                "depends_on": list(stage.depends_on),
            }
            for stage in sorted(stages, key=lambda value: value.stage_id)
        ],
    }
    return WorkflowOrchestrationReport(
        stage_count=len(stages),
        effective_pass_count=sum(item.effective_passed for item in results),
        blocked_stage_count=sum(not item.effective_passed for item in results),
        critical_failure_count=len(failed_critical) + len(missing_categories),
        results=tuple(results),
        status=status,
        closure_ready=closure_ready,
        digest=stable_digest(payload),
    )
