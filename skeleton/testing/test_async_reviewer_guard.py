"""Verify async reviewer admission never takes a blocking thread slot."""
import asyncio
from types import SimpleNamespace
import pytest
from skeleton.context.pre_delivery_guard import GuardedLocalInference, ReviewVerdict
from skeleton.context.sealed_sandwich import SealedContextBoundaryError


def test_async_only_review_timeout_and_slot_recovery():
    async def run():
        def sync_reviewer(*a):
            pytest.fail("signed reviewer was dispatched synchronously")
        entered = asyncio.Event()
        stopped = asyncio.Event()
        async def slow(*a):
            entered.set()
            try:
                await asyncio.sleep(10)
            finally:
                stopped.set()
        guard = GuardedLocalInference(SimpleNamespace(generate=lambda: None), reviewer=sync_reviewer,
                                      review_async=slow)
        evidence = SimpleNamespace(untrusted_text="source", untrusted_sha256="a"*64)
        with pytest.raises(SealedContextBoundaryError, match="timed out"):
            await guard._bounded_review(evidence, 0.03)
        assert entered.is_set() and stopped.is_set()
        async def healthy(text, digest):
            return ReviewVerdict(True,digest,"reviewer","allow")
        guard._review_async = healthy
        who, result = await guard._bounded_review(evidence, 1)
        assert who is sync_reviewer and result.allowed is True
    asyncio.run(run())


def test_async_review_cancel_releases_only_own_slot():
    async def run():
        entered = asyncio.Event()
        async def wait(*a):
            entered.set()
            await asyncio.sleep(10)
        guard = GuardedLocalInference(SimpleNamespace(generate=lambda: None),
                                      reviewer=lambda *a: None, review_async=wait)
        evidence = SimpleNamespace(untrusted_text="source", untrusted_sha256="a"*64)
        task = asyncio.create_task(guard._bounded_review(evidence, 5))
        await asyncio.wait_for(entered.wait(), 1)
        with pytest.raises(SealedContextBoundaryError, match="busy"):
            await guard._bounded_review(evidence, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert guard._review_slot.acquire(blocking=False)
        guard._review_slot.release()
    asyncio.run(run())
