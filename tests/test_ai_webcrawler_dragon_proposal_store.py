"""Regression tests for the durable dragon video proposal queue."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_proposal_store import DragonProposalStore
from skeleton.ai.webcrawler.dragon_video_discovery import VideoProposal


def proposal(key="one"):
    return VideoProposal(key, f"https://example.org/watch?v={key}",
                         f"Video {key}", "Related topic", 1.5, ("science",), True)


def store():
    return DragonProposalStore(sqlite3.connect(":memory:"))


def test_enqueue_requires_consent_and_is_idempotent():
    queue = store()
    with pytest.raises(PermissionError):
        queue.enqueue("owner", (proposal(),), now=100, consent=False)
    assert queue.enqueue("owner", (proposal(),), now=100, consent=True) == 1
    assert queue.enqueue("owner", (proposal(),), now=100, consent=True) == 0
    assert queue.get("owner", "one").state == "pending"


def test_rejected_proposals_cannot_be_claimed():
    queue = store()
    queue.enqueue("owner", (proposal(),), now=100, consent=True)
    assert queue.decide("owner", "one", approve=False, now=101, consent=True)
    assert queue.claim("owner", now=102, consent=True) is None
    assert queue.get("owner", "one").state == "rejected"


def test_claim_requires_approval_and_digestion_consent():
    queue = store()
    queue.enqueue("owner", (proposal(),), now=100, consent=True)
    assert queue.claim("owner", now=101, consent=True) is None
    queue.decide("owner", "one", approve=True, now=102, consent=True)
    with pytest.raises(PermissionError):
        queue.claim("owner", now=103, consent=False)
    claimed = queue.claim("owner", now=103, consent=True)
    assert claimed.state == "leased"
    assert claimed.attempts == 1
    assert queue.claim("owner", now=104, consent=True) is None


def test_expired_lease_can_be_reclaimed():
    queue = store()
    queue.enqueue("owner", (proposal(),), now=100, consent=True)
    queue.decide("owner", "one", approve=True, now=101, consent=True)
    queue.claim("owner", now=102, lease_seconds=10, consent=True)
    assert queue.claim("owner", now=111, consent=True) is None
    again = queue.claim("owner", now=113, consent=True)
    assert again.attempts == 2
    assert queue.finish("owner", "one", now=114, succeeded=True, consent=True)
    assert queue.get("owner", "one").state == "completed"


def test_failed_work_returns_to_approved_queue():
    queue = store()
    queue.enqueue("owner", (proposal(),), now=100, consent=True)
    queue.decide("owner", "one", approve=True, now=101, consent=True)
    queue.claim("owner", now=102, consent=True)
    assert queue.finish("owner", "one", now=103, succeeded=False, consent=True)
    assert queue.get("owner", "one").state == "approved"


def test_owner_isolation_and_erasure():
    queue = store()
    queue.enqueue("alice", (proposal(),), now=100, consent=True)
    queue.enqueue("bob", (proposal(),), now=100, consent=True)
    assert not queue.decide("bob", "missing", approve=True, now=101, consent=True)
    assert queue.erase("alice") == 1
    assert queue.get("alice", "one") is None
    assert queue.get("bob", "one") is not None


def test_queue_capacity_and_invalid_leases():
    queue = store()
    queue.enqueue("owner", (proposal("one"),), now=100, consent=True)
    with pytest.raises(ValueError, match="capacity"):
        queue.enqueue("owner", (proposal("two"),), now=101,
                      consent=True, max_pending=1)
    queue.decide("owner", "one", approve=True, now=102, consent=True)
    with pytest.raises(ValueError):
        queue.claim("owner", now=103, lease_seconds=float("nan"), consent=True)
