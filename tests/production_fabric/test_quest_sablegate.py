"""Quest DAG and prerequisites for sablegate."""
import unittest
from skeleton.ai.runtime.production_fabric.product.content.quests.sablegate import QUESTS
from skeleton.ai.runtime.production_fabric.planning.quests import compile_quests, available
from skeleton.ai.runtime.production_fabric.contracts.errors import ContractError

class QuestTests(unittest.TestCase):

    def test_all_objectives_ordered(self):
        ordered = compile_quests(list(QUESTS))
        self.assertEqual(len(ordered), 6)
        self.assertEqual(ordered[0].needs, ())
        self.assertEqual(ordered[-1].id, 'sablegate_conclusion')

    def test_prerequisite_gate(self):
        self.assertEqual(available(list(QUESTS), set(), set()), ['sablegate_arrival'])
        self.assertEqual(set(available(list(QUESTS), {'sablegate_arrival'}, {'arrival_record'})), {'sablegate_source', 'sablegate_witness'})

    def test_unknown_dependency_rejected(self):
        bad = list(QUESTS)
        from skeleton.ai.runtime.production_fabric.planning.quests import Quest
        bad[-1] = Quest(bad[-1].id, ('nonexistent',), (), ())
        with self.assertRaises(ContractError):
            compile_quests(bad)
if __name__ == '__main__':
    unittest.main()
