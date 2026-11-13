"""Offline laptop runtime qualification: outbox; test-double only, not real native E2E."""
import unittest
from skeleton.testing.laptop_runtime_test_support import FakeWorker,OUTPUT_SHA
from skeleton.ai.runtime.operational_ai.laptop_runtime.outbox_delivery import DeliveryCursor
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestOutbox(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker();self.cursor=DeliveryCursor(self.worker)
    def test_one_event_is_idempotently_acknowledged(self):
        events=self.cursor.pending()
        self.assertEqual(len(events),1)
        self.assertTrue(self.cursor.acknowledge("e_1",OUTPUT_SHA))
        self.assertFalse(self.cursor.acknowledge("e_1",OUTPUT_SHA))
    def test_wrong_digest_rejected_before_side_effect(self):
        with self.assertRaises(ValueError):
            self.cursor.acknowledge("e_1","a"*64)
        with self.assertRaises(ContractViolation):
            self.cursor.acknowledge("../escape",OUTPUT_SHA)

if __name__=="__main__":
    unittest.main()
