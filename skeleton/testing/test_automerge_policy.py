"""Risk-aware auto-merge policy regression matrix."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from skeleton.pr_automation.automerge_model import (
    CandidateClass,
    DecisionKind,
    MergeMode,
    RiskTier,
    StackRelation,
)
from skeleton.pr_automation.automerge_policy import (
    CODE_WORKFLOWS,
    DEFAULT_REQUIRED_WORKFLOWS,
    SECURITY_WORKFLOWS,
    candidate_opted_in,
    canonical_path,
    classify_candidate,
    classify_paths,
    evaluate_candidate,
    mutating_decisions,
    requirements_for_candidate,
    sort_decisions_for_execution,
)
from skeleton.testing.automerge_test_support import (
    BASE_WORKFLOWS,
    CODE_WORKFLOWS as CODE_NAMES,
    NOW,
    SHA_A,
    SHA_B,
    as_stack_child,
    policy,
    require_code_workflows,
    reviews,
    snapshot,
    successful_runs,
    with_run_state,
    workflow,
)


@pytest.mark.parametrize(
    "path",
    [
        "docs/readme.md",
        "backend/server.py",
        ".github/workflows/ci.yml",
        "a/b/c.txt",
        "pyproject.toml",
    ],
)
def test_canonical_path_accepts_normal_relative_paths(path):
    assert canonical_path(path) == path


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/absolute/path",
        "../escape.py",
        "a/../escape.py",
        "a/./b.py",
        "a//b.py",
        "a\\b.py",
        "a\x00b.py",
    ],
)
def test_canonical_path_rejects_ambiguous_paths(path):
    assert canonical_path(path) is None


def test_docs_only_classification_is_low_risk():
    candidate = snapshot(files=("docs/a.md", "README.md"))
    result = classify_paths(candidate.diff.files, policy())
    assert result.docs_only
    assert result.risk is RiskTier.LOW
    assert not result.code


def test_backend_code_is_medium_risk():
    result = classify_paths(("backend/server.py",), policy())
    assert result.code
    assert result.risk is RiskTier.MEDIUM


def test_test_only_code_is_low_risk():
    result = classify_paths(("tests/test_example.py",), policy())
    assert result.test_only
    assert result.risk is RiskTier.LOW


@pytest.mark.parametrize(
    "path",
    [
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "frontend/package.json",
        "frontend/yarn.lock",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
    ],
)
def test_dependency_surfaces_are_high_risk(path):
    result = classify_paths((path,), policy())
    assert result.dependency
    assert result.risk is RiskTier.HIGH


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        ".github/actions/custom/action.yml",
        "skeleton/pr_automation/core.py",
        "skeleton/security/scanner.py",
    ],
)
def test_security_and_automation_trust_surfaces_are_critical(path):
    result = classify_paths((path,), policy())
    assert result.risk is RiskTier.CRITICAL


@pytest.mark.parametrize(
    "path",
    [
        "Dockerfile",
        "docker/backend.Dockerfile",
        "deploy/prod.yaml",
        "helm/chart/values.yaml",
        "k8s/deployment.yaml",
        "release/manifest.json",
    ],
)
def test_release_surfaces_are_high_risk(path):
    result = classify_paths((path,), policy())
    assert result.release
    assert result.risk is RiskTier.HIGH


def test_invalid_changed_path_is_classified_critical():
    result = classify_paths(("../escape.py",), policy())
    assert result.risk is RiskTier.CRITICAL
    assert result.critical == ("<invalid:../escape.py>",)


def test_sensitive_prefixes_are_reported_exactly():
    result = classify_paths(
        (
            ".github/workflows/ci.yml",
            "docs/readme.md",
            "skeleton/pr_automation/core.py",
        ),
        policy(),
    )
    assert ".github/workflows/ci.yml" in result.sensitive
    assert "skeleton/pr_automation/core.py" in result.sensitive
    assert "docs/readme.md" not in result.sensitive


def test_owner_classification():
    candidate = snapshot(author="Apeloff1")
    assert classify_candidate(candidate, policy()) is CandidateClass.OWNER


def test_owner_classification_is_case_insensitive():
    candidate = snapshot(author="APELOFF1")
    assert classify_candidate(candidate, policy()) is CandidateClass.OWNER


def test_dependabot_classification():
    candidate = snapshot(author="dependabot[bot]")
    assert classify_candidate(candidate, policy()) is CandidateClass.DEPENDABOT


def test_untrusted_bot_classification_fails_closed():
    candidate = snapshot(author="random-bot[bot]")
    assert classify_candidate(candidate, policy()) is CandidateClass.UNKNOWN


def test_owner_opt_in_can_be_implicit():
    candidate = snapshot(labels=())
    p = policy(allow_owner_without_opt_in=True)
    assert candidate_opted_in(candidate, p, CandidateClass.OWNER)


def test_owner_opt_in_can_be_required():
    candidate = snapshot(labels=())
    p = policy(allow_owner_without_opt_in=False)
    assert not candidate_opted_in(candidate, p, CandidateClass.OWNER)


def test_owner_explicit_label_enables_when_implicit_disabled():
    candidate = snapshot(labels=("automerge",))
    p = policy(allow_owner_without_opt_in=False)
    assert candidate_opted_in(candidate, p, CandidateClass.OWNER)


def test_opt_out_always_wins_over_opt_in():
    candidate = snapshot(labels=("automerge", "do-not-merge"))
    p = policy()
    assert not candidate_opted_in(candidate, p, CandidateClass.OWNER)


def test_dependabot_can_be_implicitly_enabled():
    candidate = snapshot(author="dependabot[bot]", labels=())
    p = policy(allow_dependabot_without_opt_in=True)
    assert candidate_opted_in(candidate, p, CandidateClass.DEPENDABOT)


def test_dependabot_can_require_label():
    candidate = snapshot(author="dependabot[bot]", labels=())
    p = policy(allow_dependabot_without_opt_in=False)
    assert not candidate_opted_in(candidate, p, CandidateClass.DEPENDABOT)


def test_baseline_requirements_are_always_present():
    candidate = snapshot()
    names = {item.name for item in requirements_for_candidate(candidate, policy())}
    assert {item.name for item in DEFAULT_REQUIRED_WORKFLOWS}.issubset(names)


def test_code_candidate_adds_code_workflows():
    candidate = snapshot(files=("backend/server.py",))
    names = {item.name for item in requirements_for_candidate(candidate, policy())}
    assert {item.name for item in CODE_WORKFLOWS}.issubset(names)


def test_dependency_candidate_adds_dependency_workflows():
    candidate = snapshot(files=("pyproject.toml",))
    names = {item.name for item in requirements_for_candidate(candidate, policy())}
    assert "Dependency Review" in names
    assert "Dependency Security" in names


def test_security_candidate_adds_security_workflows():
    candidate = snapshot(files=(".github/workflows/ci.yml",))
    names = {item.name for item in requirements_for_candidate(candidate, policy())}
    assert {item.name for item in SECURITY_WORKFLOWS}.issubset(names)


def test_release_candidate_adds_reproducible_release():
    candidate = snapshot(files=("Dockerfile",))
    names = {item.name for item in requirements_for_candidate(candidate, policy())}
    assert "Reproducible Release" in names


def test_requirements_are_deduplicated():
    p = policy(required=("CI/CD", "Merge Readiness"))
    candidate = snapshot()
    names = [item.name for item in requirements_for_candidate(candidate, p)]
    assert len(names) == len(set(names))


def _ready_docs_candidate(**kwargs):
    candidate = snapshot(**kwargs)
    p = policy()
    return candidate, p


def test_clean_owner_docs_candidate_merges():
    candidate, p = _ready_docs_candidate()
    decision = evaluate_candidate(candidate, p, now=NOW)
    assert decision.kind is DecisionKind.MERGE
    assert len(decision.actions) == 1


def test_observe_mode_never_mutates():
    candidate = snapshot()
    p = policy(mode=MergeMode.OBSERVE)
    decision = evaluate_candidate(candidate, p, now=NOW)
    assert decision.kind is DecisionKind.READY
    assert decision.actions == ()


def test_native_mode_enables_native_auto_merge():
    candidate = snapshot()
    p = policy(mode=MergeMode.ENABLE_NATIVE)
    decision = evaluate_candidate(candidate, p, now=NOW)
    assert decision.kind is DecisionKind.ENABLE_AUTO_MERGE
    assert decision.actions[0].kind is DecisionKind.ENABLE_AUTO_MERGE


def test_closed_candidate_is_ignored():
    candidate = snapshot(state="closed")
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.IGNORE


def test_draft_candidate_is_held():
    candidate = snapshot(draft=True)
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD
    assert "pull_request_is_draft" in decision.reasons


def test_mergeability_none_is_held():
    candidate = snapshot(mergeable=None)
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD
    assert "mergeability_not_affirmatively_true" in decision.reasons


def test_mergeability_false_is_held():
    candidate = snapshot(mergeable=False)
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD


@pytest.mark.parametrize("state", ["dirty", "blocked", "unknown", "behind"])
def test_bad_mergeable_state_is_held(state):
    candidate = snapshot(mergeable_state=state)
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD
    assert any(reason.startswith("mergeable_state:") for reason in decision.reasons)


def test_unstable_mergeable_state_can_proceed_if_exact_gates_are_green():
    candidate = snapshot(mergeable_state="unstable")
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.MERGE


def test_fork_is_held_by_default():
    candidate = snapshot(head_repo="fork/Skeleton")
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD
    assert "fork_head_not_allowed" in decision.reasons


def test_head_must_contain_base():
    candidate = snapshot(head_contains_base=False)
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD
    assert "head_does_not_contain_current_base" in decision.reasons


def test_unknown_ancestry_is_held():
    candidate = snapshot(head_contains_base=None)
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD


def test_empty_diff_is_held():
    candidate = snapshot(files=(), additions=0, deletions=0)
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD
    assert "empty_diff" in decision.reasons


def test_changed_file_budget_is_enforced():
    files = tuple(f"docs/{index}.md" for index in range(4))
    candidate = snapshot(files=files)
    p = policy(max_changed_files=3)
    decision = evaluate_candidate(candidate, p, now=NOW)
    assert "changed_file_budget_exceeded" in decision.reasons


def test_line_delta_budget_is_enforced():
    candidate = snapshot(additions=80, deletions=30)
    p = policy(max_line_delta=100)
    decision = evaluate_candidate(candidate, p, now=NOW)
    assert "line_delta_budget_exceeded" in decision.reasons


def test_untrusted_author_is_held():
    candidate = snapshot(author="mallory")
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD
    assert "untrusted_author_class" in decision.reasons


def test_explicit_opt_out_is_held():
    candidate = snapshot(labels=("do-not-merge",))
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert "explicit_automerge_opt_out" in decision.reasons


def test_missing_opt_in_is_held_when_owner_implicit_disabled():
    candidate = snapshot(labels=())
    p = policy(allow_owner_without_opt_in=False)
    decision = evaluate_candidate(candidate, p, now=NOW)
    assert "automerge_opt_in_missing" in decision.reasons


@pytest.mark.parametrize(
    "critical_path",
    [
        ".github/workflows/ci.yml",
        ".github/actions/local/action.yml",
        "skeleton/pr_automation/core.py",
    ],
)
def test_critical_trust_surface_auto_merges_after_full_evidence(critical_path):
    candidate = snapshot(files=(critical_path,))
    run_names = tuple(
        dict.fromkeys(
            [
                *BASE_WORKFLOWS,
                *(item.name for item in CODE_WORKFLOWS),
                *(item.name for item in SECURITY_WORKFLOWS),
            ]
        )
    )
    candidate = replace(
        candidate,
        workflow_runs=successful_runs(
            run_names,
            head_sha=candidate.identity.head_sha,
        ),
    )
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.MERGE
    assert decision.actions
    assert decision.risk_tier is RiskTier.CRITICAL


@pytest.mark.parametrize("missing_name", BASE_WORKFLOWS)
def test_each_baseline_workflow_can_block_merge(missing_name):
    names = tuple(name for name in BASE_WORKFLOWS if name != missing_name)
    candidate = snapshot(run_names=names)
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD
    assert f"gate:{missing_name}:missing" in decision.reasons


def test_pending_gate_blocks_merge():
    candidate = with_run_state(
        snapshot(),
        "CI/CD",
        status="in_progress",
        conclusion=None,
    )
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD
    assert "gate:CI/CD:pending" in decision.reasons


def test_failed_gate_blocks_merge():
    candidate = with_run_state(
        snapshot(),
        "CI/CD",
        status="completed",
        conclusion="failure",
    )
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD
    assert "gate:CI/CD:failure" in decision.reasons


def test_cancelled_gate_blocks_merge():
    candidate = with_run_state(
        snapshot(),
        "CI/CD",
        status="completed",
        conclusion="cancelled",
    )
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD
    assert "gate:CI/CD:cancelled" in decision.reasons


def test_new_pending_attempt_overrides_success_and_blocks():
    candidate = snapshot()
    candidate = replace(
        candidate,
        workflow_runs=(
            *candidate.workflow_runs,
            workflow(
                "CI/CD",
                run_id=9999,
                run_number=9999,
                status="queued",
                conclusion=None,
                updated_at=NOW - timedelta(minutes=1),
            ),
        ),
    )
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert "gate:CI/CD:pending" in decision.reasons


def test_stale_other_head_success_does_not_satisfy_current_head():
    candidate = snapshot(
        workflow_runs=successful_runs(BASE_WORKFLOWS, head_sha=SHA_A),
    )
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD
    assert any(reason.endswith(":missing") for reason in decision.reasons)


def test_approval_requirement_is_enforced():
    candidate = snapshot(review_items=reviews(approvals=1))
    p = policy(approvals=2)
    decision = evaluate_candidate(candidate, p, now=NOW)
    assert "approvals:1:required:2" in decision.reasons


def test_change_request_blocks_merge():
    candidate = snapshot(review_items=reviews(changes_requested=1))
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert "changes_requested:1" in decision.reasons


def test_unknown_thread_state_blocks_merge():
    candidate = snapshot(unresolved_threads=None)
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert "review_threads:unknown" in decision.reasons


def test_unresolved_threads_block_merge():
    candidate = snapshot(unresolved_threads=2)
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert "review_threads:unresolved:2" in decision.reasons


def test_success_stability_window_is_enforced():
    recent = NOW - timedelta(seconds=5)
    candidate = snapshot(
        workflow_runs=successful_runs(BASE_WORKFLOWS, updated_at=recent),
    )
    p = policy(stability_seconds=30)
    decision = evaluate_candidate(candidate, p, now=NOW)
    assert "exact_head_success_stability_window_not_elapsed" in decision.reasons


def test_zero_stability_window_allows_immediate_decision():
    candidate = snapshot(
        workflow_runs=successful_runs(BASE_WORKFLOWS, updated_at=NOW),
    )
    p = policy(stability_seconds=0)
    decision = evaluate_candidate(candidate, p, now=NOW)
    assert decision.kind is DecisionKind.MERGE


def test_code_candidate_needs_extra_code_gates():
    candidate = snapshot(files=("backend/server.py",))
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    for name in CODE_NAMES:
        assert f"gate:{name}:missing" in decision.reasons


def test_code_candidate_merges_when_code_gates_are_green():
    candidate = require_code_workflows(
        snapshot(files=("backend/server.py",))
    )
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.MERGE
    assert decision.risk_tier is RiskTier.MEDIUM


def test_dependency_candidate_requires_dependency_evidence():
    candidate = snapshot(files=("pyproject.toml",))
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert "gate:Dependency Review:missing" in decision.reasons
    assert "gate:Dependency Security:missing" in decision.reasons


def test_dependency_candidate_merges_with_dependency_evidence():
    candidate = snapshot(files=("pyproject.toml",))
    names = (
        *BASE_WORKFLOWS,
        "Dependency Review",
        "Dependency Security",
    )
    candidate = replace(
        candidate,
        workflow_runs=successful_runs(names),
    )
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.MERGE
    assert decision.risk_tier is RiskTier.HIGH


def test_release_candidate_requires_reproducible_release():
    candidate = snapshot(files=("Dockerfile",))
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert "gate:Reproducible Release:missing" in decision.reasons


def test_release_candidate_merges_with_release_gate():
    candidate = snapshot(files=("Dockerfile",))
    candidate = replace(
        candidate,
        workflow_runs=successful_runs(
            (*BASE_WORKFLOWS, "Reproducible Release")
        ),
    )
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.MERGE
    assert decision.risk_tier is RiskTier.HIGH


def test_stack_cycle_is_held():
    candidate = replace(snapshot(), stack_relation=StackRelation.CYCLE)
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert "stack_cycle" in decision.reasons


def test_stack_orphan_is_held():
    candidate = replace(snapshot(), stack_relation=StackRelation.ORPHAN)
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert "stack_parent_missing" in decision.reasons


def test_stack_child_requires_parent_identity():
    candidate = replace(
        snapshot(base_ref="feature/parent"),
        stack_relation=StackRelation.CHILD,
        parent_pr=None,
    )
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert "stack_child_missing_parent_identity" in decision.reasons


def test_stack_child_can_be_disabled():
    candidate = replace(
        snapshot(number=2, base_ref="feature/parent"),
        stack_relation=StackRelation.CHILD,
        parent_pr=1,
    )
    p = policy(allow_stack_child_merge=False)
    decision = evaluate_candidate(candidate, p, now=NOW)
    assert "stack_child_merge_disabled" in decision.reasons


def test_stack_child_targets_non_main_and_gets_special_action():
    candidate = as_stack_child(
        snapshot(number=2, head_ref="feature/child"),
        parent_pr=1,
        base_ref="feature/parent",
        base_sha=SHA_A,
    )
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.MERGE_STACK_CHILD
    assert decision.actions[0].kind is DecisionKind.MERGE_STACK_CHILD


def test_root_relation_with_non_main_base_is_held():
    candidate = snapshot(base_ref="feature/other")
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert "root_candidate_wrong_base:feature/other" in decision.reasons


def test_stack_child_relation_on_main_is_held():
    candidate = replace(
        snapshot(),
        stack_relation=StackRelation.CHILD,
        parent_pr=9,
    )
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert "stack_child_relation_mismatch" in decision.reasons


def test_dependabot_dependency_candidate_can_merge_without_label():
    candidate = snapshot(
        author="dependabot[bot]",
        labels=(),
        files=("pyproject.toml",),
        workflow_runs=successful_runs(
            (*BASE_WORKFLOWS, "Dependency Review", "Dependency Security")
        ),
    )
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.MERGE


def test_dependabot_auto_merges_critical_trust_surface_after_full_evidence():
    candidate = snapshot(
        author="dependabot[bot]",
        labels=(),
        files=(".github/workflows/ci.yml",),
        workflow_runs=successful_runs(
            (
                *BASE_WORKFLOWS,
                *(item.name for item in CODE_WORKFLOWS),
                *(item.name for item in SECURITY_WORKFLOWS),
            )
        ),
    )
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.kind is DecisionKind.MERGE
    assert decision.risk_tier is RiskTier.CRITICAL


def test_sort_decisions_prioritizes_stack_children():
    child = evaluate_candidate(
        as_stack_child(
            snapshot(number=2, head_ref="feature/child"),
            parent_pr=1,
            base_ref="feature/parent",
            base_sha=SHA_A,
        ),
        policy(),
        now=NOW,
    )
    root = evaluate_candidate(snapshot(number=1), policy(), now=NOW)
    ordered = sort_decisions_for_execution((root, child))
    assert ordered[0].kind is DecisionKind.MERGE_STACK_CHILD


def test_sort_decisions_is_stable_by_pr_number():
    one = evaluate_candidate(snapshot(number=1), policy(), now=NOW)
    two = evaluate_candidate(
        snapshot(number=2, head_ref="feature/two"),
        policy(),
        now=NOW,
    )
    ordered = sort_decisions_for_execution((two, one))
    assert [item.pr_number for item in ordered] == [1, 2]


def test_mutating_decisions_filters_holds_and_ready():
    ready = evaluate_candidate(
        snapshot(),
        policy(mode=MergeMode.OBSERVE),
        now=NOW,
    )
    merge = evaluate_candidate(
        snapshot(number=2, head_ref="feature/two"),
        policy(),
        now=NOW,
    )
    held = evaluate_candidate(
        snapshot(number=3, head_ref="feature/three", draft=True),
        policy(),
        now=NOW,
    )
    assert [item.pr_number for item in mutating_decisions((ready, held, merge))] == [2]


@pytest.mark.parametrize(
    "label",
    [
        "do-not-merge",
        "AUTOMERGE:OFF",
    ],
)
def test_casefolded_opt_out_labels_block(label):
    candidate = snapshot(labels=(label,))
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert "explicit_automerge_opt_out" in decision.reasons


@pytest.mark.parametrize(
    "label",
    [
        "automerge",
        "AUTOMERGE",
    ],
)
def test_casefolded_opt_in_labels_work(label):
    candidate = snapshot(labels=(label,))
    p = policy(allow_owner_without_opt_in=False)
    decision = evaluate_candidate(candidate, p, now=NOW)
    assert decision.kind is DecisionKind.MERGE


def test_action_is_bound_to_snapshot_head_and_base():
    candidate = snapshot()
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    action = decision.actions[0]
    assert action.expected_head_sha == candidate.identity.head_sha
    assert action.expected_base_sha == candidate.identity.base_sha


def test_decision_fingerprints_policy_and_snapshot():
    candidate = snapshot()
    p = policy()
    decision = evaluate_candidate(candidate, p, now=NOW)
    assert decision.snapshot_fingerprint == candidate.fingerprint()
    assert decision.policy_fingerprint == p.fingerprint()


def test_risk_tier_is_derived_from_paths_not_fixture_default():
    candidate = snapshot(
        files=("backend/server.py",),
        risk_tier=RiskTier.LOW,
    )
    candidate = require_code_workflows(candidate)
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert decision.risk_tier is RiskTier.MEDIUM


def test_multiple_missing_code_gates_are_all_reported():
    candidate = snapshot(files=("backend/server.py",))
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    missing = {
        reason
        for reason in decision.reasons
        if reason.startswith("gate:")
    }
    assert {f"gate:{name}:missing" for name in CODE_NAMES}.issubset(missing)


def test_new_failure_on_required_extra_gate_blocks():
    candidate = snapshot(files=("backend/server.py",))
    names = (*BASE_WORKFLOWS, *CODE_NAMES)
    candidate = replace(
        candidate,
        workflow_runs=successful_runs(names),
    )
    candidate = with_run_state(
        candidate,
        "Backend Quality",
        status="completed",
        conclusion="failure",
        run_number=5000,
    )
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    assert "gate:Backend Quality:failure" in decision.reasons


def test_exact_head_code_evidence_cannot_be_substituted_by_old_head():
    candidate = snapshot(files=("backend/server.py",))
    current = successful_runs(BASE_WORKFLOWS, head_sha=SHA_B)
    old_code = successful_runs(CODE_NAMES, head_sha=SHA_A, start_id=5000)
    candidate = replace(candidate, workflow_runs=(*current, *old_code))
    decision = evaluate_candidate(candidate, policy(), now=NOW)
    for name in CODE_NAMES:
        assert f"gate:{name}:missing" in decision.reasons


def test_ready_decision_has_single_atomic_action():
    decision = evaluate_candidate(snapshot(), policy(), now=NOW)
    assert decision.kind is DecisionKind.MERGE
    assert len(decision.actions) == 1
    assert decision.actions[0].reason


def test_hold_decision_has_no_action():
    decision = evaluate_candidate(snapshot(draft=True), policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD
    assert decision.actions == ()


def test_ignore_decision_has_no_gate_work():
    decision = evaluate_candidate(snapshot(state="closed"), policy(), now=NOW)
    assert decision.kind is DecisionKind.IGNORE
    assert decision.gates == ()
    assert decision.actions == ()


def test_required_custom_workflow_is_enforced():
    p = policy(required=(*BASE_WORKFLOWS, "Custom Required Gate"))
    candidate = snapshot()
    decision = evaluate_candidate(candidate, p, now=NOW)
    assert "gate:Custom Required Gate:missing" in decision.reasons


def test_required_custom_workflow_can_be_satisfied():
    p = policy(required=(*BASE_WORKFLOWS, "Custom Required Gate"))
    candidate = snapshot(
        workflow_runs=successful_runs(
            (*BASE_WORKFLOWS, "Custom Required Gate")
        )
    )
    decision = evaluate_candidate(candidate, p, now=NOW)
    assert decision.kind is DecisionKind.MERGE
