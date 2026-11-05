"""capacity_admission: typed finite admission and non-refunding uncertainty."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,CognitionError
from skeleton.ai.runtime.operational_ai.offline_cognition.core.capacity_guard import CapacitySnapshot,ResourceRequest
from skeleton.ai.runtime.operational_ai.offline_cognition.families.capacity_admission import guard
S=Scope("local","owner","a"*64,"b"*64)

class CapacityAdmissionGuardTests(unittest.TestCase):
    def setUp(self):
        self.snapshot=CapacitySnapshot(S,1,10,1000,1000,1000,1000,2,1000,True)
        self.req=ResourceRequest(S,"r","c"*64,100,200,50,1,100,1000000000)

    def test_original_capacity_preview(self):
        result=guard.evaluate(self.snapshot,(self.req,),now_ns=20)
        self.assertEqual(result["admitted"],("r",))
        self.assertFalse(result["durable_reservation_made"])

    def test_pressure_only_observes(self):
        result=guard.pressure(self.snapshot,now_ns=20,memory_bytes=2000,disk_bytes=2000)
        self.assertTrue(result["held"])
        self.assertFalse(result["model_device_qualified"])

    def test_unknown_dispatch_never_refunds(self):
        r=guard.request_preemption(self.req,dispatched=True,operator_approved=True)
        self.assertFalse(r["automatic_refund"])

    def test_projection_requires_cas(self):
        quota=guard.reserve_projection(S,epoch=1,tokens=1000)
        quota.reserve(self.req,expected_revision=1,now_ns=20)
        with self.assertRaises(CognitionError):
            quota.reserve(self.req,expected_revision=1,now_ns=20)

    def test_limits_do_not_claim_native_or_durable(self):
        result=guard.limits()
        self.assertFalse(result["native_execution_performed"])
        self.assertFalse(result["durable_work_order_authority_here"])

if __name__=="__main__":
    unittest.main()
