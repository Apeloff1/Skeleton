from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.autonomous_engineering.safe_change import (
    SafeChangeError,
    acquire_change_lease,
    open_change_transaction,
    plan_safe_change,
)
from skeleton.ai.runtime.autonomous_engineering.workflow import WorkflowCompiler
from skeleton.repo_machine.model import (
    FileRecord,
    RepositoryModel,
    SubsystemRecord,
    TopologyEdge,
)
from skeleton.repo_machine.transaction import LeaseRegistry, RepositoryTransactionError


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _model() -> RepositoryModel:
    return RepositoryModel(
        schema_version=1,
        repository="fixture",
        files=(
            FileRecord(
                path="skeleton/core.py",
                zone="skeleton",
                owner="core",
                kind="source",
                language="python",
                size=10,
                lines=1,
                sha256=_digest("core"),
            ),
            FileRecord(
                path="tests/test_core.py",
                zone="tests",
                owner="quality",
                kind="test",
                language="python",
                size=10,
                lines=1,
                sha256=_digest("test"),
            ),
            FileRecord(
                path=".github/workflows/ci.yml",
                zone="workflows",
                owner="platform",
                kind="workflow",
                language="yaml",
                size=10,
                lines=1,
                sha256=_digest("ci"),
            ),
        ),
        subsystems=(
            SubsystemRecord(
                name="skeleton",
                owner="core",
                criticality="critical",
                file_count=1,
                code_files=1,
                test_files=0,
                referenced_test_files=1,
                test_evidence=("tests/test_core.py",),
                workflow_files=0,
                total_lines=1,
                total_bytes=10,
                dependents=("tests",),
            ),
            SubsystemRecord(
                name="tests",
                owner="quality",
                criticality="medium",
                file_count=1,
                code_files=0,
                test_files=1,
                workflow_files=0,
                total_lines=1,
                total_bytes=10,
                dependencies=("skeleton",),
            ),
            SubsystemRecord(
                name="workflows",
                owner="platform",
                criticality="high",
                file_count=1,
                code_files=0,
                test_files=0,
                workflow_files=1,
                total_lines=1,
                total_bytes=10,
            ),
        ),
        edges=(TopologyEdge("tests", "skeleton", "test-import"),),
        findings=(),
    )


def _workflow(effect: str = "write", approval: bool = True):
    return WorkflowCompiler().compile(
        {
            "workflow_id": "p3.safe-change",
            "version": "v1",
            "tasks": [
                {
                    "task_id": "edit",
                    "kind": "code",
                    "objective": "Apply the bounded repository edit.",
                    "effect_class": effect,
                    "approval_required": approval,
                    "required_capabilities": ["repo.write"],
                }
            ],
        }
    )


def test_plan_binds_repository_impact_and_independent_route() -> None:
    plan = plan_safe_change(
        _workflow(),
        _model(),
        task_id="edit",
        changed_paths=["skeleton/core.py"],
        author_id="author",
        reviewer_candidates=["reviewer"],
        verifier_candidates=["verifier"],
    )
    assert plan.changed_paths == ("skeleton/core.py",)
    assert plan.repository_fingerprint == _model().fingerprint
    assert plan.critical_zones == ("skeleton",)
    assert plan.reviewer_id == "reviewer"
    assert plan.verifier_id == "verifier"
    assert "critical-surface-review" in plan.required_gates
    assert "exact-path-lease" in plan.required_gates


def test_plan_is_deterministic() -> None:
    kwargs = dict(
        task_id="edit",
        changed_paths=["skeleton/core.py", "tests/test_core.py"],
        author_id="author",
        reviewer_candidates=["reviewer"],
        verifier_candidates=["verifier"],
    )
    first = plan_safe_change(_workflow(), _model(), **kwargs)
    second = plan_safe_change(_workflow(), _model(), **kwargs)
    assert first.as_dict() == second.as_dict()


def test_rejects_non_effectful_task() -> None:
    with pytest.raises(SafeChangeError, match="not declared effectful"):
        plan_safe_change(
            _workflow(effect="read", approval=False),
            _model(),
            task_id="edit",
            changed_paths=["skeleton/core.py"],
            author_id="author",
            reviewer_candidates=["reviewer"],
            verifier_candidates=["verifier"],
        )


def test_rejects_unsafe_path() -> None:
    with pytest.raises(SafeChangeError, match="unsafe change path"):
        plan_safe_change(
            _workflow(),
            _model(),
            task_id="edit",
            changed_paths=["../escape.py"],
            author_id="author",
            reviewer_candidates=["reviewer"],
            verifier_candidates=["verifier"],
        )


def test_workflow_change_requires_control_plane_security() -> None:
    plan = plan_safe_change(
        _workflow(),
        _model(),
        task_id="edit",
        changed_paths=[".github/workflows/ci.yml"],
        author_id="author",
        reviewer_candidates=["reviewer"],
        verifier_candidates=["verifier"],
    )
    assert "workflow-control-plane-security" in plan.required_gates


def test_plan_acquires_exact_lease_and_opens_transaction(tmp_path) -> None:
    target = tmp_path / "skeleton"
    target.mkdir()
    file = target / "core.py"
    file.write_text("old", encoding="utf-8")

    plan = plan_safe_change(
        _workflow(),
        _model(),
        task_id="edit",
        changed_paths=["skeleton/core.py"],
        author_id="author",
        reviewer_candidates=["reviewer"],
        verifier_candidates=["verifier"],
    )
    registry = LeaseRegistry()
    lease = acquire_change_lease(plan, registry)
    transaction = open_change_transaction(tmp_path, plan, registry, lease)
    transaction.stage_text(
        "skeleton/core.py",
        "new",
        expected_sha256=hashlib.sha256(b"old").hexdigest(),
    )
    receipt = transaction.commit()
    assert file.read_text(encoding="utf-8") == "new"
    assert receipt.owner_id == "author"
    assert tuple(entry.path for entry in receipt.entries) == ("skeleton/core.py",)


def test_transaction_cannot_escape_plan_scope(tmp_path) -> None:
    (tmp_path / "skeleton").mkdir()
    (tmp_path / "skeleton/core.py").write_text("old", encoding="utf-8")
    (tmp_path / "outside.py").write_text("outside", encoding="utf-8")
    plan = plan_safe_change(
        _workflow(),
        _model(),
        task_id="edit",
        changed_paths=["skeleton/core.py"],
        author_id="author",
        reviewer_candidates=["reviewer"],
        verifier_candidates=["verifier"],
    )
    registry = LeaseRegistry()
    lease = acquire_change_lease(plan, registry)
    transaction = open_change_transaction(tmp_path, plan, registry, lease)
    with pytest.raises(RepositoryTransactionError, match="outside lease scope"):
        transaction.stage_text("outside.py", "bad")
