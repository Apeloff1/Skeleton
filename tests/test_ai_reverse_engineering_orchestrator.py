from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.certification_bundle import (
    CertificationArtifact,
    build_certification_bundle,
    verify_certification_bundle,
)
from skeleton.ai.research.model_internals.reverse_engineering.workflow_orchestrator import (
    WorkflowStageReceipt,
    orchestrate_campaign,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_workflow_orchestrator_propagates_dependency_failure():
    stages = (
        WorkflowStageReceipt("auth", "authorization", d("auth"), True),
        WorkflowStageReceipt("protocol", "protocol", d("protocol"), True, depends_on=("auth",)),
        WorkflowStageReceipt("design", "design", d("design"), True, depends_on=("protocol",)),
        WorkflowStageReceipt("exec", "execution", d("exec"), False, depends_on=("design",)),
        WorkflowStageReceipt("evidence", "evidence", d("evidence"), True, depends_on=("exec",)),
        WorkflowStageReceipt("falsify", "falsification", d("falsify"), True, depends_on=("evidence",)),
        WorkflowStageReceipt("replicate", "replication", d("replicate"), True, depends_on=("falsify",)),
        WorkflowStageReceipt("lineage", "lineage", d("lineage"), True, depends_on=("replicate",)),
        WorkflowStageReceipt("closure", "closure", d("closure"), True, depends_on=("lineage",)),
    )
    report = orchestrate_campaign(stages)
    assert report.status == "blocked"
    assert report.closure_ready is False
    evidence = next(item for item in report.results if item.stage_id == "evidence")
    assert evidence.effective_passed is False
    assert evidence.blocked_by == ("exec",)


def test_workflow_orchestrator_closes_complete_chain():
    categories = (
        "authorization",
        "protocol",
        "design",
        "execution",
        "evidence",
        "falsification",
        "replication",
        "lineage",
        "closure",
    )
    stages = []
    previous = None
    for category in categories:
        stage_id = category
        stages.append(
            WorkflowStageReceipt(
                stage_id,
                category,
                d(category),
                True,
                depends_on=((previous,) if previous else ()),
            )
        )
        previous = stage_id
    report = orchestrate_campaign(tuple(stages))
    assert report.status == "verified"
    assert report.closure_ready is True
    assert report.effective_pass_count == len(categories)


def test_certification_bundle_is_exact_head_bound_and_tamper_evident():
    required = (
        "protocol",
        "authorization",
        "evidence",
        "replay",
        "reproducibility",
        "falsification",
        "replication",
        "lineage",
        "claim_closure",
        "closure_certificate",
        "campaign_verification",
    )
    artifacts = tuple(
        CertificationArtifact(kind, kind, d(kind))
        for kind in required
    )
    bundle = build_certification_bundle(
        campaign_id="campaign-1",
        exact_head_sha="a" * 40,
        artifacts=artifacts,
        required_kinds=required,
    )
    assert bundle.complete is True
    assert verify_certification_bundle(bundle) is True
    assert verify_certification_bundle(
        replace(bundle, exact_head_sha="b" * 40)
    ) is False


def test_certification_bundle_reports_missing_required_kind():
    bundle = build_certification_bundle(
        campaign_id="campaign-2",
        exact_head_sha="c" * 40,
        artifacts=(CertificationArtifact("protocol", "protocol", d("protocol")),),
        required_kinds=("protocol", "lineage"),
    )
    assert bundle.complete is False
    assert bundle.missing_kinds == ("lineage",)
