"""Inert offline plans, source/tool proof, ambiguous dispatch and circuit holds."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,CognitionError
from skeleton.ai.runtime.operational_ai.offline_cognition.core.planner import PlanTask
from skeleton.ai.runtime.operational_ai.offline_cognition.core.sources import bind_source
from skeleton.ai.runtime.operational_ai.offline_cognition.core.orchestration import (
    guarded_plan,plan_ready,propose_read,ReadResult,classify_outcome,
    escalation,CircuitSnapshot,observe_circuit,request_circuit_recovery,
)
S=Scope("local","owner","a"*64,"b"*64)
D="c"*64

class OfflineOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.tasks=(PlanTask("read",200,0,"retrieval",()),
                    PlanTask("reason",1000,100,"model",("read",)),
                    PlanTask("review",300,0,"verification",("reason",)))

    def plan(self):
        return guarded_plan(S,self.tasks,request_id="request_1",source_sha256=D,
                            now_ns=1,deadline_ns=2_000_000_001,
                            token_limit=1000,duration_limit_ms=2000)

    def test_compiles_finite_plan_with_dependencies(self):
        p=self.plan()
        self.assertEqual(p["order"],("read","reason","review"))
        self.assertEqual(p["critical_path_ms"],1500)
        self.assertFalse(p["approved_to_execute"])

    def test_read_only_plan_check(self):
        r=plan_ready(self.plan(),S,request_id="request_1",source_sha256=D,now_ns=100)
        self.assertFalse(r["tool_or_native_execution_authorized"])

    def test_refuse_short_deadline(self):
        with self.assertRaises(CognitionError):
            guarded_plan(S,self.tasks,request_id="request_1",source_sha256=D,
                         now_ns=1,deadline_ns=100,token_limit=1000,
                         duration_limit_ms=2000)

    def test_refuse_dependency_cycle(self):
        bad=(PlanTask("a",1,0,"operator",("b",)),
             PlanTask("b",1,0,"operator",("a",)))
        with self.assertRaises(CognitionError):
            guarded_plan(S,bad,request_id="r",source_sha256=D,
                         now_ns=1,deadline_ns=1000000000,
                         token_limit=1000,duration_limit_ms=2000)

    def test_refuse_tampered_plan_claim(self):
        p=self.plan()
        p["plan_claim"]["request_id"]="tampered"
        with self.assertRaises(CognitionError):
            plan_ready(p,S,request_id="request_1",source_sha256=D,now_ns=100)

    def test_refuse_expired_plan(self):
        with self.assertRaises(CognitionError):
            plan_ready(self.plan(),S,request_id="request_1",source_sha256=D,
                       now_ns=2_000_000_001)

    def test_tool_proposal_is_not_execution(self):
        i=propose_read(S,request_id="request_1",source_id="doc",expires_ns=100)
        self.assertEqual(i.tool,"read_source")
        self.assertEqual(i.scope_sha256,S.digest())

    def test_refuse_shell_proposal(self):
        with self.assertRaises(CognitionError):
            propose_read(S,request_id="request_1",source_id="doc",expires_ns=100,
                         tool="shell")

    def test_original_tool_read_proof(self):
        raw=b"Operator reviewed original source bytes"
        source=bind_source(raw,source_id="doc",tenant="local",subject="owner",approved=True)
        i=propose_read(S,request_id="request_1",source_id="doc",expires_ns=100)
        r=ReadResult(i,source,S,"request_1",raw,50).receipt()
        self.assertTrue(r["original_bytes_verified"])
        self.assertFalse(r["semantic_entailment_proved"])

    def test_refuse_modified_tool_result(self):
        raw=b"Authorized original"
        source=bind_source(raw,source_id="doc",tenant="local",subject="owner",approved=True)
        i=propose_read(S,request_id="request_1",source_id="doc",expires_ns=100)
        with self.assertRaises(CognitionError):
            ReadResult(i,source,S,"request_1",b"modified",50)

    def test_refuse_foreign_tool_result(self):
        raw=b"Authorized original"
        source=bind_source(raw,source_id="doc",tenant="foreign",subject="owner",approved=True)
        i=propose_read(S,request_id="request_1",source_id="doc",expires_ns=100)
        with self.assertRaises(CognitionError):
            ReadResult(i,source,S,"request_1",raw,50)

    def test_dispatch_unknown_never_retries(self):
        outcome=classify_outcome("native-effect-unknown",
                                  dispatch_marker=True,authoritative_commit=False)
        self.assertEqual(outcome["state"],"native-effect-unknown-held")
        self.assertFalse(outcome["automatic_retry_allowed"])

    def test_committed_only_replay(self):
        outcome=classify_outcome("spine-committed",dispatch_marker=True,
                                authoritative_commit=True)
        self.assertTrue(outcome["committed_replay_only"])

    def test_false_commit_claim_refused(self):
        with self.assertRaises(CognitionError):
            classify_outcome("spine-committed",dispatch_marker=True,
                             authoritative_commit=False)

    def test_escalation_has_no_implicit_operator_dispatch(self):
        r=escalation(S,request_id="r",source_sha256=D,
                     cause="native-effect-unknown",created_ns=100)
        self.assertFalse(r["operator_notified"])
        self.assertFalse(r["privilege_granted"])

    def test_circuit_trips_at_threshold(self):
        snap=CircuitSnapshot(S.digest(),1,0,0,False)
        for i in range(1,4):
            snap=observe_circuit(snap,S,failure=True,now_ns=i)
        self.assertTrue(snap.held)
        self.assertEqual(snap.revision,4)

    def test_circuit_recovery_intent_stays_held(self):
        snap=CircuitSnapshot(S.digest(),2,3,100,True)
        r=request_circuit_recovery(snap,S,expected_revision=2,operator_approved=True)
        self.assertFalse(r["automatic_reopen"])
        self.assertFalse(r["operator_signature_verified"])

    def test_circuit_refuses_stale_revision(self):
        snap=CircuitSnapshot(S.digest(),2,3,100,True)
        with self.assertRaises(CognitionError):
            request_circuit_recovery(snap,S,expected_revision=1,operator_approved=True)

if __name__=="__main__":
    unittest.main()
