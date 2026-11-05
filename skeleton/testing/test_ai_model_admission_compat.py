"""Regression: model capacity package must not shadow core inference admission."""
from __future__ import annotations
import threading
import time
import unittest
from skeleton.ai.runtime.operational_ai.model.admission import InferenceAdmission,CapacityBroker
from skeleton.ai.runtime.operational_ai.model.gateway import ModelGateway
from skeleton.ai.runtime.operational_ai.authority.canonical import ContractViolation

class AdmissionCompatibilityTests(unittest.TestCase):
    def test_both_admission_facades_available(self):
        self.assertIsInstance(InferenceAdmission(),InferenceAdmission)
        self.assertTrue(callable(CapacityBroker))
        self.assertTrue(callable(ModelGateway))

    def test_worker_limit_rejects_noninteger(self):
        for n in (True,0,65,1.0):
            with self.subTest(value=n),self.assertRaises(ContractViolation):InferenceAdmission(workers=n)

    def test_bounded_queue_worker_slot(self):
        gate=InferenceAdmission(workers=1,max_waiting=1)
        with gate.slot(deadline_ns=time.monotonic_ns()+2_000_000_000):
            self.assertEqual(gate.active,1)
            error=[]
            def second():
                try:
                    with gate.slot(deadline_ns=time.monotonic_ns()+100_000_000):pass
                except ContractViolation:error.append(True)
            t=threading.Thread(target=second);t.start();t.join(timeout=1)
            self.assertEqual(error,[True])
        self.assertEqual(gate.active,0)

    def test_cancel_before_claim(self):
        token=threading.Event();token.set()
        gate=InferenceAdmission()
        with self.assertRaises(ContractViolation):
            with gate.slot(deadline_ns=time.monotonic_ns()+100_000_000,cancel=token):pass
        self.assertEqual(gate.active,0)

    def test_nonfinite_deadline_rejected(self):
        gate=InferenceAdmission()
        for value in (0,-1,True,'10'):
            with self.subTest(value=value),self.assertRaises(ContractViolation):
                with gate.slot(deadline_ns=value):pass

if __name__=='__main__':unittest.main()
