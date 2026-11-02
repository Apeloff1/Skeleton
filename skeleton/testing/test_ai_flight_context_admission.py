"""Queued-inference context preflight and replay custody under actual SQLite."""
from __future__ import annotations
import hashlib, tempfile, unittest
from pathlib import Path
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import (
    SpineDatabase,ExecutionSpine,Identity,SpineLimits,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import SpineError
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.ledger import FlightLedger
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.driver import NativeFlightWorker
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.operator import FlightOperator
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.production import FlightApplication
from skeleton.ai.runtime.operational_ai.transport.flight.dispatch import FlightDispatcher
from skeleton.ai.runtime.operational_ai.model.native import Generated
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.context import Evidence

I=Identity('tenant','owner','a'*64,'b'*64)

class Backend:
    model_digest=I.model_sha256
    tokenizer_digest=I.tokenizer_sha256
    def __init__(self):self.calls=0;self.tokens=None
    def count_tokens(self,messages):return self.tokens if self.tokens is not None else 45
    def generate(self,messages,*,max_output_tokens,seed,temperature):
        self.calls+=1
        text='Fixture output'
        return Generated(text,45,5,hashlib.sha256(text.encode()).hexdigest(),
                         self.model_digest,self.tokenizer_digest,'stop')

class FlightCapacityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/home/oai/.cache')
        state=Path(self.temp.name)/'private';state.mkdir(mode=0o700)
        lock=state/'locks';lock.mkdir(mode=0o700)
        self.db=SpineDatabase(state);self.gate=SessionGate(lock)
        self.backend=Backend()
        self.spine=ExecutionSpine(db=self.db,session_gate=self.gate,
            backend=self.backend,identity=I,
            limits=SpineLimits(max_output_tokens=64,context_tokens=512,deadline_ms=2000))
        self.spine.create('chat')
        self.ledger=FlightLedger(self.db,I)
        worker=NativeFlightWorker(self.ledger,self.spine,'worker')
        app=FlightApplication(self.spine,self.ledger,worker,FlightOperator(self.ledger,self.spine))
        self.dispatcher=FlightDispatcher(app)
    def tearDown(self):self.gate.close();self.db.close();self.temp.cleanup()
    def submit(self,question='Hello',job='job1',request='req1'):
        return self.dispatcher.dispatch('submit',dict(job_id=job,session_id='chat',
                                    request_id=request,question=question))
    def jobs(self):
        with self.db.snapshot() as c:return c.execute('SELECT COUNT(*) FROM ai_flight_jobs').fetchone()[0]

    def test_valid_submit_only_preflights_without_inference(self):
        answer=self.submit()
        self.assertEqual(self.jobs(),1)
        self.assertEqual(self.backend.calls,0)
        self.assertEqual(answer['preflight']['status'],
            'new-job-context-preflight-admitted-not-execution-attestation')

    def test_exact_token_overflow_does_not_poison_queue(self):
        self.backend.tokens=999999
        with self.assertRaisesRegex(SpineError,'cannot fit'):
            self.submit()
        self.assertEqual(self.jobs(),0)
        self.backend.tokens=45
        self.assertEqual(self.submit()['job']['state'],'queued')

    def test_duplicate_job_replays_even_when_precount_changes(self):
        self.submit()
        self.backend.tokens=999999
        replay=self.submit()
        self.assertTrue(replay['job']['replayed'])
        self.assertEqual(replay['preflight']['status'],'existing-job-verify-with-ledger')
        self.assertEqual(self.jobs(),1)

    def test_source_principal_mismatch_holds_before_queue(self):
        def sources(identity,prompt):
            value='Not authorized'
            return [Evidence('source1',1,value,hashlib.sha256(value.encode()).hexdigest(),
                              'foreign','owner')]
        self.spine.evidence_provider=sources
        with self.assertRaisesRegex(SpineError,'principal'):
            self.submit()
        self.assertEqual(self.jobs(),0)

    def test_submitted_model_work_remains_independent(self):
        self.submit()
        outcome=self.dispatcher.dispatch('work_one',{})
        self.assertEqual(outcome['status'],'completed')
        self.assertEqual(self.backend.calls,1)
        self.assertEqual(self.submit()['job']['state'],'completed')
        self.assertEqual(self.backend.calls,1)

    def test_private_prompt_not_returned_in_preflight(self):
        text='SECRET_PRIVATE_PROMPT_TOKEN'
        answer=self.submit(question=text)
        self.assertNotIn(text,str(answer['preflight']))
        self.assertNotIn(text,answer['preflight']['context_sha256'])

if __name__=='__main__':unittest.main()
