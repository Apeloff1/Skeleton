from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path

import pytest

from skeleton.repo_machine.maintenance import (
    DeletionAssessment,
    MaintenanceAction,
    MaintenanceDecision,
    MaintenanceError,
    MaintenancePolicyError,
    MaintenanceReceipt,
    MaintenanceRegistry,
    MaintenanceRisk,
    MaintenanceTask,
    MaintenanceVerdict,
    OwnershipClass,
    RepositoryOwnership,
    ResourceEvidence,
    ResourceKind,
    authorize,
    enforce_mutation_budget,
    evaluate_batch,
    evaluate_deletion,
    plan_summary,
)

NOW = datetime(2026, 10, 5, 14, 15, 0, tzinfo=timezone.utc)
RESOURCE_DIGEST = hashlib.sha256(b"resource").hexdigest()
REGEN_DIGEST = hashlib.sha256(b"regeneration").hexdigest()
ROOT = Path(__file__).resolve().parents[2]


def ownership(**overrides):
    values = dict(
        resource_id="RESOURCE.STALE.BRANCH",
        kind=ResourceKind.BRANCH,
        ownership=OwnershipClass.UNOWNED,
        owner="OWNER.REPO.MAINTAINER",
        retention_reason="Retention window elapsed.",
        mutation_authority_refs=("AUTH.REPO.MAINTAINER",),
        repository_path=None,
        retention_until=None,
        active_refs=(),
        preservation_refs=(),
        generation_source_refs=(),
    )
    values.update(overrides)
    return RepositoryOwnership(**values)


def evidence(**overrides):
    values = dict(
        evidence_id="EVIDENCE.STALE.BRANCH",
        resource_id="RESOURCE.STALE.BRANCH",
        observed_digest=RESOURCE_DIGEST,
        observed_at=NOW - timedelta(minutes=5),
        last_activity_at=NOW - timedelta(days=30),
        reachable=False,
        active_migration=False,
        release_bound=False,
        evidence_bound=False,
        regeneration_receipt_digest=None,
        regeneration_source_refs=(),
        provenance_refs=("PROVENANCE.GIT.BRANCH",),
    )
    values.update(overrides)
    return ResourceEvidence(**values)


def task(**overrides):
    values = dict(
        task_id="TASK.DELETE.STALE.BRANCH",
        resource_id="RESOURCE.STALE.BRANCH",
        action=MaintenanceAction.DELETE,
        risk=MaintenanceRisk.HIGH,
        expected_digest=RESOURCE_DIGEST,
        authority_ref="AUTH.REPO.MAINTAINER",
        mutation_limit=1,
        evidence_ttl_seconds=600,
        stale_after_seconds=86400,
    )
    values.update(overrides)
    return MaintenanceTask(**values)


def test_safe_stale_unowned_unreachable_resource_is_authorized():
    receipt = authorize(task(), ownership(), evidence(), at=NOW)
    assert receipt.decision is MaintenanceVerdict.ALLOW
    assert receipt.reasons == ()


def test_delete_requires_fresh_resource_evidence():
    missing = authorize(task(), ownership(), None, at=NOW)
    stale = authorize(
        task(),
        ownership(),
        evidence(observed_at=NOW - timedelta(seconds=601)),
        at=NOW,
    )
    future = authorize(
        task(),
        ownership(),
        evidence(
            observed_at=NOW + timedelta(seconds=1),
            last_activity_at=NOW - timedelta(days=30),
        ),
        at=NOW,
    )

    assert missing.decision is MaintenanceVerdict.BLOCK
    assert "missing_resource_evidence" in missing.reasons
    assert "resource_evidence_stale" in stale.reasons
    assert "evidence_observed_in_future" in future.reasons


def test_changed_resource_digest_blocks_stale_observation():
    changed = hashlib.sha256(b"changed").hexdigest()
    receipt = authorize(
        task(),
        ownership(),
        evidence(observed_digest=changed),
        at=NOW,
    )
    assert "resource_changed_since_observation" in receipt.reasons


def test_resource_must_be_old_enough_before_delete():
    receipt = authorize(
        task(),
        ownership(),
        evidence(last_activity_at=NOW - timedelta(hours=1)),
        at=NOW,
    )
    assert "resource_not_stale" in receipt.reasons


