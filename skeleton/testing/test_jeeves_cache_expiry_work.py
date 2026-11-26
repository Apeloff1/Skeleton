"""Cache expiry work is bounded without relaxing existing cache semantics."""
import asyncio
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.inference.local import (
    CallableLocalModel, LocalInferenceEngine, LocalInferenceRequest,
    LocalInferenceResult, _CachedInference,
)


class CacheExpiryTests(unittest.TestCase):
    def setUp(self):
        self.engine=LocalInferenceEngine(CallableLocalModel(
            model_id="fixture",model_digest="a"*64,
            runner=lambda req,cancel:LocalInferenceResult("ok","fixture","a"*64,1,1)),
            cache_size=8, max_concurrency=1,max_queue_size=8)
        self.result=LocalInferenceResult("yes","fixture","a"*64,1,1)
        self.pressure=patch.object(self.engine,"_sample_pressure_locked")
        self.pressure.start()
        self.addCleanup(self.pressure.stop)

    def put(self,key,created,expires,size=1024):
        with self.engine._cache_lock:
            self.engine._cache[key]=_CachedInference(self.result,created,expires,size)
            self.engine._cache_bytes+=size
            self.engine._cache_next_expiry=min(self.engine._cache_next_expiry,expires)

    def sweep(self,now,force=False):
        with patch("skeleton.ai.runtime.inference.local.time.monotonic",return_value=now):
            self.engine._trim_cache(force=force)

    def test_many_requests_before_first_expiry_do_not_rescan(self):
        self.put("a",10,20)
        self.sweep(11)
        n=self.engine._cache_expiry_sweeps
        for _ in range(100):
            self.sweep(12)
        self.assertEqual(self.engine._cache_expiry_sweeps,n)
        self.assertIn("a",self.engine._cache)

    def test_expiry_boundary_evicts_and_updates_bytes(self):
        self.put("a",10,20)
        self.put("b",11,25)
        self.sweep(19)
        self.sweep(20)
        self.assertNotIn("a",self.engine._cache)
        self.assertIn("b",self.engine._cache)
        self.assertEqual(self.engine._cache_bytes,1024)
        self.assertEqual(self.engine._cache_expirations,1)

    def test_forced_trim_scans_even_before_expiry(self):
        self.put("a",10,20)
        self.sweep(11)
        previous=self.engine._cache_expiry_sweeps
        self.sweep(12,force=True)
        self.assertEqual(self.engine._cache_expiry_sweeps,previous+1)

    def test_byte_pressure_enforced_even_without_expiry_scan(self):
        self.put("a",10,20)
        self.sweep(11)
        n=self.engine._cache_expiry_sweeps
        with patch.object(self.engine,"_effective_cache_limit_locked",return_value=0):
            self.sweep(12)
        self.assertEqual(self.engine._cache_expiry_sweeps,n)
        self.assertFalse(self.engine._cache)
        self.assertEqual(self.engine._cache_bytes,0)

    def test_clear_resets_expiry_without_resurrecting_data(self):
        self.put("a",10,20)
        self.sweep(11)
        self.engine.maintain("clear_cache")
        self.assertFalse(self.engine._cache)
        self.assertEqual(self.engine._cache_next_expiry,float("inf"))

    def test_shorter_policy_invalidates_previous_expiry_schedule(self):
        self.put("a",10,100)
        self.sweep(11)
        with patch("skeleton.ai.runtime.inference.local.time.monotonic",return_value=40):
            self.engine.configure_serving({"cache_ttl_seconds":1})
        self.assertFalse(self.engine._cache)


if __name__=="__main__":
    unittest.main()
