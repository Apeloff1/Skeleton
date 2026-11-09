import unittest
from skeleton.ai.assurance.metric_semantics import AssuranceContractError, MetricDefinition

class TestMetricSemantics(unittest.TestCase):
    def test_bounds_and_direction_are_typed(self):
        metric=MetricDefinition("latency","ms","lower-better","p95",0,1000)
        self.assertEqual(metric.validate(250),250)
        with self.assertRaises(AssuranceContractError): metric.validate(1001)
        with self.assertRaises(AssuranceContractError): MetricDefinition("x","ms","sideways","mean")

if __name__=="__main__": unittest.main()
