from dataclasses import replace

import pytest

from skeleton.inference.batching import (
    BatchPlan,
    ContinuousBatchScheduler,
    verify_batch_membership,
)
from skeleton.inference.session import InferenceContractError, ModelRequest


H = "a" * 64


def req(
    op: str,
    *,
    digest: str | None = None,
    provider: str = "p",
    model: str = "m",
    max_output_tokens: int = 64,
    deadline_ms: int = 100,
) -> ModelRequest:
    return ModelRequest(
        op,
        digest or (op.encode().hex().ljust(64, "0")[:64]),
        model,
        provider,
        max_output_tokens,
        deadline_ms,
    )


def test_full_compatible_batch_drains_deterministically():
    scheduler = ContinuousBatchScheduler(max_batch_size=2, max_wait_ms=50)
    a = req("a")
    b = req("b")
    scheduler.enqueue(b, enqueued_ms=10)
    scheduler.enqueue(a, enqueued_ms=10)

    groups = scheduler.drain_ready(now_ms=10)

    assert len(groups) == 1
    plan, requests = groups[0]
    assert tuple(r.operation_id for r in requests) == ("a", "b")
    assert verify_batch_membership(plan, requests)
    assert scheduler.queued == 0
    assert len(plan.plan_digest) == 64
    assert plan.authority_scope == "batch-plan-only"


def test_incompatible_provider_model_or_output_shape_never_mix():
    scheduler = ContinuousBatchScheduler(max_batch_size=4, max_wait_ms=0)
    requests = (
        req("a", provider="p1"),
        req("b", provider="p2"),
        req("c", model="m2"),
        req("d", max_output_tokens=128),
    )
    for item in requests:
        scheduler.enqueue(item, enqueued_ms=0)

    groups = scheduler.drain_ready(now_ms=0)

    assert len(groups) == 4
    assert all(len(group_requests) == 1 for _, group_requests in groups)
    assert {
        (plan.compatibility.provider, plan.compatibility.model, plan.compatibility.max_output_tokens)
        for plan, _ in groups
    } == {
        ("p1", "m", 64),
        ("p2", "m", 64),
        ("p", "m2", 64),
        ("p", "m", 128),
    }


def test_wait_budget_or_request_deadline_flushes_partial_batch():
    scheduler = ContinuousBatchScheduler(max_batch_size=8, max_wait_ms=50)
    request = req("a", deadline_ms=20)
    scheduler.enqueue(request, enqueued_ms=100)
    assert scheduler.drain_ready(now_ms=119) == ()
    groups = scheduler.drain_ready(now_ms=120)
    assert len(groups) == 1
    assert groups[0][1] == (request,)


def test_duplicate_identity_and_queue_overflow_fail_closed():
    scheduler = ContinuousBatchScheduler(max_batch_size=2, max_queue_size=1)
    a = req("a")
    scheduler.enqueue(a, enqueued_ms=0)
    with pytest.raises(InferenceContractError, match="capacity exceeded"):
        scheduler.enqueue(req("b"), enqueued_ms=0)

    scheduler = ContinuousBatchScheduler(max_batch_size=2, max_queue_size=4)
    scheduler.enqueue(a, enqueued_ms=0)
    with pytest.raises(InferenceContractError, match="duplicate queued operation"):
        scheduler.enqueue(replace(a, request_digest="b" * 64), enqueued_ms=0)
    with pytest.raises(InferenceContractError, match="duplicate queued request digest"):
        scheduler.enqueue(req("b", digest=a.request_digest), enqueued_ms=0)


def test_batch_membership_tamper_is_rejected():
    scheduler = ContinuousBatchScheduler(max_batch_size=2, max_wait_ms=0)
    a = req("a")
    b = req("b")
    scheduler.enqueue(a, enqueued_ms=0)
    scheduler.enqueue(b, enqueued_ms=0)
    plan, requests = scheduler.drain_ready(now_ms=0)[0]

    with pytest.raises(InferenceContractError, match="operation identity mismatch"):
        verify_batch_membership(plan, tuple(reversed(requests)))


def test_flush_all_preserves_compatibility_and_bounds():
    scheduler = ContinuousBatchScheduler(max_batch_size=2, max_wait_ms=999)
    for item in (req("c"), req("a"), req("b"), req("x", provider="other")):
        scheduler.enqueue(item, enqueued_ms=0)

    groups = scheduler.flush_all(now_ms=1)

    assert scheduler.queued == 0
    assert [tuple(r.operation_id for r in requests) for _, requests in groups] == [
        ("a", "b"),
        ("c",),
        ("x",),
    ]
    assert all(verify_batch_membership(plan, requests) for plan, requests in groups)


def test_batch_plan_cannot_escalate_authority():
    scheduler = ContinuousBatchScheduler(max_batch_size=1, max_wait_ms=0)
    request = req("a")
    scheduler.enqueue(request, enqueued_ms=0)
    plan, _ = scheduler.drain_ready(now_ms=0)[0]
    with pytest.raises(InferenceContractError, match="cannot grant inference authority"):
        BatchPlan(
            plan.compatibility,
            plan.operation_ids,
            plan.request_digests,
            plan.formed_at_ms,
            "execution",
        )


def test_clock_regression_is_rejected_before_drain():
    scheduler = ContinuousBatchScheduler(max_batch_size=8, max_wait_ms=10)
    scheduler.enqueue(req("a"), enqueued_ms=10)
    with pytest.raises(InferenceContractError, match="clock moved"):
        scheduler.drain_ready(now_ms=9)
