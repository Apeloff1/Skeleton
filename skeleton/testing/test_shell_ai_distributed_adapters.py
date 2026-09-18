"""Distributed policy, session, and human-review adapter tests."""

from __future__ import annotations

import pytest

from skeleton.shells.ai.checkpoint import AISessionCheckpoint
from skeleton.shells.ai.distributed_policy import DistributedAIPolicyStore
from skeleton.shells.ai.distributed_review import DistributedAIReviewQueue
from skeleton.shells.ai.distributed_session import DistributedAISessionStore
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.policy_store import AIPolicyConflict
from skeleton.shells.ai.review import AIReviewView, ReviewAction
from skeleton.shells.ai.review_queue import ReviewQueueConflict, ReviewState
from skeleton.shells.ai.session_store import AISessionConflict


def fp(char):
    return char * 64


def checkpoint(receipt="b"):
    return AISessionCheckpoint(
        1,
        "session",
        "review",
        "intent",
        fp("a"),
        "proposal",
        fp("p"),
        3,
        fp("j"),
        fp(receipt),
        fp("c"),
        fp("d"),
        fp("e"),
    )


def review():
    return AIReviewView(
        intent_id="i",
        goal="inspect",
        proposal_id="p",
        proposal_fingerprint=fp("p"),
        model_id="m",
        confidence=0.9,
        uncertainty=0.1,
        risk_score=5,
        risk_band="low",
        requires_approval=True,
        policy_reasons=("human approval required",),
        guardrail_findings=(),
        assumptions=(),
        actions=(
            ReviewAction(
                "a",
                "python",
                ("-V",),
                None,
                (),
                1,
                ("read_filesystem",),
                True,
                "",
                (),
                False,
            ),
        ),
    )


def test_distributed_policy_initializes_once():
    backend = InMemoryFencedStore()
    first = DistributedAIPolicyStore(
        backend,
        AIShellPolicy(max_actions=31),
    )
    second = DistributedAIPolicyStore(
        backend,
        AIShellPolicy(max_actions=10),
    )
    assert first.current().policy.max_actions == 31
    assert second.current().policy.max_actions == 31


def test_distributed_policy_revision_uses_backend_revision():
    backend = InMemoryFencedStore()
    store = DistributedAIPolicyStore(backend)
    assert store.current().revision == 1
    updated = store.replace(AIShellPolicy(max_actions=31))
    assert updated.revision == 2
    assert store.current().policy.max_actions == 31


def test_distributed_policy_cas_conflict_across_instances():
    backend = InMemoryFencedStore()
    left = DistributedAIPolicyStore(backend)
    right = DistributedAIPolicyStore(backend)
    revision = left.current()
    left.compare_and_swap(
        revision.revision,
        AIShellPolicy(max_actions=31),
    )
    with pytest.raises(AIPolicyConflict):
        right.compare_and_swap(
            revision.revision,
            AIShellPolicy(max_actions=30),
        )


def test_distributed_policy_fingerprint_updates():
    backend = InMemoryFencedStore()
    store = DistributedAIPolicyStore(backend)
    before = store.current().fingerprint
    after = store.replace(
        AIShellPolicy(autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS)
    ).fingerprint
    assert before != after


def test_distributed_session_first_put():
    backend = InMemoryFencedStore()
    store = DistributedAISessionStore(backend)
    stored = store.put(checkpoint())
    assert stored.revision == 1
    assert stored.checkpoint == checkpoint()


def test_distributed_session_identical_put_is_idempotent():
    backend = InMemoryFencedStore()
    store = DistributedAISessionStore(backend)
    first = store.put(checkpoint())
    second = store.put(checkpoint())
    assert first.revision == second.revision == 1


def test_distributed_session_update_increments_revision():
    backend = InMemoryFencedStore()
    store = DistributedAISessionStore(backend)
    store.put(checkpoint())
    updated = store.put(checkpoint("9"), expected_revision=1)
    assert updated.revision == 2
    assert store.current("session").checkpoint.receipt_root == fp("9")


def test_distributed_session_stale_writer_conflict():
    backend = InMemoryFencedStore()
    left = DistributedAISessionStore(backend)
    right = DistributedAISessionStore(backend)
    left.put(checkpoint())
    left.put(checkpoint("8"), expected_revision=1)
    with pytest.raises(AISessionConflict):
        right.put(checkpoint("9"), expected_revision=1)


def test_distributed_session_missing_expected_revision_conflict():
    backend = InMemoryFencedStore()
    store = DistributedAISessionStore(backend)
    with pytest.raises(AISessionConflict):
        store.put(checkpoint(), expected_revision=4)


