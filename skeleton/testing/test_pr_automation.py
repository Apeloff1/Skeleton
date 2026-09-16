from __future__ import annotations

from dataclasses import replace
import sqlite3

import pytest

from skeleton.pr_automation.core import CIState, Decision, Mode, PRSnapshot, Policy, evaluate
from skeleton.pr_automation.index import EventIndex
from skeleton.pr_automation.runner import (
    GATE_CONTEXT,
    aggregate_ci,
    count_approvals,
    count_changes_requested,
    execute_actions,
    policy_from_env,
)


def ready_snapshot(**overrides):
    base = PRSnapshot(
        repository="Apeloff1/Skeleton",
        number=42,
        head_sha="a" * 40,
        base_sha="b" * 40,
        base_ref="main",
        head_ref="feature/example",
        mergeable=True,
        mergeable_state="clean",
        ci_state=CIState.PASSING,
        approvals=0,
        changes_requested=0,
        unresolved_threads=0,
        changed_files=3,
        additions=100,
        deletions=20,
    )
    return replace(base, **overrides)


def test_ready_when_all_fail_closed_gates_are_known():
    result = evaluate(ready_snapshot(), Policy())
    assert result.decision is Decision.READY
    assert result.actions == ()


def test_merge_action_is_head_sha_bound_and_deterministic():
    snapshot = ready_snapshot()
    policy = Policy(merge_when_ready=True)
    one = evaluate(snapshot, policy)
    two = evaluate(snapshot, policy)
    assert one.decision is Decision.MERGE
    assert one.actions[0].expected_head_sha == snapshot.head_sha
    assert one.actions[0].idempotency_key == two.actions[0].idempotency_key


def test_policy_changes_are_reflected_in_audit_fingerprint():
    snapshot = ready_snapshot()
    one = evaluate(snapshot, Policy(required_approvals=0))
    two = evaluate(snapshot, Policy(required_approvals=1))
    assert one.policy_fingerprint != two.policy_fingerprint


def test_draft_is_held():
    assert evaluate(ready_snapshot(draft=True), Policy()).decision is Decision.HOLD


def test_closed_is_ignored():
    assert evaluate(ready_snapshot(state="closed"), Policy()).decision is Decision.IGNORE


def test_fork_is_observe_only_by_default():
    result = evaluate(ready_snapshot(from_fork=True), Policy(merge_when_ready=True))
    assert result.decision is Decision.HOLD
    assert "fork" in result.reasons[0]


def test_unknown_mergeability_fails_closed():
    result = evaluate(ready_snapshot(mergeable=None, mergeable_state="unknown"), Policy())
    assert result.decision is Decision.HOLD


def test_conflict_fails_closed():
    result = evaluate(ready_snapshot(mergeable=False, mergeable_state="dirty"), Policy())
    assert result.decision is Decision.HOLD


def test_behind_branch_fails_closed():
    result = evaluate(ready_snapshot(mergeable=True, mergeable_state="behind"), Policy())
    assert result.decision is Decision.HOLD


def test_future_merge_state_fails_closed():
    result = evaluate(ready_snapshot(mergeable=True, mergeable_state="new_github_state"), Policy())
    assert result.decision is Decision.HOLD


def test_pending_failing_missing_and_unknown_ci_all_hold():
    for state in (CIState.PENDING, CIState.FAILING, CIState.MISSING, CIState.UNKNOWN):
        assert evaluate(ready_snapshot(ci_state=state), Policy()).decision is Decision.HOLD


def test_unknown_review_threads_fail_closed():
    result = evaluate(ready_snapshot(unresolved_threads=None), Policy())
    assert result.decision is Decision.HOLD


def test_unresolved_review_threads_hold():
    result = evaluate(ready_snapshot(unresolved_threads=2), Policy())
    assert result.decision is Decision.HOLD


def test_unknown_approval_state_fails_closed_even_with_zero_threshold():
    assert evaluate(ready_snapshot(approvals=None), Policy()).decision is Decision.HOLD


