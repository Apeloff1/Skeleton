"""Regression matrix for immutable auto-merge contracts."""

from __future__ import annotations

from dataclasses import asdict, replace
import json

import pytest

from skeleton.pr_automation.automerge_model import (
    AutoMergePolicy,
    CandidateClass,
    CandidateSnapshot,
    DecisionKind,
    DiffSummary,
    GateRequirement,
    GateState,
    MergeAction,
    MergeBudget,
    MergeDecision,
    MergeMethod,
    MergeMode,
    MutationReceipt,
    PullRequestIdentity,
    ReconcileReport,
    ReviewEvidence,
    RiskTier,
    StackRelation,
    WorkflowEvidence,
    canonical_json,
    fingerprint,
    immutable_identity_equal,
    labels_normalized,
    parse_timestamp,
    valid_context,
    valid_ref,
    valid_sha,
)
from skeleton.testing.automerge_test_support import (
    NOW,
    SHA_A,
    SHA_B,
    identity,
    policy,
    snapshot,
    workflow,
)


def test_sha_validation_is_exact_and_lowercase():
    assert valid_sha(SHA_A)
    assert not valid_sha("A" * 40)
    assert not valid_sha("a" * 39)
    assert not valid_sha("a" * 41)
    assert not valid_sha("g" * 40)
    assert not valid_sha(" " + SHA_A)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "/main",
        "main//x",
        "main/../x",
        "main\\x",
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    ],
)
def test_invalid_refs_fail_validation(value):
    assert not valid_ref(value)


@pytest.mark.parametrize(
    "value",
    [
        "main",
        "feature/x",
        "release/2026.09",
        "dependabot/pip/pytest-8",
        "x_y-z",
        "refs-like-but-short",
    ],
)
def test_valid_refs_are_accepted(value):
    assert valid_ref(value)


def test_context_validation_rejects_controls():
    assert valid_context("Merge Readiness")
    assert not valid_context("")
    assert not valid_context("bad\nname")
    assert not valid_context("bad\x00name")


def test_canonical_json_is_stable_across_mapping_order():
    left = {"b": 2, "a": [3, 4]}
    right = {"a": [3, 4], "b": 2}
    assert canonical_json(left) == canonical_json(right)
    assert fingerprint(left) == fingerprint(right)


def test_parse_timestamp_normalizes_zulu():
    parsed = parse_timestamp("2026-09-19T20:00:00Z")
    assert parsed is not None
    assert parsed.isoformat().endswith("+00:00")


@pytest.mark.parametrize(
    "value",
    [None, "", "not-a-date", "2026-99-99T00:00:00Z"],
)
def test_parse_timestamp_rejects_invalid_values(value):
    assert parse_timestamp(value) is None


def test_identity_rejects_bad_repository():
    with pytest.raises(ValueError, match="owner/name"):
        PullRequestIdentity(
            repository="broken",
            number=1,
            node_id="PR_1",
            state="open",
            draft=False,
            author="x",
            base_ref="main",
            base_sha=SHA_A,
            head_ref="feature/x",
            head_sha=SHA_B,
            head_repo="x/y",
            mergeable=True,
            mergeable_state="clean",
            created_at=None,
            updated_at=None,
        )


def test_identity_rejects_bad_head_repository():
    with pytest.raises(ValueError, match="head repository"):
        replace(identity(), head_repo="broken")


def test_identity_rejects_noncanonical_sha():
    with pytest.raises(ValueError, match="canonical"):
        replace(identity(), head_sha="B" * 40)


def test_identity_rejects_self_invalid_number():
    with pytest.raises(ValueError, match="positive"):
        replace(identity(), number=0)


def test_identity_fork_detection_is_case_insensitive():
    own = identity(head_repo="apeloff1/skeleton")
    fork = identity(head_repo="someone/other")
    assert own.from_fork is False
    assert fork.from_fork is True


def test_identity_fingerprint_changes_with_head_sha():
    first = identity(head_sha=SHA_A)
    second = replace(first, head_sha=SHA_B)
    assert first.fingerprint() != second.fingerprint()


def test_diff_summary_is_strict():
    with pytest.raises(ValueError, match="count"):
        DiffSummary(files=("a.py",), additions=1, deletions=0, changed_files=2)
    with pytest.raises(ValueError, match="duplicate"):
        DiffSummary(files=("a.py", "a.py"), additions=1, deletions=0, changed_files=2)
    with pytest.raises(ValueError, match="negative"):
        DiffSummary(files=("a.py",), additions=-1, deletions=0, changed_files=1)


def test_diff_line_delta():
    diff = DiffSummary(files=("a.py",), additions=7, deletions=3, changed_files=1)
    assert diff.line_delta == 10


