"""Functional, isolated work-order SQLite test harness; no real GGUF claim."""
from __future__ import annotations
import os
import tempfile
import unittest
from dataclasses import replace
from skeleton.testing.laptop_runtime_test_support import FakeWorker
from skeleton.ai.runtime.operational_ai.work_orders import WorkOrder,WorkOrderStore,WorkOrderExecutor

class QueueCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.state_dir=os.path.join(self.tmp.name,"private_state")
        os.mkdir(self.state_dir,0o700)
        self.addCleanup(self.tmp.cleanup)
        self.worker=FakeWorker()
        self.worker.spine.create("session")
        self.prompt="hello"
        self.order=WorkOrder.bind(job_id="job",tenant="local",subject="owner",
            model_sha256="a"*64,tokenizer_sha256="b"*64,
            session_id="session",request_id="request",prompt_text=self.prompt,
            max_output_tokens=64)
        self.store=WorkOrderStore(self.state_dir,clock=lambda:100000)
        self.store.configure_budget("local",ceiling=10000,operator_approved=True)
        self.executor=WorkOrderExecutor(self.store,self.worker)
        self.addCleanup(lambda:self.store.close())

    def other_order(self,**updates):
        values=dict(job_id="job",tenant="local",subject="owner",
            model_sha256="a"*64,tokenizer_sha256="b"*64,
            session_id="session",request_id="request",prompt_text=self.prompt,
            seed=0,sampler_temperature=0.8,max_output_tokens=64)
        values.update(updates)
        return WorkOrder.bind(**values)
