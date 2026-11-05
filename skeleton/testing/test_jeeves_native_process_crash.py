"""OS-process crash qualification for source-only native request custody.

These are REAL separate Python processes with REAL SQLite/WAL, session flock,
intent reservation, work order and deterministic operator approval. Model
tokens are emitted by a SYNTHETIC test backend. Hard child termination is
used to inspect real crash boundaries; not a device-pressure, true model
cancellation, GGUF accuracy or consumer Windows qualification.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity,SpineLimits,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import ExecutionSpine
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import SupervisedAI
from skeleton.jeeves.native_fabric.contracts import Scope
from skeleton.jeeves.native_fabric.durable_queue import (
    WorkOrder,DurableNativeQueue,DurableQueueHold,
)
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL,TOKENIZER,SyntheticallyGenerated,
)


_CHILD= r'''
import os,sys
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity,SpineLimits
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import ExecutionSpine
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import SupervisedAI
from skeleton.jeeves.native_fabric.contracts import Scope
from skeleton.jeeves.native_fabric.durable_queue import DurableNativeQueue,DurableQueueHold
from skeleton.testing.test_jeeves_native_sqlite_integration import MODEL,TOKENIZER,SyntheticallyGenerated

root=sys.argv[1]
mode=sys.argv[2]
session=sys.argv[3]
request=sys.argv[4]
prompt=sys.argv[5]
class ChildDeath(SyntheticallyGenerated):
    def generate(self, messages, *, max_output_tokens, seed, temperature):
        os._exit(77)

db=SpineDatabase(root)
gate=SessionGate(root)
backend=ChildDeath() if mode=="kill_during_model" else SyntheticallyGenerated()
spine=ExecutionSpine(
    db=db,session_gate=gate,backend=backend,
    identity=Identity("local","operator",MODEL,TOKENIZER),
    limits=SpineLimits(input_bytes=32768,response_bytes=131072,
                       max_output_tokens=128,context_tokens=4096),
)
worker=SupervisedAI(spine)
scope=Scope("local","operator",MODEL,TOKENIZER)
queue=DurableNativeQueue(worker,scope_sha256=scope.binding,clock_ns=lambda:1000000)
try:
    claim=queue.claim("hard_crash_order")
except DurableQueueHold:
    sys.exit(31)
if mode=="claim_only":
    sys.exit(0)
worker.turn(session,request,prompt,seed=0,temperature=0.8)
if mode=="kill_after_native_commit":
    os._exit(78)
sys.exit(0)
'''


@unittest.skipUnless(os.name=="posix" and Path("/proc/self/fd").is_dir(),
                     "Linux descriptor-backed SQLite required")
class TestNativeProcessCrashMatrix(unittest.TestCase):
    PROMPT="Source-only synthetic request exercising real crash fence."
    SESSION="hard_crash_session"
    REQUEST="hard_crash_request"

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=SpineDatabase(self.temp.name)
        self.gate=SessionGate(self.temp.name)
        self.addCleanup(self.gate.close)
        self.addCleanup(self.db.close)
        self.backend=SyntheticallyGenerated()
        self.spine=ExecutionSpine(
            db=self.db,session_gate=self.gate,backend=self.backend,
            identity=Identity("local","operator",MODEL,TOKENIZER),
            limits=SpineLimits(input_bytes=32768,response_bytes=131072,
                               max_output_tokens=128,context_tokens=4096),
        )
        self.worker=SupervisedAI(self.spine)
        scope=Scope("local","operator",MODEL,TOKENIZER)
        self.queue=DurableNativeQueue(
            self.worker,scope_sha256=scope.binding,clock_ns=lambda:1000000,
        )
        self.order=WorkOrder(
            "hard_crash_order",scope.binding,"local","operator",MODEL,TOKENIZER,
            self.SESSION,self.REQUEST,sha256(self.PROMPT.encode()).hexdigest(),
            0,0.8,"operator",10,1000000,10000000,
        )
        self.spine.create(self.SESSION)
        self.queue.submit(self.order)

    def _args(self,mode):
        return [
            sys.executable,"-c",_CHILD,self.temp.name,mode,
            self.SESSION,self.REQUEST,self.PROMPT,
        ]

    def _run(self,mode):
        return subprocess.run(
            self._args(mode),capture_output=True,text=True,
            timeout=25,check=False,
        )

    def test_real_os_death_during_synthetic_inference_leaves_pending_spine(self):
        child=self._run("kill_during_model")
        self.assertEqual(child.returncode,77,child.stderr)
        self.assertEqual(self.queue.inspect(self.order.order_id)["state"],"claimed")
        with self.db.snapshot() as conn:
            self.assertEqual(
                conn.execute("SELECT state FROM requests").fetchone(),("pending",),
            )
        self.assertIsNone(self.worker.spine.replay(
            self.SESSION,self.REQUEST,self.PROMPT,
            seed=0,temperature=0.8,
        ))
        self.assertEqual(self.backend.calls,0)
        with self.assertRaises(DurableQueueHold):
            self.queue.claim(self.order.order_id)

    def test_real_os_death_after_model_commit_can_reconcile_without_new_inference(self):
        child=self._run("kill_after_native_commit")
        self.assertEqual(child.returncode,78,child.stderr)
        self.assertEqual(self.queue.inspect(self.order.order_id)["state"],"claimed")
        with self.db.snapshot() as conn:
            self.assertEqual(
                conn.execute("SELECT state FROM requests").fetchone(),("committed",),
            )
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM turns",
            ).fetchone(),(1,))
        report=self.queue.reconcile_orphaned(
            self.order.order_id,prompt=self.PROMPT,operator_approved=True,
        )
        self.assertEqual(report["state"],"committed")
        self.assertEqual(self.backend.calls,0)

    def test_real_os_terminated_claim_cannot_be_redispatched(self):
        child=self._run("claim_only")
        self.assertEqual(child.returncode,0,child.stderr)
        self.assertEqual(self.queue.inspect(self.order.order_id)["state"],"claimed")
        self.assertFalse(self.queue.next_ready())
        with self.assertRaises(DurableQueueHold):
            self.queue.reconcile_orphaned(
                self.order.order_id,prompt=self.PROMPT,
                operator_approved=True,
            )
        self.assertEqual(self.backend.calls,0)

    def test_two_competing_processes_never_both_claim_same_native_request(self):
        p1=subprocess.Popen(self._args("claim_only"),stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,text=True)
        p2=subprocess.Popen(self._args("claim_only"),stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,text=True)
        try:
            _,e1=p1.communicate(timeout=25)
            _,e2=p2.communicate(timeout=25)
        finally:
            for proc in (p1,p2):
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate(timeout=5)
        self.assertEqual(sorted((p1.returncode,p2.returncode)),[0,31],e1+e2)
        self.assertEqual(self.queue.inspect(self.order.order_id)["state"],"claimed")
        self.assertEqual(self.backend.calls,0)

    def test_failed_native_child_never_synthesizes_verified_response(self):
        child=self._run("kill_during_model")
        self.assertEqual(child.returncode,77,child.stderr)
        with self.db.snapshot() as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM turns").fetchone(),(0,),
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM outbox").fetchone(),(0,),
            )
        with self.assertRaises(DurableQueueHold):
            self.queue.reconcile_orphaned(
                self.order.order_id,prompt=self.PROMPT,operator_approved=True,
            )

    def test_process_crash_evidence_never_claims_native_model_or_windows_device(self):
        child=self._run("claim_only")
        self.assertEqual(child.returncode,0)
        report=self.queue.no_autoretry_status()
        self.assertFalse(report["device_qualified"])
        self.assertFalse(report["release_certified"])
        self.assertTrue(report["claimed_cannot_requeue"])


if __name__=="__main__":
    unittest.main()