def test_workflow_evidence_state_machine():
    assert workflow("x", status="completed", conclusion="success").state() is GateState.SUCCESS
    assert workflow("x", status="in_progress", conclusion=None).state() is GateState.PENDING
    assert workflow("x", status="completed", conclusion="failure").state() is GateState.FAILURE
    assert workflow("x", status="completed", conclusion="cancelled").state() is GateState.CANCELLED
    assert workflow("x", status="completed", conclusion="skipped").state() is GateState.SKIPPED
    assert workflow("x", status="completed", conclusion="neutral").state() is GateState.UNKNOWN


@pytest.mark.parametrize(
    "run_id,run_number,attempt",
    [
        (0, 1, 1),
        (-1, 1, 1),
        (1, -1, 1),
        (1, 1, -1),
    ],
)
def test_workflow_evidence_rejects_invalid_identity(run_id, run_number, attempt):
    with pytest.raises(ValueError, match="identity"):
        WorkflowEvidence(
            name="CI/CD",
            run_id=run_id,
            run_number=run_number,
            attempt=attempt,
            head_sha=SHA_A,
            event="pull_request",
            status="completed",
            conclusion="success",
        )


def test_candidate_rejects_negative_threads():
    with pytest.raises(ValueError, match="non-negative"):
        replace(snapshot(), unresolved_threads=-1)


def test_candidate_rejects_parent_self_reference():
    candidate = snapshot(number=7)
    with pytest.raises(ValueError, match="parent itself"):
        replace(candidate, parent_pr=7)


def test_candidate_rejects_duplicate_labels():
    with pytest.raises(ValueError, match="duplicate labels"):
        replace(snapshot(), labels=("automerge", "automerge"))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_merges": 0},
        {"max_stack_merges": 0},
        {"max_changed_files": 0},
        {"max_line_delta": 0},
        {"max_open_pr_scan": 0},
        {"max_merges": True},
    ],
)
def test_merge_budget_rejects_invalid_positive_fields(kwargs):
    base = {
        "max_merges": 1,
        "max_stack_merges": 1,
        "max_changed_files": 1,
        "max_line_delta": 1,
        "stability_seconds": 0,
        "max_open_pr_scan": 1,
    }
    base.update(kwargs)
    with pytest.raises(ValueError):
        MergeBudget(**base)


def test_merge_budget_allows_zero_stability_window():
    budget = MergeBudget(stability_seconds=0)
    assert budget.stability_seconds == 0


def test_policy_normalizes_logins_and_labels():
    p = AutoMergePolicy(
        owner_logins=("Apeloff1", "apeloff1"),
        trusted_bot_logins=("Dependabot[bot]",),
        opt_in_labels=("AutoMerge",),
        opt_out_labels=("DO-NOT-MERGE",),
    )
    assert p.owner_logins == ("apeloff1",)
    assert p.trusted_bot_logins == ("dependabot[bot]",)
    assert p.opt_in_labels == ("automerge",)
    assert p.opt_out_labels == ("do-not-merge",)


def test_policy_rejects_duplicate_required_workflows():
    with pytest.raises(ValueError, match="duplicate"):
        AutoMergePolicy(
            required_workflows=(
                GateRequirement("CI/CD"),
                GateRequirement("CI/CD"),
            )
        )


@pytest.mark.parametrize("value", [-1, 11, True])
def test_policy_rejects_bad_approval_count(value):
    with pytest.raises(ValueError, match="approvals"):
        AutoMergePolicy(required_approvals=value)


def test_labels_normalized_deduplicates_casefolded_values():
    assert labels_normalized(("AutoMerge", "automerge", "KEEP")) == (
        "automerge",
        "keep",
    )


def test_merge_action_is_deterministic():
    candidate = snapshot()
    left = MergeAction.make(
        kind=DecisionKind.MERGE,
        snapshot=candidate,
        merge_method=MergeMethod.SQUASH,
        reason="ready",
    )
    right = MergeAction.make(
        kind=DecisionKind.MERGE,
        snapshot=candidate,
        merge_method=MergeMethod.SQUASH,
        reason="different prose",
    )
    assert left.idempotency_key == right.idempotency_key
    assert left.expected_head_sha == candidate.identity.head_sha


def test_merge_action_key_changes_with_method():
    candidate = snapshot()
    squash = MergeAction.make(
        kind=DecisionKind.MERGE,
        snapshot=candidate,
        merge_method=MergeMethod.SQUASH,
        reason="ready",
    )
    merge = MergeAction.make(
        kind=DecisionKind.MERGE,
        snapshot=candidate,
        merge_method=MergeMethod.MERGE,
        reason="ready",
    )
    assert squash.idempotency_key != merge.idempotency_key