def test_reachability_blocks_delete():
    receipt = authorize(
        task(),
        ownership(),
        evidence(reachable=True),
        at=NOW,
    )
    assert "resource_reachable" in receipt.reasons


def test_retention_is_derived_from_ownership_policy():
    receipt = authorize(
        task(),
        ownership(retention_until=NOW + timedelta(days=1)),
        evidence(),
        at=NOW,
    )
    assert "retention_not_satisfied" in receipt.reasons


@pytest.mark.parametrize(
    ("ownership_class", "preservation_refs", "reason"),
    [
        (OwnershipClass.ACTIVE, (), "protected_ownership:active"),
        (
            OwnershipClass.MIGRATION,
            ("MIGRATION.ACTIVE",),
            "protected_ownership:migration",
        ),
        (
            OwnershipClass.RELEASE,
            ("RELEASE.CANDIDATE",),
            "protected_ownership:release",
        ),
        (
            OwnershipClass.EVIDENCE,
            ("EVIDENCE.AUDIT",),
            "protected_ownership:evidence",
        ),
    ],
)
def test_protected_ownership_blocks_delete(
    ownership_class,
    preservation_refs,
    reason,
):
    receipt = authorize(
        task(),
        ownership(
            ownership=ownership_class,
            preservation_refs=preservation_refs,
        ),
        evidence(),
        at=NOW,
    )
    assert reason in receipt.reasons


def test_active_and_preservation_references_block_delete():
    active = authorize(
        task(),
        ownership(
            ownership=OwnershipClass.ACTIVE,
            active_refs=("PR.2832",),
        ),
        evidence(),
        at=NOW,
    )
    preserved = authorize(
        task(),
        ownership(
            ownership=OwnershipClass.MIGRATION,
            preservation_refs=("MIGRATION.ACTIVE",),
        ),
        evidence(),
        at=NOW,
    )

    assert "active_references" in active.reasons
    assert "preservation_references" in preserved.reasons


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("active_migration", "active_migration"),
        ("release_bound", "release_bound"),
        ("evidence_bound", "evidence_bound"),
    ],
)
def test_current_preservation_bindings_block_delete(field, reason):
    receipt = authorize(
        task(),
        ownership(),
        evidence(**{field: True}),
        at=NOW,
    )
    assert reason in receipt.reasons


def test_mutation_authority_must_belong_to_resource_policy():
    receipt = authorize(
        task(authority_ref="AUTH.OTHER"),
        ownership(),
        evidence(),
        at=NOW,
    )
    assert "mutation_authority_not_owned" in receipt.reasons


def test_generated_resource_requires_source_ownership_and_regeneration_receipt():
    generated = ownership(
        resource_id="RESOURCE.GENERATED.DOC",
        kind=ResourceKind.ARTIFACT,
        ownership=OwnershipClass.GENERATED,
        generation_source_refs=("SOURCE.MASTERPLAN", "SOURCE.SCHEMA"),
    )
    generated_task = task(
        task_id="TASK.DELETE.GENERATED.DOC",
        resource_id=generated.resource_id,
    )

    missing = authorize(
        generated_task,
        generated,
        evidence(
            evidence_id="EVIDENCE.GENERATED.DOC",
            resource_id=generated.resource_id,
        ),
        at=NOW,
    )
    mismatch = authorize(
        generated_task,
        generated,
        evidence(
            evidence_id="EVIDENCE.GENERATED.DOC",
            resource_id=generated.resource_id,
            regeneration_receipt_digest=REGEN_DIGEST,
            regeneration_source_refs=("SOURCE.MASTERPLAN",),
        ),
        at=NOW,
    )
    allowed = authorize(
        generated_task,
        generated,
        evidence(
            evidence_id="EVIDENCE.GENERATED.DOC",
            resource_id=generated.resource_id,
            regeneration_receipt_digest=REGEN_DIGEST,
            regeneration_source_refs=("SOURCE.MASTERPLAN", "SOURCE.SCHEMA"),
        ),
        at=NOW,
    )

    assert "generated_regeneration_unproven" in missing.reasons
    assert "generated_regeneration_sources_mismatch" in mismatch.reasons
    assert allowed.decision is MaintenanceVerdict.ALLOW


