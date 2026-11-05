"""Default testpath smoke of the complete bounded offline game-production path."""
import unittest
from skeleton.ai.runtime.production_fabric.product.content.catalog import WORLDS, QUEST_ARCS, DIALOGUES
from skeleton.ai.runtime.production_fabric.planning.engine import ProductionEngine
from skeleton.ai.runtime.production_fabric.planning.endings import discover
from skeleton.ai.runtime.production_fabric.contracts.spec import parse_world
from skeleton.ai.runtime.production_fabric.evaluation.quality import qualify

class ProductionFabricSmoke(unittest.TestCase):

    def test_inventory(self):
        self.assertEqual((len(WORLDS), len(QUEST_ARCS), len(DIALOGUES)), (72, 24, 24))

    def test_all_endings_are_reachable(self):
        for world in WORLDS.values():
            with self.subTest(world=world['id']):
                self.assertFalse(discover(parse_world(world))['missing_endings'])

    def test_play_recover_without_external_ai(self):
        with ProductionEngine(WORLDS['cloudbreak_signal']) as engine:
            engine.play('player', 'one', 'visit_commons', 0)
            engine.play('player', 'two', 'prepare_crossing', 1)
            engine.play('player', 'three', 'choose_public', 2)
            self.assertTrue(engine.inspect('player')['state']['ended'])
            self.assertEqual(engine.verify('player')['events_checked'], 3)

    def test_release_is_never_asserted_by_local_quality(self):
        evidence = {key: True for key in ('structural', 'ending_reachability', 'replay_integrity', 'rights', 'content_provenance', 'adversarial')}
        self.assertFalse(qualify(evidence)['release_ready'])