def test_distributed_review_enqueue_pending():
    now = [0.0]
    backend = InMemoryFencedStore(clock=lambda: now[0])
    queue = DistributedAIReviewQueue(backend, clock=lambda: now[0])
    item = queue.enqueue(review(), ttl_seconds=10)
    assert item.state is ReviewState.PENDING
    assert item.expires_at == 10


def test_distributed_review_claim_uses_fencing_token():
    backend = InMemoryFencedStore()
    queue = DistributedAIReviewQueue(backend)
    item = queue.enqueue(review())
    claim = queue.claim(item.item_id, "alice")
    assert claim.fencing_token == 1
    assert queue.get(item.item_id).state is ReviewState.CLAIMED
    assert queue.get(item.item_id).reviewer == "alice"


def test_distributed_review_second_reviewer_blocked():
    backend = InMemoryFencedStore()
    queue = DistributedAIReviewQueue(backend)
    item = queue.enqueue(review())
    queue.claim(item.item_id, "alice")
    with pytest.raises(ReviewQueueConflict):
        queue.claim(item.item_id, "bob")


def test_distributed_review_decision_requires_live_fence():
    now = [0.0]
    backend = InMemoryFencedStore(clock=lambda: now[0])
    queue = DistributedAIReviewQueue(backend, clock=lambda: now[0])
    item = queue.enqueue(review(), ttl_seconds=100)
    claim = queue.claim(item.item_id, "alice", ttl_seconds=1)
    now[0] = 1
    with pytest.raises(Exception):
        queue.decide(claim, approve=True)


def test_distributed_review_approve_releases_lease():
    backend = InMemoryFencedStore()
    queue = DistributedAIReviewQueue(backend)
    item = queue.enqueue(review())
    claim = queue.claim(item.item_id, "alice")
    decided = queue.decide(
        claim,
        approve=True,
        reason="checked",
    )
    assert decided.state is ReviewState.APPROVED
    assert decided.reason == "checked"
    assert backend.leases() == ()


def test_distributed_review_reject():
    backend = InMemoryFencedStore()
    queue = DistributedAIReviewQueue(backend)
    item = queue.enqueue(review())
    claim = queue.claim(item.item_id, "alice")
    decided = queue.decide(claim, approve=False, reason="unsafe")
    assert decided.state is ReviewState.REJECTED
    assert decided.reason == "unsafe"


def test_distributed_review_expiry():
    now = [0.0]
    backend = InMemoryFencedStore(clock=lambda: now[0])
    queue = DistributedAIReviewQueue(backend, clock=lambda: now[0])
    item = queue.enqueue(review(), ttl_seconds=1)
    now[0] = 1
    assert queue.get(item.item_id).state is ReviewState.EXPIRED


def test_distributed_review_expired_cannot_claim():
    now = [0.0]
    backend = InMemoryFencedStore(clock=lambda: now[0])
    queue = DistributedAIReviewQueue(backend, clock=lambda: now[0])
    item = queue.enqueue(review(), ttl_seconds=1)
    now[0] = 1
    with pytest.raises(ReviewQueueConflict):
        queue.claim(item.item_id, "alice")


def test_distributed_review_stale_claim_cannot_decide_after_reacquire():
    now = [0.0]
    backend = InMemoryFencedStore(clock=lambda: now[0])
    queue = DistributedAIReviewQueue(backend, clock=lambda: now[0])
    item = queue.enqueue(review(), ttl_seconds=100)
    first = queue.claim(item.item_id, "alice", ttl_seconds=1)
    now[0] = 1
    # Reset review state to pending simulates an operator-side retry after the
    # stale claim is observed. The new lease receives a larger fencing token.
    current = backend.get(queue.namespace, item.item_id)
    from skeleton.shells.ai.distributed_review import DistributedReviewRecord

    backend.compare_and_swap(
        queue.namespace,
        item.item_id,
        expected_revision=current.revision,
        value=DistributedReviewRecord(
            item.item_id,
            item.review,
            ReviewState.PENDING,
            expires_at=item.expires_at,
        ),
    )
    second = queue.claim(item.item_id, "bob", ttl_seconds=10)
    assert second.fencing_token > first.fencing_token
    with pytest.raises(Exception):
        queue.decide(first, approve=True)
    assert queue.decide(second, approve=True).state is ReviewState.APPROVED


def test_distributed_review_same_timestamp_still_gets_unique_ids():
    now = [0.0]
    backend = InMemoryFencedStore(clock=lambda: now[0])
    queue = DistributedAIReviewQueue(backend, clock=lambda: now[0])
    first = queue.enqueue(review())
    second = queue.enqueue(review())
    assert first.item_id != second.item_id