def test_approval_threshold():
    assert evaluate(ready_snapshot(approvals=0), Policy(required_approvals=1)).decision is Decision.HOLD
    assert evaluate(ready_snapshot(approvals=1), Policy(required_approvals=1)).decision is Decision.READY


def test_active_changes_requested_blocks_even_with_zero_approval_threshold():
    result = evaluate(ready_snapshot(changes_requested=1), Policy(required_approvals=0))
    assert result.decision is Decision.HOLD
    assert "change request" in result.reasons[0]


def test_unknown_blocking_review_state_fails_closed():
    result = evaluate(ready_snapshot(changes_requested=None), Policy())
    assert result.decision is Decision.HOLD


def test_scope_limits_hold_oversized_prs():
    assert evaluate(ready_snapshot(changed_files=251), Policy()).decision is Decision.HOLD
    assert evaluate(ready_snapshot(additions=19_999, deletions=2), Policy()).decision is Decision.HOLD


def test_wrong_base_is_held():
    assert evaluate(ready_snapshot(base_ref="release"), Policy()).decision is Decision.HOLD


def test_invalid_change_metrics_hold():
    assert evaluate(ready_snapshot(additions=-1), Policy()).decision is Decision.HOLD


def test_ci_aggregation_requires_named_checks_when_configured():
    runs = [{"id": 1, "name": "unit", "status": "completed", "conclusion": "success"}]
    assert aggregate_ci(runs, [], {"unit"}) is CIState.PASSING
    assert aggregate_ci(runs, [], {"unit", "security"}) is CIState.MISSING


def test_ci_aggregation_prefers_failure_over_pending():
    runs = [
        {"id": 1, "name": "unit", "status": "in_progress", "conclusion": None},
        {"id": 2, "name": "security", "status": "completed", "conclusion": "failure"},
    ]
    assert aggregate_ci(runs, [], set()) is CIState.FAILING


def test_ci_aggregation_empty_is_missing():
    assert aggregate_ci([], [], set()) is CIState.MISSING


@pytest.mark.parametrize("conclusion", ["neutral", "skipped", None, "future_conclusion"])
def test_non_success_completed_check_never_satisfies_required_gate(conclusion):
    runs = [{"id": 1, "name": "unit", "status": "completed", "conclusion": conclusion}]
    assert aggregate_ci(runs, [], {"unit"}) is CIState.UNKNOWN


def test_newer_rerun_wins_within_same_check_provider():
    app = {"id": 15368, "slug": "github-actions"}
    runs = [
        {
            "id": 10,
            "name": "unit",
            "app": app,
            "status": "completed",
            "conclusion": "failure",
            "completed_at": "2026-01-01T00:00:00Z",
        },
        {
            "id": 11,
            "name": "unit",
            "app": app,
            "status": "completed",
            "conclusion": "success",
            "completed_at": "2026-01-01T00:05:00Z",
        },
    ]
    assert aggregate_ci(runs, [], {"unit"}) is CIState.PASSING


def test_same_named_failure_from_other_provider_cannot_be_overwritten():
    runs = [
        {
            "id": 10,
            "name": "unit",
            "app": {"id": 1},
            "status": "completed",
            "conclusion": "failure",
        },
        {
            "id": 11,
            "name": "unit",
            "app": {"id": 2},
            "status": "completed",
            "conclusion": "success",
        },
    ]
    assert aggregate_ci(runs, [], {"unit"}) is CIState.FAILING


def test_gate_status_does_not_create_a_self_dependency():
    statuses = [{"id": 1, "context": GATE_CONTEXT, "state": "success"}]
    assert aggregate_ci([], statuses, set()) is CIState.MISSING


def test_latest_review_state_prevents_stale_approval_counting():
    reviews = [
        {
            "id": 1,
            "user": {"login": "alice"},
            "state": "APPROVED",
            "submitted_at": "2026-01-01T00:00:00Z",
        },
        {
            "id": 2,
            "user": {"login": "alice"},
            "state": "CHANGES_REQUESTED",
            "submitted_at": "2026-01-02T00:00:00Z",
        },
        {
            "id": 3,
            "user": {"login": "bob"},
            "state": "APPROVED",
            "submitted_at": "2026-01-01T00:00:00Z",
        },
    ]
    assert count_approvals(reviews) == 1
    assert count_changes_requested(reviews) == 1


