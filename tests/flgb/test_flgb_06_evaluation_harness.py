import unittest
from skeleton.ai.assurance.evaluation_harness import AssuranceContractError, CaseResult, EvaluationCase, EvaluationRun, aggregate_score
D="a"*64
E="b"*64

class TestEvaluationHarness(unittest.TestCase):
    def test_exact_case_identity_and_weighted_score(self):
        cases=(EvaluationCase("a",D,D,D,1000000),EvaluationCase("b",D,D,D,500000))
        run=EvaluationRun("r",D,D,D,(CaseResult("a",E,1000000,D),CaseResult("b",E,400000,D)))
        self.assertEqual(aggregate_score(cases,run),800000)
        bad=EvaluationRun("r2",D,D,D,(CaseResult("a",E,1,D),CaseResult("c",E,1,D)))
        with self.assertRaises(AssuranceContractError): aggregate_score(cases,bad)

if __name__=="__main__": unittest.main()