def test_generated_resource_requires_explicit_generation_sources():
    with pytest.raises(MaintenanceError, match="generation source"):
        ownership(
            ownership=OwnershipClass.GENERATED,
            kind=ResourceKind.ARTIFACT,
        )


def test_regeneration_sources_cannot_exist_without_receipt():
    with pytest.raises(MaintenanceError, match="require regeneration receipt"):
        evidence(regeneration_source_refs=("SOURCE.MASTERPLAN",))


def test_non_waivable_repository_paths_block_delete():
    protected = ownership(
        resource_id="RESOURCE.MASTERPLAN",
        kind=ResourceKind.FILE,
        ownership=OwnershipClass.GENERATED,
        repository_path="machine/ai_master_plan.json",
        generation_source_refs=("SOURCE.MASTERPLAN.GENERATOR",),
    )
    protected_task = task(
        task_id="TASK.DELETE.MASTERPLAN",
        resource_id=protected.resource_id,
    )
    receipt = authorize(
        protected_task,
        protected,
        evidence(
            evidence_id="EVIDENCE.MASTERPLAN",
            resource_id=protected.resource_id,
            regeneration_receipt_digest=REGEN_DIGEST,
            regeneration_source_refs=("SOURCE.MASTERPLAN.GENERATOR",),
        ),
        at=NOW,
    )
    assert "non_waivable_protected_path" in receipt.reasons


def test_file_ownership_requires_repository_path():
    with pytest.raises(MaintenanceError, match="repository_path"):
        ownership(kind=ResourceKind.FILE)


def test_update_requires_fresh_evidence_and_owned_authority_but_not_staleness():
    update = task(
        task_id="TASK.UPDATE.DEPENDENCY",
        action=MaintenanceAction.UPDATE,
        risk=MaintenanceRisk.MEDIUM,
        stale_after_seconds=86400,
    )
    recent = evidence(last_activity_at=NOW - timedelta(minutes=1))
    assert authorize(update, ownership(), recent, at=NOW).decision is MaintenanceVerdict.ALLOW
    assert authorize(update, ownership(), None, at=NOW).decision is MaintenanceVerdict.BLOCK


def test_inspect_is_non_mutating_and_does_not_require_resource_evidence():
    inspect = task(
        task_id="TASK.INSPECT.RESOURCE",
        action=MaintenanceAction.INSPECT,
        risk=MaintenanceRisk.LOW,
    )
    receipt = authorize(inspect, ownership(), None, at=NOW)
    assert receipt.decision is MaintenanceVerdict.ALLOW


def test_delete_cannot_be_low_or_medium_risk():
    with pytest.raises(MaintenanceError, match="below high"):
        task(risk=MaintenanceRisk.LOW)
    with pytest.raises(MaintenanceError, match="below high"):
        task(risk=MaintenanceRisk.MEDIUM)


def test_task_inputs_are_typed_and_bounded():
    with pytest.raises(MaintenanceError, match="MaintenanceAction"):
        task(action="delete")
    with pytest.raises(MaintenanceError, match="MaintenanceRisk"):
        task(risk="high")
    with pytest.raises(MaintenanceError, match="mutation_limit"):
        task(mutation_limit=101)
    with pytest.raises(MaintenanceError, match="integer"):
        task(mutation_limit=True)


def test_resource_evidence_claims_are_typed_and_time_ordered():
    with pytest.raises(MaintenanceError, match="reachable must be bool"):
        evidence(reachable=1)
    with pytest.raises(MaintenanceError, match="cannot be after"):
        evidence(
            observed_at=NOW - timedelta(hours=1),
            last_activity_at=NOW,
        )
    with pytest.raises(MaintenanceError, match="provenance"):
        evidence(provenance_refs=())


def test_registry_is_order_independent_and_rejects_duplicate_ownership():
    first = ownership()
    second = ownership(
        resource_id="RESOURCE.STALE.FILE",
        kind=ResourceKind.FILE,
        repository_path="tmp/stale.txt",
    )
    one = MaintenanceRegistry((first, second))
    two = MaintenanceRegistry((second, first))
    assert one.digest == two.digest

    with pytest.raises(MaintenanceError, match="duplicate resource"):
        MaintenanceRegistry((first, first))


