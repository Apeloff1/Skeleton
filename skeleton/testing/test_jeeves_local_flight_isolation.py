"""Exercise real local scheduler with a synthetic, controlled blocking backend."""
import asyncio
import threading
import time
import unittest

from skeleton.ai.runtime.inference.local import (
    CallableLocalModel, LocalInferenceEngine, LocalInferenceRequest,
    LocalInferenceResult, LocalInferenceCancelled,
)
from skeleton.provider_runtime import ProviderPolicyError


class FlightIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.lock = threading.Lock()
        self.calls = 0

        def runner(request, cancel):
            with self.lock:
                self.calls += 1
            self.started.set()
            if not self.release.wait(5):
                raise RuntimeError("test worker release deadline")
            return LocalInferenceResult("ok","fixture","a"*64,1,1)

        self.engine = LocalInferenceEngine(CallableLocalModel(
            model_id="fixture",model_digest="a"*64,runner=runner),
            cache_size=0,max_concurrency=1,max_queue_size=8)
        # No live machine pressure claim; deterministic fixture policy.
        self.engine.configure_serving({"enabled":False})
        self.request=LocalInferenceRequest("hi",max_output_tokens=8)
        self.tasks=[]

    async def asyncTearDown(self):
        self.release.set()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        await self.engine.close()

    def generate(self, **kwargs):
        task=asyncio.create_task(self.engine.generate(self.request,scope_id="same",
                       tenant_scope_id="tenant",**kwargs))
        self.tasks.append(task)
        return task

    async def until(self, condition):
        for _ in range(300):
            if condition():
                return
            await asyncio.sleep(0.01)
        self.fail("scheduler state was not reached")

    def flights(self):
        with self.engine._cache_lock:
            return len(self.engine._singleflight)

    def waiters(self):
        with self.engine._cache_lock:
            return self.engine._singleflight_waiters

    async def test_same_authority_coalesces(self):
        one=self.generate()
        await self.until(self.started.is_set)
        two=self.generate()
        await self.until(lambda:self.waiters()==1)
        self.release.set()
        await asyncio.gather(one,two)
        self.assertEqual(self.calls,1)

    async def test_distinct_preemption_lineage_cannot_share_inflight(self):
        one=self.generate(preemption_scope_id="one")
        await self.until(self.started.is_set)
        two=self.generate(preemption_scope_id="two")
        await self.until(lambda:self.flights()==2)
        self.release.set()
        await asyncio.gather(one,two)
        self.assertEqual(self.calls,2)

    async def test_interactive_does_not_inherit_background_leader(self):
        one=self.generate(work_class="background")
        await self.until(self.started.is_set)
        two=self.generate(work_class="interactive")
        await self.until(lambda:self.flights()==2)
        self.release.set()
        # Foreground work may intentionally preempt an already running
        # background worker. The interactive result must not inherit that
        # cancellation or share the background leader's physical output.
        background, interactive = await asyncio.gather(one,two,return_exceptions=True)
        self.assertTrue(isinstance(background,(LocalInferenceResult,LocalInferenceCancelled)))
        self.assertIsInstance(interactive,LocalInferenceResult)
        self.assertEqual(interactive.text,"ok")
        self.assertEqual(self.calls,2)

    async def test_distinct_explicit_deadlines_cannot_share_leader_failure(self):
        now=time.monotonic()
        one=self.generate(deadline=now+10)
        await self.until(self.started.is_set)
        two=self.generate(deadline=now+20)
        await self.until(lambda:self.flights()==2)
        self.release.set()
        await asyncio.gather(one,two)
        self.assertEqual(self.calls,2)

    async def test_identical_explicit_deadline_still_deduplicates(self):
        deadline=time.monotonic()+10
        one=self.generate(deadline=deadline)
        await self.until(self.started.is_set)
        two=self.generate(deadline=deadline)
        await self.until(lambda:self.waiters()==1)
        self.release.set()
        await asyncio.gather(one,two)
        self.assertEqual(self.calls,1)

    async def test_clear_cache_separates_following_generation(self):
        one=self.generate()
        await self.until(self.started.is_set)
        self.engine.maintain("clear_cache")
        two=self.generate()
        await self.until(lambda:self.flights()==2)
        self.release.set()
        await asyncio.gather(one,two)
        self.assertEqual(self.calls,2)

    async def test_existing_follower_does_not_take_invalidated_result(self):
        one=self.generate()
        await self.until(self.started.is_set)
        two=self.generate()
        await self.until(lambda:self.waiters()==1)
        self.engine.maintain("clear_cache")
        self.release.set()
        await one
        with self.assertRaises(ProviderPolicyError):
            await two
        self.assertEqual(self.calls,1)


if __name__=="__main__":
    unittest.main()
