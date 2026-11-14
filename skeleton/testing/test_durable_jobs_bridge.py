"""Native service interface injection; no fixture is offered as production LLM."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from skeleton.ai.runtime.operational_ai.durable_jobs.bridge import NativeJobBridge
from skeleton.ai.runtime.operational_ai.durable_jobs.case_oracle import (
    OWNER, make_spec, make_store,
)
from skeleton.ai.runtime.operational_ai.durable_jobs.errors import JobDenied

MODEL="a"*64
TOK="b"*64


class NativeServiceFixture:
    def __init__(self,*,throws=False,wrong_identity=False):
        self.actor=SimpleNamespace(tenant="tenant",user="user",
                                   model_digest=MODEL,tokenizer_digest=TOK)
        self.calls=[]
        self.throws=throws
        self.wrong_identity=wrong_identity

    def turn(self,*,session,request_id,question):
        self.calls.append((session,request_id,question))
        if self.throws:
            raise RuntimeError("simulated transport loss, not a model response")
        return SimpleNamespace(
            session_id="wrong" if self.wrong_identity else session,
            request_id=request_id,model_digest=MODEL,tokenizer_digest=TOK,
            text="Fixture native service interface only.",
            prompt_tokens=14,generated_tokens=7,
        )


class TestNativeJobBridge(unittest.TestCase):
    def setUp(self):
        self.store=make_store()
        self.store.submit(make_spec(),now_ms=1000)

    def tearDown(self):
        self.store.db.close()

    def test_real_service_turn_interface_is_called_once(self):
        service=NativeServiceFixture()
        bridge=NativeJobBridge(service,self.store)
        times=iter((1000,1200))
        result=bridge.run_one("worker",clock_ms=lambda:next(times))
        self.assertEqual(service.calls,[("session","job_1","Explain this text.")])
        self.assertEqual(self.store.inspect("job_1",OWNER)["state"],"completed")
        self.assertEqual(result.text,"Fixture native service interface only.")

    def test_failure_is_held_no_fallback(self):
        service=NativeServiceFixture(throws=True)
        bridge=NativeJobBridge(service,self.store)
        times=iter((1000,1200,1200))
        with self.assertRaises(RuntimeError):
            bridge.run_one("worker",clock_ms=lambda:next(times))
        self.assertEqual(self.store.inspect("job_1",OWNER)["state"],"held")
        self.assertEqual(len(service.calls),1)

    def test_wrong_result_identity_held(self):
        service=NativeServiceFixture(wrong_identity=True)
        bridge=NativeJobBridge(service,self.store)
        times=iter((1000,1200))
        with self.assertRaises(JobDenied):
            bridge.run_one("worker",clock_ms=lambda:next(times))
        self.assertEqual(self.store.inspect("job_1",OWNER)["state"],"held")

    def test_missing_clock_never_starts_generation(self):
        service=NativeServiceFixture()
        bridge=NativeJobBridge(service,self.store)
        with self.assertRaises(JobDenied):
            bridge.run_one("worker",clock_ms=None)
        self.assertEqual(service.calls,[])


if __name__=="__main__":
    unittest.main()
