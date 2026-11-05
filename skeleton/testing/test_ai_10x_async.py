"""Durable async call scheduling, dedupe and restart quarantine without fake model claims."""
from __future__ import annotations
import time,unittest
from skeleton.ai.runtime.operational_ai.persistence.durable.database import DurableDatabase,DurableError
from skeleton.ai.runtime.operational_ai.orchestration.async_service.executor import AsyncAIExecutor
from skeleton.ai.runtime.operational_ai.orchestration.async_service.recovery import diagnose_incomplete

class TestActor:tenant='tenant';user='owner'
class TestOnlyService:
    actor=TestActor()
    def __init__(self):self.calls=0
    def turn(self,*,session,request_id,question,seed,temperature):
        self.calls+=1
        class Receipt:
            def to_record(self):return {'text':'test-fixture-only','id':request_id}
        return Receipt()

class TestAsync(unittest.TestCase):
    def test_submitted_work_has_durable_receipt(self):
        with DurableDatabase() as db:
            svc=TestOnlyService()
            with AsyncAIExecutor(svc,db,workers=1) as engine:
                accepted=engine.submit(session='session',request_id='req1',question='hello')
                self.assertEqual(accepted.state,'admitted')
            finished=engine.get('req1')
            self.assertEqual(finished.state,'succeeded')
            self.assertEqual(svc.calls,1)
            self.assertFalse(diagnose_incomplete(db,tenant='tenant',owner='owner'))

    def test_same_request_is_idempotent(self):
        with DurableDatabase() as db:
            svc=TestOnlyService()
            with AsyncAIExecutor(svc,db,workers=1) as engine:
                engine.submit(session='session',request_id='req1',question='hello')
                engine.submit(session='session',request_id='req1',question='hello')
            self.assertEqual(svc.calls,1)

    def test_conflicting_id_denied(self):
        with DurableDatabase() as db:
            svc=TestOnlyService()
            with AsyncAIExecutor(svc,db,workers=1) as engine:
                engine.submit(session='session',request_id='req1',question='hello')
                with self.assertRaises(DurableError):
                    engine.submit(session='session',request_id='req1',question='different')

if __name__=='__main__':unittest.main()
