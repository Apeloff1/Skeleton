import pytest
from skeleton.ai.providers.model_lifecycle import *


def evidence(evidence_id="e"):
    return ModelGovernanceEvidence(
        evidence_id,
        "owner",
        "rollback",
        "retain",
    )


def test_invalid_transition_rejected():
    with pytest.raises(ValueError):
        transition(
            ModelLifecycle("m", "intake", ()),
            "operation",
            evidence(),
        )


def test_transition_requires_governance_evidence():
    assert transition(
        ModelLifecycle("m", "intake", ()),
        "training",
        evidence(),
    ).state == "training"


def test_duplicate_governance_evidence_rejected():
    item = ModelGovernanceEvidence("e", "o", "r", "keep")
    lifecycle = ModelLifecycle("m", "training", (item,))
    with pytest.raises(ValueError):
        transition(lifecycle, "evaluation", item)


def test_transition_receipt_binds_source_target_and_evidence():
    updated, receipt = transition_with_receipt(
        ModelLifecycle("m", "evaluation", ()),
        "deployment",
        evidence("deploy-evidence"),
    )
    assert updated.state == "deployment"
    assert receipt == ModelTransition(
        "evaluation",
        "deployment",
        "deploy-evidence",
    )


def test_archive_is_terminal():
    with pytest.raises(ValueError):
        transition(
            ModelLifecycle("m", "archive", ()),
            "operation",
            evidence(),
        )
