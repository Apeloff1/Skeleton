import unittest
from skeleton.ai.assurance.fault_taxonomy import AssuranceContractError, FaultDescriptor, FaultTaxonomy

class TestFaultTaxonomy(unittest.TestCase):
    def test_critical_faults_cannot_auto_retry(self):
        fault=FaultDescriptor("timeout","dependency","error",True,"retry-bounded")
        self.assertEqual(FaultTaxonomy((fault,)).classify("timeout"),fault)
        with self.assertRaises(AssuranceContractError):
            FaultDescriptor("corruption","state","critical",True,"operator")

if __name__=="__main__": unittest.main()
