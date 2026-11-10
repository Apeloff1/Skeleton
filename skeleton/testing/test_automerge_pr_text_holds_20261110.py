"""Explicit title/body merge holds override opt-in in immutable GitHub policy.

No mocked, skipped, or ancestor workflow can grant a held PR merge permission.
"""
from dataclasses import replace
import pytest

from skeleton.pr_automation.automerge_engine import _snapshot_matches
from skeleton.pr_automation.automerge_model import (
    DecisionKind, has_explicit_merge_hold,
)
from skeleton.pr_automation.automerge_policy import evaluate_candidate
from skeleton.testing.automerge_test_support import NOW, policy, snapshot


@pytest.mark.parametrize(("title", "body"), [
    ("[REVIEW ONLY — DO NOT MERGE] reconcile setup", ""),
    ("Fix a subsystem", "REVIEW ONLY / NO MERGE / NO AUTO-MERGE / NO RELEASE"),
    ("Fix a subsystem", "No squash/merge before all required gates."),
    ("Fix a subsystem", "**Not approved for merge** pending security review."),
    ("Fix a subsystem", "Merge held until native acceptance."),
    ("fix docs", "Never merge before independent source review."),
    ("DO NOT AUTO-MERGE security candidate", ""),
    ("Fix a subsystem", "Do not merge child before the held parent."),
])
def test_explicit_text_holds_are_always_detected(title, body):
    assert has_explicit_merge_hold(title, body)


@pytest.mark.parametrize(("title", "body"), [
    ("fix(ci): improve test coverage", "All exact head checks are green."),
    ("feat(game): bounded route solver", "No production release approval implied."),
    ("", ""),
    (None, None),
])
def test_non_merge_claims_do_not_fabricate_positive_authorization(title, body):
    assert not has_explicit_merge_hold(title, body)


@pytest.mark.parametrize(("title", "body"), [
    ({"wrong": "type"}, ""),
    ("Normal title", ["invalid description"]),
    ("x" * 131073, ""),
])
def test_malformed_or_unbounded_authority_text_is_held(title, body):
    assert has_explicit_merge_hold(title, body)


def test_owner_implicit_opt_in_never_overrides_author_review_hold():
    candidate = snapshot(labels=())
    p = policy(allow_owner_without_opt_in=True)
    ordinary = evaluate_candidate(candidate, p, now=NOW)
    assert ordinary.kind is not DecisionKind.HOLD, ordinary.reasons
    held = replace(candidate, explicit_merge_hold=True)
    decision = evaluate_candidate(held, p, now=NOW)
    assert decision.kind is DecisionKind.HOLD
    assert decision.reasons == ("explicit_pr_text_merge_hold",)
    assert not decision.actions


def test_explicit_automerge_label_cannot_override_review_hold():
    held = replace(snapshot(labels=("automerge",)), explicit_merge_hold=True)
    decision = evaluate_candidate(held, policy(), now=NOW)
    assert decision.kind is DecisionKind.HOLD
    assert "explicit_pr_text_merge_hold" in decision.reasons


def test_merge_hold_changes_invalidate_pre_mutation_snapshot():
    original = snapshot(labels=("automerge",))
    after_edit = replace(original, explicit_merge_hold=True)
    assert not _snapshot_matches(original, after_edit)
    assert not _snapshot_matches(after_edit, original)


def test_snapshot_rejects_non_boolean_holds():
    candidate = snapshot()
    with pytest.raises(ValueError, match="exact boolean"):
        replace(candidate, explicit_merge_hold=1)
