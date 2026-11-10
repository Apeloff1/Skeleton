"""Cross-process custody and restart tests, fixture models only."""
from __future__ import annotations
from pathlib import Path
import json,os,subprocess,sys,tempfile,threading,time,unittest
from hashlib import sha256
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import Identity,SpineDatabase,ExecutionSpine,SpineLimits
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.flight_control import (
    FlightLedger,FlightPolicy,FlightSpec,reconcile,inspect)
from skeleton.testing.test_ai_flight_control import FakeBackend,M,T

WORKER_SCRIPT='''
import json,sys
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import Identity,SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.flight_control import FlightLedger,FlightPolicy
from pathlib import Path
root=Path(sys.argv[1]); identity=Identity('tenant1','human1','a'*64,'b'*64)
with SpineDatabase(root) as db:
 ledger=FlightLedger(db,identity,settings=FlightPolicy(lease_ms=50,max_running=4,max_claimed=8))
 result=ledger.claim(sys.argv[2])
 print(json.dumps({'job':result.job_id if result else None}),flush=True)
'''

CRASH_AFTER_INFERENCE='''
import os,sys
from pathlib import Path
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import Identity,SpineDatabase,ExecutionSpine,SpineLimits
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.flight_control import FlightLedger,FlightPolicy
from skeleton.testing.test_ai_flight_control import FakeBackend,M,T
root=Path(sys.argv[1]);identity=Identity('tenant1','human1',M,T)
with SpineDatabase(root) as db, SessionGate(root/'locks') as gate:
 spine=ExecutionSpine(db=db,session_gate=gate,backend=FakeBackend(),identity=identity,
   limits=SpineLimits(context_tokens=8192,max_output_tokens=64,deadline_ms=4000))
 ledger=FlightLedger(db,identity,settings=FlightPolicy(lease_ms=50,max_running=4,max_claimed=8))
 ticket=ledger.claim('crashWorker');ledger.start(ticket)
 spine.turn('chat1','ask1','Explain idea 1')
 # Deliberately kill process before queue finish; spine committed independently.
 os._exit(73)
'''

class ProcessFlights(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='flight-multiproc-')
        self.root=Path(self.temp.name)/'private';self.root.mkdir(mode=0o700)
        (self.root/'locks').mkdir(mode=0o700)
        self.identity=Identity('tenant1','human1',M,T)
        self.backend=FakeBackend()
        self.db=SpineDatabase(self.root)
        self.gate=SessionGate(self.root/'locks')
        self.spine=ExecutionSpine(db=self.db,session_gate=self.gate,
            backend=self.backend,identity=self.identity,
            limits=SpineLimits(context_tokens=8192,max_output_tokens=64,deadline_ms=4000))
        self.spine.create('chat1')
        self.ledger=FlightLedger(self.db,self.identity,
            settings=FlightPolicy(lease_ms=50,max_running=4,max_claimed=8))
    def tearDown(self):
        self.gate.close();self.db.close();self.temp.cleanup()
    def run_child(self,script,worker='w1'):
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[2])+os.pathsep+os.environ.get('PYTHONPATH',''))
        return subprocess.run([sys.executable,'-c',script,str(self.root),worker],
                              capture_output=True,text=True,timeout=15,env=env)

    def test_two_processes_cannot_claim_same_session(self):
        self.ledger.submit(FlightSpec(self.identity,'job1','chat1','ask1','Explain idea 1'))
        self.ledger.submit(FlightSpec(self.identity,'job2','chat1','ask2','Explain idea 2'))
        results=[]
        def run(worker):results.append(self.run_child(WORKER_SCRIPT,worker))
        a=threading.Thread(target=run,args=('w1',));b=threading.Thread(target=run,args=('w2',))
        a.start();b.start();a.join(15);b.join(15)
        self.assertEqual(len(results),2)
        self.assertTrue(
            all(r.returncode == 0 for r in results),
            [{"code": r.returncode, "out": r.stdout[-256:],
              "err": r.stderr[-512:]} for r in results],
        )
        names=[json.loads(r.stdout)['job'] for r in results]
        self.assertEqual(sum(x is not None for x in names),1)
        self.assertEqual(self.ledger.state_count()['claimed'],1)
        self.assertEqual(self.backend.calls,0)

    def test_crash_after_authoritative_commit_recovered_without_inference(self):
        self.ledger.submit(FlightSpec(self.identity,'job1','chat1','ask1','Explain idea 1'))
        child=self.run_child(CRASH_AFTER_INFERENCE)
        self.assertEqual(child.returncode,73,child.stderr)
        self.assertEqual(self.ledger.state_count()['running'],1)
        self.assertEqual(self.spine.history('chat1')[-1]['role'],'assistant')
        time.sleep(.08)
        outcome=reconcile(self.ledger,self.spine,approved=True)
        self.assertEqual(outcome['recovered_from_committed_receipt'],1)
        self.assertEqual(self.ledger.state_count()['completed'],1)
        self.assertEqual(self.backend.calls,0)
        self.assertEqual(inspect(self.ledger)['status'],'verified')

if __name__=='__main__':unittest.main()
