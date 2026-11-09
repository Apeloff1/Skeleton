"""Quest DAG and prerequisites for cloudbreak."""
import unittest
from skeleton.ai.runtime.production_fabric.product.content.quests.cloudbreak import QUESTS
from skeleton.ai.runtime.production_fabric.planning.quests import compile_quests, available
from skeleton.ai.runtime.production_fabric.contracts.errors import ContractError

class QuestTests(unittest.TestCase):

    def test_all_objectives_ordered(self):
        ordered = compile_quests(list(QUESTS))
        self.assertEqual(len(ordered), 6)
        self.assertEqual(ordered[0].needs, ())
        self.assertEqual(ordered[-1].id, 'cloudbreak_conclusion')

    def test_prerequisite_gate(self):
        self.assertEqual(available(list(QUESTS), set(), set()), ['cloudbreak_arrival'])
        self.assertEqual(set(available(list(QUESTS), {'cloudbreak_arrival'}, {'arrival_record'})), {'cloudbreak_source', 'cloudbreak_witness'})

    def test_unknown_dependency_rejected(self):
        bad = list(QUESTS)
        from skeleton.ai.runtime.production_fabric.planning.quests import Quest
        bad[-1] = Quest(bad[-1].id, ('nonexistent',), (), ())
        with self.assertRaises(ContractError):
            compile_quests(bad)
if __name__ == '__main__':
    unittest.main()
