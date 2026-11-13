"""Independent adversarial contracts for evaluation metrics f1 and balanced_accuracy.

These checks do not assert model intelligence or real-device performance.
"""
from __future__ import annotations
import unittest,math
from skeleton.ai.runtime.operational_ai.agent_fabric.core.errors import Invalid
from skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation import f1 as left
from skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation import balanced_accuracy as right
class AssuranceEvaluationPair3(unittest.TestCase):

    def test_left_exact_oracle(self):
        metric=left.measure({'true_positive': 12, 'false_positive': 13, 'false_negative': 14})
        self.assertEqual(metric['schema'],'agent.measurement.v1')
        self.assertEqual(metric['domain'],'evaluation')
        self.assertEqual(metric['metric'],'f1')
        self.assertAlmostEqual(metric['value'],0.47058823529411764,places=6)
        self.assertEqual(metric['assessment'],'observed-only-not-model-or-release-certification')
        self.assertNotIn('release_accepted',metric)
    def test_left_deterministic_digest(self):
        payload={'true_positive': 12, 'false_positive': 13, 'false_negative': 14}
        x=left.measure(payload)
        y=left.measure(dict(reversed(list(payload.items()))))
        self.assertEqual(x,y)
        payload[next(iter(payload))]+=1
        self.assertNotEqual(x['inputs_sha256'],left.measure(payload)['inputs_sha256'])
    def test_left_unknown_field_denied(self):
        payload={'true_positive': 12, 'false_positive': 13, 'false_negative': 14}
        payload['not_a_measurement']=1
        with self.assertRaises(Invalid):left.measure(payload)
    def test_left_missing_field_denied(self):
        payload={'true_positive': 12, 'false_positive': 13, 'false_negative': 14}
        payload.pop(next(iter(payload)))
        with self.assertRaises(Invalid):left.measure(payload)
    def test_left_negative_denied(self):
        payload={'true_positive': 12, 'false_positive': 13, 'false_negative': 14};payload[next(iter(payload))]=-1
        with self.assertRaises(Invalid):left.measure(payload)
    def test_left_bool_denied(self):
        payload={'true_positive': 12, 'false_positive': 13, 'false_negative': 14};payload[next(iter(payload))]=True
        with self.assertRaises(Invalid):left.measure(payload)
    def test_left_nonfinite_denied(self):
        payload={'true_positive': 12, 'false_positive': 13, 'false_negative': 14};payload[next(iter(payload))]=float('nan')
        with self.assertRaises(Invalid):left.measure(payload)
    def test_left_huge_denied(self):
        payload={'true_positive': 12, 'false_positive': 13, 'false_negative': 14};payload[next(iter(payload))]=10**40
        with self.assertRaises(Invalid):left.measure(payload)
    def test_left_integer_zero_bounds(self):
        payload={key:0 for key in left.FIELDS}
        result=left.measure(payload)
        self.assertTrue(math.isfinite(result['value']))
    def test_left_nonmap_denied(self):
        for item in ([],None,'random',123):
            with self.subTest(item=str(item)),self.assertRaises(Invalid):
                left.measure(item)


    def test_right_exact_oracle(self):
        metric=right.measure({'true_positive': 13, 'false_negative': 14, 'true_negative': 15, 'false_positive': 16})
        self.assertEqual(metric['schema'],'agent.measurement.v1')
        self.assertEqual(metric['domain'],'evaluation')
        self.assertEqual(metric['metric'],'balanced_accuracy')
        self.assertAlmostEqual(metric['value'],0.48267622461170845,places=6)
        self.assertEqual(metric['assessment'],'observed-only-not-model-or-release-certification')
        self.assertNotIn('release_accepted',metric)
    def test_right_deterministic_digest(self):
        payload={'true_positive': 13, 'false_negative': 14, 'true_negative': 15, 'false_positive': 16}
        x=right.measure(payload)
        y=right.measure(dict(reversed(list(payload.items()))))
        self.assertEqual(x,y)
        payload[next(iter(payload))]+=1
        self.assertNotEqual(x['inputs_sha256'],right.measure(payload)['inputs_sha256'])
    def test_right_unknown_field_denied(self):
        payload={'true_positive': 13, 'false_negative': 14, 'true_negative': 15, 'false_positive': 16}
        payload['not_a_measurement']=1
        with self.assertRaises(Invalid):right.measure(payload)
    def test_right_missing_field_denied(self):
        payload={'true_positive': 13, 'false_negative': 14, 'true_negative': 15, 'false_positive': 16}
        payload.pop(next(iter(payload)))
        with self.assertRaises(Invalid):right.measure(payload)
    def test_right_negative_denied(self):
        payload={'true_positive': 13, 'false_negative': 14, 'true_negative': 15, 'false_positive': 16};payload[next(iter(payload))]=-1
        with self.assertRaises(Invalid):right.measure(payload)
    def test_right_bool_denied(self):
        payload={'true_positive': 13, 'false_negative': 14, 'true_negative': 15, 'false_positive': 16};payload[next(iter(payload))]=True
        with self.assertRaises(Invalid):right.measure(payload)
    def test_right_nonfinite_denied(self):
        payload={'true_positive': 13, 'false_negative': 14, 'true_negative': 15, 'false_positive': 16};payload[next(iter(payload))]=float('nan')
        with self.assertRaises(Invalid):right.measure(payload)
    def test_right_huge_denied(self):
        payload={'true_positive': 13, 'false_negative': 14, 'true_negative': 15, 'false_positive': 16};payload[next(iter(payload))]=10**40
        with self.assertRaises(Invalid):right.measure(payload)
    def test_right_integer_zero_bounds(self):
        payload={key:0 for key in right.FIELDS}
        result=right.measure(payload)
        self.assertTrue(math.isfinite(result['value']))
    def test_right_nonmap_denied(self):
        for item in ([],None,'random',123):
            with self.subTest(item=str(item)),self.assertRaises(Invalid):
                right.measure(item)

if __name__=='__main__':unittest.main()
