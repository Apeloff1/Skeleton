"""Actual SpineDatabase+ExecutionSpine integration, with an explicit test-only backend."""
from __future__ import annotations
import hashlib,tempfile,unittest
from pathlib import Path
from skeleton.ai.runtime.operational_ai.agent_fabric.core.identity import Identity as AgentIdentity
from skeleton.ai.runtime.operational_ai.agent_fabric.custody.store import AgentStore
from skeleton.ai.runtime.operational_ai.agent_fabric.planning.spec import Plan,Step
from skeleton.ai.runtime.operational_ai.agent_fabric.execution.engine import AgentFabric
from skeleton.ai.runtime.operational_ai.agent_fabric.execution.ports import Ports
from skeleton.ai.runtime.operational_ai.agent_fabric.integration.spine import SpinePort
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import Identity,SpineLimits,SpineDatabase,ExecutionSpine
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.model.native import Generated
MODEL='a'*64;TOK='b'*64
class LocalFixtureBackend:
    model_digest=MODEL;tokenizer_digest=TOK
    def __init__(self):self.calls=0
    def generate(self,messages,*,max_output_tokens,seed,temperature):
        self.calls+=1;output='Test-only native-path result '+str(self.calls)
        return Generated(output,50,8,hashlib.sha256(output.encode()).hexdigest(),MODEL,TOK,'stop')
class NativeSpineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='agent-native-spine-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'private';self.root.mkdir(mode=0o700)
        self.lockdir=self.root/'locks';self.lockdir.mkdir(mode=0o700)
        self.db=SpineDatabase(self.root);self.addCleanup(self.db.close)
        self.gate=SessionGate(self.lockdir);self.addCleanup(self.gate.close)
        self.backend=LocalFixtureBackend()
        self.identity=Identity('tenant','operator',MODEL,TOK)
        self.spine=ExecutionSpine(db=self.db,session_gate=self.gate,backend=self.backend,
           identity=self.identity,limits=SpineLimits(context_tokens=2048,max_output_tokens=128,deadline_ms=4000))
        self.spine.create('s1')
        self.store=AgentStore(self.db,AgentIdentity.from_spine(self.identity))
        self.agent=AgentFabric(self.store,Ports(model=SpinePort(self.spine)))
    def test_real_sqlite_atomic_model_and_agent_receipts(self):
        plan=Plan('plan1','s1',(Step('first','model','Original AI reasoning path'),),'Tested DAG')
        self.agent.submit(plan)
        completed=self.agent.run_one('plan1')
        self.assertEqual(completed['status'],'complete')
        self.assertEqual(self.backend.calls,1)
        self.assertEqual(self.store.load('plan1')[2],'complete')
        with self.db.snapshot() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM turns').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_events').fetchone()[0],4)
    def test_restart_without_second_inference(self):
        self.agent.submit(Plan('p2','s1',(Step('x','model','One source-bound answer'),),'Tested DAG'))
        self.agent.run_one('p2')
        next_agent=AgentFabric(AgentStore(self.db,AgentIdentity.from_spine(self.identity)),Ports(model=SpinePort(self.spine)))
        self.assertIsNone(next_agent.run_one('p2'))
        self.assertEqual(self.backend.calls,1)
    def test_no_plausible_forged_model_identity(self):
        self.agent.submit(Plan('p3','s1',(Step('x','model','No fake model proof'),),'Tested DAG'))
        class Forged:
            def complete(self,**kwargs):return {'output_sha256':'f'*64,'model_sha256':'c'*64,'tokenizer_sha256':TOK}
        self.agent.ports=Ports(model=Forged())
        with self.assertRaises(Exception):self.agent.run_one('p3')
        self.assertEqual(self.store.load('p3')[2],'held')
if __name__=='__main__':unittest.main()