def test_merge_decision_mutating_property():
    candidate = snapshot()
    action = MergeAction.make(
        kind=DecisionKind.MERGE,
        snapshot=candidate,
        merge_method=MergeMethod.SQUASH,
        reason="ready",
    )
    decision = MergeDecision(
        pr_number=1,
        kind=DecisionKind.MERGE,
        reasons=("ready",),
        gates=(),
        actions=(action,),
        snapshot_fingerprint=candidate.fingerprint(),
        policy_fingerprint=policy().fingerprint(),
        risk_tier=RiskTier.LOW,
    )
    assert decision.mutating
    assert len(decision.fingerprint()) == 64


def test_mutation_receipt_fingerprint_is_stable():
    receipt = MutationReceipt(
        pr_number=1,
        action_key="key",
        requested_head_sha=SHA_A,
        observed_head_sha=SHA_A,
        base_ref="main",
        merged=True,
        merge_sha=SHA_B,
        message="merged",
        recorded_at="2026-09-19T20:00:00+00:00",
    )
    assert receipt.fingerprint() == receipt.fingerprint()


def test_reconcile_report_validates_heads():
    with pytest.raises(ValueError, match="canonical"):
        ReconcileReport(
            repository="Apeloff1/Skeleton",
            default_branch="main",
            policy_fingerprint="x" * 64,
            scanned=0,
            decisions=(),
            receipts=(),
            base_head_before="bad",
            base_head_after=SHA_A,
            started_at=NOW.isoformat(),
            finished_at=NOW.isoformat(),
        )


def test_reconcile_report_rejects_negative_scan():
    with pytest.raises(ValueError, match="non-negative"):
        ReconcileReport(
            repository="Apeloff1/Skeleton",
            default_branch="main",
            policy_fingerprint="x" * 64,
            scanned=-1,
            decisions=(),
            receipts=(),
            base_head_before=SHA_A,
            base_head_after=SHA_A,
            started_at=NOW.isoformat(),
            finished_at=NOW.isoformat(),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "closed"),
        ("draft", True),
        ("author", "different"),
        ("base_ref", "release"),
        ("base_sha", SHA_B),
        ("head_ref", "other"),
        ("head_sha", SHA_A),
        ("head_repo", "fork/repo"),
    ],
)
def test_immutable_identity_detects_every_merge_relevant_move(field, value):
    left = identity()
    right = replace(left, **{field: value})
    assert not immutable_identity_equal(left, right)


def test_immutable_identity_accepts_non_merge_metadata_changes():
    left = identity()
    right = replace(
        left,
        updated_at="2026-09-19T21:00:00Z",
        mergeable_state="unstable",
        mergeable=False,
    )
    assert immutable_identity_equal(left, right)


def test_snapshot_fingerprint_covers_workflow_evidence():
    candidate = snapshot()
    changed = replace(
        candidate,
        workflow_runs=(
            *candidate.workflow_runs,
            workflow(
                "extra",
                run_id=999,
                run_number=999,
            ),
        ),
    )
    assert candidate.fingerprint() != changed.fingerprint()


def test_snapshot_fingerprint_covers_stack_relation():
    candidate = snapshot()
    changed = replace(
        candidate,
        stack_relation=StackRelation.CHILD,
        parent_pr=9,
    )
    assert candidate.fingerprint() != changed.fingerprint()


def test_review_state_normalization():
    review = ReviewEvidence(login="x", state=" approved ")
    assert review.normalized_state() == "APPROVED"


def test_policy_fingerprint_changes_with_mode():
    direct = policy(mode=MergeMode.MERGE_DIRECT)
    observe = policy(mode=MergeMode.OBSERVE)
    assert direct.fingerprint() != observe.fingerprint()


def test_candidate_class_enum_values_are_stable():
    assert CandidateClass.OWNER.value == "owner"
    assert CandidateClass.DEPENDABOT.value == "dependabot"
    assert CandidateClass.BOT.value == "bot"
    assert CandidateClass.UNKNOWN.value == "unknown"


def test_risk_tier_enum_values_are_stable():
    assert [tier.value for tier in RiskTier] == [
        "low",
        "medium",
        "high",
        "critical",
    ]


def test_decision_kind_enum_has_stack_child_action():
    assert DecisionKind.MERGE_STACK_CHILD.value == "merge_stack_child"


def test_stack_relation_enum_has_fail_closed_states():
    assert StackRelation.ORPHAN.value == "orphan"
    assert StackRelation.CYCLE.value == "cycle"


def test_serializable_policy_contract():
    payload = json.loads(canonical_json(asdict(policy())))
    assert payload["default_branch"] == "main"
    assert payload["merge_method"] == "squash"
    assert payload["mode"] == "merge_direct"
