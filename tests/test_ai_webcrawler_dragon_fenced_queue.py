"""Adversarial lease fencing tests for idle video digestion."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_fenced_queue import FencedDragonQueue
from skeleton.ai.webcrawler.dragon_proposal_store import DragonProposalStore
from skeleton.ai.webcrawler.dragon_video_discovery import VideoProposal


def prepared_queue():
    store = DragonProposalStore(sqlite3.connect(":memory:"))
    queue = FencedDragonQueue(store)
    proposal = VideoProposal(
        "item-1", "https://example.org/watch?v=1", "Example",
        "science interest", 1.0, ("science",), True,
    )
    store.enqueue("owner", (proposal,), now=10, consent=True)
    assert store.decide("owner", "item-1", approve=True, now=11, consent=True)
    return store, queue


def test_current_worker_can_complete_once():
    store, queue = prepared_queue()
    claim = queue.claim("owner", now=12, consent=True, lease_seconds=10)
    assert claim is not None
    assert queue.finish(claim, now=13, succeeded=True, consent=True)
    assert not queue.finish(claim, now=14, succeeded=True, consent=True)
    assert store.get("owner", "item-1").state == "completed"


def test_stale_worker_cannot_complete_after_reclaim():
    store, queue = prepared_queue()
    old = queue.claim("owner", now=12, consent=True, lease_seconds=10)
    replacement = queue.claim("owner", now=23, consent=True, lease_seconds=10)
    assert old.token != replacement.token
    assert not queue.finish(old, now=24, succeeded=True, consent=True)
    assert queue.finish(replacement, now=25, succeeded=True, consent=True)
    assert store.get("owner", "item-1").state == "completed"


def test_revoke_prevents_completion():
    store, queue = prepared_queue()
    claim = queue.claim("owner", now=12, consent=True)
    assert queue.revoke_owner("owner") == 1
    assert not queue.finish(claim, now=13, succeeded=True, consent=True)
    assert store.get("owner", "item-1").state == "leased"


def test_consent_required_for_claim_and_finish():
    _, queue = prepared_queue()
    with pytest.raises(PermissionError):
        queue.claim("owner", now=12, consent=False)
    claim = queue.claim("owner", now=12, consent=True)
    with pytest.raises(PermissionError):
        queue.finish(claim, now=13, succeeded=True, consent=False)


def test_expired_claim_cannot_finish():
    store, queue = prepared_queue()
    claim = queue.claim("owner", now=12, consent=True, lease_seconds=2)
    assert not queue.finish(claim, now=14, succeeded=True, consent=True)
    assert store.get("owner", "item-1").state == "leased"
