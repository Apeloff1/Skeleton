"""Regression coverage for separately bounded CI admission classes.

These tests preserve the existing release/security gates. They only ensure
that event-driven maintenance is not misclassified as pull-request CI.
"""
from scripts.check_ci_workflow_tiers import (
    MAX_OTHER_ADMISSIONS,
    MAX_PR_ADMISSIONS,
    admission_group,
    events,
    independently_triggered,
)


def test_manual_and_reusable_are_not_independent_admissions():
    for triggers in (
        {"workflow_dispatch"}, {"workflow_call", "workflow_dispatch"}
    ):
        assert not independently_triggered(triggers)
        assert admission_group(triggers) is None


def test_pr_and_merge_queue_admissions_count_as_pr():
    for triggers in (
        {"pull_request"}, {"pull_request_target"},
        {"merge_group"}, {"pull_request", "schedule"}
    ):
        assert independently_triggered(triggers)
        assert admission_group(triggers) == "pr"


def test_scheduled_and_owner_event_operations_remain_bounded():
    for triggers in (
        {"schedule", "workflow_dispatch"}, {"issue_comment"},
        {"push"}, {"workflow_run"}, {"workflow_dispatch", "push"}
    ):
        assert independently_triggered(triggers)
        assert admission_group(triggers) == "other"


def test_independent_budgets_keep_existing_caps():
    assert MAX_PR_ADMISSIONS == 20
    assert MAX_OTHER_ADMISSIONS == 12
    assert events("name: test\non:\n  workflow_dispatch:\n  pull_request:\n") == {
        "workflow_dispatch", "pull_request"
    }
