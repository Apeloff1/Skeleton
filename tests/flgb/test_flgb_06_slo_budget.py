import unittest
from skeleton.ai.assurance.slo_budget import AssuranceContractError, SLOTarget, error_budget_remaining

class TestSLOBudget(unittest.TestCase):
    def test_error_budget_is_non_negative(self):
        slo=SLOTarget("api",990000,100)
        self.assertEqual(slo.error_budget_ppm,10000)
        self.assertEqual(error_budget_remaining(slo,1000,5),5000)
        self.assertEqual(error_budget_remaining(slo,1000,50),0)
        with self.assertRaises(AssuranceContractError): error_budget_remaining(slo,10,11)

if __name__=="__main__": unittest.main()
