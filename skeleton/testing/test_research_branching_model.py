import pytest
from skeleton.ai.research_branching import *


def test_research_branch_cannot_bypass_production_gates():
    policy = ResearchBranchPolicy(
        "research/",
        "owner",
        ("ci", "security"),
    )
    candidate = ResearchMergeCandidate(
        ResearchBranch("research/x", "sha", "exp", "owner"),
        ("evidence",),
        frozenset({"ci"}),
    )
    with pytest.raises(PermissionError):
        promote(candidate, policy)


def test_lineage_and_evidence_allow_promotion():
    candidate = ResearchMergeCandidate(
        ResearchBranch("research/x", "sha", "exp", "owner"),
        ("evidence",),
        frozenset({"ci"}),
    )
    policy = ResearchBranchPolicy("research/", "owner", ("ci",))
    assert promote(candidate, policy)


def test_duplicate_promotion_evidence_rejected():
    branch = ResearchBranch("r/x", "sha", "exp", "owner")
    with pytest.raises(ValueError):
        ResearchMergeCandidate(
            branch,
            ("x", "x"),
            frozenset({"gate"}),
        )


def test_promotion_receipt_binds_lineage_evidence_and_gates():
    branch = ResearchBranch("research/x", "parent", "exp-1", "owner")
    candidate = ResearchMergeCandidate(
        branch,
        ("ev-1", "ev-2"),
        frozenset({"security", "ci"}),
    )
    receipt = promote_with_receipt(
        candidate,
        ResearchBranchPolicy(
            "research/",
            "owner",
            ("ci", "security"),
        ),
    )
    assert receipt.branch == "research/x"
    assert receipt.parent_sha == "parent"
    assert receipt.experiment_id == "exp-1"
    assert receipt.evidence_ids == ("ev-1", "ev-2")
    assert receipt.passed_gates == ("ci", "security")


def test_branch_owner_mismatch_blocks_promotion():
    candidate = ResearchMergeCandidate(
        ResearchBranch("research/x", "parent", "exp", "other"),
        ("ev",),
        frozenset({"ci"}),
    )
    with pytest.raises(PermissionError):
        promote(
            candidate,
            ResearchBranchPolicy("research/", "owner", ("ci",)),
        )
