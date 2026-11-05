"""Fixture-only first boot and replay: never claim a real GGUF qualification."""
import copy,hashlib,json,os,tempfile,unittest
from pathlib import Path
from contextlib import ExitStack
from skeleton.ai.runtime.operational_ai.deployment.qualification import (
    QualificationInput,QualificationError,probe_first_boot,
)
from skeleton.ai.runtime.operational_ai.deployment.qualification.verification import verify
from skeleton.ai.runtime.operational_ai.deployment.qualification.paths import publish_private_report
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import (
    SpineDatabase, ExecutionSpine, Identity, SpineLimits,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import SupervisedAI
from skeleton.ai.runtime.operational_ai.model.native import Generated

I=Identity('team','owner','a'*64,'b'*64)

class ProbeBackend:
    model_digest=I.model_sha256
    tokenizer_digest=I.tokenizer_sha256
    def __init__(self,counters):self.counters=counters
    def generate(self,messages,*,max_output_tokens,seed,temperature):
        self.counters['generated']+=1
        text='Native fixture response'
        return Generated(text,60,5,hashlib.sha256(text.encode()).hexdigest(),
                         self.model_digest,self.tokenizer_digest,'stop')

class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/home/oai/.cache')
        self.state=Path(self.tmp.name)/'private'
        self.state.mkdir(mode=0o700)
        self.out=Path(self.tmp.name)/'reports';self.out.mkdir(mode=0o700)
        self.counter={'generated':0}
        self.plan=QualificationInput(Path(self.tmp.name)/'model',self.state,
                                     'team','owner')
    def tearDown(self):self.tmp.cleanup()
    def factory(self,**kwargs):
        stack=ExitStack()
        db=stack.enter_context(SpineDatabase(self.state))
        lock=self.state/'lock'
        lock.mkdir(mode=0o700,exist_ok=True)
        gate=stack.enter_context(SessionGate(lock))
        spine=ExecutionSpine(db=db,session_gate=gate,
            backend=ProbeBackend(self.counter),identity=I,
            limits=SpineLimits(max_output_tokens=64,context_tokens=2048))
        return stack,SupervisedAI(spine)

    def test_reboot_replay_executes_native_fixture_once(self):
        proof=probe_first_boot(self.plan,activation=self.factory)
        self.assertEqual(proof['status'],'fixture-only-not-production-certified')
        self.assertEqual(self.counter['generated'],1)
        self.assertEqual(proof['database_turns'],1)
        self.assertEqual(verify(proof,require_real=False)['real_model_executed'],False)
        with self.assertRaisesRegex(QualificationError,'fixture'):
            verify(proof)

    def test_proof_records_no_source_prompt_or_model_output(self):
        proof=probe_first_boot(self.plan,activation=self.factory)
        result=json.dumps(proof)
        self.assertNotIn('Native fixture response',result)
        self.assertNotIn('offline model should preserve',result)
        self.assertNotIn(self.tmp.name,result)

    def test_proof_tampering_detected(self):
        proof=probe_first_boot(self.plan,activation=self.factory)
        changed=copy.deepcopy(proof);changed['generated_tokens']=1234
        with self.assertRaisesRegex(QualificationError,'digest mismatch'):
            verify(changed,require_real=False)

    def test_same_report_filename_never_overwrites(self):
        proof=probe_first_boot(self.plan,activation=self.factory)
        publish_private_report(self.out,'report.json',proof)
        before=(self.out/'report.json').read_bytes()
        with self.assertRaises(FileExistsError):
            publish_private_report(self.out,'report.json',proof)
        self.assertEqual((self.out/'report.json').read_bytes(),before)
        self.assertEqual((self.out/'report.json').stat().st_mode & 0o777,0o600)

    def test_report_parent_permissions_hold(self):
        proof=probe_first_boot(self.plan,activation=self.factory)
        os.chmod(self.out,0o755)
        with self.assertRaises(QualificationError):
            publish_private_report(self.out,'report.json',proof)

    def test_report_name_traversal_refused(self):
        proof=probe_first_boot(self.plan,activation=self.factory)
        for name in ('../escape.json','/tmp/x.json','.json','bad.txt'):
            with self.subTest(name=name),self.assertRaises(QualificationError):
                publish_private_report(self.out,name,proof)

    def test_second_restart_with_mismatched_identity_fails(self):
        count=[0]
        def factory(**kwargs):
            count[0]+=1
            stack,worker=self.factory(**kwargs)
            if count[0]==2:worker.spine.identity=Identity('foreign','owner','a'*64,'b'*64)
            return stack,worker
        with self.assertRaises(QualificationError):
            probe_first_boot(self.plan,activation=factory)

    def test_no_real_checkpoint_is_reported_by_fixture(self):
        result=probe_first_boot(self.plan,activation=self.factory)
        self.assertEqual(result['checkpoint_execution_mode'],'injected-test-double')

if __name__=='__main__':unittest.main()
