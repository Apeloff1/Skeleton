import unittest
from skeleton.ai.runtime.production_fabric.context.documents import document
from skeleton.ai.runtime.production_fabric.context.index import EvidenceIndex
from skeleton.ai.runtime.production_fabric.context.compiler import compile_context
from skeleton.ai.runtime.production_fabric.context.citations import cite
from skeleton.ai.runtime.production_fabric.context.claims import claim
from skeleton.ai.runtime.production_fabric.context.memory import MemoryBook
from skeleton.ai.runtime.production_fabric.context.continuity import audit
from skeleton.ai.runtime.production_fabric.context.window import project
from skeleton.ai.runtime.production_fabric.contracts.errors import ContractError

class ContextTests(unittest.TestCase):

    def test_retrieval_is_provenance_bound(self):
        a = document('a', 'The lanterns illuminate the harbor.', 'operator:original', 'operator-reviewed')
        b = document('b', 'The gardens hide bronze gears.', 'operator:original')
        index = EvidenceIndex([a, b])
        self.assertEqual(index.query('lantern harbor')[0]['id'], 'a')
        bundle = compile_context(index, 'lantern harbor', budget=1000)
        self.assertFalse(bundle['evidence'][0]['instruction_authority'])
        self.assertEqual(bundle['evidence'][0]['sha256'], a.sha256)
        self.assertEqual(cite(a, 4, 12)['excerpt'], 'lanterns')

    def test_duplicate_document_denied(self):
        d = document('x', 'small text', 'source')
        with self.assertRaises(ContractError):
            EvidenceIndex([d, d])

    def test_untrusted_cannot_become_verified_claim(self):
        doc = document('x', 'a claim', 'source')
        with self.assertRaises(ContractError):
            claim('c', 'fact', [doc], status='verified')

    def test_scope_separation(self):
        mem = MemoryBook()
        mem.append('worlda', 'name', 'alpha', 'source')
        self.assertIsNone(mem.read('worldb', 'name'))
        self.assertEqual(mem.read('worlda', 'name').value, 'alpha')

    def test_continuity_conflict(self):
        a = {'entity': 'npc', 'property': 'location', 'value': 'forest', 'valid_from': 1, 'valid_to': 10, 'source': 'a'}
        b = {**a, 'value': 'desert', 'valid_from': 5, 'valid_to': 11, 'source': 'b'}
        self.assertEqual(len(audit([a, b])), 1)

    def test_context_window_preserves_original(self):
        turns = [{'role': 'user', 'text': 'x' * 100, 'trust': 'untrusted'}, {'role': 'assistant', 'text': 'done', 'trust': 'trusted'}]
        projected = project(turns, budget=64)
        self.assertEqual(projected['retained_count'], 2)
        self.assertEqual(len(turns), 2)
