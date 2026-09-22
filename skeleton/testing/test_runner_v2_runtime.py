"""Transport, targeting, and scheduler regressions for runner v2."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from email.message import Message
from urllib.error import HTTPError

import pytest

from skeleton.pr_automation.core import Decision, Mode
from skeleton.pr_automation.runner_contracts import (
    AdmissionState,
    PriorityBand,
    RequestOutcome,
    RunBudget,
    RunTrigger,
    WorkState,
)
from skeleton.pr_automation.runner_scheduler import (
    MutableBudget,
    budget_allows_mutation,
    budget_allows_target,
    build_work_item,
    deadline_reached,
    deadline_remaining_seconds,
    defer_item,
    evaluate_snapshot,
    make_budget,
    mutation_candidates,
    observe_queue,
    schedule_items,
    score_work_item,
)
from skeleton.pr_automation.runner_targeting import (
    TargetResolver,
    TargetingError,
    admission_for_identity,
    identity_from_env,
    merge_hint_sets,
    parse_pr_hints,
    target_numbers,
)
from skeleton.pr_automation.runner_transport import (
    BudgetedGitHubTransport,
    GitHubHTTPError,
    GraphQLBudgetExceeded,
    RateLimitFloorReached,
    RequestBudgetExceeded,
    ResponseTooLarge,
    RunnerTransportError,
    UnsafeMutationRetry,
)
from skeleton.testing.runner_v2_test_support import (
    NOW,
    SHA_A,
    SHA_B,
    SHA_C,
    FakeResponse,
    RouteOpener,
    ScriptedTransport,
    admission,
    core_snapshot,
    identity,
    limits,
    pr_payload,
    runner_policy,
    snapshot,
    target,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", ()),
        ("[]", ()),
        ("null", ()),
        ("[1,2,1]", (1, 2)),
    ],
)
def test_parse_pr_hints(raw, expected):
    assert parse_pr_hints(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "{bad",
        "{}",
        "[0]",
        "[-1]",
        "[true]",
        '["1"]',
    ],
)
def test_parse_pr_hints_rejects_invalid(raw):
    with pytest.raises(TargetingError):
        parse_pr_hints(raw)


def test_merge_hint_sets_deduplicates_in_order():
    assert merge_hint_sets((2, 1), (1, 3)) == (2, 1, 3)


def test_merge_hint_sets_rejects_invalid():
    with pytest.raises(TargetingError):
        merge_hint_sets((0,))


def test_identity_from_env_explicit():
    result = identity_from_env(
        {
            "GITHUB_RUN_ID": "88",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
        },
        repository="Apeloff1/Skeleton",
        explicit_pr=42,
    )
    assert result.trigger is RunTrigger.EXPLICIT
    assert result.delivery_id == "88"


def test_identity_from_env_workflow_completion():
    result = identity_from_env(
        {
            "GITHUB_RUN_ID": "88",
            "GITHUB_EVENT_NAME": "workflow_run",
            "WORKFLOW_RUN_HEAD_SHA": SHA_B,
            "WORKFLOW_RUN_HEAD_REF": "feature/x",
            "WORKFLOW_RUN_ID": "999",
            "WORKFLOW_RUN_NAME": "Merge Readiness",
        },
        repository="Apeloff1/Skeleton",
        default_branch="main",
    )
    assert result.trigger is RunTrigger.WORKFLOW_COMPLETION
    assert result.workflow_run_id == 999


def test_identity_from_env_default_branch_completion():
    result = identity_from_env(
        {
            "GITHUB_RUN_ID": "88",
            "GITHUB_EVENT_NAME": "workflow_run",
            "WORKFLOW_RUN_HEAD_SHA": SHA_B,
            "WORKFLOW_RUN_HEAD_REF": "main",
        },
        repository="Apeloff1/Skeleton",
        default_branch="main",
    )
    assert result.trigger is RunTrigger.DEFAULT_BRANCH_COMPLETION


def test_identity_from_env_schedule():
    result = identity_from_env(
        {
            "GITHUB_RUN_ID": "88",
            "GITHUB_EVENT_NAME": "schedule",
        },
        repository="Apeloff1/Skeleton",
    )
    assert result.trigger is RunTrigger.SCHEDULED_SWEEP


def test_schedule_admission_is_observe_only_by_default():
    ident = identity(
        trigger=RunTrigger.SCHEDULED_SWEEP,
        explicit_pr=None,
    )
    decision = admission_for_identity(
        ident,
        runner_policy(),
        {},
    )
    assert decision.state is AdmissionState.OBSERVE_ONLY
    assert not decision.mutation_authorized


def test_observe_mode_admission_never_mutates():
    ident = identity()
    policy = replace(runner_policy(), mode=Mode.OBSERVE)
    decision = admission_for_identity(ident, policy, {})
    assert decision.state is AdmissionState.OBSERVE_ONLY


def _workflow_completion_identity():
    return identity(
        trigger=RunTrigger.WORKFLOW_COMPLETION,
        explicit_pr=None,
        workflow_name="Merge Readiness",
        workflow_run_id=999,
        head_sha=SHA_B,
        head_ref="feature/runner-v2",
        event_name="workflow_run",
    )


def _workflow_completion_env(*, conclusion: str) -> dict[str, str]:
    return {
        "WORKFLOW_RUN_NAME": "Merge Readiness",
        "WORKFLOW_RUN_ID": "999",
        "WORKFLOW_RUN_ATTEMPT": "1",
        "WORKFLOW_RUN_WORKFLOW_ID": "123",
        "WORKFLOW_RUN_STATUS": "completed",
        "WORKFLOW_RUN_CONCLUSION": conclusion,
        "WORKFLOW_RUN_EVENT": "pull_request",
        "WORKFLOW_RUN_HEAD_REPOSITORY": "Apeloff1/Skeleton",
    }


def test_workflow_completion_observe_reason_is_preserved():
    decision = admission_for_identity(
        _workflow_completion_identity(),
        runner_policy(),
        _workflow_completion_env(conclusion="failure"),
    )
    assert decision.state is AdmissionState.OBSERVE_ONLY
    assert not decision.mutation_authorized
    assert any("non-success" in reason for reason in decision.reasons)


def test_workflow_completion_drop_reason_is_preserved():
    decision = admission_for_identity(
        _workflow_completion_identity(),
        runner_policy(),
        _workflow_completion_env(conclusion="cancelled"),
    )
    assert decision.state is AdmissionState.DROP
    assert decision.dropped
    assert any("tombstone" in reason for reason in decision.reasons)


def test_target_resolver_explicit_validates_pr():
    transport = ScriptedTransport()
    transport.get_map["/repos/Apeloff1/Skeleton/pulls/42"] = pr_payload()
    result = TargetResolver(
        transport,
        runner_policy(),
    ).resolve(identity())
    assert target_numbers(result) == (42,)
    assert result.complete


def test_target_resolver_sweep_filters_base():
    transport = ScriptedTransport()
    transport.list_map[
        "/repos/Apeloff1/Skeleton/pulls?state=open&sort=updated&direction=asc"
    ] = (
        [
            pr_payload(number=1, base_ref="main"),
            pr_payload(number=2, base_ref="release"),
        ],
        True,
    )
    ident = identity(
        trigger=RunTrigger.MANUAL_SWEEP,
        explicit_pr=None,
    )
    result = TargetResolver(
        transport,
        runner_policy(),
    ).resolve(ident)
    assert target_numbers(result) == (1,)


def test_target_resolver_sweep_filters_before_applying_target_cap():
    transport = ScriptedTransport()
    transport.list_map[
        "/repos/Apeloff1/Skeleton/pulls?state=open&sort=updated&direction=asc"
    ] = (
        [
            pr_payload(number=1, base_ref="release", head_ref="feature/release"),
            pr_payload(number=2, base_ref="main", head_ref="feature/main"),
        ],
        True,
    )
    policy = replace(
        runner_policy(),
        limits=replace(runner_policy().limits, max_targets=1),
    )
    ident = identity(
        trigger=RunTrigger.MANUAL_SWEEP,
        explicit_pr=None,
    )

    result = TargetResolver(transport, policy).resolve(ident)

    assert target_numbers(result) == (2,)
    assert result.complete is True


def test_target_resolver_sweep_marks_incomplete_when_target_cap_truncates():
    transport = ScriptedTransport()
    transport.list_map[
        "/repos/Apeloff1/Skeleton/pulls?state=open&sort=updated&direction=asc"
    ] = (
        [
            pr_payload(number=1, base_ref="main", head_ref="feature/1"),
            pr_payload(number=2, base_ref="main", head_ref="feature/2"),
        ],
        True,
    )
    policy = replace(
        runner_policy(),
        limits=replace(runner_policy().limits, max_targets=1),
    )
    ident = identity(
        trigger=RunTrigger.MANUAL_SWEEP,
        explicit_pr=None,
    )

    result = TargetResolver(transport, policy).resolve(ident)

    assert target_numbers(result) == (1,)
    assert result.complete is False


def test_target_resolver_sweep_preserves_incomplete_pagination_at_exact_cap():
    transport = ScriptedTransport()
    transport.list_map[
        "/repos/Apeloff1/Skeleton/pulls?state=open&sort=updated&direction=asc"
    ] = (
        [pr_payload(number=1, base_ref="main", head_ref="feature/1")],
        False,
    )
    policy = replace(
        runner_policy(),
        limits=replace(runner_policy().limits, max_targets=1),
    )
    ident = identity(
        trigger=RunTrigger.MANUAL_SWEEP,
        explicit_pr=None,
    )

    result = TargetResolver(transport, policy).resolve(ident)

    assert target_numbers(result) == (1,)
    assert result.complete is False


def test_target_resolver_workflow_hint_requires_exact_identity():
    transport = ScriptedTransport()
    transport.get_map["/repos/Apeloff1/Skeleton/pulls/42"] = pr_payload(
        head_sha=SHA_B,
        head_ref="feature/x",
    )
    transport.list_map[
        f"/repos/Apeloff1/Skeleton/commits/{SHA_B}/pulls"
    ] = ([], True)
    ident = identity(
        trigger=RunTrigger.WORKFLOW_COMPLETION,
        explicit_pr=None,
        head_sha=SHA_B,
        head_ref="feature/x",
        hinted_prs=(42,),
    )
    result = TargetResolver(
        transport,
        runner_policy(),
    ).resolve(ident)
    assert target_numbers(result) == (42,)
    assert result.targets[0].hinted


def test_target_resolver_rejects_stale_hint():
    transport = ScriptedTransport()
    transport.get_map["/repos/Apeloff1/Skeleton/pulls/42"] = pr_payload(
        head_sha=SHA_A,
        head_ref="feature/x",
    )
    transport.list_map[
        f"/repos/Apeloff1/Skeleton/commits/{SHA_B}/pulls"
    ] = ([], True)
    transport.list_map[
        "/repos/Apeloff1/Skeleton/pulls?state=all&head=Apeloff1%3Afeature%2Fx&sort=updated&direction=desc"
    ] = ([], True)
    ident = identity(
        trigger=RunTrigger.WORKFLOW_COMPLETION,
        explicit_pr=None,
        head_sha=SHA_B,
        head_ref="feature/x",
        hinted_prs=(42,),
    )
    result = TargetResolver(
        transport,
        runner_policy(),
    ).resolve(ident)
    assert result.targets == ()


def test_target_resolver_commit_association():
    transport = ScriptedTransport()
    transport.list_map[
        f"/repos/Apeloff1/Skeleton/commits/{SHA_B}/pulls"
    ] = (
        [
            pr_payload(
                number=7,
                head_sha=SHA_B,
                head_ref="feature/x",
            )
        ],
        True,
    )
    ident = identity(
        trigger=RunTrigger.WORKFLOW_COMPLETION,
        explicit_pr=None,
        head_sha=SHA_B,
        head_ref="feature/x",
        hinted_prs=(),
    )
    result = TargetResolver(
        transport,
        runner_policy(),
    ).resolve(ident)
    assert target_numbers(result) == (7,)
    assert result.targets[0].associated_by_sha


def test_target_resolver_fails_on_incomplete_association():
    transport = ScriptedTransport()
    transport.list_map[
        f"/repos/Apeloff1/Skeleton/commits/{SHA_B}/pulls"
    ] = ([], False)
    ident = identity(
        trigger=RunTrigger.WORKFLOW_COMPLETION,
        explicit_pr=None,
        head_sha=SHA_B,
        head_ref="feature/x",
    )
    with pytest.raises(TargetingError, match="bounded"):
        TargetResolver(
            transport,
            runner_policy(),
        ).resolve(ident)


@pytest.mark.parametrize(
    "method_name",
    ["consume_request", "consume_graphql", "consume_mutation", "consume_target"],
)
def test_mutable_budget_rejects_fractional_consumption(method_name):
    budget = MutableBudget(make_budget(runner_policy(), started_at=NOW))
    with pytest.raises(ValueError, match="integer"):
        getattr(budget, method_name)(1.5)


def test_make_budget_uses_policy_limits():
    policy = runner_policy()
    budget = make_budget(policy, started_at=NOW)
    assert budget.request_limit == policy.limits.max_requests
    assert budget.mutation_limit == policy.limits.max_mutations
    assert not deadline_reached(budget, now=NOW)


def test_deadline_helpers():
    budget = RunBudget(
        request_limit=10,
        graphql_limit=10,
        mutation_limit=1,
        target_limit=2,
        deadline_at=(NOW + timedelta(seconds=30)).isoformat(),
    )
    assert deadline_remaining_seconds(budget, now=NOW) == 30
    assert deadline_reached(
        budget,
        now=NOW + timedelta(seconds=31),
    )


def test_mutable_budget_consumes_all_dimensions():
    mutable = MutableBudget(
        RunBudget(
            request_limit=10,
            graphql_limit=5,
            mutation_limit=2,
            target_limit=3,
            deadline_at=(NOW + timedelta(minutes=1)).isoformat(),
        )
    )
    mutable.consume_request(2)
    mutable.consume_graphql(1)
    mutable.consume_mutation(1)
    mutable.consume_target(1)
    assert mutable.value.request_used == 2
    assert mutable.value.graphql_used == 1
    assert mutable.value.mutations_used == 1
    assert mutable.value.targets_used == 1


def test_budget_target_blocks_insufficient_requests():
    budget = RunBudget(
        request_limit=5,
        graphql_limit=5,
        mutation_limit=1,
        target_limit=1,
        deadline_at=(NOW + timedelta(minutes=1)).isoformat(),
        request_used=4,
    )
    decision = budget_allows_target(
        budget,
        estimated_requests=2,
        estimated_graphql=0,
        now=NOW,
    )
    assert not decision.allowed
    assert "request_budget_insufficient" in decision.reasons


def test_budget_mutation_blocks_queue_pressure():
    budget = make_budget(runner_policy(), started_at=NOW)
    observation = observe_queue(
        queued_actions=41,
        rate_remaining=5000,
        now=NOW,
    )
    decision = budget_allows_mutation(
        budget,
        observation,
        runner_policy(),
        now=NOW,
    )
    assert not decision.allowed
    assert "queue_pressure" in decision.reasons


def test_budget_mutation_blocks_low_rate_limit():
    budget = make_budget(runner_policy(), started_at=NOW)
    observation = observe_queue(
        queued_actions=0,
        rate_remaining=1,
        now=NOW,
    )
    decision = budget_allows_mutation(
        budget,
        observation,
        runner_policy(),
        now=NOW,
    )
    assert not decision.allowed
    assert "rate_limit" in decision.reasons


def test_budget_mutation_blocks_unknown_rate_limit():
    budget = make_budget(runner_policy(), started_at=NOW)
    observation = observe_queue(
        queued_actions=0,
        rate_remaining=None,
        now=NOW,
    )
    decision = budget_allows_mutation(
        budget,
        observation,
        runner_policy(),
        now=NOW,
    )
    assert not decision.allowed
    assert "rate_limit_unknown" in decision.reasons


def test_evaluate_snapshot_ready():
    evaluation, reasons = evaluate_snapshot(
        snapshot(),
        runner_policy(),
    )
    assert evaluation.decision is Decision.MERGE
    assert reasons == ("all policy gates satisfied",)


def test_evaluate_snapshot_incomplete_holds():
    snap = replace(
        snapshot(),
        completeness=replace(
            snapshot().completeness,
            reviews=False,
        ),
    )
    evaluation, reasons = evaluate_snapshot(
        snap,
        runner_policy(),
    )
    assert evaluation.decision is Decision.HOLD
    assert "evidence_incomplete:reviews" in reasons


def test_evaluate_snapshot_denied_label_holds():
    snap = replace(
        snapshot(),
        labels=("automerge", "do-not-merge"),
    )
    evaluation, reasons = evaluate_snapshot(
        snap,
        runner_policy(),
    )
    assert evaluation.decision is Decision.HOLD
    assert any(reason.startswith("denied_label:") for reason in reasons)


def test_evaluate_snapshot_base_move_holds():
    snap = replace(snapshot(), base_head_sha=SHA_C)
    evaluation, reasons = evaluate_snapshot(
        snap,
        runner_policy(),
    )
    assert evaluation.decision is Decision.HOLD
    assert "base_head_mismatch" in reasons


def test_score_prioritizes_interactive_over_sweep():
    snap = snapshot()
    interactive = score_work_item(
        target(priority=PriorityBand.INTERACTIVE),
        snap,
        evaluate_snapshot(snap, runner_policy())[0],
        WorkState.READY,
        now=NOW,
    )
    sweep = score_work_item(
        target(priority=PriorityBand.SWEEP),
        snap,
        evaluate_snapshot(snap, runner_policy())[0],
        WorkState.READY,
        now=NOW,
    )
    assert interactive > sweep


def test_schedule_respects_target_budget():
    policy = runner_policy()
    observation = observe_queue(
        queued_actions=0,
        rate_remaining=5000,
        now=NOW,
    )
    one = build_work_item(
        target(number=1),
        replace(snapshot(), core=replace(core_snapshot(), number=1)),
        policy,
        observation,
        now=NOW,
    )
    two = build_work_item(
        target(number=2),
        replace(snapshot(), core=replace(core_snapshot(), number=2)),
        policy,
        observation,
        now=NOW,
    )
    budget = RunBudget(
        request_limit=100,
        graphql_limit=100,
        mutation_limit=2,
        target_limit=1,
        deadline_at=(NOW + timedelta(minutes=1)).isoformat(),
    )
    schedule = schedule_items((one, two), budget, policy, now=NOW)
    assert len(schedule.items) == 1
    assert len(schedule.deferred) == 1


def test_defer_item_accumulates_reason():
    policy = runner_policy()
    observation = observe_queue(
        queued_actions=0,
        rate_remaining=5000,
        now=NOW,
    )
    item = build_work_item(
        target(),
        snapshot(),
        policy,
        observation,
        now=NOW,
    )
    deferred = defer_item(item, ("budget",), now=NOW)
    assert deferred.state is WorkState.DEFERRED
    assert "budget" in deferred.reasons


def test_mutation_candidates_require_authority():
    policy = runner_policy()
    observation = observe_queue(
        queued_actions=0,
        rate_remaining=5000,
        now=NOW,
    )
    item = build_work_item(
        target(),
        snapshot(),
        policy,
        observation,
        now=NOW,
    )
    schedule = schedule_items(
        (item,),
        make_budget(policy, started_at=NOW),
        policy,
        now=NOW,
    )
    denied = replace(admission(), mutation_authorized=False)
    assert mutation_candidates(
        schedule,
        denied,
        policy,
        make_budget(policy, started_at=NOW),
        observation,
        now=NOW,
    ) == ()


def _transport(
    opener: RouteOpener,
    **limit_changes,
) -> BudgetedGitHubTransport:
    return BudgetedGitHubTransport(
        "token",
        limits(**limit_changes),
        opener=opener,
        sleeper=lambda _seconds: None,
        clock=lambda: NOW,
    )


def test_transport_get_records_success():
    opener = RouteOpener()
    opener.add(
        "GET",
        "https://api.github.com/repos/a/b",
        FakeResponse(
            {"ok": True},
            headers={"X-RateLimit-Remaining": "4999"},
        ),
    )
    transport = _transport(opener)
    assert transport.get("/repos/a/b") == {"ok": True}
    summary = transport.summary()
    assert summary.requests == 1
    assert summary.failures == 0
    assert summary.minimum_remaining_seen == 4999
    assert summary.records[0].outcome is RequestOutcome.SUCCESS


def test_transport_rejects_external_host():
    transport = _transport(RouteOpener())
    with pytest.raises(ValueError):
        transport.request("GET", "https://example.com/")


def test_transport_rejects_retry_safe_mutation():
    transport = _transport(RouteOpener())
    with pytest.raises(UnsafeMutationRetry):
        transport.put("/repos/a/b", {}, retry_safe=True)


def test_transport_request_budget():
    opener = RouteOpener()
    opener.add(
        "GET",
        "https://api.github.com/a",
        FakeResponse({}),
    )
    transport = _transport(opener, max_requests=1)
    transport.get("/a")
    with pytest.raises(RequestBudgetExceeded):
        transport.get("/a")


def test_transport_graphql_budget():
    opener = RouteOpener()
    opener.add(
        "POST",
        "https://api.github.com/graphql",
        FakeResponse({"data": {}}),
    )
    transport = _transport(
        opener,
        max_graphql_requests=1,
    )
    transport.graphql("query { viewer { login } }", {})
    with pytest.raises(GraphQLBudgetExceeded):
        transport.graphql("query { viewer { login } }", {})


def test_transport_response_size_bound():
    opener = RouteOpener()
    opener.add(
        "GET",
        "https://api.github.com/large",
        FakeResponse(b"x" * 101),
    )
    transport = _transport(
        opener,
        max_response_bytes=100,
    )
    with pytest.raises(ResponseTooLarge):
        transport.get("/large")


def _http_error(code: int, body: bytes = b"error", **headers: str) -> HTTPError:
    message = Message()
    for key, value in headers.items():
        message[key] = value
    return HTTPError(
        "https://api.github.com/test",
        code,
        "boom",
        message,
        __import__("io").BytesIO(body),
    )


def test_transport_retries_read_server_error():
    opener = RouteOpener()
    opener.add(
        "GET",
        "https://api.github.com/test",
        _http_error(503),
        FakeResponse({"ok": True}),
    )
    transport = _transport(opener)
    assert transport.get("/test") == {"ok": True}
    assert transport.summary().retries == 1


def test_transport_does_not_retry_mutation_server_error():
    opener = RouteOpener()
    opener.add(
        "PUT",
        "https://api.github.com/test",
        _http_error(503),
    )
    transport = _transport(opener)
    with pytest.raises(GitHubHTTPError) as caught:
        transport.put("/test", {"x": 1})
    assert caught.value.status_code == 503
    assert caught.value.definitive_mutation_rejection is False
    assert transport.summary().retries == 0


def test_transport_exposes_definitive_mutation_rejection():
    opener = RouteOpener()
    opener.add(
        "PUT",
        "https://api.github.com/test",
        _http_error(422, b'{"message":"Validation Failed"}'),
    )
    transport = _transport(opener)
    with pytest.raises(GitHubHTTPError) as caught:
        transport.put("/test", {"x": 1})
    assert caught.value.status_code == 422
    assert caught.value.definitive_mutation_rejection is True
    assert "Validation Failed" in caught.value.detail


def test_transport_rate_floor():
    opener = RouteOpener()
    opener.add(
        "GET",
        "https://api.github.com/test",
        FakeResponse(
            {},
            headers={"X-RateLimit-Remaining": "1"},
        ),
    )
    transport = _transport(opener, minimum_rate_remaining=10)
    transport.get("/test")
    with pytest.raises(RateLimitFloorReached):
        transport.ensure_rate_floor()


@pytest.mark.parametrize("method_name", ["paged_list", "paged_named_list"])
def test_transport_pagination_rejects_zero_page_bound(method_name):
    transport = _transport(RouteOpener())
    method = getattr(transport, method_name)
    with pytest.raises(ValueError, match="max_pages"):
        if method_name == "paged_list":
            method("/items", max_pages=0)
        else:
            method("/checks", "check_runs", max_pages=0)


def test_transport_paged_named_list_rejects_page_bound_over_limit():
    transport = _transport(RouteOpener(), max_pages=1)
    with pytest.raises(ValueError, match="max_pages"):
        transport.paged_named_list(
            "/checks",
            "check_runs",
            max_pages=2,
        )


@pytest.mark.parametrize("per_page", [0, 101])
def test_transport_paged_named_list_rejects_invalid_page_size(per_page):
    transport = _transport(RouteOpener())
    with pytest.raises(ValueError, match="per_page"):
        transport.paged_named_list(
            "/checks",
            "check_runs",
            per_page=per_page,
        )


def test_transport_paged_list_complete():
    opener = RouteOpener()
    opener.add(
        "GET",
        "https://api.github.com/items?per_page=100&page=1",
        FakeResponse([{"id": 1}]),
    )
    transport = _transport(opener)
    items, complete = transport.paged_list("/items")
    assert items == [{"id": 1}]
    assert complete


def test_transport_paged_list_incomplete_at_bound():
    opener = RouteOpener()
    opener.add(
        "GET",
        "https://api.github.com/items?per_page=1&page=1",
        FakeResponse([{"id": 1}]),
    )
    transport = _transport(opener, max_pages=1)
    items, complete = transport.paged_list(
        "/items",
        max_pages=1,
        per_page=1,
    )
    assert items == [{"id": 1}]
    assert not complete
