"""Focused world regression: duskmeadow_survey."""
import unittest
from skeleton.ai.runtime.production_fabric.contracts.spec import parse_world
from skeleton.ai.runtime.production_fabric.planning.endings import discover
from skeleton.ai.runtime.production_fabric.planning.engine import ProductionEngine
from skeleton.ai.runtime.production_fabric.product.content.worlds.duskmeadow_survey import WORLD

class WorldTests(unittest.TestCase):

    def test_both_endings_really_reachable(self):
        result = discover(parse_world(WORLD))
        self.assertEqual(result['missing_endings'], [])
        self.assertEqual(result['reachable_endings'], ['daybreak', 'deep_end'])

    def test_open_play_path_and_replay(self):
        engine = ProductionEngine(WORLD)
        self.addCleanup(engine.journal.close)
        session = 'testsession'
        for token, choice in (('one', 'visit_commons'), ('two', 'prepare_crossing'), ('three', 'choose_public')):
            rev = engine.inspect(session)['state']['revision']
            engine.play(session, token, choice, rev)
        self.assertTrue(engine.inspect(session)['state']['ended'])
        self.assertEqual(engine.inspect(session)['state']['scene'], 'daybreak')
        self.assertEqual(engine.verify(session)['events_checked'], 3)

    def test_hidden_ending_requires_insight(self):
        engine = ProductionEngine(WORLD)
        self.addCleanup(engine.journal.close)
        for token, choice in (('one', 'enter_archive'), ('two', 'learn_secret'), ('three', 'prepare_crossing'), ('four', 'choose_hidden')):
            rev = engine.inspect('secret')['state']['revision']
            engine.play('secret', token, choice, rev)
        self.assertEqual(engine.inspect('secret')['state']['scene'], 'deep_end')
if __name__ == '__main__':
    unittest.main()