def test_registry_requires_known_resource_policy():
    registry = MaintenanceRegistry((ownership(),))
    unknown = task(
        task_id="TASK.DELETE.UNKNOWN",
        resource_id="RESOURCE.UNKNOWN",
    )
    with pytest.raises(MaintenanceError, match="lacks ownership"):
        registry.plan((unknown,), (), at=NOW)


def test_registry_rejects_ambiguous_evidence_snapshots():
    registry = MaintenanceRegistry((ownership(),))
    one = evidence()
    two = evidence(evidence_id="EVIDENCE.STALE.BRANCH.2")
    with pytest.raises(MaintenanceError, match="ambiguous"):
        registry.plan((task(),), (one, two), at=NOW)


def test_plan_is_deterministic_and_summarizes_allowed_and_blocked():
    second_owner = ownership(
        resource_id="RESOURCE.ACTIVE.FILE",
        kind=ResourceKind.FILE,
        ownership=OwnershipClass.ACTIVE,
        repository_path="src/active.py",
    )
    registry = MaintenanceRegistry((second_owner, ownership()))
    blocked_task = task(
        task_id="TASK.DELETE.ACTIVE.FILE",
        resource_id=second_owner.resource_id,
    )
    blocked_evidence = evidence(
        evidence_id="EVIDENCE.ACTIVE.FILE",
        resource_id=second_owner.resource_id,
    )
    plan = registry.plan(
        (blocked_task, task()),
        (blocked_evidence, evidence()),
        at=NOW,
    )
    summary = plan_summary(plan)

    assert len(plan.allowed) == 1
    assert len(plan.blocked) == 1
    assert summary["allowed_count"] == 1
    assert summary["blocked_count"] == 1
    assert summary["plan_digest"] == plan.digest


def test_forged_allow_receipt_cannot_bypass_reauthorization():
    bad_task = task(authority_ref="AUTH.OTHER")
    expected = authorize(bad_task, ownership(), evidence(), at=NOW)
    assert expected.decision is MaintenanceVerdict.BLOCK

    forged = MaintenanceReceipt(
        task_id=bad_task.task_id,
        task_digest=bad_task.digest,
        resource_id=bad_task.resource_id,
        ownership_digest=ownership().digest,
        evidence_digest=evidence().digest,
        authority_ref=bad_task.authority_ref,
        assessed_at=NOW,
        decision=MaintenanceVerdict.ALLOW,
        reasons=(),
    )
    with pytest.raises(MaintenanceError, match="current authorization"):
        enforce_mutation_budget(
            bad_task,
            ownership(),
            evidence(),
            forged,
            1,
            at=NOW,
        )


def test_execution_boundary_enforces_exact_receipt_and_mutation_budget():
    target_task = task(mutation_limit=2)
    target_owner = ownership()
    target_evidence = evidence()
    receipt = authorize(target_task, target_owner, target_evidence, at=NOW)

    enforce_mutation_budget(
        target_task,
        target_owner,
        target_evidence,
        receipt,
        2,
        at=NOW,
    )
    with pytest.raises(MaintenanceError, match="exceeds task limit"):
        enforce_mutation_budget(
            target_task,
            target_owner,
            target_evidence,
            receipt,
            3,
            at=NOW,
        )


def test_execution_boundary_rejects_evidence_changed_after_receipt():
    target_task = task()
    target_owner = ownership()
    target_evidence = evidence()
    receipt = authorize(target_task, target_owner, target_evidence, at=NOW)
    changed = evidence(
        evidence_id="EVIDENCE.STALE.BRANCH.NEW",
        observed_digest=hashlib.sha256(b"changed").hexdigest(),
    )

    with pytest.raises(MaintenanceError, match="current authorization"):
        enforce_mutation_budget(
            target_task,
            target_owner,
            changed,
            receipt,
            1,
            at=NOW,
        )


