"""Finite capacity, true resource conservation and crash-ambiguous native holds."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,CognitionError,hash_bytes
from skeleton.ai.runtime.operational_ai.offline_cognition.core.capacity_guard import (
    CapacitySnapshot,ResourceRequest,QuotaProjection,preview,pressure_gate,
    fair_preview,preemption_hold,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.core.scheduler import Task
from skeleton.ai.runtime.operational_ai.offline_cognition.core.receipts import NativeReceipt
S=Scope("local","owner","a"*64,"b"*64)

def snapshot(*,observed=True,mem=1000,disk=1000,tokens=1000,slots=2):
    return CapacitySnapshot(S,1,10,1000,mem,disk,tokens,slots,1000,observed)

def request(request_id="r",tokens=300,mem=200,disk=50,deadline=1000000000):
    return ResourceRequest(S,request_id,"c"*64,tokens,mem,disk,1,100,deadline)

class CapacityGuardTests(unittest.TestCase):
    def test_preview_conserves_all_dimensions(self):
        p=preview(snapshot(),(request("a"),request("b")),now_ns=20)
        self.assertEqual(p["admitted"],("a","b"))
        self.assertEqual(p["remaining"]["tokens"],400)
        self.assertEqual(p["remaining"]["memory"],600)
        self.assertFalse(p["durable_reservation_made"])

    def test_refuse_stale_observation(self):
        with self.assertRaises(CognitionError):
            preview(snapshot(),(request(),),now_ns=1000)

    def test_refuse_unattested_observer(self):
        with self.assertRaises(CognitionError):
            preview(snapshot(observed=False),(request(),),now_ns=20)

    def test_refuse_cross_tenant_batch(self):
        other=ResourceRequest(Scope("other","owner","a"*64,"b"*64),
                              "r","c"*64,100,100,0,1,100,1000000000)
        with self.assertRaises(CognitionError):
            preview(snapshot(),(other,),now_ns=20)

    def test_capacity_refusal_retains_remaining(self):
        p=preview(snapshot(mem=100),(request(),),now_ns=20)
        self.assertEqual(p["held"],(("r","capacity"),))
        self.assertEqual(p["remaining"]["tokens"],1000)

    def test_pressure_gate(self):
        p=pressure_gate(snapshot(mem=100,disk=100),now_ns=20,
                        memory_guard_bytes=200,disk_guard_bytes=200)
        self.assertTrue(p["held"])
        self.assertEqual(p["reasons"],("memory-pressure","disk-pressure"))

    def test_quota_revision_cas(self):
        q=QuotaProjection(S,epoch=1,token_ceiling=500)
        q.reserve(request(),expected_revision=1,now_ns=20)
        with self.assertRaises(CognitionError):
            q.reserve(request("b"),expected_revision=1,now_ns=20)

    def test_quota_overbooking_refused(self):
        q=QuotaProjection(S,epoch=1,token_ceiling=500)
        q.reserve(request("a"),expected_revision=1,now_ns=20)
        with self.assertRaises(CognitionError):
            q.reserve(request("b"),expected_revision=2,now_ns=20)

    def test_cancellation_before_dispatch_releases_reservation(self):
        q=QuotaProjection(S,epoch=1,token_ceiling=500)
        q.reserve(request(),expected_revision=1,now_ns=20)
        r=q.cancel_before_dispatch("r",expected_revision=2)
        self.assertTrue(r["unconsumed_reservation_released"])
        self.assertEqual(q.status()["remaining_tokens"],500)

    def test_dispatch_unknown_is_not_refundable(self):
        q=QuotaProjection(S,epoch=1,token_ceiling=500)
        q.reserve(request(),expected_revision=1,now_ns=20)
        q.mark_dispatch_unknown("r",expected_revision=2)
        with self.assertRaises(CognitionError):
            q.cancel_before_dispatch("r",expected_revision=3)

    def test_commit_actual_tokens_once(self):
        q=QuotaProjection(S,epoch=1,token_ceiling=500)
        q.reserve(request(),expected_revision=1,now_ns=20)
        q.mark_dispatch_unknown("r",expected_revision=2)
        msg="verified original output"
        receipt=NativeReceipt(S,"session","r",msg,hash_bytes(msg.encode()),100,50,False)
        first=q.settle_committed(receipt,expected_revision=3)
        self.assertEqual(first["tokens_charged"],150)
        second=q.settle_committed(receipt,expected_revision=4)
        self.assertEqual(second["state"],"already-settled")
        self.assertFalse(second["double_charged"])
        self.assertEqual(q.status()["remaining_tokens"],350)

    def test_replayed_first_settlement_refused(self):
        q=QuotaProjection(S,epoch=1,token_ceiling=500)
        q.reserve(request(),expected_revision=1,now_ns=20)
        q.mark_dispatch_unknown("r",expected_revision=2)
        msg="verified"
        receipt=NativeReceipt(S,"session","r",msg,hash_bytes(msg.encode()),100,50,True)
        with self.assertRaises(CognitionError):
            q.settle_committed(receipt,expected_revision=3)

    def test_oversized_native_usage_is_not_charged(self):
        q=QuotaProjection(S,epoch=1,token_ceiling=500)
        q.reserve(request(),expected_revision=1,now_ns=20)
        q.mark_dispatch_unknown("r",expected_revision=2)
        msg="verified"
        receipt=NativeReceipt(S,"session","r",msg,hash_bytes(msg.encode()),280,80,False)
        with self.assertRaises(CognitionError):
            q.settle_committed(receipt,expected_revision=3)
        self.assertEqual(q.status()["spent_tokens"],0)

    def test_fair_queue_only_proposes_order(self):
        p=fair_preview((Task("a","local",100,1,1000),
                        Task("b","other",100,1,1000)),
                        {"local":1.0,"other":2.0},now_ns=10,token_capacity=100)
        self.assertEqual(len(p["admitted"]),1)
        self.assertFalse(p["native_worker_dispatched"])

    def test_preemption_never_refunds_unknown_effect(self):
        p=preemption_hold(request(),dispatched=True,operator_approved=True)
        self.assertFalse(p["automatic_refund"])
        self.assertTrue(p["requires_canonical_spine_reconciliation"])

if __name__=="__main__":
    unittest.main()