def test_approval_must_target_current_head_when_head_is_supplied():
    reviews = [
        {
            "id": 1,
            "user": {"login": "alice"},
            "state": "APPROVED",
            "commit_id": "b" * 40,
            "submitted_at": "2026-01-01T00:00:00Z",
        }
    ]
    assert count_approvals(reviews, head_sha="a" * 40) == 0
    assert count_approvals(reviews, head_sha="b" * 40) == 1


def test_event_index_deduplicates_identical_state_and_builds_chain(tmp_path):
    path = tmp_path / "index.sqlite3"
    index = EventIndex(path)
    snapshot = ready_snapshot()
    result = evaluate(snapshot, Policy())

    assert index.append(
        snapshot=snapshot, evaluation=result, event_type="evaluation", delivery_id="delivery-1"
    )
    assert not index.append(
        snapshot=snapshot, evaluation=result, event_type="evaluation", delivery_id="delivery-2"
    )
    assert index.verify_chain(snapshot.repository, snapshot.number)

    second = ready_snapshot(head_sha="c" * 40)
    second_result = evaluate(second, Policy())
    assert index.append(
        snapshot=second, evaluation=second_result, event_type="evaluation", delivery_id="delivery-3"
    )
    assert index.verify_chain(snapshot.repository, snapshot.number)
    assert len(list(index.iter_events(snapshot.repository, snapshot.number))) == 2


def test_event_index_action_claim_is_idempotent(tmp_path):
    index = EventIndex(tmp_path / "index.sqlite3")
    kwargs = dict(
        idempotency_key="k",
        repository="Apeloff1/Skeleton",
        pr_number=42,
        expected_head_sha="a" * 40,
        action_kind="merge",
    )
    assert index.claim_action(**kwargs)
    assert not index.claim_action(**kwargs)
    index.finish_action("k", success=True)
    assert not index.claim_action(**kwargs)


def test_event_index_failed_action_can_retry(tmp_path):
    index = EventIndex(tmp_path / "index.sqlite3")
    kwargs = dict(
        idempotency_key="k",
        repository="Apeloff1/Skeleton",
        pr_number=42,
        expected_head_sha="a" * 40,
        action_kind="merge",
    )
    assert index.claim_action(**kwargs)
    index.finish_action("k", success=False, error="transient")
    assert index.claim_action(**kwargs)


def test_event_index_detects_tampering(tmp_path):
    path = tmp_path / "index.sqlite3"
    index = EventIndex(path)
    snapshot = ready_snapshot()
    result = evaluate(snapshot, Policy())
    assert index.append(snapshot=snapshot, evaluation=result, event_type="evaluation")

    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE events SET decision = 'tampered' WHERE sequence = 1")
        conn.commit()

    assert not index.verify_chain(snapshot.repository, snapshot.number)


def test_event_index_exports_jsonl(tmp_path):
    index = EventIndex(tmp_path / "index.sqlite3")
    snapshot = ready_snapshot()
    result = evaluate(snapshot, Policy())
    index.append(snapshot=snapshot, evaluation=result, event_type="evaluation")
    out = tmp_path / "events.jsonl"
    index.export_jsonl(out)
    assert '"event_type":"evaluation"' in out.read_text(encoding="utf-8")


class FakeClient:
    def __init__(self, *, protected=True):
        self.protected = protected
        self.merges = 0
        self.statuses = []
        self.last_merge_body = None

    def get(self, path):
        if "/branches/" in path:
            return {"protected": self.protected}
        raise AssertionError(f"unexpected GET {path}")

    def request(self, method, url, body=None):
        if method == "POST" and "/statuses/" in url:
            self.statuses.append(body)
            return {}
        if method == "PUT" and "/merge" in url:
            self.merges += 1
            self.last_merge_body = body
            return {"merged": True, "sha": "d" * 40}
        raise AssertionError(f"unexpected request {method} {url}")


