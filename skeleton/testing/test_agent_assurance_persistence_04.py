"""Independent adversarial contracts for persistence metrics orphan_fraction and transaction_failure_ratio.

These checks do not assert model intelligence or real-device performance.
"""
from __future__ import annotations
import unittest,math
from skeleton.ai.runtime.operational_ai.agent_fabric.core.errors import Invalid
from skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence import orphan_fraction as left
from skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence import transaction_failure_ratio as right
class AssurancePersistencePair4(unittest.TestCase):

    def test_left_exact_oracle(self):
        metric=left.measure({'orphan_requests': 13, 'all_requests': 14})
        self.assertEqual(metric['schema'],'agent.measurement.v1')
        self.assertEqual(metric['domain'],'persistence')
        self.assertEqual(metric['metric'],'orphan_fraction')
        self.assertAlmostEqual(metric['value'],0.9285714285714286,places=6)
        self.assertEqual(metric['assessment'],'observed-only-not-model-or-release-certification')
        self.assertNotIn('release_accepted',metric)
    def test_left_deterministic_digest(self):
        payload={'orphan_requests': 13, 'all_requests': 14}
        x=left.measure(payload)
        y=left.measure(dict(reversed(list(payload.items()))))
        self.assertEqual(x,y)
        payload[next(iter(payload))]+=1
        self.assertNotEqual(x['inputs_sha256'],left.measure(payload)['inputs_sha256'])
    def test_left_unknown_field_denied(self):
        payload={'orphan_requests': 13, 'all_requests': 14}
        payload['not_a_measurement']=1
        with self.assertRaises(Invalid):left.measure(payload)
    def test_left_missing_field_denied(self):
        payload={'orphan_requests': 13, 'all_requests': 14}
        payload.pop(next(iter(payload)))
        with self.assertRaises(Invalid):left.measure(payload)
    def test_left_negative_denied(self):
        payload={'orphan_requests': 13, 'all_requests': 14};payload[next(iter(payload))]=-1
        with self.assertRaises(Invalid):left.measure(payload)
    def test_left_bool_denied(self):
        payload={'orphan_requests': 13, 'all_requests': 14};payload[next(iter(payload))]=True
        with self.assertRaises(Invalid):left.measure(payload)
    def test_left_nonfinite_denied(self):
        payload={'orphan_requests': 13, 'all_requests': 14};payload[next(iter(payload))]=float('nan')
        with self.assertRaises(Invalid):left.measure(payload)
    def test_left_huge_denied(self):
        payload={'orphan_requests': 13, 'all_requests': 14};payload[next(iter(payload))]=10**40
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
        metric=right.measure({'rolled_back_transactions': 14, 'attempted_transactions': 15})
        self.assertEqual(metric['schema'],'agent.measurement.v1')
        self.assertEqual(metric['domain'],'persistence')
        self.assertEqual(metric['metric'],'transaction_failure_ratio')
        self.assertAlmostEqual(metric['value'],0.9333333333333333,places=6)
        self.assertEqual(metric['assessment'],'observed-only-not-model-or-release-certification')
        self.assertNotIn('release_accepted',metric)
    def test_right_deterministic_digest(self):
        payload={'rolled_back_transactions': 14, 'attempted_transactions': 15}
        x=right.measure(payload)
        y=right.measure(dict(reversed(list(payload.items()))))
        self.assertEqual(x,y)
        payload[next(iter(payload))]+=1
        self.assertNotEqual(x['inputs_sha256'],right.measure(payload)['inputs_sha256'])
    def test_right_unknown_field_denied(self):
        payload={'rolled_back_transactions': 14, 'attempted_transactions': 15}
        payload['not_a_measurement']=1
        with self.assertRaises(Invalid):right.measure(payload)
    def test_right_missing_field_denied(self):
        payload={'rolled_back_transactions': 14, 'attempted_transactions': 15}
        payload.pop(next(iter(payload)))
        with self.assertRaises(Invalid):right.measure(payload)
    def test_right_negative_denied(self):
        payload={'rolled_back_transactions': 14, 'attempted_transactions': 15};payload[next(iter(payload))]=-1
        with self.assertRaises(Invalid):right.measure(payload)
    def test_right_bool_denied(self):
        payload={'rolled_back_transactions': 14, 'attempted_transactions': 15};payload[next(iter(payload))]=True
        with self.assertRaises(Invalid):right.measure(payload)
    def test_right_nonfinite_denied(self):
        payload={'rolled_back_transactions': 14, 'attempted_transactions': 15};payload[next(iter(payload))]=float('nan')
        with self.assertRaises(Invalid):right.measure(payload)
    def test_right_huge_denied(self):
        payload={'rolled_back_transactions': 14, 'attempted_transactions': 15};payload[next(iter(payload))]=10**40
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
