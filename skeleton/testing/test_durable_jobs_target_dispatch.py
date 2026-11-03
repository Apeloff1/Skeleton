"""A newly submitted request must never execute an older unrelated pending job."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from skeleton.ai.runtime.operational_ai.durable_jobs.case_oracle import (
    OWNER, make_spec, make_store,
)
from skeleton.ai.runtime.operational_ai.durable_jobs.bridge import NativeJobBridge


class StrictNativeServiceInterfaceFixture:
    def __init__(self):
        self.calls=[]
        self.actor=SimpleNamespace(
            tenant="tenant",user="user",model_digest="a"*64,tokenizer_digest="b"*64,
        )

    def turn(self,*,session,request_id,question):
        self.calls.append((session,request_id,question))
        return SimpleNamespace(
            session_id=session,request_id=request_id,model_digest="a"*64,
            tokenizer_digest="b"*64,text="Native interface fixture only.",
            prompt_tokens=2,generated_tokens=4,
        )


class TestTargetedNativeWork(unittest.TestCase):
    def setUp(self):
        self.store=make_store()
        self.store.submit(make_spec(name="old_job"),now_ms=1000)
        self.store.submit(make_spec(name="new_job",question="New question"),
                          now_ms=1000)

    def tearDown(self):
        self.store.db.close()

    def test_targeted_dispatch_only_new_request(self):
        service=StrictNativeServiceInterfaceFixture()
        clock=iter((1000,1100))
        result=NativeJobBridge(service,self.store).run_one(
            "worker",clock_ms=lambda:next(clock),target_job_id="new_job"
        )
        self.assertEqual(result.text,"Native interface fixture only.")
        self.assertEqual(len(service.calls),1)
        self.assertEqual(service.calls[0][1],"new_job")
        self.assertEqual(self.store.inspect("new_job",OWNER)["state"],"completed")
        self.assertEqual(self.store.inspect("old_job",OWNER)["state"],"pending")

    def test_nonexistent_target_never_calls_model(self):
        service=StrictNativeServiceInterfaceFixture()
        result=NativeJobBridge(service,self.store).run_one(
            "worker",clock_ms=lambda:1000,target_job_id="absent_job"
        )
        self.assertIsNone(result)
        self.assertEqual(service.calls,[])

    def test_original_spec_recoverable_without_mutation(self):
        saved=self.store.load_spec("new_job",OWNER)
        self.assertEqual(saved.question,"New question")
        self.assertEqual(saved.request_id,"new_job")
        self.assertEqual(self.store.inspect("new_job",OWNER)["state"],"pending")


if __name__=="__main__":
    unittest.main()