def test_stale_head_is_never_merged(tmp_path):
    snapshot = ready_snapshot()
    policy = Policy(merge_when_ready=True)
    evaluation = evaluate(snapshot, policy)
    client = FakeClient()
    index = EventIndex(tmp_path / "index.sqlite3")
    outcome = execute_actions(
        client,
        index,
        snapshot,
        evaluation,
        policy=policy,
        required_checks={"unit"},
        mode=Mode.APPLY,
        max_mutations=1,
        delivery_id="run:42",
        merge_method="squash",
        refresh_snapshot=lambda: ready_snapshot(head_sha="c" * 40),
    )
    assert outcome.mutations == 0
    assert client.merges == 0
    assert client.statuses[-1]["state"] == "pending"


def test_review_state_change_during_apply_discards_plan(tmp_path):
    snapshot = ready_snapshot()
    policy = Policy(merge_when_ready=True)
    evaluation = evaluate(snapshot, policy)
    client = FakeClient()
    index = EventIndex(tmp_path / "index.sqlite3")
    outcome = execute_actions(
        client,
        index,
        snapshot,
        evaluation,
        policy=policy,
        required_checks={"unit"},
        mode=Mode.APPLY,
        max_mutations=1,
        delivery_id="run:42",
        merge_method="squash",
        refresh_snapshot=lambda: ready_snapshot(changes_requested=1),
    )
    assert outcome.mutations == 0
    assert outcome.evaluation.decision is Decision.HOLD
    assert client.merges == 0


def test_unprotected_base_is_never_auto_merged(tmp_path):
    snapshot = ready_snapshot()
    policy = Policy(merge_when_ready=True)
    evaluation = evaluate(snapshot, policy)
    client = FakeClient(protected=False)
    index = EventIndex(tmp_path / "index.sqlite3")
    outcome = execute_actions(
        client,
        index,
        snapshot,
        evaluation,
        policy=policy,
        required_checks={"unit"},
        mode=Mode.APPLY,
        max_mutations=1,
        delivery_id="run:42",
        merge_method="squash",
        refresh_snapshot=lambda: snapshot,
    )
    assert outcome.mutations == 0
    assert client.merges == 0
    assert "protected" in outcome.evaluation.reasons[0]


def test_exhausted_run_budget_never_mutates_but_preserves_readiness(tmp_path):
    snapshot = ready_snapshot()
    policy = Policy(merge_when_ready=True)
    evaluation = evaluate(snapshot, policy)
    client = FakeClient()
    index = EventIndex(tmp_path / "index.sqlite3")
    outcome = execute_actions(
        client,
        index,
        snapshot,
        evaluation,
        policy=policy,
        required_checks={"unit"},
        mode=Mode.APPLY,
        max_mutations=0,
        delivery_id="run:42",
        merge_method="squash",
        refresh_snapshot=lambda: snapshot,
    )
    assert outcome.mutations == 0
    assert outcome.evaluation.decision is Decision.MERGE
    assert client.merges == 0


def test_merge_request_uses_expected_head_sha(tmp_path):
    snapshot = ready_snapshot()
    policy = Policy(merge_when_ready=True)
    evaluation = evaluate(snapshot, policy)
    client = FakeClient()
    index = EventIndex(tmp_path / "index.sqlite3")
    outcome = execute_actions(
        client,
        index,
        snapshot,
        evaluation,
        policy=policy,
        required_checks={"unit"},
        mode=Mode.APPLY,
        max_mutations=1,
        delivery_id="run:42",
        merge_method="squash",
        refresh_snapshot=lambda: snapshot,
    )
    assert outcome.mutations == 1
    assert client.merges == 1
    assert client.last_merge_body == {"sha": snapshot.head_sha, "merge_method": "squash"}


def test_negative_policy_config_is_rejected_instead_of_silently_clamped(monkeypatch):
    monkeypatch.setenv("PR_AUTOMATION_REQUIRED_APPROVALS", "-1")
    with pytest.raises(ValueError, match="between 0 and 50"):
        policy_from_env()
