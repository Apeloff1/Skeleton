"""SQLite integration: overbudget input never reserves an inference request."""
import hashlib,tempfile,unittest
from pathlib import Path
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import (
    SpineDatabase,ExecutionSpine,Identity,SpineLimits,SpineError,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Busy, Conflict
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.context import Evidence
from skeleton.ai.runtime.operational_ai.model.native import Generated
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.capacity.replay import from_receipt

I=Identity('team','owner','a'*64,'b'*64)

class Backend:
    model_digest=I.model_sha256
    tokenizer_digest=I.tokenizer_sha256
    def __init__(self):self.calls=0;self.count_override=None
    def count_tokens(self,messages):
        if self.count_override is not None:return self.count_override
        return 45  # Exactly the fixture's native prompt-token accounting
    def generate(self,messages,*,max_output_tokens,seed,temperature):
        self.calls+=1
        text='Original native fixture result '+str(self.calls)
        return Generated(text,45,12,hashlib.sha256(text.encode()).hexdigest(),
                         self.model_digest,self.tokenizer_digest,'stop')

class CapacityIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        state=Path(self.tmp.name)/'private';state.mkdir(mode=0o700)
        lock=state/'lock';lock.mkdir(mode=0o700)
        self.db=SpineDatabase(state);self.gate=SessionGate(lock)
        self.backend=Backend()
        self.limits=SpineLimits(max_output_tokens=64,context_tokens=512,deadline_ms=2000)
        self.spine=ExecutionSpine(db=self.db,session_gate=self.gate,
                    backend=self.backend,identity=I,limits=self.limits)
        self.spine.create('session')
    def tearDown(self):self.gate.close();self.db.close();self.tmp.cleanup()
    def count(self,table):
        with self.db.snapshot() as db:return db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]

    def test_exact_overflow_no_stranded_pending(self):
        self.backend.count_override=999999
        with self.assertRaisesRegex(SpineError,'cannot fit'):
            self.spine.turn('session','r1','Hello')
        self.assertEqual(self.count('requests'),0)
        self.assertEqual(self.count('turns'),0)
        self.assertEqual(self.backend.calls,0)
        self.backend.count_override=45
        self.assertFalse(self.spine.turn('session','r1','Hello')['replayed'])
        self.assertEqual(self.count('requests'),1)

    def test_malformed_evidence_no_stranded_pending(self):
        self.spine.evidence_provider=lambda identity,prompt:(Evidence('bad',1,'text',
            hashlib.sha256(b'text').hexdigest(),'other','owner'),)
        with self.assertRaisesRegex(SpineError,'principal'):
            self.spine.turn('session','r1','Hello')
        self.assertEqual(self.count('requests'),0)

    def test_preflight_receipt_is_atomic_and_replayable(self):
        result=self.spine.turn('session','r1','Hello')
        self.assertIn('context_capacity',result)
        self.assertEqual(from_receipt(result)['status'],
                         'integrity-bound-context-decision-not-release-certification')
        with self.db.snapshot() as db:
            self.assertGreaterEqual(db.execute('SELECT COUNT(*) FROM chain').fetchone()[0],2)
        again=self.spine.turn('session','r1','Hello')
        self.assertEqual(self.backend.calls,1)
        self.assertTrue(again['replayed'])
        self.assertEqual(result['context_capacity'],again['context_capacity'])

    def test_overlong_prompt_no_request(self):
        with self.assertRaises(SpineError):
            self.spine.turn('session','r1','x'*(self.limits.input_bytes+1))
        self.assertEqual(self.count('requests'),0)

    def test_failing_backend_still_retains_pending_custody(self):
        class Failing(Backend):
            def generate(self,*args,**kwargs):
                self.calls+=1
                raise RuntimeError('backend crashed after possible computation')
        self.spine.backend=Failing()
        with self.assertRaises(RuntimeError):self.spine.turn('session','r1','Hello')
        self.assertEqual(self.count('requests'),1)
        with self.assertRaises(Busy):self.spine.turn('session','r1','Hello')

    def test_preflight_does_not_regenerate_or_rewrite_committed_work(self):
        first=self.spine.turn('session','r1','Hello')
        self.backend.count_override=999999
        again=self.spine.turn('session','r1','Hello')
        self.assertTrue(again['replayed'])
        self.assertEqual(self.count('turns'),1)

    def test_unverified_counter_status_is_explicit(self):
        self.backend.count_tokens=None
        result=self.spine.turn('session','r1','Hello')
        self.assertEqual(result['context_capacity']['token_admission'],
                         'native-backend-must-enforce-unknown-precount')

if __name__=='__main__':unittest.main()
