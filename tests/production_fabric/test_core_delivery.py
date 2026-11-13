import unittest
from skeleton.ai.runtime.production_fabric.delivery.capacity import admit
from skeleton.ai.runtime.production_fabric.delivery.manifest import make
from skeleton.ai.runtime.production_fabric.delivery.order import REQUIRED, validate
from skeleton.ai.runtime.production_fabric.delivery.preflight import preflight
from skeleton.ai.runtime.production_fabric.delivery.rollback import plan
from skeleton.ai.runtime.production_fabric.contracts.errors import BudgetError, ContractError

class DeliveryTests(unittest.TestCase):

    def test_limits(self):
        self.assertEqual(admit([{'bytes': 4}, {'bytes': 3}])['bytes'], 7)
        with self.assertRaises(BudgetError):
            admit([{'bytes': 100000000}])

    def test_build_graph(self):
        self.assertEqual(validate([{'id': k, 'hard_dependencies': v} for k, v in REQUIRED.items()])[0], 'MBW-00')

    def test_manifest_digests(self):
        entry = {'path': 'skeleton/ai/world.py', 'sha256': 'a' * 64, 'size': 10, 'wave': 'MBW-05'}
        self.assertEqual(make([entry], source_ref='head')['payload']['entries'][0], entry)
        with self.assertRaises(ContractError):
            make([entry, entry], source_ref='head')

    def test_invalid_entry_digest_fails_closed(self):
        with self.assertRaises(ContractError):
            make([{'path': 'world/a', 'sha256': 'invalid', 'size': 1, 'wave': 'MBW-05'}], source_ref='head')

    def test_promotion_hold(self):
        result = preflight(evidence={'structural': True}, files=[])
        self.assertEqual(result['status'], 'hold')
        self.assertFalse(result['release_certified'])

    def test_rollback_no_fake_execution(self):
        result = plan({'source_ref': 'old'}, {'source_ref': 'new'})
        self.assertFalse(result['performed'])
