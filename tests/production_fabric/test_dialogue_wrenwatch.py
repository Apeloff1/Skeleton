"""Dialogue graph contract, locked branches and terminal behavior."""
import unittest
from skeleton.ai.runtime.production_fabric.product.content.dialogues.wrenwatch import NODES, START
from skeleton.ai.runtime.production_fabric.planning.dialogue import validate, next_options

class DialogueTests(unittest.TestCase):

    def test_terminal_is_reachable_structurally(self):
        report = validate(NODES, START)
        self.assertIn('farewell', report['terminals'])
        self.assertEqual(report['nodes'], 4)

    def test_evidence_protected_secret(self):
        self.assertEqual([c['id'] for c in next_options(NODES, 'greeting', set())], ['request_guidance'])
        self.assertEqual([c['id'] for c in next_options(NODES, 'greeting', {'clue'})], ['request_guidance', 'seek_secret'])

    def test_terminal_is_explicit(self):
        self.assertEqual(next_options(NODES, 'farewell', set()), [])
if __name__ == '__main__':
    unittest.main()