def legacy_assessment(path="tmp/stale.txt", **overrides):
    values = dict(
        path=path,
        owner_resolved=True,
        trace_reachable=False,
        retention_hold=False,
        migration_safe=True,
        regeneration_authority="scripts/regenerate.py",
        rollback_ref="receipt:rollback",
        owner_evidence_ref="owner:evidence",
        trace_evidence_ref="trace:evidence",
        retention_evidence_ref="retention:evidence",
        migration_evidence_ref="migration:evidence",
        protected_paths=(),
    )
    values.update(overrides)
    return DeletionAssessment(**values)


def test_legacy_deletion_assessor_remains_compatible():
    decision = evaluate_deletion(legacy_assessment())
    assert isinstance(decision, MaintenanceDecision)
    assert decision.allowed is True

    protected = evaluate_deletion(
        legacy_assessment("machine/ai_master_plan.json")
    )
    assert protected.allowed is False
    assert "protected path" in protected.blockers


def test_legacy_batch_rejects_overlap_and_duplicates():
    with pytest.raises(MaintenancePolicyError, match="duplicate"):
        evaluate_batch((legacy_assessment(), legacy_assessment()))
    with pytest.raises(MaintenancePolicyError, match="overlapping"):
        evaluate_batch(
            (
                legacy_assessment("tmp"),
                legacy_assessment("tmp/stale.txt"),
            )
        )


def test_canonical_and_governed_maintenance_runtime_are_byte_identical():
    assert (
        ROOT / "skeleton/repo_machine/maintenance.py"
    ).read_bytes() == (
        ROOT / "skeleton/ai/build/repo_machine/maintenance.py"
    ).read_bytes()


def test_registry_rejects_duplicate_repository_path_ownership():
    first = ownership(
        resource_id="RESOURCE.FILE.ONE",
        kind=ResourceKind.FILE,
        repository_path="tmp/shared.txt",
    )
    second = ownership(
        resource_id="RESOURCE.FILE.TWO",
        kind=ResourceKind.FILE,
        repository_path="tmp/shared.txt",
    )
    with pytest.raises(MaintenanceError, match="duplicate repository path"):
        MaintenanceRegistry((first, second))


def test_plan_rejects_multiple_tasks_for_one_resource():
    registry = MaintenanceRegistry((ownership(),))
    one = task(task_id="TASK.ONE")
    two = task(
        task_id="TASK.TWO",
        action=MaintenanceAction.UPDATE,
        risk=MaintenanceRisk.MEDIUM,
    )
    with pytest.raises(MaintenanceError, match="one resource"):
        registry.plan((one, two), (evidence(),), at=NOW)


def test_plan_rejects_overlapping_repository_delete_paths():
    parent = ownership(
        resource_id="RESOURCE.DIR.PARENT",
        kind=ResourceKind.ARTIFACT,
        repository_path="tmp/generated",
    )
    child = ownership(
        resource_id="RESOURCE.FILE.CHILD",
        kind=ResourceKind.FILE,
        repository_path="tmp/generated/child.txt",
    )
    registry = MaintenanceRegistry((parent, child))
    parent_task = task(
        task_id="TASK.DELETE.PARENT",
        resource_id=parent.resource_id,
    )
    child_task = task(
        task_id="TASK.DELETE.CHILD",
        resource_id=child.resource_id,
    )
    with pytest.raises(MaintenanceError, match="overlapping repository"):
        registry.plan((parent_task, child_task), (), at=NOW)


@pytest.mark.parametrize(
    "kind",
    [
        ResourceKind.BRANCH,
        ResourceKind.DEPENDENCY,
        ResourceKind.ARTIFACT,
    ],
)
def test_non_file_resource_kinds_can_use_evidence_bound_cleanup(kind):
    target_owner = ownership(kind=kind)
    target_task = task()
    target_evidence = evidence()
    assert (
        authorize(target_task, target_owner, target_evidence, at=NOW).decision
        is MaintenanceVerdict.ALLOW
    )


def test_repository_machine_package_exports_remain_byte_identical():
    assert (
        ROOT / "skeleton/repo_machine/__init__.py"
    ).read_bytes() == (
        ROOT / "skeleton/ai/build/repo_machine/__init__.py"
    ).read_bytes()
