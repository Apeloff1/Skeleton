"""Executable state-machine and fail-closed regression tests."""
from skeleton.ai.runtime.operational_ai.trust_gates.control.model_epoch import ModelEpoch
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
import unittest
class TestModelEpoch(unittest.TestCase):
    def test_live_leases_block_swap(self):
        slot=ModelEpoch("a"*64,"a"*64)
        old=slot.identity
        with slot.pin(expected=old) as seen:
            self.assertEqual(seen,old)
            with self.assertRaises(GateViolation):slot.swap("b"*64,"b"*64,approved=True)
        new=slot.swap("b"*64,"b"*64,expected=old,approved=True)
        self.assertEqual(new[0],2)
        with self.assertRaises(GateViolation):
            with slot.pin(expected=old): pass
    def test_unapproved_swap_and_active_retirement(self):
        slot=ModelEpoch("a"*64,"a"*64)
        with self.assertRaises(GateViolation):slot.swap("b"*64,"b"*64)
        with slot.pin():
            with self.assertRaises(GateViolation):slot.close()
        slot.close()
        with self.assertRaises(GateViolation):
            with slot.pin():pass

if __name__=="__main__":
    unittest.main()
