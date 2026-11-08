"""Real execution control flow, using an explicitly non-native interface double."""
import unittest
from skeleton.testing.reliability_fabric_test_support import scenario,FakeWorker
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.preflight import REQUIRED_INFERENCE
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.assured_supervisor import AssuredSupervisor
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected, canonical, sha256
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.evidence_bundle import EvidenceBundle

def evidence():
    return {name:scenario(name,subject="owner") for name in REQUIRED_INFERENCE}

def test_evidence_bundle_uses_roundtrip_safe_identity_without_claiming_native_device():
    records = evidence()
    bundle = EvidenceBundle()
    for name, record in records.items():
        bundle.add(name, record)
    receipt = bundle.seal(required=REQUIRED_INFERENCE)
    identity = next(iter(records.values()))["identity"]
    fields = [
        identity["tenant"], identity["subject"],
        identity["model_sha256"], identity["scope"],
    ]
    assert receipt.identity_sha256 == sha256(canonical(fields))
    assert receipt.source_only is True
    assert receipt.release_certified is False


class AssuredSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()
        self.worker.spine.create("session")
        self.api=AssuredSupervisor(self.worker,tenant_token_cap=8192,global_token_cap=16384)

    def test_first_turn_uses_spine_and_second_uses_durable_replay(self):
        first=self.api.execute(evidence(),session_id="session",request_id="req1",prompt="hello")
        self.assertEqual(first["status"],"native-committed")
        self.assertEqual(self.worker.generation_calls,1)
        replay=self.api.execute(evidence(),session_id="session",request_id="req1",prompt="hello")
        self.assertEqual(replay["status"],"durable-replayed")
        self.assertEqual(replay["charged_tokens"],0)
        self.assertEqual(self.worker.generation_calls,1)

    def test_incomplete_or_cross_model_preflight_never_generates(self):
        for name in ("native_identity","tokenizer_custody","model_capacity"):
            records=evidence();del records[name]
            with self.subTest(name=name):
                with self.assertRaises(Rejected):
                    self.api.execute(records,session_id="session",
                                     request_id="blocked",prompt="hello")
        self.assertEqual(self.worker.generation_calls,0)

    def test_insufficient_budget_refuses_before_native_inference(self):
        tiny=AssuredSupervisor(self.worker,tenant_token_cap=128,global_token_cap=256)
        with self.assertRaises(Rejected):
            tiny.execute(evidence(),session_id="session",request_id="small",prompt="hello")
        self.assertEqual(self.worker.generation_calls,0)

    def test_uncertain_native_failure_keeps_reservation(self):
        self.worker.turn=lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError("uncertain native effect"))
        with self.assertRaises(RuntimeError):
            self.api.execute(evidence(),session_id="session",request_id="uncertain",prompt="hello")
        self.assertGreater(self.api.status()["quota"]["reserved"],0)

if __name__=="__main__":unittest.main()
