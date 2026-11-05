"""Offline laptop runtime qualification: boot_chain; test-double only, not real native E2E."""
import unittest
from skeleton.ai.runtime.operational_ai.laptop_runtime.boot_chain import BootChain,_STAGES
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestBootProofs(unittest.TestCase):
    def test_all_six_independent_boot_boundaries(self):
        chain=BootChain()
        for i,phase in enumerate(_STAGES):
            chain.add(phase,(hex(i+10)[2:]).rjust(64,"0"))
        self.assertTrue(chain.audit()["complete"])
        self.assertEqual(chain.audit()["stage_count"],6)
        self.assertFalse(chain.audit()["release_certified"])
    def test_skipped_stage_refused(self):
        chain=BootChain()
        with self.assertRaises(ContractViolation):
            chain.add("native-backend-activated","a"*64)
        self.assertFalse(chain.audit()["complete"])
    def test_recycled_evidence_does_not_equal_release_proof(self):
        chain=BootChain()
        chain.add(_STAGES[0],"a"*64)
        self.assertFalse(chain.audit()["complete"])

if __name__=="__main__":
    unittest.main()
