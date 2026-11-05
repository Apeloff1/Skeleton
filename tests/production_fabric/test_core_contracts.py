import unittest
from skeleton.ai.runtime.production_fabric.contracts.canonical import loads, dumps, digest
from skeleton.ai.runtime.production_fabric.contracts.graph import topological, reachable
from skeleton.ai.runtime.production_fabric.contracts.identity import identifier, scoped
from skeleton.ai.runtime.production_fabric.contracts.errors import ContractError, BudgetError
from skeleton.ai.runtime.production_fabric.contracts.limits import Budget
from skeleton.ai.runtime.production_fabric.contracts.clock import LogicalTime
from skeleton.ai.runtime.production_fabric.contracts.spec import parse_world, to_data
from skeleton.ai.runtime.production_fabric.product.content.worlds.cloudbreak_signal import WORLD

class ContractTests(unittest.TestCase):

    def test_canonical_digest_is_order_independent(self):
        self.assertEqual(digest({'b': 1, 'a': 2}), digest({'a': 2, 'b': 1}))
        self.assertEqual(loads(dumps({'utf8': 'é'})), {'utf8': 'é'})

    def test_duplicate_and_nan_denied(self):
        for raw in ('{"v":1,"v":2}', '{"v":NaN}', '{"v":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ContractError):
                loads(raw)

    def test_depth_and_bytes_denied(self):
        with self.assertRaises(ContractError):
            loads('[' * 55 + '0' + ']' * 55)
        with self.assertRaises(ContractError):
            loads('"' + 'x' * 99 + '"', max_bytes=50)

    def test_unknown_dependency_and_cycle_denied(self):
        with self.assertRaises(ContractError):
            topological({'x': ['z']})
        with self.assertRaises(ContractError):
            topological({'x': ['y'], 'y': ['x']})

    def test_stable_order(self):
        self.assertEqual(topological({'b': ['a'], 'a': []}), ['a', 'b'])
        self.assertEqual(reachable({'a': ['b'], 'b': []}, 'a'), {'a', 'b'})

    def test_identifier_enforces_ascii(self):
        self.assertEqual(scoped('world', 'one'), 'world:one')
        for value in ('../hello', 'A', 'é', ''):
            with self.assertRaises(ContractError):
                identifier(value)

    def test_budget_is_atomic(self):
        b = Budget({'steps': 3, 'tokens': 10})
        b.charge({'steps': 2})
        with self.assertRaises(BudgetError):
            b.charge({'steps': 2, 'tokens': 1})
        self.assertEqual(b.spent, {'steps': 2})

    def test_logical_clock(self):
        self.assertEqual(LogicalTime().advance(4).tick, 4)

    def test_world_roundtrip(self):
        world = parse_world(WORLD)
        self.assertEqual(parse_world(to_data(world)), world)
